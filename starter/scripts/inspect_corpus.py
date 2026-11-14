"""Đếm ký tự từng trang, đánh dấu trang rỗng/references để lập manifest.

Chạy từ thư mục starter/:  python scripts/inspect_corpus.py
"""
import re
import sys
import unicodedata
from pathlib import Path

from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")
REF_LINE = re.compile(r"^\s*\[\d+\]")


def inspect(pdf: Path) -> list[dict]:
    rows = []
    for no, page in enumerate(PdfReader(pdf).pages, start=1):
        try:
            raw = page.extract_text() or ""
            error = None
        except Exception as exc:  # ghi lỗi, không bỏ qua âm thầm
            raw, error = "", repr(exc)
        text = " ".join(unicodedata.normalize("NFKC", raw).split())
        lines = [line for line in raw.splitlines() if line.strip()]
        ref_ratio = sum(bool(REF_LINE.match(line)) for line in lines) / max(len(lines), 1)
        rows.append({
            "page": no,
            "chars": len(text),
            "ref_line_ratio": round(ref_ratio, 2),
            "empty": len(text) < 200,
            "error": error,
            "preview": text[:80],
        })
    return rows


if __name__ == "__main__":
    data_dir = Path(__file__).resolve().parents[1] / "data"
    for pdf in sorted(data_dir.glob("*.pdf")):
        rows = inspect(pdf)
        print(f"\n=== {pdf.name} | physical_pages={len(rows)}")
        for r in rows:
            flag = "EMPTY" if r["empty"] else ("REFS?" if r["ref_line_ratio"] > 0.15 else "")
            err = f" ERROR={r['error']}" if r["error"] else ""
            print(f"p{r['page']:>3} {r['chars']:>5} ch  refs={r['ref_line_ratio']:.2f} {flag:6}{err} {r['preview']}")
