"""Pipeline Day 06.

Chạy từ thư mục starter/:
    python -m src.run ingest      # đọc PDF -> chunk A, B -> embed -> lưu pgvector
    python -m src.run evaluate    # 20 câu x 3 cấu hình -> trace top-3 + metrics
    python -m src.run all
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import CohereEmbedder
from .evaluation import build_trace_file, evaluate_query, summarize
from .ingestion import load_corpus
from .store import PgVectorStore

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
RESULTS = STARTER / "results"
TOP_K = 3

# A–B chỉ khác cách chunk; B–C chỉ khác filter (C dùng lại index của B).
STRATEGIES = {
    "A": {"index": "A", "chunker": "fixed_size", "params": {"size": 500, "overlap": 50},
          "use_filter": False},
    "B": {"index": "B", "chunker": "by_paragraph", "params": {"max_size": 1000},
          "use_filter": False},
    "C": {"index": "B", "chunker": "by_paragraph (dùng lại index B)", "params": {},
          "use_filter": True},
}
CHUNKERS = {"fixed_size": fixed_size, "by_paragraph": by_paragraph}

log = logging.getLogger("run")


def build_chunks(pages, index: str):
    cfg = STRATEGIES[index]
    fn = CHUNKERS[cfg["chunker"]]
    return [c for p in pages for c in fn(p, strategy=index, **cfg["params"])]


def _length_stats(chunks) -> dict:
    lens = [len(c.text) for c in chunks]
    return {"chunks": len(lens), "total_chars": sum(lens), "min": min(lens),
            "median": statistics.median(lens), "mean": round(statistics.mean(lens), 1),
            "max": max(lens), "approx_tokens": sum(lens) // 4}


def ingest(embedder, store) -> None:
    pages, issues = load_corpus(ROOT)
    n_pages = len({(p.document_id, p.page) for p in pages})
    if n_pages < 30:
        raise SystemExit(f"Chỉ có {n_pages} trang nội dung, cần >= 30")
    store.create_schema()
    stats = {"content_pages": n_pages, "issues": len(issues), "strategies": {}}
    for index in ("A", "B"):
        chunks = build_chunks(pages, index)
        tokens0, calls0 = embedder.total_tokens, embedder.calls
        t0 = time.perf_counter()
        vectors = embedder.embed_documents([c.text for c in chunks])
        t_embed = time.perf_counter() - t0
        deleted = store.upsert(index, chunks, vectors)
        t_total = time.perf_counter() - t0
        # Nạp lại cùng phiên bản: chunk_id ổn định -> số bản ghi không đổi.
        before = store.count(index)
        store.upsert(index, build_chunks(pages, index), vectors)
        after = store.count(index)
        if before != after or after != len(chunks):
            raise RuntimeError(f"{index}: nạp lại bị lệch ({len(chunks)} / {before} / {after})")
        stats["strategies"][index] = {
            **_length_stats(chunks), "embed_seconds": round(t_embed, 2),
            "ingest_seconds": round(t_total, 2), "obsolete_deleted": deleted,
            "reingest_count_before_after": [before, after],
            "embedding_tokens": embedder.total_tokens - tokens0,
            "api_calls": embedder.calls - calls0,
            "cost_usd": "tính = embedding_tokens x giá Cohere/1M token (ghi vào báo cáo)",
        }
        log.info("%s: %s chunk, %.1fs", index, len(chunks), t_total)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "ingest_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), "utf-8")
    (RESULTS / "ingest_issues.json").write_text(json.dumps(issues, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def evaluate(embedder, store) -> None:
    questions = json.loads((ROOT / "benchmark/questions.json").read_text("utf-8"))["questions"]
    qvecs = dict(zip([q["id"] for q in questions],
                     embedder.embed_queries([q["question"] for q in questions])))
    all_traces = []
    RESULTS.mkdir(exist_ok=True)
    for name, cfg in STRATEGIES.items():
        for q in questions:
            flt = q["filter"] if cfg["use_filter"] and q["filter"] else None
            hits = store.search(cfg["index"], qvecs[q["id"]], TOP_K, flt)
            all_traces.append({"strategy": name, "id": q["id"], "split": q["split"], "type": q["type"],
                               "question": q["question"], "filter_applied": flt, "gold": q["gold"],
                               "hits": [{"rank": i + 1, **h} for i, h in enumerate(hits)],
                               **evaluate_query(q, hits, flt)})
    metrics = summarize(all_traces)
    for name, cfg in STRATEGIES.items():
        doc = build_trace_file(name, cfg, [t for t in all_traces if t["strategy"] == name], metrics[name])
        (RESULTS / f"traces_{name}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    metrics["embedding_usage_this_run"] = {"tokens": embedder.total_tokens, "api_calls": embedder.calls}
    (RESULTS / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), "utf-8")
    print(f"{'Cấu hình':<9}{'Split':<6}{'Hit@1':<14}{'Hit@3':<14}Filter")
    for name in STRATEGIES:
        splits = metrics[name]
        for split in ("dev", "test"):
            g = splits[split]
            print(f"{name:<9}{split:<6}{g['Hit@1']:<14}{g['Hit@3']:<14}{g['Filter']}")


def save_config(embedder, store) -> None:
    with store._connect() as conn:
        pg = conn.execute("SELECT current_setting('server_version') AS pg, "
                          "(SELECT extversion FROM pg_extension WHERE extname='vector') AS vec").fetchone()
    config = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "embedding": {"provider": "Cohere Embed API v2 (https://api.cohere.com/v2/embed)",
                      "model": embedder.model_name, "dimensions": embedder.dimensions,
                      "query_document_handling": "input_type search_document / search_query, embedding_types float, truncate NONE",
                      "output_dimension": embedder.output_dimension,
                      "batch_size": embedder.batch_size},
        "vector_store": {"postgres": pg["pg"], "pgvector": pg["vec"], "table": store.table,
                         "metric": "cosine (<=>)", "search": "exact (không có index ANN)"},
        "top_k": TOP_K, "strategies": STRATEGIES,
        "libraries": {p: version(p) for p in
                      ("pypdf", "psycopg", "python-dotenv")},
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), "utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["ingest", "evaluate", "all"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv(STARTER / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("Thiếu DATABASE_URL trong starter/.env")
    dim = os.getenv("EMBEDDING_DIMENSION")
    embedder = CohereEmbedder(os.getenv("EMBEDDING_MODEL") or "embed-v4.0",
                              output_dimension=int(dim) if dim else None)
    store = PgVectorStore(url, embedder.dimensions)
    save_config(embedder, store)
    if args.step in ("ingest", "all"):
        ingest(embedder, store)
    if args.step in ("evaluate", "all"):
        evaluate(embedder, store)


if __name__ == "__main__":
    main()
