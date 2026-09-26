# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Họ và tên       | Nguyễn Văn Thân        |
| MSSV               | 2A202602859                 |
| Khóa/Lớp         | K4                        |
| Tên nhóm         | soopi                     |
| Vai trò chính    | Pipeline Integrator (orchestration & reproducibility) |
| Repository         | https://github.com/meth04/K4-L3B-DAY10-soopi-DataPipelineDataObservability |
| Ngày hoàn thành | 2026-09-26                |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao  | Trạng thái |
| ------------------ | --------------------- | ---------------- | ----------------- | ------------ |
| Cấu hình & đường dẫn | `src/core/config.py`, `src/core/utils.py` | Biến môi trường `.env` | `Settings`, `Paths` dùng chung toàn pipeline | Hoàn thành |
| Baseline orchestration | `src/pipelines/phase1.py` (`main`) | Raw records + settings | `baseline_metrics.json`, `phase1_report.md`, clean/chroma/eval artifacts | Hoàn thành |
| Corruption & repair orchestration | `src/pipelines/corruption_flow.py` (`main`) | Baseline metrics + raw snapshot | `corrupted_metrics.json`, `repaired_metrics.json`, `corruption_report.md` | Hoàn thành |
| Self-healing guardrail | `src/observability/self_healing.py` (`auto_heal`) | Dataframe + settings | `self_healing_log.json`, dataframe đã phục hồi | Hoàn thành |
| Dashboard observability | `src/observability/dashboard.py`, `script/run_dashboard.py` | Các file trong `data/` | `observability_dashboard.html` | Hoàn thành |
| Bộ test + CI | `tests/`, `.github/workflows/ci.yml` | Code pipeline | 26 test pass, CI chạy 2 pipeline | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                         | Thành viên/module được hỗ trợ | Kết quả                    |
| ------------------------------------ | ------------------------------------ | ---------------------------- |
| Debug tích hợp GX 1.x | Module Observability | Xác nhận API 1.x (`add_pandas` → `add_dataframe_asset` → `add_batch_definition_whole_dataframe`) chạy đúng, 5/5 expectations pass trên dữ liệu sạch |
| Kiểm tra secret & hardcoded path | Cả nhóm | Không phát hiện secret trong source/report/log; `.env` không bị track; không có đường dẫn tuyệt đối hardcode |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao       | Cách xác minh         |
| --------------------------- | ----------------------------- | ------------------------- | ----------------------- |
| Ghép 2 pipeline end-to-end | `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` | 2 script chạy exit code 0 | `uv run python script/run_phase1.py` |
| Thiết kế repair idempotent | `corruption_flow.py` (bước 6), `self_healing.py` | `repaired_df.equals(repaired_again) == True` | Log `[corruption] Repair idempotent: True` |
| Đảm bảo 3 trạng thái dùng chung test set | `phase1.py::_load_or_build_test_set` | 1 file `data/eval/test_set.json` dùng cho cả 3 lần evaluate | So sánh `ground_truth_doc_ids` trong 3 file `*_answers.json` |
| Xây dashboard + test suite | `observability/dashboard.py`, `tests/` | `observability_dashboard.html`, 26 test pass | `uv run pytest tests -q` |

Output cụ thể mà phần việc của tôi tạo ra: bảng đối chiếu 3 trạng thái trong
`data/reports/corruption_report.md` — chứng minh `retrieval_hit_rate` 1.0 → 0.6 → 1.0 và
`mean_token_f1` 1.0 → 0.7741 → 1.0, tức corruption thực sự gây suy giảm và repair phục hồi 100%.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Ghép các module rời (ingestion, cleaning, index, evaluation, observability) thành một luồng chạy
được end-to-end, đảm bảo thứ tự phụ thuộc đúng và mọi kết luận trong báo cáo đều truy vết được về
một artifact thực tế. Đồng thời phải chứng minh repair là **idempotent** chứ không chỉ "chạy lại
thấy số đẹp".

### Cách triển khai

1. **Thứ tự phụ thuộc cứng trong `phase1.py`:** ingest → clean → build index → build/reuse test set
   → evaluate → quality gate → report. Nếu clean ra dataframe rỗng thì raise ngay, không để lỗi
   lan sang bước index.
2. **Test set dùng chung:** `_load_or_build_test_set` chỉ sinh test set khi `REFRESH_TEST_SET=1`
   hoặc file chưa tồn tại. Nhờ vậy corrupted/repaired evaluate trên đúng câu hỏi của baseline —
   điều kiện bắt buộc để phép so sánh có nghĩa.
