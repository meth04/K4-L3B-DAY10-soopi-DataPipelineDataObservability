# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Khóa/Lớp         | K4                        |
| Tên nhóm         | soopi                     |
| Repository         | https://github.com/meth04/K4-L3B-DAY10-soopi-DataPipelineDataObservability |
| Ngày hoàn thành | 2026-09-26                |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Nguyễn Văn Thân | `[MSSV]` | Pipeline Integrator | `core/config.py`, `pipelines/phase1.py`, `pipelines/corruption_flow.py` |
| 2 | `[Họ tên]` | `[MSSV]` | Source & Data Foundation | `ingestion/crossref.py`, `ingestion/cleaning.py`, `data/raw/` |
| 3 | `[Họ tên]` | `[MSSV]` | RAG & Vector Index | `retrieval/index.py`, `retrieval/embeddings.py`, ChromaDB |
| 4 | `[Họ tên]` | `[MSSV]` | Observability & Evaluation | `observability/quality.py`, `evaluation/testset.py`, `observability/reporting.py` |

## 2. Tóm tắt kết quả

Nhóm đã hoàn thành toàn bộ pipeline end-to-end: thu thập 24 bản ghi Crossref, làm sạch thành
dataframe 24 dòng có `text_for_embedding` 5 phần, index vào ChromaDB với mô hình
`all-MiniLM-L6-v2`, và đánh giá trên bộ 10 câu hỏi phủ 4 nhóm nghiệp vụ. Baseline đạt
`retrieval_hit_rate = 1.0`, `mean_token_f1 = 1.0`, `judge_accuracy = 1.0`.

Sau khi tiêm 6 kịch bản corruption, chỉ số suy giảm rõ rệt: hit rate từ **1.0 → 0.6**,
Token F1 từ **1.0 → 0.7741**, judge accuracy **1.0 → 0.8**. Quality Gate GX 1.x báo
`success = False` với 2 vi phạm (trùng `paper_id` và độ dài `summary`), đồng thời Freshness SLA
chuyển sang `is_fresh = False` (7 dòng stale / 22). Corruption ảnh hưởng mạnh nhất là
`drop_latest_records` (5 bản ghi mới nhất bị mất → truy vấn không còn tài liệu đích) và
`blank_summary`/`inject_noise` (làm hỏng ngữ nghĩa embedding).

Cơ chế Self-healing tự phát hiện vi phạm và repair idempotent từ raw snapshot, phục hồi **100%**
chỉ số về mức baseline (`retrieval_hit_rate = 1.0`, `mean_judge_score = 5`), Quality Gate trở lại
`success = True` và freshness `is_fresh = True`. Blocker chính là thời gian cài đặt dependencies
(torch ~117MB) rất chậm, và Ragas bị tắt mặc định nên các chỉ số ngữ nghĩa nâng cao chưa được đo.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API (hoặc snapshot offline)
    -> raw response/raw records          (data/raw/)
    -> cleaning và data modeling         (data/clean/)
    -> embedding + ChromaDB index        (data/chroma/, data/embeddings/)
    -> evaluation baseline               (data/results/baseline_metrics.json)
    -> quality/freshness reports         (data/quality/)
    -> corruption                        (data/results/corruption_log.json)
    -> re-index và re-evaluate           (data/results/corrupted_metrics.json)
    -> repair từ raw snapshot            (data/results/repaired_metrics.json)
    -> comparison report                 (data/reports/corruption_report.md)
