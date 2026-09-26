# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Dương Phương Hiếu |
| MSSV | 2A202603008 |
| Khóa/Lớp | K4 — L3B |
| Tên nhóm | soopi |
| Vai trò chính | Source & Data Foundation (Ingestion, Cleaning & Repair) |
| Repository | https://github.com/meth04/K4-L3B-DAY10-soopi-DataPipelineDataObservability |
| Ngày hoàn thành | 2026-09-26 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Thu thập dữ liệu Crossref | `src/ingestion/crossref.py`, `fetch_source_records`, `parse_crossref_payload` | Query string, filter và `Settings` | `data/raw/crossref_response.json`, `data/raw/crossref_records.json` (24 bản ghi `PaperRecord`) | Hoàn thành |
| Làm sạch và chuẩn hoá dữ liệu | `src/ingestion/cleaning.py`, `build_clean_dataframe`, `build_text_for_embedding` | Danh sách `PaperRecord` và `run_date` | `data/clean/papers_clean.{csv,json}` — 24 dòng, 16 cột, có `text_for_embedding` 5 phần | Hoàn thành |
| Cơ chế Idempotent Repair | `src/ingestion/crossref.py::load_raw_records`, `src/ingestion/cleaning.py::build_clean_dataframe` | Raw snapshot `crossref_records.json` | Dataframe sạch 24 dòng giống hệt baseline, dùng cho self-healing và corruption flow | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Đồng bộ schema giữa raw records và clean dataframe | Module Retrieval (index, embeddings) và Evaluation (testset) | Các cột `paper_id`, `title`, `summary`, `authors_joined`, `categories_joined`, `published`, `abs_url`, `pdf_url` được đảm bảo luôn có mặt và nhất quán, giúp index và evaluation sử dụng trực tiếp |
| Cung cấp hàm `build_text_for_embedding` cho module Corruption | `src/ingestion/corruption.py` | Corruption module import trực tiếp `build_text_for_embedding` để rebuild embedding text sau khi tiêm lỗi |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Fetch 24 bản ghi từ Crossref API với retry và fallback offline | `src/ingestion/crossref.py::fetch_source_records`, `_request_with_retry` | `data/raw/crossref_response.json` (25.8 KB), `data/raw/crossref_records.json` (20.2 KB, 24 records) | `python script/run_phase1.py` — log `[phase1] Loaded 24 raw records from Crossref REST API` |
| Parse payload, strip JATS XML, validate DOI/title/abstract | `crossref.py::parse_crossref_payload`, `_strip_jats`, `_format_date_parts`, `_format_authors` | 24 `PaperRecord` hợp lệ (loại bỏ record thiếu DOI, title hoặc abstract tại biên) | `tests/test_ingestion.py::test_parse_crossref_payload_strips_jats_and_filters` |
| Chuẩn hoá schema, tính `age_days`, dedup, ghép `text_for_embedding` | `src/ingestion/cleaning.py::build_clean_dataframe` | 24 dòng clean, mỗi dòng có `text_for_embedding` 5 phần (Title/Authors/Published/Categories/Abstract) | `tests/test_ingestion.py::test_build_clean_dataframe_schema`, `test_build_clean_dataframe_deduplicates` |
| Đảm bảo repair idempotent từ raw snapshot | `load_raw_records` + `build_clean_dataframe` | `repaired_df.equals(repaired_again) == True` — chạy hai lần cho kết quả giống nhau | Log `[corruption] Repair idempotent: True` |

Output tiêu biểu: dataframe sạch `data/clean/papers_clean.json` với 24 dòng, 16 cột, `paper_id` duy nhất, `age_days ≥ 0`, `text_for_embedding` đủ 5 nhãn cấu trúc — là đầu vào duy nhất cho toàn bộ pipeline index, evaluation và observability phía sau.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Pipeline RAG cần nguồn dữ liệu bài báo khoa học đáng tin cậy, được chuẩn hoá theo schema chung để các module phía sau (embedding, evaluation, quality gate) có thể sử dụng mà không phải xử lý raw data. Dữ liệu từ Crossref API có format không đồng nhất: abstract lẫn markup JATS XML, date dạng `date-parts` lồng nhau, author thiếu trường `given`/`family`. Ngoài ra, cần cơ chế fallback khi mất mạng và khả năng repair idempotent từ snapshot thô.

### Cách triển khai

