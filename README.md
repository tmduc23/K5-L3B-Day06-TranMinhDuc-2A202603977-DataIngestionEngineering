# Day 06 · Data Ingestion Engineering — Trần Minh Đức (2A202603977, L3B)

Pipeline biến 2 bài báo về **Vision Transformers cho semantic segmentation** thành kho tri thức truy xuất được (PostgreSQL + pgvector, embedding Cohere), và so sánh 3 chiến lược chuẩn bị dữ liệu A/B/C trên cùng bộ 20 câu hỏi.

- **Corpus:** 2 bài arXiv, giấy phép CC BY 4.0, **37 trang nội dung** (survey 2305.03273v1: 26/35 trang; Swin Transformer 2103.14030v2: 11/14 trang) — [data/manifest.json](data/manifest.json)
- **Benchmark:** 20 câu (15 dev / 5 test), 3 câu có metadata filter — [benchmark/](benchmark/)
- **Cấu hình được chọn:** **C** (chunk theo heading + câu, có metadata filter) — lý do trong [benchmark/README.md](benchmark/README.md)
- **Báo cáo:** [report/individual/2A202603977_TranMinhDuc.md](report/individual/2A202603977_TranMinhDuc.md)

Đề bài gốc: [GUIDE.md](GUIDE.md) · [BENCHMARK.md](BENCHMARK.md) · [RUBRIC.md](RUBRIC.md) · [RULES.md](RULES.md) · [SUBMISSION.md](SUBMISSION.md) · [CHECKPOINTS.md](CHECKPOINTS.md)

---

## Kết quả tóm tắt

| Cấu hình | Chunk | Filter | Hit@1 dev | Hit@3 dev | Hit@1 test | Hit@3 test | Coherence /2 | Metadata đúng |
|---|---|---|---|---|---|---|---|---|
| A | Cố định 500 ký tự, overlap 50 | Không | 9/15 | 13/15 | 5/5 | 5/5 | 0,90 | 13/15 |
| B | Theo heading + câu, ≤ 1000 ký tự | Không | 13/15 | 13/15 | 2/5 | 5/5 | 1,50 | 15/15 |
| **C** | Như B (dùng lại index B) | Có (q06, q08, q15) | 13/15 | 13/15 | 2/5 | 5/5 | 1,50 | 15/15 |

Grounding (5 câu test, /2): cả 3 cấu hình 2,00. Tuân thủ filter của C: dev 2/2, test 1/1. Phân tích, ví dụ lỗi và giới hạn: xem báo cáo cá nhân.

---

## Cấu trúc thư mục

```text
.
├── STUDENT.md                       # thông tin học viên
├── data/
│   ├── manifest.json                # nguồn, giấy phép, trang nội dung, số ký tự từng trang
│   └── section_map.json             # heading → trang bắt đầu (dùng gán section / section_top)
├── benchmark/
│   ├── questions.json               # 20 câu: split, type, expected_answer, gold (source_id, page, evidence_quote), filter
│   └── README.md                    # quy tắc chia dev/test, filter, tiêu chí & kết quả chọn cấu hình
├── artifacts/experiment_log.csv     # cấu hình, giả thuyết, Hit dev/test của A/B/C
├── report/individual/2A202603977_TranMinhDuc.md
└── starter/
    ├── data/                        # 2 PDF corpus (CC BY 4.0)
    ├── docker-compose.yml, init.sql # PostgreSQL 16 + pgvector
    ├── requirements.txt, .env.example
    ├── src/                         # mã pipeline
    │   ├── ingestion.py             # đọc PDF theo trang, chuẩn hóa, cắt References, gắn heading
    │   ├── chunking.py              # A: fixed_size · B: by_paragraph (heading + câu)
    │   ├── embeddings.py            # CohereEmbedder (Embed API v2)
    │   ├── store.py                 # PgVectorStore: schema, upsert không trùng, search cosine + filter
    │   ├── evaluation.py            # Hit@1, Evidence Hit@3, tuân thủ filter, định dạng trace
    │   └── run.py                   # điều phối: ingest / evaluate / all
    ├── scripts/                     # kiểm tra setup/corpus/benchmark, xuất trace, mẫu & tổng hợp audit
    └── results/                     # ⟵ KẾT QUẢ (tương ứng thư mục results/ trong SUBMISSION.md)
        ├── config.json              # model, số chiều, phiên bản PostgreSQL/pgvector/thư viện, tham số A/B/C
        ├── ingest_stats.json        # số chunk, độ dài, token, lần gọi API, thời gian, kiểm tra nạp lại
        ├── ingest_issues.json       # log trang bị cắt References / lỗi trích xuất
        ├── traces_A.json, traces_B.json, traces_C.json   # trace top-3 đầy đủ từng câu
        ├── metrics.json             # Hit@1 / Hit@3 theo cấu hình × split
        ├── traces_readable.md, top3_all.csv               # bản dễ đọc của trace
        ├── audit/                   # chấm thủ công: coherence.json, metadata.json, grounding.json, audit_summary.md
        └── page_inspection.txt, benchmark_check.txt, setup_check.txt
```

---

## Yêu cầu môi trường

