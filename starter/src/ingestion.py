"""Đọc PDF theo trang, chuẩn hóa text, gắn heading/section và metadata tài liệu."""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage

log = logging.getLogger(__name__)
REFERENCES = re.compile(r"(?m)^\s*References\s*$")


def normalize_text(text: str) -> str:
    """NFKC, nối từ bị gạch nối xuống dòng, gộp khoảng trắng; giữ xuống dòng để nhận heading."""
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    text = re.sub(r"(\w)-\n(?=[a-z])", r"\1", text)          # "pro-\ncessing" -> "processing"
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _heading_pattern(section: str) -> re.Pattern:
    """Khớp heading theo số mục ở đầu dòng ("4.", "A2.1."), vì tên trong PDF có thể lệch."""
    m = re.match(r"^(A?\d+(?:\.\d+)*\.)\s", section)
    head = re.escape(m.group(1)) + r"\s" if m else re.escape(section) + r"\b"
    return re.compile(r"(?m)^" + head)


def find_headings(text: str, entries: list[dict]) -> list[tuple[int, dict]]:
    """Vị trí ký tự của các heading bắt đầu trên trang này (theo thứ tự trong section_map)."""
    found, pos = [], 0
    for entry in entries:
        m = _heading_pattern(entry["section"]).search(text, pos)
        if m:
            pos = m.start()
        else:
            log.warning("Không thấy heading %r ở trang %s; gán vị trí %s",
                        entry["section"], entry["start_page"], pos)
        found.append((pos, entry))
    return found


def load_pdf(path: Path, document_id: str, source: str, content_pages: list[int],
             sections: list[dict], doc_meta: dict) -> tuple[list[DocumentPage], list[dict]]:
    """Trích từng trang nội dung; trả về các trang và danh sách vấn đề (không bỏ qua âm thầm)."""
    reader = PdfReader(path)
    pages: list[DocumentPage] = []
    issues: list[dict] = []
    current = sections[0]                      # section đang mở, mang sang trang sau
    for n in content_pages:
        try:
            raw = reader.pages[n - 1].extract_text() or ""
        except Exception as exc:               # ghi lỗi, không âm thầm bỏ qua
            issues.append({"document_id": document_id, "page": n,
                           "issue": "extract_error", "detail": repr(exc)})
            continue
        text = normalize_text(raw)
        ref = REFERENCES.search(text)
        if ref:
            issues.append({"document_id": document_id, "page": n, "issue": "references_trimmed",
                           "detail": f"bỏ {len(text) - ref.start()} ký tự sau 'References'"})
            text = text[:ref.start()].rstrip()
        if len(text) < 200:
            issues.append({"document_id": document_id, "page": n,
                           "issue": "short_page", "detail": f"{len(text)} ký tự"})
        if not text:
            continue
        on_page = [e for e in sections if e["start_page"] == n]
        headings = [(0, current)] + find_headings(text, on_page)
        if on_page:
            current = on_page[-1]
        pages.append(DocumentPage(
            document_id=document_id, source=source, page=n, text=text,
            metadata={**doc_meta,
                      "headings": [(p, e["section"], e["section_top"]) for p, e in headings]},
        ))
    return pages, issues


def load_corpus(root: Path) -> tuple[list[DocumentPage], list[dict]]:
    """Đọc toàn bộ corpus theo data/manifest.json và data/section_map.json."""
    manifest = json.loads((root / "data/manifest.json").read_text(encoding="utf-8"))
    section_map = json.loads((root / "data/section_map.json").read_text(encoding="utf-8"))
    pages, issues = [], []
    for src in manifest["sources"]:
        doc_pages, doc_issues = load_pdf(
            root / src["local_path"], src["source_id"], src["local_path"], src["content_pages"],
            section_map[src["source_id"]],
            {"document_type": src["document_type"], "year": src["year"]},
        )
        pages += doc_pages
        issues += doc_issues
    return pages, issues
