"""Sinh 3 mẫu chấm thủ công (coherence, metadata, grounding) dạng JSON từ corpus + traces.

Chạy từ thư mục starter/:  python scripts\\make_audit_templates.py
Tạo trong results/audit/ (không ghi đè file đã có, trừ khi thêm --force):
  coherence.json   10 vị trí nguồn, mỗi vị trí có chunk A và B (C dùng chung chunk B) -> điền score, reason
  metadata.json    5 câu test × top-3 × A, B, C                                       -> điền checks.*, note
  grounding.json   5 câu test × A, B, C                                               -> điền score, reason

Các trường *_auto chỉ là gợi ý khách quan do máy tính (không phải nhãn). Trường null = chưa chấm.
"""
import json
import re
import sys
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STARTER))

from src.evaluation import squash  # noqa: E402
from src.ingestion import load_corpus  # noqa: E402
from src.run import ROOT, build_chunks  # noqa: E402

OUT = STARTER / "results" / "audit"
N_POSITIONS = 10
SENT_END = re.compile(r"[.!?]$")
SCALE_COHERENCE = {
    "0": "bị cắt giữa ý / thiếu chủ thể làm không hiểu",
    "1": "hiểu một phần, thiếu ngữ cảnh",
    "2": "tự hiểu được và giữ trọn ý",
}
SCALE_GROUNDING = {
    "0": "không có bằng chứng",
    "1": "có nhưng thiếu điều kiện/ngữ cảnh cần thiết",
    "2": "đủ để trả lời và truy nguồn",
}


def write_json(path: Path, data: dict, force: bool) -> None:
    if path.exists() and not force:
        print(f"Bỏ qua {path.name}: đã tồn tại (dùng --force để ghi đè — sẽ mất điểm đã chấm)")
        return
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Đã tạo {path}")


def sentence_at(text: str, pos: int) -> str:
    """Câu chứa vị trí pos (xuống dòng của PDF coi như khoảng trắng)."""
    text = text.replace("\n", " ")
    start = text.rfind(". ", 0, pos)
    start = start + 2 if start != -1 else 0
    end = text.find(". ", pos)
    end = end + 1 if end != -1 else len(text)
    return " ".join(text[start:end].split())


def coherence_doc(pages) -> dict:
    n = len(pages)
    idx = [round(i * (n - 1) / (N_POSITIONS - 1)) for i in range(N_POSITIONS)]
    chunks = {s: build_chunks(pages, s) for s in ("A", "B")}
    positions = []
    for k, i in enumerate(idx, start=1):
        page = pages[i]
        pos = len(page.text) // 2
        entry = {"position_id": f"P{k:02d}", "document_id": page.document_id, "page": page.page,
                 "char_pos": pos, "sentence_at_position": sentence_at(page.text, pos), "chunks": {}}
        for s in ("A", "B"):
            cands = [c for c in chunks[s] if c.document_id == page.document_id and c.page == page.page
                     and c.metadata["char_start"] <= pos]
            chunk = max(cands, key=lambda c: c.metadata["char_start"])
            text = chunk.text
            entry["chunks"][s] = {
                "chunk_id": chunk.chunk_id, "section": chunk.metadata["section"], "chunk_len": len(text),
                "starts_mid_sentence_auto": text[:1].islower() or text[:1] in ",;)",
                "ends_mid_sentence_auto": not SENT_END.search(text.rstrip()),
                "score": None, "reason": "",
                "chunk_text": text,
            }
        positions.append(entry)
    return {
        "aspect": "chunk coherence",
        "selection_rule": "Sắp 37 trang nội dung theo (thứ tự manifest, số trang), lấy 10 trang cách đều "
                          "(chỉ số 0, 4, …, 36); vị trí = ký tự giữa trang. Chọn trước, không phụ thuộc kết quả.",
        "scale": SCALE_COHERENCE,
        "note": "C dùng chung chunk của B nên không chấm riêng.",
        "positions": positions,
    }


def load_traces() -> dict[str, list[dict]]:
    return {s: json.loads((STARTER / f"results/traces_{s}.json").read_text("utf-8"))["traces"]
            for s in ("A", "B", "C")}


def metadata_doc(traces, pages, sources) -> dict:
    texts = {(p.document_id, p.page): squash(p.text) for p in pages}
    records = []
    for s, items in traces.items():
        for t in items:
            if t["split"] != "test":
                continue
            flt = t["filter_applied"]
            for h in t["hits"]:
                records.append({
                    "strategy": s, "id": t["id"], "rank": h["rank"], "chunk_id": h["chunk_id"],
                    "document_id": h["document_id"], "source": sources.get(h["document_id"], ""),
                    "page": h["page"], "section": h["section"], "section_top": h["section_top"],
                    "document_type": h["document_type"], "year": h["year"],
                    "filter_applied": flt,
                    "filter_compliant_auto": (all(h.get(k) == v for k, v in flt.items()) if flt else None),
                    "text_found_on_page_auto": squash(h["text"])[:120] in texts.get((h["document_id"], h["page"]), ""),
                    "checks": {"source_ok": None, "page_ok": None, "section_ok": None, "all_ok": None},
                    "note": "",
                    "text_excerpt": " ".join(h["text"].split())[:300],
                })
    return {
        "aspect": "metadata usefulness",
        "scope": "5 câu test × top-3 × A, B, C",
        "checks_meaning": {
            "source_ok": "document_id + source đúng file chứa đoạn text",
            "page_ok": "đoạn text nằm đúng trang ghi trong page",
            "section_ok": "section đúng là mục chứa (phần lớn) đoạn text",
            "all_ok": "cả 3 đúng và document_type, year khớp manifest",
        },
        "records": records,
    }


def grounding_doc(traces) -> dict:
    items = []
    for s, ts in traces.items():
        for t in ts:
            if t["split"] != "test":
                continue
            items.append({
                "strategy": s, "id": t["id"], "type": t["type"], "question": t["question"],
                "gold": t["gold"], "filter_applied": t["filter_applied"],
                "evidence_hit3_auto": t["result"]["hit_at_3"],
                "score": None, "reason": "",
                "hits": [{"rank": h["rank"], "document_id": h["document_id"], "page": h["page"],
                          "section": h["section"], "score": h["score"], "auto_label": h["label"],
                          "text": h["text"]} for h in t["hits"]],
            })
    return {
        "aspect": "grounding quality",
        "scope": "5 câu test × A, B, C; chỉ dựa vào top-3",
        "scale": SCALE_GROUNDING,
        "note": "Đánh giá độ đủ của evidence truy xuất, không phải độ chính xác câu trả lời LLM.",
        "items": items,
    }


def main() -> None:
    force = "--force" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    pages, _ = load_corpus(ROOT)
    manifest = json.loads((ROOT / "data/manifest.json").read_text("utf-8"))
    sources = {s["source_id"]: s["local_path"] for s in manifest["sources"]}
    traces = load_traces()
    write_json(OUT / "coherence.json", coherence_doc(pages), force)
    write_json(OUT / "metadata.json", metadata_doc(traces, pages, sources), force)
    write_json(OUT / "grounding.json", grounding_doc(traces), force)


if __name__ == "__main__":
    main()
