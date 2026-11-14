"""Xuất traces_A/B/C.json ra dạng dễ đọc.

Chạy từ thư mục starter/:  python scripts\\export_traces.py

Tạo:
  results/top3_all.csv        mỗi dòng = 1 chunk top-3 (mở bằng Excel, lọc/sắp xếp được)
  results/traces_readable.md  mỗi câu hỏi: gold + top-3 của A, B, C cạnh nhau
"""
import csv
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"
STRATEGIES = ["A", "B", "C"]
LABEL_VI = {"evidence": "✅ đủ evidence", "page_only": "⚠️ đúng trang, thiếu evidence", None: "❌ sai nguồn"}


def load() -> dict[str, list[dict]]:
    """Đọc traces_{A,B,C}.json và trả về dạng phẳng cho các hàm xuất bên dưới."""
    data = {}
    for s in STRATEGIES:
        doc = json.loads((RESULTS / f"traces_{s}.json").read_text(encoding="utf-8"))
        data[s] = [{**t, **t["result"],
                    "labels": [None if h["label"] == "miss" else h["label"] for h in t["hits"]]}
                   for t in doc["traces"]]
    return data


def short(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n - 1] + "…"


def write_csv(traces: dict[str, list[dict]]) -> Path:
    path = RESULTS / "top3_all.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:      # utf-8-sig để Excel hiện đúng tiếng Việt
        w = csv.writer(fh)
        w.writerow(["strategy", "id", "split", "type", "filter", "hit@1", "hit@3", "rank",
                    "score", "label", "document_id", "page", "section", "chunk_id", "text"])
        for s in STRATEGIES:
            for t in traces[s]:
                flt = json.dumps(t["filter_applied"], ensure_ascii=False) if t["filter_applied"] else ""
                for h, label in zip(t["hits"], t["labels"]):
                    w.writerow([s, t["id"], t["split"], t["type"], flt, int(t["hit_at_1"]),
                                int(t["hit_at_3"]), h["rank"], round(h["score"], 4), label or "miss",
                                h["document_id"], h["page"], h["section"], h["chunk_id"], h["text"]])
    return path


def write_markdown(traces: dict[str, list[dict]]) -> Path:
    path = RESULTS / "traces_readable.md"
    by_id = {s: {t["id"]: t for t in traces[s]} for s in STRATEGIES}
    lines = ["# Trace top-3 dễ đọc", "",
             "Score = cosine similarity (1 − cosine distance). Nhãn tự động: "
             "✅ đủ evidence · ⚠️ đúng trang nhưng thiếu evidence · ❌ sai nguồn/trang.", ""]
    for qid, base in by_id["A"].items():
        lines += [f"## {qid} · {base['split']} · {base['type']}", "",
                  f"**Câu hỏi:** {base['question']}", ""]
        for g in base["gold"]:
            lines.append(f"- Gold: `{g['source_id']}` trang {g['page']} — “{short(g['evidence_quote'], 160)}”")
        lines.append("")
        for s in STRATEGIES:
            t = by_id[s][qid]
            flt = f" · filter `{json.dumps(t['filter_applied'], ensure_ascii=False)}`" if t["filter_applied"] else ""
            lines += [f"**{s}** — Hit@1 {'✅' if t['hit_at_1'] else '❌'} · Hit@3 {'✅' if t['hit_at_3'] else '❌'}{flt}",
                      "", "| # | Score | Nhãn | Nguồn | Trang | Section | Trích |", "|---|---|---|---|---|---|---|"]
            for h, label in zip(t["hits"], t["labels"]):
                lines.append(f"| {h['rank']} | {h['score']:.3f} | {LABEL_VI[label]} | {h['document_id']} | "
                             f"{h['page']} | {short(h['section'] or '', 40)} | {short(h['text'], 120).replace('|', '/')} |")
            lines.append("")
        lines.append("---")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def print_summary(traces: dict[str, list[dict]]) -> None:
    print(f"{'ID':<5}{'Split':<6}" + "".join(f"{s + ' (rank:score:nhãn)':<40}" for s in STRATEGIES))
    sym = {"evidence": "✅", "page_only": "⚠️", None: "·"}
    for i, base in enumerate(traces["A"]):
        row = f"{base['id']:<5}{base['split']:<6}"
        for s in STRATEGIES:
            t = traces[s][i]
            row += f"{' '.join(f'{h['score']:.2f}{sym[l]}' for h, l in zip(t['hits'], t['labels'])):<40}"
        print(row)


if __name__ == "__main__":
    data = load()
    print_summary(data)
    print("\nĐã tạo:", write_csv(data))
    print("Đã tạo:", write_markdown(data))
