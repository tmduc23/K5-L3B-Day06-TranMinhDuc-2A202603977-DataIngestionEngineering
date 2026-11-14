"""Tổng hợp điểm chấm thủ công trong results/audit/*.json -> results/audit/audit_summary.md.

Chạy từ thư mục starter/ SAU KHI đã chấm:  python scripts\\summarize_audit.py
Báo mục chưa chấm / giá trị không hợp lệ thay vì tự đoán.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

AUDIT = Path(__file__).resolve().parents[1] / "results" / "audit"


def read(name: str) -> dict:
    return json.loads((AUDIT / name).read_text(encoding="utf-8"))


def score_table(scores: dict[str, list[int]]) -> list[str]:
    out = ["| Cấu hình | n | 0 | 1 | 2 | Trung bình /2 |", "|---|---:|---:|---:|---:|---:|"]
    for s in sorted(scores):
        if not scores[s]:
            continue
        c = Counter(scores[s])
        out.append(f"| {s} | {len(scores[s])} | {c[0]} | {c[1]} | {c[2]} | "
                   f"{sum(scores[s]) / len(scores[s]):.2f} |")
    return out


def main() -> None:
    problems: list[str] = []
    lines = ["# Tổng hợp chấm thủ công", "",
             "- **Người chấm:** Trần Minh Đức (tác giả bài, MSSV 2A202603977).",
             "- **Phương pháp:** nhãn được soạn với sự hỗ trợ của công cụ AI (Claude Code) dựa trên trace "
             "top-3 và đối chiếu PDF gốc; tác giả rà soát lại từng nhãn. Thang đo theo GUIDE.md §4.",
             "- **Nguy cơ thiên lệch:** người chấm đã biết cấu hình được chọn (C) và kết quả Hit@k; "
             "chưa có người chấm thứ hai.", ""]

    # coherence
    coh = defaultdict(list)
    for p in read("coherence.json")["positions"]:
        for s, c in p["chunks"].items():
            if c["score"] not in (0, 1, 2):
                problems.append(f"coherence: {p['position_id']} / {s} chưa chấm (score phải là 0, 1 hoặc 2)")
            else:
                coh[s].append(c["score"])
    lines += ["## Chunk coherence (10 vị trí, thang 0–2)", "", *score_table(coh), "",
              "C dùng chung chunk của B nên coherence của C = B.", ""]

    # metadata
    by = defaultdict(list)
    for r in read("metadata.json")["records"]:
        by[r["strategy"]].append(r)
        if r["checks"]["all_ok"] not in (True, False):
            problems.append(f"metadata: {r['strategy']} {r['id']} rank {r['rank']} chưa điền checks.all_ok (true/false)")
    lines += ["## Metadata usefulness (5 câu test × top-3)", "",
              "| Cấu hình | Bản ghi đủ & đúng | Tuân thủ filter (câu có filter) |", "|---|---|---|"]
    errors = []
    for s in sorted(by):
        rows = by[s]
        n_ok = sum(1 for r in rows if r["checks"]["all_ok"] is True)
        fq = defaultdict(list)
        for r in rows:
            if r["filter_applied"]:
                fq[r["id"]].append(bool(r["filter_compliant_auto"]))
            if r["checks"]["all_ok"] is False:
                errors.append(f"- {s} {r['id']} #{r['rank']}: {r['note']}")
        filt = f"{sum(all(v) for v in fq.values())}/{len(fq)} câu" if fq else "N/A (không áp filter)"
        lines.append(f"| {s} | {n_ok}/{len(rows)} | {filt} |")
    lines += ["", "Lỗi metadata ghi nhận:", *(errors or ["- (không có)"]), ""]

    # grounding
    gr = defaultdict(list)
    for it in read("grounding.json")["items"]:
        if it["score"] not in (0, 1, 2):
            problems.append(f"grounding: {it['id']} / {it['strategy']} chưa chấm (score phải là 0, 1 hoặc 2)")
        else:
            gr[it["strategy"]].append(it["score"])
    lines += ["## Grounding quality (5 câu test, thang 0–2)", "", *score_table(gr), "",
              "Đây là độ đủ của evidence truy xuất, không phải độ chính xác câu trả lời LLM.", ""]

    if problems:
        lines += ["## ⚠️ Chưa hoàn tất", "", *[f"- {p}" for p in problems], ""]
    (AUDIT / "audit_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