```

### Trách nhiệm của từng khối

| Khối             | Input          | Xử lý chính             | Output/artifact          | Owner          |
| ----------------- | -------------- | -------------------------- | ------------------------ | -------------- |
| Ingestion         | Crossref API / snapshot | Fetch có retry 429/503, fallback offline, parse JATS XML | `data/raw/crossref_{response,records}.json` | Thành viên 2 |
| Cleaning          | Raw records | Chuẩn hoá, `age_days`, dedup, `text_for_embedding` | `data/clean/papers_clean.{csv,json}` | Thành viên 2 |
| Embedding/index   | Clean dataframe | MiniLM-L6-v2 + ChromaDB cosine | `data/chroma/`, `data/embeddings/` | Thành viên 3 |
| Evaluation        | Clean df + index | Test set 10 câu, Hit Rate / Token F1 / LLM Judge | `data/eval/test_set.json`, `data/results/*_metrics.json` | Thành viên 4 |
| Observability     | Clean df | GX 1.x (5 expectations) + Freshness SLA | `data/quality/*.json` | Thành viên 4 |
| Corruption/repair | Clean df + raw snapshot | 6 kịch bản corruption + self-healing idempotent | `data/results/corruption_log.json` | Thành viên 1 |
| Orchestration     | Tất cả artifacts | Thứ tự chạy 2 script | `data/reports/*.md`, dashboard | Thành viên 1 |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình             | Giá trị sử dụng |
| ---------------------------- | ------------------- |
| `LLM_PROVIDER`             | `mock` (offline, không cần API key) |
| `LLM_MODEL`                | `gemini-2.5-flash` (không dùng khi provider=mock) |
| Embedding model              | `sentence-transformers/all-MiniLM-L6-v2` |
| Số lượng Crossref records | 24 |
| Retrieval `top_k`           | 4 |
| Freshness threshold          | 180 ngày, ngưỡng stale ratio 25% |
| Random seed, nếu có        | 42 (corruption suite) |

### Lệnh cài đặt

```bash
uv sync --extra dev
```

### Lệnh chạy

```bash
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
uv run python script/run_dashboard.py
uv run pytest tests -q
```

### Kết quả tái hiện

| Lệnh             | Trạng thái                                    | Thời điểm chạy gần nhất | Bằng chứng                         |
| ----------------- | ----------------------------------------------- | ----------------------------- | ------------------------------------ |
| Baseline pipeline | Thành công | 2026-09-26 | `data/results/baseline_metrics.json`, `data/reports/phase1_report.md` |
| Corruption flow   | Thành công | 2026-09-26 | `data/reports/corruption_report.md`, `data/results/corruption_log.json` |
| Test suite        | Thành công (26 passed) | 2026-09-26 | `uv run pytest tests -q` |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính                | Giá trị                             |
| --------------------------- | ------------------------------------- |
| Source                      | Crossref REST API (`https://api.crossref.org/works`), fallback `data/raw/crossref_response.json` |
| Query/filter                | `agentic retrieval augmented generation large language model`, `from-pub-date:<180d>,has-abstract:true` |
| Thời điểm lấy dữ liệu | 2026-09-26 |
| Số record nhận được    | 24 |
| Cơ chế retry/backoff      | 4 lần thử, backoff `min(2^attempt, 8)` giây cho 429/5xx; fallback snapshot khi mất mạng |

### Raw và clean schema

| Trường        | Kiểu dữ liệu | Bắt buộc?  | Ý nghĩa   | Xử lý khi thiếu/sai |
| --------------- | --------------- | ------------ | ----------- | ---------------------- |
| `paper_id` | string (DOI) | Có | Định danh tài liệu | Loại record nếu rỗng |
| `title` | string | Có | Tiêu đề | Loại nếu < 8 ký tự |
| `summary` | string | Có | Abstract đã strip JATS | Loại nếu < 40 ký tự |
| `authors_joined` | string | Không | Danh sách tác giả | `Unknown` trong embedding text |
| `categories_joined` | string | Không | Danh mục chủ đề | `Uncategorized` |
| `published` | string (ISO) | Có | Ngày xuất bản | Loại nếu parse thất bại |
| `age_days` | int | Có | Số ngày kể từ published | Dùng cho Freshness SLA |
| `text_for_embedding` | string | Có | Document 5 phần để embed | Sinh sau khi làm sạch |

### Quy tắc cleaning

| Quy tắc                                 | Quality dimension liên quan | Số record bị tác động | Cách xác minh      |
| ---------------------------------------- | ---------------------------- | -------------------------: | -------------------- |
| Loại record thiếu DOI/title/abstract | Completeness | 0 (24/24 hợp lệ) | `data/raw/crossref_records.json` |
| Strip JATS XML tag khỏi abstract | Validity | 24 | `summary` không còn `<jats:p>` |
| Loại title < 8 ký tự và summary < 40 ký tự | Validity | 0 | `tests/test_ingestion.py` |
| Dedup theo `paper_id` (keep first) | Uniqueness | 0 | `df["paper_id"].is_unique` |

Cách tạo `text_for_embedding`: ghép 5 phần có nhãn `Title:` / `Authors:` / `Published:` /
`Categories:` / `Abstract:`, phân tách bằng newline. `document ID` = `f"{paper_id}::{index}"`
đảm bảo ổn định và duy nhất kể cả khi corpus có bản ghi trùng. `age_days = (run_date - published).days`,
kẹp giá trị âm về 0.

## 6. Evaluation setup

| Thành phần                             | Cấu hình thực tế          |
| ---------------------------------------- | ----------------------------- |
| Số câu hỏi                            | 10 (quota `[3, 3, 2, 2]`) |
| Các `question_type`                    | `summary`, `authors`, `date`, `categories` |
| Ground-truth document ID                 | `ground_truth_doc_ids` = `paper_id` của tài liệu sinh câu hỏi |
| Embedding model                          | `all-MiniLM-L6-v2` |
| Vector store/collection                  | ChromaDB, cosine; `papers-baseline` / `papers-corrupted` / `papers-repaired` |
| Retrieval `top_k`                       | 4 |
| LLM provider/model                       | `mock` (offline) |
| Test set dùng chung cho ba trạng thái | `data/eval/test_set.json` (sinh 1 lần, `REFRESH_TEST_SET=0` tái sử dụng) |

Test set được giữ nguyên vì nếu đổi câu hỏi giữa các trạng thái thì chênh lệch metric không còn
phản ánh tác động của dữ liệu mà phản ánh độ khó của câu hỏi. Sampling có stride cố định trên
corpus đã sort theo `published` nên tái lập được.

## 7. Kết quả baseline

### Artifact checklist

| Artifact                 | Đường dẫn thực tế                | Trạng thái | Ghi chú   |
| ------------------------ | -------------------------------------- | ------------ | ---------- |
| Raw response/records     | `data/raw/`                          | Có | 24 bản ghi |
| Cleaned dataset          | `data/clean/`                        | Có | 24 dòng, 16 cột |
| Embedding manifest/index | `data/embeddings/`                   | Có | 3 manifest |
| Evaluation set           | `data/eval/`                         | Có | 10 câu |
| Baseline metrics         | `data/results/baseline_metrics.json` | Có | - |
| Quality/freshness        | `data/quality/`                      | Có | GX 1.x |
| Baseline report          | `data/reports/phase1_report.md`      | Có | - |

### Baseline metrics

| Metric                 |       Giá trị | Diễn giải                             |
| ---------------------- | --------------: | --------------------------------------- |
| `retrieval_hit_rate` |     1.0000 | 10/10 câu truy vấn tìm được đúng tài liệu đích |
| `mean_token_f1`      |     1.0000 | Câu trả lời khớp hoàn toàn ground truth (câu hỏi trích xuất từ metadata) |
| `judge_accuracy`     |     1.0000 | LLM Judge (fallback heuristic) đánh giá đúng 10/10 |
| `mean_judge_score`   |     5.0000 | Điểm tối đa |
| Ragas, nếu có        | N/A | Chưa chạy — cần `RUN_RAGAS=1`, tốn thời gian và cần LLM thật |

## 8. Data quality và freshness

### Quality checks

| Check        | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline      | Bằng chứng |
| ------------ | ----------------- | ------------------ | ----------------------- | ------------ |
| `ExpectTableRowCountToBeBetween` | Volume | 10 ≤ rows ≤ 100 | PASS (24) | `data/quality/baseline_quality_report.json` |
| `ExpectColumnValuesToNotBeNull[paper_id]` | Completeness | 0 null | PASS | nt |
| `ExpectColumnValuesToNotBeNull[title]` | Completeness | 0 null | PASS | nt |
| `ExpectColumnValuesToBeUnique[paper_id]` | Uniqueness | 0 trùng | PASS | nt |
| `ExpectColumnValueLengthsToBeBetween[summary]` | Validity | 40 ≤ len ≤ 4000 | PASS | nt |

### Freshness

| Thuộc tính               | Giá trị                           |
| -------------------------- | ----------------------------------- |
| Freshness được đo tại | `data/clean/papers_clean.json` (dataset sạch) |
| Timestamp mới nhất       | 2026-07-22 |
| Ngưỡng freshness         | 180 ngày, stale ratio ≤ 25% |
| Trạng thái baseline      | Fresh |
| Lý do                     | 1/24 dòng stale (4.17%), mean age 115.33 ngày — dưới ngưỡng 25% |

## 9. Corruption scenarios và repair

| Corruption         | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair   |
| ------------------ | ---------- | ---------------------: | ------------------------ | --------------------- | -------------- |
| `drop_latest_records` | Bỏ 20% bản ghi mới nhất | 5 | Giảm row count, mất tài liệu đích | Hit rate giảm mạnh | Rebuild từ raw snapshot |
| `blank_summary` | Xoá rỗng abstract | 5 | `ExpectColumnValueLengthsToBeBetween[summary]` FAIL | Mất ngữ nghĩa để retrieve | nt |
| `inject_noise` | Chèn lorem ipsum + token rác | 4 | Embedding nhiễu | Câu trả lời sai lệch | nt |
| `truncate_title` | Cắt tiêu đề còn 7 ký tự | 4 | Title < 8 ký tự | Truy vấn theo title thất bại | nt |
| `stale_date` | Lùi ngày 900 ngày | 6 | Freshness `is_fresh = False` | 7 dòng stale | nt |
| `duplicate_rows` | Nhân bản 15% dòng đầu | 3 | `ExpectColumnValuesToBeUnique[paper_id]` FAIL | Ghost vectors trong index | nt |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: Log ghi đủ 6 loại corruption, mỗi loại có `description`, `affected_rows` và danh sách
  `affected_paper_ids`; kèm `seed=42`, `original_rows=24`, `final_rows=22` nên tái lập được.

Repair lấy lại dữ liệu từ nguồn đáng tin cậy (`data/raw/crossref_records.json` — snapshot thô
bất biến) chứ không sửa trực tiếp dataframe bẩn. Vì repair đi qua đúng hàm
`build_clean_dataframe` như baseline, kết quả là **idempotent** (đã kiểm chứng: repair hai lần
cho dataframe bằng nhau, `repaired_df.equals(repaired_again) == True`).

## 10. So sánh baseline, corrupted và repaired

| Metric/signal            | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét   |
| ------------------------ | -------: | --------: | -------: | -----------------------: | --------------: | ------------ |
| `retrieval_hit_rate`   |     1.0000 |      0.6000 |     1.0000 |                      -0.4000 |             100% | Mất bản ghi + summary rỗng làm trượt 4/10 truy vấn |
| `mean_token_f1`        |     1.0000 |      0.7741 |     1.0000 |                      -0.2259 |             100% | Câu trả lời lệch so với ground truth |
| `judge_accuracy`       |     1.0000 |      0.8000 |     1.0000 |                      -0.2000 |             100% | 2 câu bị judge đánh giá sai |
| `mean_judge_score`     |     5.0000 |      4.0000 |     5.0000 |                      -1.0000 |             100% | Điểm trung bình giảm 1.0 |
| Quality checks pass/fail |     PASS |      FAIL |     PASS |              2 vi phạm |             100% | Unique + Length vi phạm rồi được khôi phục |
| Freshness status         |     Fresh |     Stale |     Fresh |     7 dòng stale / 22 |             100% | `is_fresh` True → False → True |

Hai kết luận có quan hệ nhân quả được hỗ trợ bởi artifacts:

1. **Corruption → quality signal → agent metric.** `blank_summary` + `inject_noise` (9 dòng) và
   `drop_latest_records` (5 dòng) → `ExpectColumnValueLengthsToBeBetween[summary]` FAIL và row count
   giảm → `retrieval_hit_rate` 1.0 → 0.6, `mean_token_f1` 1.0 → 0.7741.
   (`data/results/corruption_log.json`, `data/quality/corrupted_quality_report.json`,
   `data/results/corrupted_metrics.json`)
2. **Repair → quality recovery → metric recovery.** Self-healing rebuild 24 dòng từ raw snapshot →
   quality gate `success = True`, freshness `is_fresh = True` → cả 4 metric phục hồi về đúng baseline
   (`data/quality/self_healing_log.json`, `data/results/repaired_metrics.json`).

Không kết luận nào dựa trên số liệu không đổi: `retrieval_hit_rate` thực sự giảm 0.4 và
`judge_accuracy` giảm 0.2, đều vượt ngưỡng nhiễu 0 trên 10 mẫu.

## 11. Vấn đề tích hợp quan trọng

Ba lỗi tích hợp đã gặp và xử lý dứt điểm (không chỉ che bằng `try/except`):

**11.1 Test set cũ không khớp corpus sau khi raw snapshot thay đổi**

- **Triệu chứng:** `retrieval_hit_rate` sụp về `0.0` dù pipeline chạy exit code 0 và không có
  exception nào. Đây là silent failure điển hình.
- **Nguyên nhân:** `data/raw/crossref_records.json` được fetch lại và chứa bộ DOI mới, trong khi
  `data/eval/test_set.json` vẫn là test set sinh từ corpus cũ. Toàn bộ 10 `ground_truth_doc_ids`
  không còn tồn tại trong corpus, nên không truy vấn nào có thể "hit".
- **Cách xử lý:** Thêm `_test_set_matches_corpus()` trong `phase1.py` — kiểm tra mọi
  `ground_truth_doc_ids` phải resolve được trong corpus hiện tại; nếu không thì rebuild test set
  thay vì tái sử dụng.
- **Cách xác minh:** `tests/test_observability.py::test_stale_test_set_detected_when_corpus_drifts`;
  và log thực tế `[phase1] Cached test set does not match the current corpus; rebuilding.`

**11.2 Test set sinh câu hỏi có ground truth rỗng**

- **Triệu chứng:** 2/10 câu hỏi loại `categories` có `ground_truth` rỗng, khiến
  `mean_token_f1` và `judge_accuracy` giảm ngay trên dữ liệu sạch (0.8/0.8) dù không có corruption.
- **Nguyên nhân:** Bộ sinh test set lấy mẫu cứng theo 4 loại câu hỏi bất kể cột nguồn có dữ liệu
  hay không. Khi cột `categories_joined` rỗng, câu hỏi vẫn được sinh ra nhưng không thể trả lời đúng.
- **Cách xử lý:** `build_test_set()` chỉ sinh câu hỏi cho loại có cột nguồn không rỗng, dồn quota
  sang các loại còn trả lời được, và raise nếu một câu có ground truth rỗng.
- **Cách xác minh:**
  `tests/test_observability.py::test_test_set_skips_type_with_empty_source_column` và
  `::test_test_set_rejects_corpus_with_no_answerable_type`.

**11.3 Demo agent không chạy với provider `mock`**

- **Triệu chứng:** `[demo] Agent demo skipped: NotImplementedError:` khi chạy `script/run_phase1.py`.
- **Nguyên nhân:** Không phải `create_agent` bị thiếu — API này **có** trong `langchain 1.3.4`.
  Nguyên nhân thật là `create_agent` gọi `bind_tools()` trên model, nhưng `FakeListChatModel`
  (provider `mock`) không cài đặt `bind_tools` nên ném `NotImplementedError` từ lớp cơ sở.
- **Cách xử lý:** Thêm `_ToolCapableFakeChatModel` trong `src/retrieval/llm.py` — lớp con của
  `GenericFakeChatModel` có `bind_tools()` trả về chính nó, đủ để chạy trọn vòng tool-calling
  offline mà không cần API key. Đồng thời sửa `_judge_answer()` để fallback heuristic khi provider
  trả về `None` thay vì raise (trước đó gây `AttributeError: 'NoneType' object has no attribute
  'model_dump'`).
- **Cách xác minh:** `tests/test_retrieval.py::test_mock_llm_supports_tool_binding`; và log thực tế
  in ra `[demo] Q: ... A: This is a mock response from the scholarly corpus.` thay vì skip.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng   | Hướng cải thiện có thể kiểm chứng |
| --------------------- | -------------- | ----------------------------------------- |
| LLM provider = `mock` | Câu trả lời sinh theo template trích xuất metadata, không kiểm chứng được năng lực suy luận LLM thật | Đặt `LLM_PROVIDER=gemini` + `GOOGLE_API_KEY`, so sánh `judge_accuracy` trước/sau |
| Ragas bị tắt mặc định | Thiếu chỉ số ngữ nghĩa (faithfulness, context precision) | Chạy `RUN_RAGAS=1` và ghi kết quả vào `baseline_metrics.json` |
| Corpus chỉ 24 tài liệu | Metric dễ đạt trần 1.0, khó thấy suy giảm tinh tế | Tăng `max_results` lên 100+ và đo lại độ nhạy của corruption |
| Raw snapshot là nguồn sống | Fetch lại có thể đổi DOI khiến test set cũ hết hiệu lực | Đã xử lý bằng `_test_set_matches_corpus()`; có thể bổ sung ghi hash corpus vào test set |

## 13. Checklist trước khi nộp

- [x] Thông tin nhóm và repository chính xác.
- [x] Phân công khớp với module, artifact và kết quả thực tế.
- [x] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [x] Baseline, corrupted và repaired dùng cùng evaluation set.
- [x] Bảng metrics khớp với các file trong `data/results/`.
- [x] Quality/freshness conclusions khớp với `data/quality/`.
- [x] Các đường dẫn báo cáo và artifact truy cập được.
- [x] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [x] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
