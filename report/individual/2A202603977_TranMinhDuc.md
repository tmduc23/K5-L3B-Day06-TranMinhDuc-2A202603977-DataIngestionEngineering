# Báo cáo cá nhân — Day 6

- Học viên: Trần Minh Đức — MSSV 2A202603977 — Lớp L3B
- Chủ đề: Vision Transformers cho semantic segmentation
- Thời điểm chạy: 2026-11-14 (theo `starter/results/config.json`)

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  Corpus gồm 2 bài báo arXiv, đều giấy phép **CC BY 4.0** (kiểm tra trên trang arXiv ngày 2026-11-14), được phép lưu trong repo và gửi text tới API embedding, chỉ cần ghi công tác giả.

  | `source_id` | Tài liệu | Phiên bản | Trang vật lý | Trang nội dung | Loại |
  |---|---|---|---:|---:|---|
  | `vit-seg-survey-2023` | Thisanke et al., *Semantic Segmentation using Vision Transformers: A survey* | arXiv 2305.03273v1 | 35 | 26 (p1–26) | p27–35: chỉ References |
  | `swin-2021` | Liu et al., *Swin Transformer: Hierarchical Vision Transformer using Shifted Windows* | arXiv 2103.14030v2 | 14 | 11 (p1–11) | p12–14: chỉ References |
  | **Tổng** | | | 49 | **37** | |

  Quy tắc tính: tính trang có nội dung văn bản liên quan (abstract, thân bài, appendix, bảng/hình có chú thích); loại trang chỉ chứa References; trang lẫn nội dung + References vẫn tính và ghi chú. Số ký tự từng trang đo bằng `starter/scripts/inspect_corpus.py` (log `starter/results/page_inspection.txt` sinh khi chạy script, không commit; số ký tự từng trang đã ghi lại trong `data/manifest.json`). Chi tiết: `data/manifest.json`. Bài survey ban đầu chỉ có 26 trang nội dung (< 30) nên bổ sung bài Swin — cũng là chủ đề mục 4.2 của survey.

- **Chuẩn hóa, lỗi và giới hạn:**
  Đọc bằng `pypdf` 6.21.4 theo từng trang (PDF sinh từ LaTeX, không cần OCR). Chuẩn hóa: Unicode NFKC (`ﬁ` → `fi`), nối từ bị gạch nối xuống dòng (`pro-\ncessing` → `processing`), gộp khoảng trắng nhưng giữ xuống dòng để nhận heading. Phần sau dòng `References` trên trang lẫn được cắt và ghi log (`starter/results/ingest_issues.json`: survey p26 bỏ 359 ký tự, Swin p11 bỏ 4.435 ký tự). Không có trang lỗi trích xuất hay trang rỗng.
  Giới hạn: **bảng bị vỡ cột** khi trích xuất (survey p13 Table 1, p25 Table 2; Swin p7–11) → chunk từ bảng khó đọc; công thức (survey p10–12) trích xuất không đẹp; nối gạch nối có thể dính từ ghép thật (`self-attention` → `selfattention`).

- **Embedding model/provider/version/số chiều, vector store/version, metric, lệnh chạy và chi phí:**
  - Embedding: **Cohere Embed API v2, model `embed-v4.0`, 1536 chiều** (`output_dimension=1536`), `embedding_types=float`, `truncate=NONE` (quá dài thì báo lỗi, không cắt âm thầm). Văn bản gửi `input_type="search_document"`, câu hỏi gửi `input_type="search_query"`; cùng model cho cả A/B/C. Gọi bằng `urllib` (không SDK), batch ≤ 96, thử lại chỉ với lỗi tạm thời; hết quota thì dừng, không fallback sang vector giả.
  - Vector store: **PostgreSQL 16.16 + pgvector 0.8.7** (Docker image `pgvector/pgvector:0.8.7-pg16`, cổng `127.0.0.1:55433`), bảng `chunks`, cột `embedding vector(1536)`. Metric **cosine** (`<=>`, score = 1 − distance), **exact search** (không tạo index ANN), top-3.
  - Lệnh chạy (thư mục `starter/`):
    ```powershell
    docker compose -p day6_student_starter up -d --wait
    python scripts\check_setup.py
    python -m src.run ingest      # đọc PDF → chunk A, B → embed → lưu pgvector
    python -m src.run evaluate    # 20 câu × A/B/C → traces + metrics
    ```
  - Chi phí: tính theo token Cohere tính phí (`meta.billed_units.input_tokens`): ingest A **28.902 token / 3 lần gọi**, B **26.165 token / 2 lần gọi**; evaluate **398 token / 2 lần gọi** (20 câu hỏi gửi trong 1 lần + 1 lần kiểm tra số chiều). Tổng ≈ 55,5 nghìn token. Chi phí USD = token × đơn giá `embed-v4.0` của Cohere tại thời điểm chạy (key trial: không phát sinh phí; trial giới hạn 1.000 lần gọi/tháng).

- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:**

  | Trường | Kiểu | Nguồn giá trị | Vai trò |
  |---|---|---|---|
  | `document_id`, `source` | text | `data/manifest.json` | Truy vết tài liệu (bắt buộc); lọc theo tài liệu |
  | `page` | int | Số trang vật lý PDF | Truy vết (bắt buộc) |
  | `section` | text | Heading đánh số trong PDF, chuẩn hóa qua `data/section_map.json` | Truy vết tới mục; phân tích lỗi |
  | `section_top` | text | Phần số đầu của heading (`2`, `4`, `A`…) | **Lọc** theo phần lớn của bài |
  | `document_type` | text | manifest: `survey` / `original_paper` | **Lọc** "theo bài gốc" |
  | `year` | int | manifest: 2023 / 2021 | Phụ |
  | `char_start`, `content_hash` | int / text | Tính khi chunk | Truy vết vị trí; phát hiện chunk thay đổi |

  Heading được tìm trên trang bằng **số mục ở đầu dòng** (vd. `^4\.\s`, `^A2\.1\.\s`) vì tên trong PDF có thể lệch (`Meta - analysis`, ký tự ghép); section đang mở được mang sang trang sau. Chọn `section_top` + `document_type` vì đây là ngữ cảnh người dùng có thể nêu trước ("trong phần ứng dụng", "theo bài báo gốc") và giá trị kiểm chứng được từ nguồn.

## Cấu hình và benchmark

- **A / B / C (tham số cụ thể, khác biệt duy nhất B–C):**

  | | Chunk | Tham số | Filter | Số chunk |
  |---|---|---|---|---:|
  | **A** | Cửa sổ ký tự cố định, không vượt ranh giới trang | size 500, overlap 50 | Không | 242 |
  | **B** | Cắt tại heading → gom nguyên câu tới max_size; heading đứng trơ trọi gộp vào đoạn sau; không vượt ranh giới trang | max_size 1000 | Không | 151 |
  | **C** | **Dùng lại index B** (cùng chunk, cùng vector) | — | `WHERE` theo `document_id` / `document_type` / `section_top`, chỉ khi câu hỏi có `filter` | (index B) |

  A–B chỉ khác cách chunk; **B–C chỉ khác việc áp metadata filter**. `chunk_id` ổn định (`<strategy>-<doc>-p<page>-c<idx>`) + `INSERT … ON CONFLICT DO UPDATE` → nạp lại cùng phiên bản không nhân đôi (đã chạy ingest 2 lần trong một lượt: A 242→242, B 151→151); chunk cũ không còn trong tài liệu bị xóa khi nạp lại.

- **≥20 câu: phân chia ≥15 dev / ≥5 test, câu metadata filter và cách kiểm chứng evidence:**
  20 câu (`benchmark/questions.json`): **15 dev / 5 test**, chia **trước khi chạy**, theo section — test chỉ lấy từ section không có câu dev (2.2.2 Medical, Swin 3.1, 4.6 Twins, 4.7 DPT, 4.9 Mask2Former). Loại câu: trực tiếp 5, diễn đạt lại 6, điều kiện 3, ngoại lệ 2, metadata filter 3, nhiều nguồn 1. Câu hỏi tiếng Việt, evidence nguyên văn tiếng Anh.
  **3 câu filter**: q06 (dev, `document_type=original_paper`), q15 (dev, `document_id`+`section_top=4`), **q08 (test**, `document_id`+`section_top=2`). Filter là ngữ cảnh người dùng nêu trong câu hỏi, không lấy từ gold.
  Gold dạng mảng (`source_id`, `page`, `evidence_quote`); câu có nhiều nguồn hợp lệ ghi đủ (q06, q07, q18). Kiểm chứng tự động bằng `starter/scripts/verify_benchmark.py` (evidence nằm đúng trang sau chuẩn hóa; filter có giá trị tồn tại và khớp ít nhất một gold) → `starter/results/benchmark_check.txt`: "Benchmark hợp lệ."

