"""Chấm truy xuất tự động: Hit@1, Evidence Hit@3, tuân thủ filter. Không thay chấm thủ công."""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def squash(text: str) -> str:
    """So khớp bền vững với lỗi trích xuất PDF: NFKC, bỏ khoảng trắng/gạch nối, viết thường."""
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[\s\-­‐‑]+", "", text)


def _label(question: dict[str, Any], hit: dict[str, Any]) -> str | None:
    """'evidence' = đúng nguồn + trang và chứa đủ evidence; 'page_only' = đúng trang, thiếu evidence."""
    label = None
    for g in question["gold"]:
        if hit["document_id"] == g["source_id"] and hit["page"] == g["page"]:
            if squash(g["evidence_quote"]) in squash(hit["text"]):
                return "evidence"
            label = "page_only"
    return label


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]],
                   applied_filter: dict[str, Any] | None = None) -> dict[str, Any]:
    labels = [_label(question, h) for h in hits[:3]]
    compliant = None
    if applied_filter:
        compliant = all(all(h.get(k) == v for k, v in applied_filter.items()) for h in hits[:3])
    return {
        "labels": labels,
        "hit_at_1": bool(labels) and labels[0] == "evidence",
        "hit_at_3": "evidence" in labels,
        "page_hit_at_3": any(labels),
        "filter_compliant": compliant,
    }


LABEL_LEGEND = {
    "evidence": "chunk đúng source + page của gold và chứa đủ evidence_quote (tính là hit)",
    "page_only": "đúng source + page nhưng thiếu evidence (evidence bị tách / chunk khác cùng trang)",
    "miss": "sai nguồn hoặc sai trang",
}
HIT_FIELDS = ["rank", "score", "label", "document_id", "page", "section", "section_top",
              "document_type", "year", "chunk_id", "text"]


def to_readable(trace: dict[str, Any]) -> dict[str, Any]:
    """Sắp trường quan trọng lên đầu, gắn nhãn vào từng hit, làm tròn score."""
    hits = []
    for h, label in zip(trace["hits"], trace["labels"]):
        h = {**h, "score": round(h["score"], 4), "label": label or "miss"}
        hits.append({k: h.get(k) for k in HIT_FIELDS})
    return {
        "id": trace["id"], "split": trace["split"], "type": trace["type"],
        "question": trace["question"], "filter_applied": trace["filter_applied"],
        "result": {k: trace[k] for k in ("hit_at_1", "hit_at_3", "page_hit_at_3", "filter_compliant")},
        "gold": trace["gold"],
        "hits": hits,
    }


def build_trace_file(strategy: str, config: dict[str, Any], traces: list[dict[str, Any]],
                     summary: dict[str, Any]) -> dict[str, Any]:
    """Một file / cấu hình: cấu hình + tóm tắt ở đầu, chi tiết từng câu ở dưới."""
    return {
        "strategy": strategy,
        "config": config,
        "summary": {split: {k: g[k] for k in ("Hit@1", "Hit@3", "Filter")} for split, g in summary.items()},
        "score": "cosine similarity = 1 - cosine distance (pgvector <=>); chỉ so sánh trong cùng câu hỏi",
        "label_legend": LABEL_LEGEND,
        "traces": [to_readable(t) for t in traces],
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Gộp theo chiến lược × split; báo tử số/mẫu số, không chỉ %."""
    out: dict[str, Any] = {}
    for t in traces:
        g = out.setdefault(t["strategy"], {}).setdefault(t["split"], {
            "n": 0, "hit_at_1": 0, "hit_at_3": 0, "page_hit_at_3": 0,
            "filter_n": 0, "filter_compliant": 0})
        g["n"] += 1
        g["hit_at_1"] += t["hit_at_1"]
        g["hit_at_3"] += t["hit_at_3"]
        g["page_hit_at_3"] += t["page_hit_at_3"]
        if t["filter_compliant"] is not None:
            g["filter_n"] += 1
            g["filter_compliant"] += t["filter_compliant"]
    for splits in out.values():
        for g in splits.values():
            n = g["n"]
            g["Hit@1"] = f"{g['hit_at_1']}/{n} ({g['hit_at_1'] / n:.0%})"
            g["Hit@3"] = f"{g['hit_at_3']}/{n} ({g['hit_at_3'] / n:.0%})"
            g["Filter"] = f"{g['filter_compliant']}/{g['filter_n']}" if g["filter_n"] else "N/A"
    return out
