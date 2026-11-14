"""Embedding thật qua Cohere Embed API v2: POST https://api.cohere.com/v2/embed."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, question: str) -> list[float]: ...


class CohereEmbedder:
    """Gọi Cohere Embed v2.

    - Văn bản dùng input_type="search_document", câu hỏi dùng "search_query" (bắt buộc với model v3+).
    - Tối đa 96 text mỗi lần gọi -> tự chia batch.
    - truncate="NONE": input quá dài sẽ báo lỗi thay vì bị cắt âm thầm.
    - Ghi lại số lần gọi và số token tính phí (meta.billed_units.input_tokens).
    - Lỗi API -> raise, KHÔNG fallback sang vector giả. Chỉ thử lại lỗi tạm thời (429, 5xx).
    """

    MAX_BATCH = 96
    RETRY_STATUS = {429, 500, 503, 504}

    def __init__(self, model_name: str = "embed-v4.0", api_key: str | None = None,
                 output_dimension: int | None = None, batch_size: int = 96, timeout: int = 60,
                 max_retries: int = 4, base_url: str = "https://api.cohere.com/v2") -> None:
        self.api_key = api_key or os.getenv("COHERE_API_KEY")
        if not self.api_key:
            raise RuntimeError("Thiếu COHERE_API_KEY trong starter/.env")
        self.model_name = model_name
        self.output_dimension = output_dimension      # chỉ dùng cho embed-v4.0 / v5 trở lên
        self.batch_size = min(batch_size, self.MAX_BATCH)
        self.timeout = timeout
        self.max_retries = max_retries
        self.url = base_url.rstrip("/") + "/embed"
        self.calls = 0
        self.total_tokens = 0
        self.dimensions = len(self._embed(["dimension check"], "search_query")[0])

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.url, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
            "Accept": "application/json"})
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                quota_exhausted = exc.code == 429 and "month" in detail.lower()
                if quota_exhausted:      # hết quota tháng: thử lại chỉ tốn thêm lượt gọi
                    raise RuntimeError(f"Cohere: hết quota tháng của key. {detail}") from exc
                if exc.code in self.RETRY_STATUS and attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Cohere lỗi HTTP {exc.code}: {detail}") from exc
            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Không kết nối được Cohere: {exc.reason}") from exc
        raise RuntimeError("Cohere: hết số lần thử lại")

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        if any(not t.strip() for t in texts):
            raise ValueError("Có input rỗng")
        payload = {"model": self.model_name, "texts": texts, "input_type": input_type,
                   "embedding_types": ["float"], "truncate": "NONE"}
        if self.output_dimension:
            payload["output_dimension"] = self.output_dimension
        result = self._post(payload)
        vectors = (result.get("embeddings") or {}).get("float")
        if vectors is None:
            raise RuntimeError(f"Response không có embeddings.float: {str(result)[:300]}")
        if len(vectors) != len(texts):
            raise RuntimeError(f"Gửi {len(texts)} text nhưng nhận {len(vectors)} vector")
        billed = (result.get("meta") or {}).get("billed_units") or {}
        self.total_tokens += int(billed.get("input_tokens") or 0)
        self.calls += 1
        return vectors

    def _embed_all(self, texts: list[str], input_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            vectors += self._embed(texts[i:i + self.batch_size], input_type)
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed_all(texts, "search_document")

    def embed_queries(self, questions: list[str]) -> list[list[float]]:
        """Embed nhiều câu hỏi trong ít lần gọi (tiết kiệm quota trial)."""
        return self._embed_all(questions, "search_query")

    def embed_query(self, question: str) -> list[float]:
        return self._embed([question], "search_query")[0]