3. **Repair idempotent:** `corruption_flow.py` không sửa dataframe bẩn. Nó đọc lại
   `data/raw/crossref_records.json` (snapshot thô bất biến) và chạy lại đúng hàm
   `build_clean_dataframe` như baseline. Vì hàm này là pure function của (records, run_date), chạy
   hai lần cho kết quả bằng nhau — tôi verify trực tiếp bằng `repaired_df.equals(repaired_again)`.
4. **Self-healing thay vì repair mù:** `auto_heal()` chạy quality gate trên dữ liệu hiện tại trước;
   chỉ khi gate fail mới rebuild. Sau rebuild nó **validate lại** và chỉ báo thành công nếu gate
   pass. Nếu không, trả về dataframe gốc kèm log thất bại để không che giấu sự cố.
5. **Chống silent failure ở tầng test set:** `_test_set_matches_corpus()` kiểm tra mọi
   `ground_truth_doc_ids` còn resolve được trong corpus hiện tại. Nếu raw snapshot được fetch lại
   và đổi DOI, test set cũ sẽ khiến `retrieval_hit_rate` sụp về 0.0 mà **không có exception nào**.
   Hàm này biến lỗi im lặng đó thành một lần rebuild tường minh.
6. **Demo agent chạy được offline:** thêm `_ToolCapableFakeChatModel` để provider `mock` hỗ trợ
   `bind_tools()`, nhờ đó `create_agent` chạy trọn vòng tool-calling mà không cần API key.

### Input, output và contract

| Thành phần                   | Mô tả                                     |
| ------------------------------ | ------------------------------------------- |
| Input                          | `data/raw/crossref_records.json`, `.env` (`LLM_PROVIDER`, `REFRESH_*`) |
| Output                         | `data/results/*_metrics.json`, `data/quality/*.json`, `data/reports/*.md` |
| Module phụ thuộc             | `ingestion.*`, `retrieval.index`, `evaluation.*`, `observability.*` |
| Module sử dụng output        | `observability.dashboard`, `observability.reporting` |
| Điều kiện lỗi cần xử lý | Mất mạng (fallback snapshot), baseline chưa chạy (raise rõ ràng), clean rỗng (raise), LLM demo lỗi (skip) |

### Cách xác minh

```bash
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
uv run python script/run_dashboard.py
uv run pytest tests -q
```

- **Kết quả mong đợi:** cả 2 pipeline exit code 0, sinh đủ artifacts, test pass.
- **Kết quả thực tế:** baseline `hit_rate=1.0`, corrupted `0.6`, repaired `1.0`; 26 test pass;
  dashboard ghi ra `data/reports/observability_dashboard.html`.
- **Artifact/log:** `data/reports/corruption_report.md`, `data/results/corruption_log.json`,
  `data/quality/self_healing_log.json` (không chứa secret).

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Làm sao để repair chứng minh được là "phục hồi thật" chứ không phải sửa số liệu?
- **Các phương án đã cân nhắc:**
  1. Sửa trực tiếp dataframe bẩn (khôi phục các dòng bị corruption tại chỗ).
  2. Rebuild toàn bộ từ raw snapshot qua đúng cleaning path của baseline.
- **Phương án đã chọn:** Phương án 2.
- **Lý do:** Phương án 1 chỉ che triệu chứng — nếu corruption làm hỏng cấu trúc thì không thể khôi
  phục chính xác, và không chứng minh được tính idempotent. Phương án 2 dùng raw snapshot làm
  nguồn chân lý duy nhất (single source of truth), nên kết quả tái lập được và verify được bằng
  phép so sánh dataframe.
- **Bằng chứng quyết định phù hợp:** `repaired_df.equals(repaired_again) == True`; quality gate
  trên repaired data `success = True`; cả 4 metric phục hồi về đúng baseline.

## 6. Một lỗi hoặc blocker đã xử lý

**Lỗi nghiêm trọng nhất: test set cũ không khớp corpus làm hit rate sụp về 0.0 trong im lặng.**

- **Triệu chứng:** `[phase1] Baseline metrics: {'retrieval_hit_rate': 0.0, 'mean_token_f1':
  0.00625, 'judge_accuracy': 0.0}` — pipeline vẫn exit code 0, **không có exception nào**.
- **Lệnh tái hiện:** `uv run python script/run_phase1.py` sau khi `data/raw/crossref_records.json`
  được fetch lại.
- **Nguyên nhân gốc:** `data/raw/crossref_records.json` chứa bộ DOI mới (ví dụ
  `10.47576/2949-1894.2026.7.7.023`), nhưng `data/eval/test_set.json` vẫn là test set sinh từ
  corpus cũ (`10.1145/3637528.*`). Kiểm tra bằng script cho thấy **10/10** `ground_truth_doc_ids`
  không còn tồn tại trong corpus, nên không truy vấn nào có thể "hit". Hàm `_load_or_build_test_set`
  cũ chỉ kiểm tra `path.exists()`, nên đã tái sử dụng test set mất hiệu lực.