**Ingestion (`crossref.py`):**
- `_request_with_retry` thử tối đa 4 lần với backoff lũy thừa `min(2^attempt, 8)` giây cho các mã trạng thái 429/5xx. Khi tất cả lần thử thất bại, `fetch_source_records` fallback sang đọc `crossref_response.json` (toàn bộ payload) hoặc `crossref_records.json` (danh sách record đã parse).
- `parse_crossref_payload` duyệt `message.items`, validate 3 trường bắt buộc (DOI, title, abstract) ngay tại biên — record không hợp lệ bị loại trước khi vào pipeline, tránh lỗi lan sang bước cleaning.
- `_strip_jats` dùng regex xoá mọi tag XML và thay thế 7 HTML entity phổ biến (`&amp;`, `&lt;`, `&gt;`, `&quot;`, `&apos;`, `&#x2010;`, `&nbsp;`).
- `_format_date_parts` chuyển đổi node `date-parts` lồng nhau thành chuỗi ISO `YYYY-MM-DD`, fallback sang `date-time` khi `date-parts` rỗng, và đệm tháng/ngày thiếu thành 01.

**Cleaning (`cleaning.py`):**
- `build_clean_dataframe` chuẩn hoá whitespace, loại bỏ record có title < 8 ký tự hoặc summary < 40 ký tự (quá ngắn để làm retrieval target). Parse `published` thành UTC timestamp, tính `age_days = max(0, (run_date - published).days)`.
- Dedup theo `paper_id` giữ bản ghi đầu tiên (`keep='first'`), sort giảm dần theo `published`.
- `build_text_for_embedding` ghép 5 phần có nhãn cấu trúc (`Title:`, `Authors:`, `Published:`, `Categories:`, `Abstract:`) phân tách bằng newline — đây là nội dung duy nhất được embed vào ChromaDB.

