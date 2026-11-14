# Benchmark

- File: `questions.json`
- Ngày chốt: 2026-11-14, trước khi chạy pipeline / bất kỳ cấu hình nào
- Số câu: 20 (15 dev / 5 test); câu có filter: 3 (1 test: q08)
- Loại câu: trực tiếp 5, diễn đạt lại 6, điều kiện 3, ngoại lệ 2, metadata filter 3, nhiều nguồn 1
- Ngôn ngữ: câu hỏi tiếng Việt; `evidence_quote` là nguyên văn tiếng Anh từ PDF → embedding model phải đa ngữ
- Kiểm chứng: `starter/scripts/verify_benchmark.py` → `starter/results/benchmark_check.txt` (evidence nằm đúng trang sau chuẩn hóa NFKC, bỏ khoảng trắng/gạch nối). Người viết đã đọc lại từng evidence trên PDF.

## Định dạng gold

Mỗi câu có mảng `gold` gồm (`source_id`, `page`, `evidence_quote`). Một câu có thể có nhiều nguồn hợp lệ; chunk được tính **hit** nếu thuộc đúng `source_id` + `page` của **bất kỳ** phần tử nào và chứa đủ `evidence_quote` của phần tử đó.

Các câu có nhiều gold: q06 (Swin trang 4, 5), q07 (Swin trang 1, 8; survey trang 15), q18 (survey trang 20, 21).

## Quy tắc chia dev / test

Chia theo section để giảm rò rỉ — test chỉ lấy từ các section không có câu dev:

| Test | Section |
|---|---|
| q08 | survey 2.2.2 Medical Images |
| q09 | Swin 3.1 Overall Architecture (Swin Transformer block) |
| q18 | survey 4.6 Twins |
| q19 | survey 4.7 DPT |
| q20 | survey 4.9 Mask2Former |

Không đổi câu hỏi, đáp án, gold hay split của test sau khi xem kết quả.

Nguy cơ rò rỉ còn lại:
- Survey mục 4.2 và bài Swin trùng nội dung; q09 (test) và q06, q10, q16 (dev) cùng nói về Swin.
- q18 (Twins, test) nhắc tới hạn chế của PVT v1, cùng chủ đề với q17 (PVT, dev).

## Metadata filter

- Giá trị filter là ngữ cảnh người dùng nêu trước khi truy xuất ("theo bài báo gốc", "trong phần ứng dụng của survey", "trong phần meta-analysis"), không lấy từ gold.
- q06: `{"document_type": "original_paper"}` — hạn chế: mỗi `document_type` chỉ có 1 tài liệu, nên filter này gần như chỉ ra nguồn gold.
- q08, q15: `document_id` + `section_top` — thu hẹp xuống nhiều trang (mục 2: trang 3–12; mục 4: trang 13–25), không chỉ thẳng trang gold.
- Câu không có filter: cấu hình C chạy không lọc.

## Tiêu chí chọn cấu hình (chốt trước khi xem test)

1. Evidence Hit@3 trên **dev** cao nhất.
2. Nếu chênh lệch ≤ 1 câu: chọn cấu hình có Hit@1 dev cao hơn.
3. Nếu vẫn hòa: chọn cấu hình ít chunk hơn / ingest nhanh hơn.

Chọn xong trên dev mới đọc và báo cáo kết quả test.

## Áp dụng tiêu chí (2026-11-14)

Embedding: Cohere `embed-v4.0`, 1536 chiều; pgvector cosine, exact search; top-3. Số liệu từ `starter/results/metrics.json`.

| Cấu hình | Hit@1 dev | Hit@3 dev | Hit@1 test | Hit@3 test | Filter (dev / test) | Số chunk | Ingest |
|---|---|---|---|---|---|---:|---:|
| A — fixed 500 / overlap 50 | 9/15 | 13/15 | 5/5 | 5/5 | N/A | 242 | 5,63 s |
| B — heading + câu, ≤ 1000 | 13/15 | 13/15 | 2/5 | 5/5 | N/A | 151 | 3,45 s |
| C — B + metadata filter | 13/15 | 13/15 | 2/5 | 5/5 | 2/2 / 1/1 | (index B) | (index B) |

Áp dụng trên **dev**:

1. Hit@3 dev: A = B = C = 13/15 → chênh 0 câu (≤ 1) → sang bước 2.
2. Hit@1 dev: B = C = 13/15 > A = 9/15 → **loại A**.
3. Tài nguyên: C dùng lại index của B → B và C bằng nhau → **vẫn hòa**.

Tiêu chí chốt trước không tách được B và C. **Tiêu chí bổ sung** (đặt ra sau khi xem kết quả, ghi rõ ở đây): khi kết quả và tài nguyên bằng nhau, chọn cấu hình bảo đảm phạm vi truy xuất khi người dùng có cung cấp ngữ cảnh → **chọn C**. Trên dev, top-3 của C tuân thủ filter 2/2 câu; B không lọc nên không bảo đảm điều này (dù với q06, q15 top-3 của B tình cờ vẫn nằm trong phạm vi).

**Cấu hình được chọn: C.**

### Minh bạch về việc xem test

- Lệnh `python -m src.run evaluate` in kết quả dev và test **cùng một lúc**, nên test đã hiển thị khi áp dụng tiêu chí. Quyết định loại A dựa hoàn toàn trên tiêu chí 1–2 đã chốt từ trước.
- Tiêu chí bổ sung chỉ phân xử giữa B và C, mà B và C có kết quả test **giống hệt nhau** (2/5, 5/5) → kết quả test không ảnh hưởng tới lựa chọn này.
- Trên test, A tốt hơn ở Hit@1 (5/5 so với 2/5). Kết quả này **chỉ được báo cáo**, không dùng để đổi lựa chọn. Với 5 câu test, mỗi câu tương đương 20 điểm %, nên chênh lệch nằm trong mức dao động của mẫu nhỏ.
- Không sửa câu hỏi, gold, split hay tham số A/B/C sau khi xem kết quả. Mọi thí nghiệm cải tiến sau này (vd. kích thước chunk khác, reranker) là thí nghiệm bổ sung, chỉnh trên dev và cần bộ test mới.

## Ghi chú

- Không lấy evidence từ bảng (survey trang 13, 25; Swin trang 7–11 phần bảng) vì text bảng bị vỡ cột khi trích xuất. Ngoại lệ: q16 lấy từ đoạn văn (không phải bảng) ở Swin trang 8.
- q10: Swin trang 8 cũng nói absolute position embedding "harms object detection and semantic segmentation", nhưng không nói trực tiếp là không dùng → không đưa vào gold; nếu top-k trả về đoạn này, người chấm xem xét như bằng chứng một phần.
