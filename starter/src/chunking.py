"""Hai cách chia chunk: cố định (A) và theo heading + câu (B). Chunk không vượt qua ranh giới trang."""
from __future__ import annotations

import hashlib
import re

from .models import Chunk, DocumentPage

SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[•])")
MIN_SEGMENT = 80   # đoạn ngắn hơn (chỉ có tiêu đề) được gộp vào đoạn kế tiếp


def section_at(page: DocumentPage, pos: int) -> tuple[str, str]:
    """Section của vị trí pos = heading cuối cùng đứng trước (hoặc tại) pos."""
    section, top = page.metadata["headings"][0][1:]
    for hpos, name, sec_top in page.metadata["headings"]:
        if hpos <= pos:
            section, top = name, sec_top
    return section, top


def _make_chunk(strategy: str, page: DocumentPage, idx: int, start: int, text: str) -> Chunk:
    section, top = section_at(page, start)
    flat = " ".join(text.split())
    return Chunk(
        chunk_id=f"{strategy}-{page.document_id}-p{page.page:03d}-c{idx:02d}",
        document_id=page.document_id, source=page.source, page=page.page, text=flat,
        metadata={
            "strategy": strategy, "section": section, "section_top": top,
            "document_type": page.metadata["document_type"], "year": page.metadata["year"],
            "char_start": start,
            "content_hash": hashlib.sha1(flat.encode("utf-8")).hexdigest()[:12],
        },
    )


def fixed_size(page: DocumentPage, size: int = 500, overlap: int = 50,
               strategy: str = "A") -> list[Chunk]:
    """Cửa sổ trượt `size` ký tự, chồng lấn `overlap` ký tự; có thể cắt giữa câu (có chủ đích)."""
    if not 0 <= overlap < size:
        raise ValueError("Cần 0 <= overlap < size")
    text, chunks, start = page.text, [], 0
    while start < len(text):
        piece = text[start:start + size]
        if piece.strip():
            chunks.append(_make_chunk(strategy, page, len(chunks), start, piece))
        if start + size >= len(text):
            break
        start += size - overlap
    return chunks


def _pack(text: str, a: int, b: int, max_size: int) -> list[tuple[int, int]]:
    """Gom các câu trong đoạn [a, b) thành nhóm <= max_size; câu quá dài thì cắt cứng."""
    units, s = [], a
    for m in SENTENCE_END.finditer(text, a, b):
        units.append((s, m.start()))
        s = m.end()
    units.append((s, b))
    out, cur = [], None
    for us, ue in units:
        if ue - us > max_size:
            if cur:
                out.append(cur)
                cur = None
            out += [(k, min(k + max_size, ue)) for k in range(us, ue, max_size)]
        elif cur is None:
            cur = (us, ue)
        elif ue - cur[0] <= max_size:
            cur = (cur[0], ue)
        else:
            out.append(cur)
            cur = (us, ue)
    if cur:
        out.append(cur)
    return [(x, y) for x, y in out if text[x:y].strip()]


def by_paragraph(page: DocumentPage, max_size: int = 1000, strategy: str = "B") -> list[Chunk]:
    """Cắt tại heading trước, rồi gom câu đến max_size; mỗi chunk thuộc trọn 1 section."""
    text = page.text
    real_headings = {p for p, _, _ in page.metadata["headings"][1:]}   # [0] là section mang từ trang trước
    bounds = [0]
    for b in sorted(real_headings - {0}) + [len(text)]:
        # Heading đứng trơ trọi (vd. "A2." ngay trước "A2.1.") -> gộp vào đoạn sau, không tạo chunk rỗng ý
        if bounds[-1] in real_headings and b - bounds[-1] < MIN_SEGMENT and b != len(text):
            continue
        bounds.append(b)
    chunks: list[Chunk] = []
    for a, b in zip(bounds, bounds[1:]):
        for x, y in _pack(text, a, b, max_size):
            chunks.append(_make_chunk(strategy, page, len(chunks), x, text[x:y]))
    return chunks