- **Cách xử lý:** Thêm `_test_set_matches_corpus()` — mọi `ground_truth_doc_ids` phải resolve được
  trong corpus hiện tại (so khớp theo DOI gốc, bỏ hậu tố `::index`); nếu không thì rebuild test set
  và in log tường minh thay vì tái sử dụng.
- **Cách xác minh sau khi sửa:** log in `[phase1] Cached test set does not match the current
  corpus; rebuilding.` và baseline trở lại `retrieval_hit_rate = 1.0`. Có regression test
  `tests/test_observability.py::test_stale_test_set_detected_when_corpus_drifts`.
- **Điều học được:** Đây là bài học đắt nhất của phần việc tôi phụ trách. Metric sụp về 0.0 mà
  pipeline vẫn "thành công" là dạng lỗi nguy hiểm nhất — nếu tôi chỉ nhìn exit code và dòng
  `Baseline pipeline complete.` thì đã bỏ qua. **Một metric bất thường phải được truy vết đến
  artifact, không được chấp nhận chỉ vì pipeline không crash.**

**Hai lỗi thứ cấp đã xử lý cùng lúc:**

- **Test set sinh câu hỏi ground truth rỗng:** 2/10 câu loại `categories` có `ground_truth` rỗng
  làm `mean_token_f1`/`judge_accuracy` giảm ngay trên dữ liệu sạch (0.8/0.8). Nguyên nhân: bộ sinh
  lấy mẫu cứng theo 4 loại câu hỏi bất kể cột nguồn có dữ liệu hay không. Đã sửa: chỉ sinh câu hỏi
  cho loại có cột nguồn không rỗng, dồn quota sang loại còn trả lời được, và raise nếu ground truth
  rỗng. Verify: `test_test_set_skips_type_with_empty_source_column`.
- **Demo agent không chạy với provider `mock`:** `[demo] Agent demo skipped: NotImplementedError:`.
  Nguyên nhân **không phải** `create_agent` bị thiếu (API này có trong `langchain 1.3.4` — tôi đã
  kiểm chứng trực tiếp), mà là `create_agent` gọi `bind_tools()` còn `FakeListChatModel` không cài
  đặt phương thức này. Đã sửa bằng `_ToolCapableFakeChatModel` (con của `GenericFakeChatModel`).
  Kèm theo đó, sửa `_judge_answer()` để fallback heuristic khi provider trả `None` thay vì để lộ
  `AttributeError: 'NoneType' object has no attribute 'model_dump'`. Verify:
  `test_mock_llm_supports_tool_binding`.

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?** `fetch_source_records` gọi Crossref
   (hoặc đọc snapshot offline), lưu `crossref_response.json` rồi parse thành `PaperRecord` và lưu
   `crossref_records.json`. `build_clean_dataframe` chuẩn hoá text, strip JATS, tính `age_days`,
   dedup theo `paper_id` và ghép `text_for_embedding` 5 phần. `LocalEmbeddingIndex.build` encode
   text bằng MiniLM-L6-v2, tạo collection ChromaDB với cosine và ghi manifest embedding.
2. **Evaluation set và ground-truth document IDs dùng để đo gì?** `test_set.json` gồm 10 câu hỏi,
   mỗi câu có `ground_truth` (đáp án đúng) và `ground_truth_doc_ids` (paper_id của tài liệu sinh
   câu hỏi). `retrieval_hit_rate` đo tỷ lệ câu mà danh sách `retrieved_doc_ids` chứa ít nhất một
   `ground_truth_doc_ids` → đo chất lượng **retrieval**. `mean_token_f1` và judge score so sánh
   `answer` với `ground_truth` → đo chất lượng **câu trả lời**.
3. **Quality checks khác freshness monitoring ở điểm nào?** Quality checks (GX 1.x) kiểm tra tính
   chất của dữ liệu *tại thời điểm hiện tại*: đủ số dòng, không null, không trùng, độ dài hợp lệ.
   Freshness monitoring chỉ quan tâm *độ mới* của dữ liệu theo thời gian: đếm tỷ lệ dòng có
   `age_days > 180` và cảnh báo nếu vượt 25%. Một dataset có thể pass toàn bộ quality checks nhưng
   vẫn stale (dữ liệu sạch nhưng cũ), và ngược lại.
4. **Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?** Vì biến duy nhất được
   phép thay đổi giữa 3 lần đo là **dữ liệu**. Nếu đổi câu hỏi, chênh lệch metric có thể do câu hỏi
   khó/dễ hơn chứ không phải do corruption, và kết luận nhân quả sẽ sai.
