"""Kiểm tra benchmark trước khi chạy pipeline.

Chạy từ thư mục starter/:
    python scripts/verify_benchmark.py ../benchmark/questions.json

Kiểm tra:
  - đủ trường bắt buộc, id không trùng
  - >= 20 câu, >= 15 dev, >= 5 test
  - >= 3 câu có filter, >= 1 câu filter thuộc test
  - mỗi evidence_quote thực sự nằm trong trang gold (sau chuẩn hóa)
  - gold_page thuộc content_pages trong manifest
  - giá trị filter tồn tại trong manifest / section_map
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]          # thư mục repo
REQUIRED = ["id", "split", "type", "question", "expected_answer", "gold", "filter"]


def squash(text: str) -> str:
    """So khớp bền vững: NFKC, bỏ khoảng trắng, gạch nối, viết thường.

    PDF hay làm mất/thừa khoảng trắng ("set toM = 7") và gạch nối xuống dòng
    ("pro-\\ncessing"), nên so sánh trên dạng đã 'nén'.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[\s\-­‐‑]+", "", text)


def load_pages(manifest: dict) -> dict[str, dict[int, str]]:
    pages: dict[str, dict[int, str]] = {}
    for src in manifest["sources"]:
        reader = PdfReader(ROOT / src["local_path"])
        pages[src["source_id"]] = {
            n: squash(reader.pages[n - 1].extract_text() or "") for n in src["content_pages"]
        }
    return pages


def section_tops_on_page(entries: list[dict], page: int) -> set[str]:
    """Các section_top xuất hiện trên một trang: section đang mở từ trang trước
    cộng các heading bắt đầu ngay trên trang đó."""
    before = [e for e in entries if e["start_page"] < page]
    tops = {e["section_top"] for e in entries if e["start_page"] == page}
    if before:
        tops.add(before[-1]["section_top"])
    return tops


def gold_matches_filter(gold: dict, flt: dict, sources: dict, section_map: dict) -> bool:
    src = sources.get(gold["source_id"], {})
    meta = {"document_id": gold["source_id"], "document_type": src.get("document_type"),
            "year": src.get("year")}
    for key, value in flt.items():
        if key == "section_top":
            if value not in section_tops_on_page(section_map.get(gold["source_id"], []), gold["page"]):
                return False
        elif meta.get(key) != value:
            return False
    return True


def main(path: Path) -> int:
    questions = json.loads(path.read_text(encoding="utf-8"))["questions"]
    manifest = json.loads((ROOT / "data/manifest.json").read_text(encoding="utf-8"))
    section_map = json.loads((ROOT / "data/section_map.json").read_text(encoding="utf-8"))
    sources = {s["source_id"]: s for s in manifest["sources"]}
    pages = load_pages(manifest)
    allowed = {
        "document_id": set(sources),
        "document_type": {s["document_type"] for s in sources.values()},
        "year": {s["year"] for s in sources.values()},
        "section_top": {e["section_top"] for v in section_map.values() for e in v},
    }

    errors: list[str] = []
    ids = [q.get("id") for q in questions]
    if len(ids) != len(set(ids)):
        errors.append("Có id bị trùng")

    for q in questions:
        qid = q.get("id", "?")
        missing = [k for k in REQUIRED if k not in q]
        if missing:
            errors.append(f"{qid}: thiếu trường {missing}")
            continue
        if q["split"] not in ("dev", "test"):
            errors.append(f"{qid}: split phải là dev/test")
        if not q["gold"]:
            errors.append(f"{qid}: gold rỗng")
        for g in q["gold"]:
            sid, page, quote = g.get("source_id"), g.get("page"), g.get("evidence_quote", "")
            if sid not in sources:
                errors.append(f"{qid}: source_id '{sid}' không có trong manifest")
                continue
            if page not in sources[sid]["content_pages"]:
                errors.append(f"{qid}: trang {page} không thuộc content_pages của {sid}")
                continue
            if len(quote) < 20:
                errors.append(f"{qid}: evidence_quote quá ngắn")
            elif squash(quote) not in pages[sid][page]:
                errors.append(f"{qid}: KHÔNG tìm thấy evidence ở {sid} trang {page}: \"{quote[:60]}...\"")
        for key, value in (q["filter"] or {}).items():
            if key not in allowed:
                errors.append(f"{qid}: trường filter '{key}' không hỗ trợ")
            elif value not in allowed[key]:
                errors.append(f"{qid}: giá trị filter {key}={value!r} không tồn tại trong nguồn")
        # filter phải khớp ít nhất một gold, nếu không câu hỏi tự mâu thuẫn
        if q["filter"] and not any(
            gold_matches_filter(g, q["filter"], sources, section_map) for g in q["gold"]
        ):
            errors.append(f"{qid}: không gold nào thỏa filter {q['filter']}")

    dev = [q for q in questions if q.get("split") == "dev"]
    test = [q for q in questions if q.get("split") == "test"]
    filt = [q for q in questions if q.get("filter")]
    filt_test = [q for q in filt if q.get("split") == "test"]
    print(f"Tổng: {len(questions)} | dev: {len(dev)} | test: {len(test)} | "
          f"có filter: {len(filt)} (test: {len(filt_test)})")
    types: dict[str, int] = {}
    for q in questions:
        types[q.get("type", "?")] = types.get(q.get("type", "?"), 0) + 1
    print("Loại câu:", types)
    if len(questions) < 20: errors.append("Cần >= 20 câu")
    if len(dev) < 15: errors.append("Cần >= 15 câu dev")
    if len(test) < 5: errors.append("Cần >= 5 câu test")
    if len(filt) < 3: errors.append("Cần >= 3 câu có filter")
    if not filt_test: errors.append("Cần >= 1 câu filter thuộc test")

    if errors:
        print(f"\n{len(errors)} lỗi:")
        for e in errors:
            print(" -", e)
        return 1
    print("\nBenchmark hợp lệ.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Cách dùng: python scripts/verify_benchmark.py ../benchmark/questions.json")
    sys.exit(main(Path(sys.argv[1])))
