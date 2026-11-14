"""Lưu và tìm vector bằng PostgreSQL + pgvector (cosine, exact search)."""
from __future__ import annotations

import re
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .models import Chunk

FILTER_COLUMNS = {"document_id", "document_type", "year", "section", "section_top"}


def _vec(values: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in values) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int, table: str = "chunks") -> None:
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
            raise ValueError("Tên bảng không hợp lệ")
        if dimensions <= 0:
            raise ValueError("Số chiều phải > 0")
        self.url, self.dim, self.table = database_url, dimensions, table

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.url, row_factory=dict_row)

    def create_schema(self) -> None:
        t = self.table
        with self._connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {t} (
                    chunk_id      text PRIMARY KEY,
                    strategy      text NOT NULL,
                    document_id   text NOT NULL,
                    source        text NOT NULL,
                    page          int  NOT NULL,
                    section       text,
                    section_top   text,
                    document_type text,
                    year          int,
                    char_start    int,
                    content_hash  text,
                    text          text NOT NULL,
                    embedding     vector({self.dim}) NOT NULL
                )""")
            conn.execute(f"CREATE INDEX IF NOT EXISTS {t}_strategy_idx ON {t} (strategy)")
            row = conn.execute(
                "SELECT format_type(atttypid, atttypmod) AS t FROM pg_attribute "
                "WHERE attrelid = %s::regclass AND attname = 'embedding'", (t,)).fetchone()
            if row["t"] != f"vector({self.dim})":
                raise RuntimeError(f"Bảng {t} đang dùng {row['t']}, model cần vector({self.dim}). "
                                   "Đổi tên bảng hoặc xóa bảng cũ có chủ đích.")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> int:
        """Ghi theo chunk_id ổn định (không nhân đôi); xóa chunk cũ không còn trong tài liệu.

        Trả về số chunk cũ đã xóa.
        """
        if len(chunks) != len(vectors):
            raise ValueError("Số chunk khác số vector")
        if any(len(v) != self.dim for v in vectors):
            raise ValueError(f"Có vector không đủ {self.dim} chiều")
        rows = [(c.chunk_id, strategy, c.document_id, c.source, c.page,
                 c.metadata.get("section"), c.metadata.get("section_top"),
                 c.metadata.get("document_type"), c.metadata.get("year"),
                 c.metadata.get("char_start"), c.metadata.get("content_hash"),
                 c.text, _vec(v)) for c, v in zip(chunks, vectors)]
        t, deleted = self.table, 0
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(f"""
                    INSERT INTO {t} (chunk_id, strategy, document_id, source, page, section,
                        section_top, document_type, year, char_start, content_hash, text, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        source = EXCLUDED.source, page = EXCLUDED.page,
                        section = EXCLUDED.section, section_top = EXCLUDED.section_top,
                        document_type = EXCLUDED.document_type, year = EXCLUDED.year,
                        char_start = EXCLUDED.char_start, content_hash = EXCLUDED.content_hash,
                        text = EXCLUDED.text, embedding = EXCLUDED.embedding""", rows)
                for doc in {c.document_id for c in chunks}:
                    keep = [c.chunk_id for c in chunks if c.document_id == doc]
                    cur.execute(f"DELETE FROM {t} WHERE strategy = %s AND document_id = %s "
                                f"AND NOT (chunk_id = ANY(%s))", (strategy, doc, keep))
                    deleted += cur.rowcount
        return deleted

    def count(self, strategy: str) -> int:
        with self._connect() as conn:
            return conn.execute(f"SELECT count(*) AS n FROM {self.table} WHERE strategy = %s",
                                (strategy,)).fetchone()["n"]

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if len(query_vector) != self.dim:
            raise ValueError(f"Vector truy vấn phải có {self.dim} chiều")
        where, params = ["strategy = %s"], [strategy]
        for key, value in (filters or {}).items():
            if key not in FILTER_COLUMNS:            # chỉ nhận cột trong whitelist
                raise ValueError(f"Không hỗ trợ filter theo '{key}'")
            where.append(f"{key} = %s")
            params.append(value)
        q = _vec(query_vector)
        sql = (f"SELECT chunk_id, document_id, source, page, section, section_top, document_type, "
               f"year, text, 1 - (embedding <=> %s::vector) AS score FROM {self.table} "
               f"WHERE {' AND '.join(where)} ORDER BY embedding <=> %s::vector LIMIT %s")
        with self._connect() as conn:
            rows = conn.execute(sql, [q, *params, q, top_k]).fetchall()
        return [{**r, "score": float(r["score"])} for r in rows]