- **Tiêu chí chọn chiến lược đã chốt trước khi xem test** (`benchmark/README.md`):
  1. Evidence Hit@3 dev cao nhất; 2. nếu chênh ≤ 1 câu → Hit@1 dev cao hơn; 3. nếu vẫn hòa → ít chunk / ingest nhanh hơn.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 9/15 (60%) | 13/15 (87%) | 242 | ingest 5,63 s | 28.902 token / 3 lần gọi |
| A | test | 5/5 (100%) | 5/5 (100%) | 242 | | |
| B | dev | 13/15 (87%) | 13/15 (87%) | 151 | ingest 3,45 s | 26.165 token / 2 lần gọi |
| B | test | 2/5 (40%) | 5/5 (100%) | 151 | | |
| C | dev | 13/15 (87%) | 13/15 (87%) | (index B) | không ingest thêm | 0 thêm |
| C | test | 2/5 (40%) | 5/5 (100%) | (index B) | | |

Truy vấn 20 câu dùng chung cho cả 3 cấu hình: 398 token / 2 lần gọi. Thời gian ingest gồm embed + upsert; thời gian truy vấn không đo riêng. MRR@3 (bổ sung): A dev 0,733 / test 1,000; B và C dev 0,867 / test 0,700.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 0,90 (n=10; 0/1/2 = 1/9/0) | 13/15 | N/A (không áp filter) | 0/0/5 — 2,00 |
| B | 1,50 (n=10; 0/1/2 = 1/3/6) | 15/15 | N/A (không áp filter) | 0/0/5 — 2,00 |
| C | 1,50 (= B, cùng chunk) | 15/15 | dev 2/2, test 1/1 | 0/0/5 — 2,00 |

**Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**
- Trace top-3 đầy đủ (câu hỏi, split, filter, chunk ID/text, score, metadata, nhãn tự động): `starter/results/traces_A.json`, `traces_B.json`, `traces_C.json`; bản dễ đọc `traces_readable.md`, `top3_all.csv` sinh bằng `scripts/export_traces.py` (không commit). Chỉ số: `starter/results/metrics.json`. Cấu hình chạy: `config.json`; thống kê ingest: `ingest_stats.json`.
- Nhãn audit: `starter/results/coherence.json`, `metadata.json`, `grounding.json`; tổng hợp `audit_summary.md` sinh bằng `scripts/summarize_audit.py` (đọc từ `results/audit/`, không commit).
- Cách chọn mẫu: **coherence** — quy tắc cố định chọn trước: sắp 37 trang theo (thứ tự manifest, số trang), lấy 10 trang cách đều (chỉ số 0, 4, …, 36), vị trí = ký tự giữa trang; chấm chunk chứa vị trí đó ở A và B (C dùng chunk B). Hai vị trí rơi vào bảng (P07 survey p25, P09 Swin p7) được giữ nguyên, không chọn lại. **Metadata** — 5 câu test × top-3 × A/B/C = 45 bản ghi, đối chiếu PDF. **Grounding** — 5 câu test × A/B/C, chỉ dựa vào top-3.
- Nhãn audit được soạn với sự hỗ trợ của công cụ AI (Claude Code) dựa trên trace và PDF gốc; tác giả chịu trách nhiệm rà soát từng nhãn. Người chấm là tác giả bài, đã biết cấu hình nào được chọn → có nguy cơ thiên lệch.

## Phân tích và kết luận