| Thành phần | Phiên bản đã dùng |
|---|---|
| Docker Desktop + Compose | Docker 29.8.2, Compose v5.6.0 |
| Python | 3.14.2 (starter hỗ trợ 3.11–3.14) |
| PostgreSQL / pgvector | 16.16 / 0.8.7 (image `pgvector/pgvector:0.8.7-pg16`) |
| Thư viện Python | `pypdf` 6.21.4, `psycopg[binary]` 3.3.8, `python-dotenv` 1.2.4 (không cần SDK Cohere — gọi API bằng `urllib`) |
| Embedding | Cohere Embed API v2, model `embed-v4.0`, 1536 chiều — cần **Cohere API key** |

---

## Cài đặt

Chạy trong PowerShell tại thư mục `starter/`:

```powershell
cd starter
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Sửa `starter/.env` (**không commit file này**):

```text
DATABASE_URL=postgresql://day6:day6_local_only@127.0.0.1:55433/day6_lab
COHERE_API_KEY=<key của bạn — https://dashboard.cohere.com/api-keys>
EMBEDDING_MODEL=embed-v4.0
EMBEDDING_DIMENSION=1536
```

Khởi động database và kiểm tra:

```powershell
docker compose -p day6_student_starter up -d --wait
python scripts\check_setup.py          # kỳ vọng: "... pgvector: 0.8.7" và "Setup OK"
python scripts\test_embedding.py       # gọi thử Cohere: in số chiều 1536, đoạn SegFormer có cosine cao nhất (3 lần gọi API)
```

---

## Chạy pipeline

Trong `starter/`, `(.venv)` đang bật, database `healthy`:

```powershell
python -m src.run ingest      # đọc 37 trang → chunk A (242) và B (151) → embed → upsert pgvector; nạp lại lần 2 để kiểm tra không trùng
python -m src.run evaluate    # 20 câu × A/B/C → results/traces_*.json, results/metrics.json
# hoặc: python -m src.run all
```

| Lệnh | Lần gọi Cohere (ước tính) | Ghi ra |
|---|---:|---|
| `ingest` | ~6 (1 kiểm tra số chiều + A 3 + B 2) | `config.json`, `ingest_stats.json`, `ingest_issues.json`, bảng `chunks` |
| `evaluate` | ~2 (1 kiểm tra số chiều + 20 câu trong 1 lần) | `config.json`, `traces_A/B/C.json`, `metrics.json` |

Kiểm tra số chunk trong database:

```powershell
docker exec -it day6_student_starter-postgres-1 psql -U day6 -d day6_lab -c "SELECT strategy, count(*) FROM chunks GROUP BY strategy;"
```

### Cấu hình A/B/C

Khai báo trong `STRATEGIES` ở [starter/src/run.py](starter/src/run.py). A–B chỉ khác cách chunk; B–C chỉ khác filter (C dùng lại index B). Cùng corpus, model, store, metric cosine (exact search, không index ANN) và top-3.

---

## Script phụ (`starter/scripts/`)

| Script | Tác dụng | Gọi API? |
|---|---|---|
| `check_setup.py` | Kiểm tra kết nối PostgreSQL + extension pgvector | Không |
| `inspect_corpus.py` | Đếm ký tự từng trang, đánh dấu trang rỗng/References → `results/page_inspection.txt` | Không |
| `verify_benchmark.py ..\benchmark\questions.json` | Kiểm tra số câu/split/filter, evidence nằm đúng trang gold → `results/benchmark_check.txt` | Không |
| `test_embedding.py` | Gọi thử Cohere với 1 câu hỏi + 3 đoạn văn | Có (3 lần) |
| `export_traces.py` | Xuất trace dễ đọc → `results/traces_readable.md`, `results/top3_all.csv` | Không |
| `make_audit_templates.py` | Sinh mẫu chấm thủ công (10 vị trí coherence chọn theo quy tắc cố định; 5 câu test cho metadata/grounding) → `results/audit/*.json` (không ghi đè nếu đã có) | Không |
| `summarize_audit.py` | Tổng hợp nhãn chấm → `results/audit/audit_summary.md` | Không |

---

## Tái lập kết quả

1. Corpus có sẵn trong `starter/data/` (nguồn và phiên bản trong `data/manifest.json`).
2. Benchmark và gold cố định trong `benchmark/questions.json` (chạy `verify_benchmark.py` để kiểm chứng).
3. Chạy `ingest` rồi `evaluate` như trên. Số chunk và độ dài là tất định; score có thể lệch rất nhỏ nếu Cohere cập nhật model phía server.
4. Số liệu trong báo cáo lấy từ `starter/results/` của lần chạy ngày 2026-11-14.

---

## Lưu ý

- **Bảo mật:** `starter/.env` chứa API key và đã nằm trong `.gitignore`; `starter/.env.example` chỉ có tên biến, không có key.
- **Quota:** key trial của Cohere giới hạn 1.000 lần gọi/tháng. Khi hết quota, code báo lỗi và dừng (không thử lại, không dùng vector giả).
- **Đổi model hoặc số chiều** sau khi đã ingest: chạy `DROP TABLE chunks;` trong psql rồi ingest lại (code sẽ báo lỗi nếu số chiều bảng không khớp model). Phải chạy lại cả A/B/C.
- **Dừng database, giữ dữ liệu:** `docker compose -p day6_student_starter stop`.
- **Công cụ AI:** có dùng Claude Code hỗ trợ viết mã, soạn nháp benchmark/nhãn audit và phân tích; phương pháp và cách kiểm tra ghi trong báo cáo cá nhân.
