"""Gọi thử Cohere embedding: 1 câu hỏi tiếng Việt với 3 đoạn tiếng Anh.

Chạy từ thư mục starter/:  python scripts\\test_embedding.py
Dùng EMBEDDING_MODEL / EMBEDDING_DIMENSION / COHERE_API_KEY trong starter/.env.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

STARTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STARTER))
load_dotenv(STARTER / ".env")

from src.embeddings import CohereEmbedder  # noqa: E402

dim = os.getenv("EMBEDDING_DIMENSION")
emb = CohereEmbedder(os.getenv("EMBEDDING_MODEL") or "embed-v4.0",
                     output_dimension=int(dim) if dim else None)
print("Model:", emb.model_name, "| số chiều:", emb.dimensions)

question = "SegFormer dùng patch size bao nhiêu, so với ViT?"
passages = [
    "To obtain a precise segmentation, it uses a patch size of 4 × 4 in contrast to ViT which uses a patch size of 16 × 16.",
    "Cityscapes contains large-scale pixel-level and instance-level semantic segmentation annotations.",
    "Dice loss is one such widely used popular measure in computer vision tasks.",
]
q = emb.embed_query(question)
docs = emb.embed_documents(passages)


def norm(v: list[float]) -> float:
    return sum(x * x for x in v) ** 0.5


for text, d in zip(passages, docs):
    cosine = sum(a * b for a, b in zip(q, d)) / (norm(q) * norm(d))
    print(f"{cosine:.4f}  {text[:70]}")
print("Số lần gọi API:", emb.calls, "| token tính phí:", emb.total_tokens)