- **So sánh A–B và B–C; 2 ví dụ sai có ID câu và nguồn:**
  - **A–B (chỉ đổi chunk):** B hơn A ở Hit@1 dev (13/15 so với 9/15), coherence (1,50 so với 0,90) và metadata (15/15 so với 13/15); Hit@3 dev bằng nhau (13/15). Trên test thì ngược: A Hit@1 5/5, B 2/5; Hit@3 test cả hai 5/5. Theo loại câu (Hit@1, 20 câu): B thắng ở câu trực tiếp (5/5 so với 3/5) và điều kiện (3/3 so với 2/3) — cần trọn câu; A thắng ở câu filter (3/3 so với 1/3) và ngoại lệ (1/2 so với 0/2). Chunk A gần như luôn bắt đầu/kết thúc giữa từ (9/10 vị trí coherence được 1 điểm); 2 lỗi section của A do chunk cố định vắt qua heading.
  - **B–C (chỉ thêm filter):** kết quả **trùng nhau ở mọi câu**. Với q06, q15 (dev), B không lọc vẫn trả top-3 nằm trong phạm vi filter; với q08 (test), filter chỉ thay hạng 3 (survey p26 mục 5 Discussion → p5 mục 2.2.1) nên Hit không đổi. Đo thêm: không lọc, top-3 của A và B ở q08 chỉ 2/3 chunk nằm trong phạm vi; C 3/3. → Filter bảo đảm phạm vi nhưng không cải thiện chỉ số trên bộ câu hiện tại.
  - **Ví dụ sai 1 — q05 (dev, điều kiện), cấu hình A, survey `vit-seg-survey-2023` p12:** câu evidence "If data is collected under some deviated environmental conditions including rainy, cloudy, nighttime, snowy, etc then such data are categorized under cross-domain datasets." bị **cắt đôi** giữa chunk `A-vit-seg-survey-2023-p012-c01` (có vế "If data is collected…" nhưng kết thúc ở "…nighttime, snowy, etc") và `c02` (bắt đầu giữa từ "ns including rainy, cloudy, nighttime, snowy, etc then such data are categorized…", thiếu vế điều kiện đầu câu). Top-1, top-2 đều đúng trang nhưng không chunk nào chứa đủ evidence → Hit@3 = 0. B giữ trọn câu → hit ở hạng 1.
  - **Ví dụ sai 2 — q20 (test, ngoại lệ), cấu hình B/C, survey p23–p24:** top-1 là chunk mở đầu mục 4.9 (p23, score 0,6052) chứa "introduce a universal architecture" — trùng từ khóa "universal" trong câu hỏi — trong khi đáp án "still needs to be trained separately for each of the specific tasks" nằm ở chunk p24 hạng 2 (score 0,6018, chênh 0,003). Tương tự q18 (test, Twins): top-1 p19 nhắc "PVT v1" (trùng câu hỏi), đáp án CPE ở p21 hạng 2 (chênh < 0,001).
  - **Ví dụ sai 3 — q10 (dev, ngoại lệ), B/C, Swin p8:** cả 3 hit ở Swin p8 (ablation), trong đó có câu "absolute position embedding … harms object detection and semantic segmentation" — bằng chứng gần nghĩa nhưng không phải gold (p5: "…drops performance slightly, thus it is not adopted"). Đây vừa là lỗi truy xuất vừa là giới hạn của gold (đã ghi chú trước trong `benchmark/README.md`).

- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:**
  Áp dụng tiêu chí trên dev: Hit@3 hòa (13/15) → Hit@1: B = C = 13/15 > A = 9/15 → loại A; tài nguyên: C dùng lại index B → B, C vẫn hòa. Tiêu chí chốt trước không tách được B và C; **tiêu chí bổ sung** (đặt sau khi xem dev, ghi trong `benchmark/README.md`): khi kết quả và tài nguyên bằng nhau, chọn cấu hình bảo đảm phạm vi khi người dùng cung cấp ngữ cảnh → **chọn C**. Lệnh `evaluate` in dev và test cùng lúc; tuy nhiên B và C có kết quả test giống hệt nên test không ảnh hưởng lựa chọn này, và việc loại A dựa hoàn toàn trên tiêu chí đã chốt. Kết quả A tốt hơn ở Hit@1 test chỉ được báo cáo, không dùng để đổi lựa chọn.
  Đánh đổi: B/C cho chunk tự hiểu được, giữ trọn điều kiện/ngoại lệ, metadata `section` chính xác, ít chunk hơn (151 so với 242, ingest nhanh hơn, ít token hơn); đổi lại chunk dài hơn (trung bình 676 so với 465 ký tự) nên khi câu hỏi nhắm vào chi tiết nằm giữa một section dài, chunk giới thiệu cùng section dễ chiếm hạng 1. A cho chunk ngắn, xếp hạng chi tiết tốt hơn trên test, nhưng cắt evidence (q05) và gán section sai khi vắt qua heading.
  Điều kiện áp dụng: C phù hợp khi người dùng/hệ thống có ngữ cảnh phạm vi (tài liệu, phần) đáng tin trước khi truy xuất và câu trả lời cần trích dẫn trọn câu; nếu ưu tiên hạng 1 cho câu hỏi chi tiết, cần thêm reranker hoặc chunk nhỏ hơn (xem cải tiến).