**Repair:** Vì `build_clean_dataframe` là hàm thuần (pure function) của `(records, run_date)` và `load_raw_records` đọc snapshot bất biến, self-healing chỉ cần gọi lại hai hàm này để phục hồi hoàn toàn dataframe sạch.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Crossref API query/filter hoặc offline snapshot `data/raw/crossref_response.json` |
| Output | `data/raw/crossref_records.json` (24 `PaperRecord`), `data/clean/papers_clean.{csv,json}` (24 dòng, 16 cột) |
| Module phụ thuộc | `src/core/config.py` (Settings, Paths), `src/core/utils.py` (normalize_whitespace, compact_join, write_json) |
| Module sử dụng output | `src/retrieval/index.py`, `src/retrieval/embeddings.py`, `src/evaluation/testset.py`, `src/observability/quality.py`, `src/ingestion/corruption.py`, `src/observability/self_healing.py` |
| Điều kiện lỗi cần xử lý | Mất mạng (fallback snapshot), record thiếu DOI/title/abstract (loại tại biên), date parse thất bại (loại record), corpus rỗng sau cleaning (pipeline raise) |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
uv run pytest tests/test_ingestion.py -q
```

- **Kết quả mong đợi:** 24 raw records → 24 dòng clean, `paper_id` unique, `age_days ≥ 0`, `text_for_embedding` chứa 5 nhãn, pipeline không lỗi.
- **Kết quả thực tế:** 24 dòng clean; dedup không loại dòng nào (24 DOI đều unique); 5/5 test ingestion pass; log `[phase1] Clean dataframe: 24 rows`.
- **Artifact/log:** `data/raw/crossref_records.json`, `data/clean/papers_clean.json`, `data/clean/papers_clean.csv`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Chọn cách xử lý abstract từ Crossref — dữ liệu gốc lẫn JATS XML markup (`<jats:p>`, `<jats:italic>`, `&amp;`, ...).
- **Các phương án đã cân nhắc:**
  1. Giữ nguyên markup, để embedding model tự hiểu.
  2. Dùng thư viện XML parser (lxml/BeautifulSoup) để parse cây DOM rồi extract text.
  3. Strip bằng regex đơn giản + thay thế HTML entity thủ công.
- **Phương án đã chọn:** Phương án 3 — regex `<[^>]+>` kết hợp bảng 7 entity phổ biến.
- **Lý do:** Phương án 1 làm nhiễu embedding — các tag XML không mang ngữ nghĩa nhưng chiếm token. Phương án 2 thêm dependency nặng (lxml) chỉ để xử lý inline markup đơn giản, và Crossref abstract không có cấu trúc DOM phức tạp (không lồng sâu, không attribute cần giữ). Phương án 3 đủ tốt cho JATS inline markup và zero-dependency ngoài `re`. Trade-off: nếu Crossref thêm entity hiếm thì cần cập nhật bảng, nhưng 7 entity hiện tại phủ toàn bộ 24 bản ghi.
- **Bằng chứng:** `test_parse_crossref_payload_strips_jats_and_filters` xác nhận summary không còn `<jats:p>` và bắt đầu bằng nội dung văn bản thuần. Toàn bộ 24 record clean có summary > 40 ký tự, không lẫn tag.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Khi chạy pipeline trên máy không có kết nối mạng, `fetch_source_records` ném `RuntimeError: No network and no local raw snapshot available.` dù lần chạy trước đã tạo ra file raw.
- **Lệnh tái hiện:** Tắt mạng, xoá `data/raw/crossref_response.json`, chạy `python script/run_phase1.py`.
- **Nguyên nhân gốc:** Ban đầu fallback chỉ kiểm tra `crossref_response.json`. Nếu file này không tồn tại (đã bị xoá hoặc chưa fetch lần nào), hàm raise ngay dù `crossref_records.json` (danh sách record đã parse) vẫn có sẵn trong repo.
- **Cách xử lý:** Thêm tầng fallback thứ hai: nếu `crossref_response.json` không tồn tại, kiểm tra `crossref_records.json` và gọi `load_raw_records` để đọc trực tiếp danh sách record đã parse, bỏ qua bước parse payload. Thứ tự fallback: (1) live API → (2) `crossref_response.json` → (3) `crossref_records.json` → (4) raise.
- **Cách xác minh sau khi sửa:** Xoá `crossref_response.json`, tắt mạng, chạy `python script/run_phase1.py` — pipeline đọc từ `crossref_records.json` và chạy thành công, log `[ingestion] Live Crossref fetch failed (...); falling back to local snapshot.`
- **Điều học được:** Fallback nhiều tầng tốt hơn fallback đơn tầng. File raw records đã parse nhẹ hơn và dễ version control hơn full API response, nên nó nên là fallback cuối cùng trước khi raise. Đồng thời, lưu cả hai artifact (`crossref_response.json` cho data lineage, `crossref_records.json` cho offline portability) giúp pipeline vừa truy vết được nguồn gốc, vừa chạy được offline.

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?** `fetch_source_records` gọi Crossref REST API (hoặc đọc snapshot offline), parse JSON thành danh sách `PaperRecord`, strip JATS markup, validate DOI/title/abstract, lưu `crossref_response.json` và `crossref_records.json`. `build_clean_dataframe` chuẩn hoá whitespace, tính `age_days`, dedup theo `paper_id`, ghép `text_for_embedding` 5 phần. `LocalEmbeddingIndex.build` encode text bằng MiniLM-L6-v2, lưu vector vào ChromaDB collection với cosine distance.
2. **Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?** `test_set.json` gồm 10 câu hỏi, mỗi câu có `ground_truth` (đáp án đúng) và `ground_truth_doc_ids` (paper_id gốc). `retrieval_hit_rate` đo tỷ lệ câu mà top-k documents chứa tài liệu đích. `mean_token_f1` so sánh token overlap giữa câu trả lời và ground truth. Judge score đánh giá chất lượng câu trả lời qua LLM hoặc heuristic fallback.
3. **Quality checks khác freshness monitoring ở điểm nào?** Quality checks (GX 1.x) kiểm tra tính chất tĩnh của dữ liệu tại thời điểm chạy: row count, null, uniqueness, string length. Freshness monitoring quan tâm chiều thời gian: tỷ lệ record có `age_days > 180` so với ngưỡng 25%. Một dataset có thể pass quality checks nhưng fail freshness (dữ liệu sạch nhưng quá cũ), và ngược lại.
4. **Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?** Biến duy nhất được phép thay đổi giữa 3 lần đo là dữ liệu. Nếu đổi câu hỏi, chênh lệch metric có thể phản ánh độ khó câu hỏi chứ không phải tác động corruption, làm mất tính nhân quả của phép so sánh.
5. **Repair được xem là thành công dựa trên artifact và metric nào?** Ba tầng xác minh: (a) quality gate repaired `success = True` (`data/quality/repaired_quality_report.json`); (b) freshness `is_fresh = True`; (c) 4 metric trong `data/results/repaired_metrics.json` trở về bằng baseline (`hit_rate = 1.0`, `token_f1 = 1.0`, `judge_accuracy = 1.0`, `judge_score = 5`). `self_healing_log.json` ghi `healthy_before=false → repaired=true → healthy_after=true`.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.6000 | 1.0000 | `drop_latest_records` loại 5 bản ghi mới nhất khiến 4/10 truy vấn mất tài liệu đích — dữ liệu thiếu ở tầng ingestion ảnh hưởng trực tiếp retrieval. |
| `mean_token_f1` | 1.0000 | 0.7741 | 1.0000 | `blank_summary` (5 dòng) và `inject_noise` (4 dòng) làm hỏng nội dung embed, câu trả lời lệch ground truth. |
| `judge_accuracy` | 1.0000 | 0.8000 | 1.0000 | 2 câu bị đánh giá sai do retrieval trả về tài liệu không liên quan. |
| `mean_judge_score` | 5 | 4 | 5 | Giảm 1 điểm trung bình rồi phục hồi về mức tối đa. |
| Quality checks | True | False | True | 2 vi phạm: `ExpectColumnValuesToBeUnique[paper_id]` (duplicate) và `ExpectColumnValueLengthsToBeBetween[summary]` (blank summary). |
| Freshness status | True | False | True | `stale_date` đẩy 6 dòng lùi 900 ngày → 7/22 dòng stale (31.8%) vượt ngưỡng 25%. |

### Kết luận từ số liệu

1. **Corruption → quality signal → agent metric.** `blank_summary` xoá rỗng abstract 5 dòng + `inject_noise` chèn rác 4 dòng → `ExpectColumnValueLengthsToBeBetween[summary]` FAIL. `drop_latest_records` loại 5 bản ghi → row count giảm từ 24 xuống 19 (trước duplicate). `duplicate_rows` nhân bản 3 dòng → `ExpectColumnValuesToBeUnique[paper_id]` FAIL. Kết quả: `retrieval_hit_rate` 1.0 → 0.6, `mean_token_f1` 1.0 → 0.7741.
2. **Repair → quality recovery → metric recovery.** Self-healing đọc lại `crossref_records.json` (snapshot thô bất biến), chạy `build_clean_dataframe` rebuild 24 dòng sạch → quality gate `success = True`, freshness `is_fresh = True` → cả 4 metric phục hồi 100% về baseline.

**Corruption ảnh hưởng rõ nhất:** `drop_latest_records` — vì đây là mất mát dữ liệu ở tầng source, không thể khắc phục bằng retrieval thông minh. Tài liệu đích đơn giản không còn trong corpus, nên hit rate giảm trực tiếp 0.40. Ngược lại, `blank_summary`/`inject_noise` chỉ làm giảm chất lượng ngữ nghĩa nên suy giảm mượt hơn ở Token F1.

**Kết quả khác kỳ vọng:** Baseline đạt trần 1.0 ở cả 4 metric. Ban đầu kỳ vọng có nhiễu, nhưng vì `LLM_PROVIDER=mock` nên câu trả lời được trích xuất trực tiếp từ metadata tài liệu đúng — khớp hoàn hảo với ground truth vốn cũng sinh từ metadata. Điều này cho thấy vai trò cleaning rất quan trọng: khi metadata sạch, câu trả lời đúng hoàn toàn; khi metadata bị hỏng, kết quả suy giảm rõ rệt.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** Raw snapshot bất biến (`data/raw/crossref_records.json`) là tài sản quan trọng nhất — nhờ nó mà repair là idempotent và data lineage có thể truy vết ngược từ clean → raw → API. Không bao giờ sửa trực tiếp trên dữ liệu thô.
2. **Về data quality/observability:** Validation tại biên (loại record thiếu DOI/title/abstract ngay khi parse) ngăn lỗi lan vào pipeline. Nhưng chỉ validation tại biên là không đủ — cần quality gate (GX 1.x) ở giữa pipeline để bắt corruption xảy ra sau bước ingestion.
3. **Về ảnh hưởng của data đến RAG agent:** Chất lượng câu trả lời RAG phụ thuộc trực tiếp vào chất lượng dữ liệu tại tầng source. `text_for_embedding` sạch → embedding đúng ngữ nghĩa → retrieval chính xác. Khi summary bị blank hoặc nhiễu, embedding mất thông tin và câu trả lời lệch — nhưng pipeline không crash, tạo ra silent failure.

### Nếu có thêm thời gian

Thêm schema validation tự động cho raw records trước khi lưu: kiểm tra kiểu dữ liệu từng trường trong `PaperRecord`, đảm bảo DOI theo format regex `10\.\d{4,}/.*`, date ISO hợp lệ, summary có ít nhất 1 câu hoàn chỉnh. Đo cải thiện bằng cách tạo payload giả với các trường sai kiểu (DOI là số, date format lạ), chạy validation và xác nhận record bị từ chối trước khi vào cleaning. Điều này sẽ bắt lỗi data sớm hơn nữa, trước cả bước `build_clean_dataframe`.

## 10. Cam kết của thành viên

- [X] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [X] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [X] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [X] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [X] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [X] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Dương Phương Hiếu

**Ngày xác nhận:** 2026-09-26