5. **Repair được xem là thành công dựa trên artifact và metric nào?** Ba tầng: (a) quality gate
   trên repaired data `success = True` trong `data/quality/repaired_quality_report.json`;
   (b) freshness `is_fresh = True`; (c) các metric trong `data/results/repaired_metrics.json` quay
   về bằng baseline (`retrieval_hit_rate = 1.0`, `mean_token_f1 = 1.0`). Ngoài ra
   `self_healing_log.json` ghi lại `healthy_before=False → repaired=True → healthy_after=True`.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal          | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| ---------------------- | -------: | --------: | -------: | ------------------------- |
| `retrieval_hit_rate` |     1.0000 |      0.6000 |     1.0000 | Giảm 0.40 — mất 5 bản ghi mới nhất khiến 4/10 truy vấn không còn tài liệu đích trong corpus |
| `mean_token_f1`      |     1.0000 |      0.7741 |     1.0000 | Giảm 0.226 — summary bị blank/noise làm câu trả lời lệch ground truth |
| `judge_accuracy`     |     1.0000 |      0.8000 |     1.0000 | Giảm 0.20 — 2 câu bị đánh giá sai |
| `mean_judge_score`   |     5.0000 |      4.0000 |     5.0000 | Giảm 1.00 |
| Quality checks         |     PASS |      FAIL |     PASS | 2 vi phạm: unique `paper_id` (6) và độ dài `summary` (6) |
| Freshness status       |     Fresh |     Stale |     Fresh | 7/22 dòng stale (31.8%) > ngưỡng 25% |

### Kết luận từ số liệu

1. **Corruption → quality signal → agent metric.** `drop_latest_records` (5 dòng) +
   `blank_summary`/`inject_noise` (9 dòng) → `ExpectColumnValueLengthsToBeBetween[summary]` FAIL,
   row count 24 → 22 → `retrieval_hit_rate` 1.0 → 0.6 và `mean_token_f1` 1.0 → 0.7741.
2. **Repair → quality recovery → metric recovery.** Self-healing rebuild 24 dòng từ raw snapshot →
   gate `success = True` + freshness `is_fresh = True` → cả 4 metric về đúng mức baseline.

**Corruption nào ảnh hưởng rõ nhất?** `drop_latest_records` — vì đây là mất mát *không thể phục
hồi bằng retrieval thông minh*: tài liệu đích đơn giản là không còn trong index, nên hit rate
giảm trực tiếp. Các corruption khác (noise, blank) chỉ làm giảm chất lượng ngữ nghĩa nên suy giảm
mượt hơn (Token F1 giảm 0.226 so với hit rate giảm 0.40).

**Kết quả khác kỳ vọng?** Baseline đạt trần 1.0 ở cả 4 metric — ban đầu tôi kỳ vọng có nhiễu. Giả
thuyết: vì `LLM_PROVIDER=mock` nên câu trả lời được trích xuất trực tiếp từ metadata của tài liệu
đúng, và test set cũng sinh từ chính metadata đó, nên khớp hoàn hảo. Đã kiểm tra bằng cách đọc
`data/results/baseline_answers.json`: `answer` đúng bằng `ground_truth` từng ký tự. Điều này cũng
giải thích vì sao corruption lại gây suy giảm rõ — khi metadata bị hỏng, câu trả lời hỏng ngay.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. **Về data pipeline:** Snapshot thô bất biến (`data/raw/`) là tài sản quan trọng nhất — nhờ nó
   mà repair có thể idempotent và tái lập được, thay vì phụ thuộc vào việc "sửa lại dữ liệu bẩn".
2. **Về data quality/observability:** Quality gate và freshness bắt được hai loại lỗi khác nhau và
   cả hai đều cần thiết. Trong bài này, `stale_date` không vi phạm expectation nào về null/unique/
   length — nếu chỉ có GX mà không có freshness SLA thì corruption đó sẽ lọt hoàn toàn.
3. **Về ảnh hưởng của data đến RAG agent:** Corruption gây **silent failure** — pipeline vẫn chạy
   exit code 0, không exception nào, nhưng chất lượng câu trả lời giảm thật. Không có observability
   thì nhóm sẽ không biết hệ thống đang trả lời sai.

### Nếu có thêm thời gian

Chạy evaluation với LLM provider thật (`gemini`) thay vì `mock`, và so sánh `judge_accuracy` giữa
hai chế độ. Lý do: hiện tại baseline đạt trần 1.0 vì câu trả lời mock được trích xuất trực tiếp từ
metadata, nên chưa đo được năng lực suy luận thực sự của agent. Cách đo cải thiện: dùng cùng test
set, đặt `LLM_PROVIDER=gemini`, ghi lại `judge_accuracy` và `mean_judge_score` mới vào
`data/results/`, rồi so sánh với baseline mock.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Văn Thân
**Ngày xác nhận:** 2026-09-26