- **Hạn chế của dữ liệu, nhãn, test nhỏ, đo thời gian/chi phí:**
  - Corpus nhỏ (2 bài, 37 trang), cùng chủ đề và **trùng nội dung** (survey mục 4.2 ≈ bài Swin) → nguy cơ rò rỉ giữa dev/test cho câu về Swin; mỗi giá trị `document_type` chỉ có 1 tài liệu nên filter này gần như chỉ ra nguồn gold.
  - **Test chỉ 5 câu**: mỗi câu = 20 điểm %; chênh A–B trên test (3 câu) nằm trong dao động mẫu nhỏ. Test có 4/5 câu evidence nằm sâu trong section (dev 8/15) — cách chia đề góp phần làm test ngược dev. Không khái quát ngoài corpus này.
  - Phân tích theo đặc điểm câu: evidence ở chunk đầu section (A 5/8, B 6/8 Hit@1) và nằm sâu (A 9/12, B 9/12) — không thấy khác biệt rõ; giả thuyết "chunk dài làm loãng chi tiết" **chưa được xác nhận**. Cách diễn đạt câu hỏi (trùng từ khóa với đoạn giới thiệu) giải thích phần lớn lỗi top-1 của B.
  - Câu hỏi tiếng Việt / tài liệu tiếng Anh: score thấp (≈ 0,4–0,6) và biên top-1/top-2 nhỏ (A 0,056, B 0,078 trung bình) → thứ hạng mong manh.
  - Grounding 0–2 trên top-3 **bão hòa** (cả 3 cấu hình 2,00) nên không phân biệt được cấu hình. Chấm tự động Hit khắt khe (nhãn `page_only` khi evidence ở chunk khác cùng trang).
  - Nhãn audit do một người (tác giả) chấm với hỗ trợ AI; chưa có người chấm thứ hai. Coherence chỉ 10 vị trí, 2 vị trí rơi vào bảng.
  - Thời gian ingest đo một lần, gồm độ trễ mạng tới Cohere; không đo thời gian truy vấn riêng. Chi phí ghi bằng token; đơn giá USD phụ thuộc loại key.
  - Bảng biểu bị vỡ khi trích xuất; chunk không vượt ranh giới trang nên ý nối sang trang sau bị tách (vd. coherence P03-B).

- **Nếu làm lại hoặc mở rộng, cải tiến gì?**
  1. **Reranker** (vd. Cohere Rerank đa ngữ): lấy top-10 từ pgvector rồi rerank xuống top-3 — nhắm vào lỗi "chunk giới thiệu cùng section chiếm hạng 1" (q18, q20), không đổi chunk.
  2. **Cấu hình D = B với max_size ≈ 600**: giữ trọn câu như B, chunk ngắn như A; so sánh D–B chỉ khác kích thước.
  3. **Dịch câu hỏi sang tiếng Anh** trước khi embed (áp dụng như nhau cho mọi cấu hình) để giảm chênh lệch ngôn ngữ.
  4. **Tiêu đề ngữ cảnh** (tên tài liệu + section) ghép vào chunk khi embed; **hybrid BM25 + dense** cho thuật ngữ chính xác (CPE, M = 7) — hạn chế: câu hỏi tiếng Việt chỉ khớp được tên riêng.
  5. **Xử lý bảng** riêng (gắn `content_type=table` hoặc loại khỏi index văn bản).
  6. **Benchmark**: thêm câu test (≥ 10) cân bằng loại câu và vị trí evidence; thêm câu filter "khó" (không lọc thì lẫn sang tài liệu khác); báo thêm MRR; có người chấm thứ hai. Vì bộ test hiện tại đã bị xem, mọi cải tiến trên phải chỉnh trên dev và đánh giá bằng **bộ test mới** viết trước khi chạy.

## Công cụ AI và cách kiểm tra

Có dùng công cụ AI (Claude Code) để: giải thích yêu cầu, gợi ý và viết mã pipeline (`starter/src/`), các script kiểm tra (`inspect_corpus.py`, `verify_benchmark.py`, `export_traces.py`, `make_audit_templates.py`, `summarize_audit.py`), soạn nháp câu hỏi benchmark, phân tích kết quả và soạn nháp nhãn audit. Cách kiểm tra: chạy thử từng phần trên corpus thật (số trang, số chunk, evidence nằm trong chunk), kiểm thử lưu/tìm/filter/nạp lại trên bảng thử riêng, kiểm thử gọi API với server giả lập trước khi gọi Cohere thật; evidence benchmark được kiểm bằng script đối chiếu text trang PDF; số liệu trong báo cáo lấy trực tiếp từ các file kết quả đã dẫn. Tác giả chịu trách nhiệm hiểu, giải thích và rà soát mã, câu hỏi và nhãn.
