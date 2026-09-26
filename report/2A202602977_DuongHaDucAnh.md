# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Dương Hà Đức Anh |
| MSSV | 2A202602977 |
| Khóa/Lớp | K4 — L3B |
| Tên nhóm | soopi |
| Vai trò chính | RAG & Vector Index |
| Repository | https://github.com/meth04/K4-L3B-DAY10-soopi-DataPipelineDataObservability |
| Ngày hoàn thành | 2026-09-26 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Sinh embedding | `src/retrieval/embeddings.py`, `MiniLMEmbeddings` | Văn bản `text_for_embedding` và tên model | Vector embedding của tài liệu và câu truy vấn | Hoàn thành theo artifact và pipeline hiện có |
| Vector index và truy vấn | `src/retrieval/index.py`, `LocalEmbeddingIndex` | Clean dataframe, settings và đường dẫn lưu | Ba collection ChromaDB, metadata, manifest, kết quả search/lookup | Hoàn thành theo artifact và pipeline hiện có |
| RAG retrieval evaluation | `src/evaluation/metrics.py`, phối hợp với pipeline | Test set, index và ground-truth document IDs | Hit rate, Token F1 và các metric QA | Hoàn thành theo kết quả baseline/corruption/repair đã lưu |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Đồng bộ schema và metadata | Ingestion, cleaning và pipeline | Index nhận `paper_id`, `title`, `published`, `authors_joined`, `categories_joined`, `summary`, `abs_url` và `pdf_url` để truy vấn/hiển thị nguồn |
| Kiểm tra so sánh ba trạng thái | Pipeline và evaluation | Các metric baseline, corrupted và repaired được lưu riêng để đối chiếu trên cùng test set |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Tạo nội dung và metadata cho từng tài liệu index | `src/retrieval/index.py::_build_documents` | 24 tài liệu sạch, mỗi tài liệu có ID ổn định dạng `paper_id::index` và metadata truy vấn | `data/embeddings/papers_embeddings.json`, `data/clean/papers_clean.json` |
| Sinh embedding và lưu index ChromaDB | `src/retrieval/embeddings.py`, `src/retrieval/index.py::build` | ChromaDB persistent index; manifest cho baseline, corrupted và repaired | `data/chroma/chroma.sqlite3`, các file `data/embeddings/papers_embeddings*.json` |
| Hỗ trợ truy vấn top-k và tra cứu tài liệu | `src/retrieval/index.py::search`, `lookup` | Kết quả có paper ID, title, content, metadata và similarity score | `data/results/*_answers.json`, `data/results/*_metrics.json` |
| Đối chiếu ảnh hưởng đến chất lượng RAG | `data/results/*_metrics.json`, `data/reports/corruption_report.md` | Hit rate `1.0 → 0.6 → 1.0`; Token F1 `1.0 → 0.7741 → 1.0` | So sánh JSON metrics và bảng trong báo cáo |

Output tiêu biểu là ba trạng thái index độc lập (`papers-baseline`, `papers-corrupted`, `papers-repaired`) cùng bảng metric cho thấy truy xuất giảm trên dữ liệu lỗi rồi phục hồi sau repair.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

RAG cần biến tài liệu thành vector để tìm các đoạn liên quan đến câu hỏi. Index cũng phải giữ metadata để biết vector thuộc bài báo nào và trả nguồn có thể truy vết. Khi dữ liệu bị corruption, cần đo retrieval trên index mới mà không làm lẫn dữ liệu với collection baseline.

### Cách triển khai

`MiniLMEmbeddings` dùng `sentence-transformers/all-MiniLM-L6-v2`, chuẩn hóa vector khi encode cả documents và query. `LocalEmbeddingIndex._build_documents` tạo record ID từ `paper_id` và vị trí dòng, dùng `text_for_embedding` làm nội dung embedding, đồng thời lưu metadata bài báo. `build()` tạo ChromaDB persistent collection với cosine distance và ghi manifest mô tả collection cùng các tài liệu. Tên collection được suy ra từ output path, giúp baseline, corrupted và repaired được lưu riêng.

Khi tìm kiếm, `search()` embed câu hỏi, gọi ChromaDB với `top_k`, rồi đổi distance thành score `1 - distance`. `lookup()` tra cứu nhanh theo paper ID hoặc title đã chuẩn hóa chữ thường.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Dataframe sạch có `paper_id`, `title`, `published`, `authors_joined`, `categories_joined`, `summary`, `text_for_embedding`, `abs_url`, `pdf_url` |
| Output | Collection ChromaDB, manifest JSON và danh sách `SearchResult` |
| Module phụ thuộc | `src/ingestion/cleaning.py`, `src/core/config.py`, `src/retrieval/embeddings.py`, ChromaDB |
| Module sử dụng output | `src/evaluation/metrics.py`, `src/retrieval/qa.py`, các pipeline trong `src/pipelines/` |
| Điều kiện lỗi cần xử lý | Corpus rỗng hoặc thiếu cột bắt buộc; collection chưa tồn tại khi load; manifest trỏ tới đường dẫn persist không có trên máy hiện tại |

### Cách xác minh

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** Pipeline tạo index baseline, corrupted, repaired và metric tương ứng.
- **Kết quả trong artifact hiện có:** 24 dòng clean; baseline và repaired có `retrieval_hit_rate = 1.0`, corrupted có `0.6`.
- **Artifact/log:** `data/chroma/`, `data/embeddings/`, `data/results/*_metrics.json`, `data/reports/corruption_report.md`.
- **Giới hạn xác minh:** Báo cáo này đối chiếu artifact đang có trong repo; các lệnh trên cần được chạy lại trên máy nộp để xác nhận môi trường hiện tại.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần so sánh kết quả retrieval giữa dữ liệu sạch, dữ liệu lỗi và dữ liệu đã repair.
- **Các phương án đã cân nhắc:** Dùng một collection rồi ghi đè mỗi lần chạy; hoặc lưu mỗi trạng thái trong collection riêng.
- **Phương án đã chọn:** Ba collection ChromaDB persistent riêng, tên lần lượt là `papers-baseline`, `papers-corrupted`, `papers-repaired`.
- **Lý do:** Tách collection giúp tránh dữ liệu của lần chạy trước lẫn vào lần sau, đồng thời thuận tiện tái dựng và so sánh. Chi phí là cần thêm dung lượng lưu trữ.
- **Bằng chứng:** Ba manifest embedding và ba bộ metrics riêng trong `data/embeddings/` và `data/results/`.

## 6. Một lỗi hoặc blocker đã xử lý

Trong lúc rà soát artifact, manifest `data/embeddings/papers_embeddings.json` đang ghi `persist_path` là đường dẫn tuyệt đối thuộc một máy Windows khác (`C:\Users\...`). `LocalEmbeddingIndex.load()` đọc trực tiếp đường dẫn này. Vì vậy, load index từ manifest có thể lỗi trên máy khác dù file ChromaDB đã có trong repo.

- **Nguyên nhân:** Manifest được tạo trên máy khác và chứa đường dẫn tuyệt đối.
- **Trạng thái:** Đây là blocker portability được phát hiện khi rà soát; chưa có bằng chứng manifest baseline đã được tái sinh trên máy nộp.
- **Bước tiếp theo:** Chạy lại `python script/run_phase1.py` và `python script/run_corruption_flow.py` trong workspace nộp để sinh manifest theo cấu hình hiện tại, sau đó thử load index từ manifest. Có thể cải thiện lâu dài bằng cách lưu đường dẫn tương đối hoặc luôn lấy `settings.paths.chroma_dir` khi load.
- **Điều học được:** Artifact vector database cần được kiểm tra cùng metadata/manifest của nó; đường dẫn tuyệt đối làm giảm tính tái lập khi chuyển máy.

## 7. Hiểu biết về luồng end-to-end

1. Raw records Crossref được cleaning và ghép thành `text_for_embedding`; MiniLM biến từng văn bản thành vector, ChromaDB lưu vector cùng metadata để truy vấn.
2. Mỗi câu hỏi test có ground-truth document IDs. Evaluation tìm top-k tài liệu và kiểm tra có tài liệu đích hay không; câu trả lời tiếp tục được so với ground truth bằng Token F1 và các metric QA.
3. Quality checks kiểm tra schema/nội dung như số dòng, null, uniqueness và độ dài summary. Freshness theo dõi tuổi bài báo và tỷ lệ bản ghi vượt ngưỡng 180 ngày.
4. Cùng test set giữ phép so sánh công bằng: metric thay đổi phản ánh khác biệt của corpus/index thay vì bộ câu hỏi khác nhau.
5. Repair thành công khi dữ liệu dựng lại từ raw qua quality gate đạt, collection repaired được tạo lại và metric trở về gần hoặc bằng baseline. Artifact hiện có ghi quality `True → False → True` và hit rate `1.0 → 0.6 → 1.0`.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.6000 | 1.0000 | Corruption làm mất hoặc giảm khả năng tìm tài liệu đích; repair khôi phục trong bộ artifact hiện có. |
| `mean_token_f1` | 1.0000 | 0.7741 | 1.0000 | Nội dung retrieval kém liên quan làm câu trả lời lệch ground truth hơn. |
| `judge_accuracy` | 1.0000 | 0.8000 | 1.0000 | Tỷ lệ câu trả lời được đánh giá đúng giảm trên corpus lỗi. |
| `mean_judge_score` | 5 | 4 | 5 | Điểm trung bình giảm một điểm rồi trở lại mức baseline. |
| Quality checks | True | False | True | Gate bắt được dữ liệu corrupted và pass lại sau repair. |
| Freshness status | True | False | True | Dữ liệu stale làm freshness SLA fail trước khi được khôi phục. |

### Kết luận từ số liệu

1. **Corruption** (summary rỗng/nhiễu, title bị cắt, ngày stale và duplicate) → quality gate fail, stale rows tăng lên 7 → hit rate giảm từ 1.0 xuống 0.6 và Token F1 từ 1.0 xuống 0.7741.
2. **Repair từ raw snapshot** → quality gate và freshness trở lại `True` → hit rate, Token F1 và judge accuracy trong artifact đều trở về baseline.

`drop_latest_records` ảnh hưởng trực tiếp đến khả năng tìm các tài liệu mới nhất; blank/noisy summary và title bị cắt làm giảm chất lượng nội dung được embed. Bộ corruption tiêm nhiều lỗi cùng lúc nên không thể quy toàn bộ mức giảm cho riêng một lỗi chỉ dựa trên metrics tổng hợp.

Metric Ragas trong các JSON hiện ghi nhận bị bỏ qua trừ khi bật `RUN_RAGAS=1`; vì vậy các kết luận ở đây dựa trên hit rate, Token F1 và judge metrics đã lưu.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Embedding chỉ hữu ích khi document text có cấu trúc tốt và metadata đủ để truy vết nguồn.
2. Tách collection theo trạng thái giúp thí nghiệm corruption/recovery có thể lặp lại và đối chiếu rõ ràng.
3. Retrieval metric có thể suy giảm dù pipeline vẫn chạy; cần đọc cùng quality/freshness signals để phát hiện silent failure.

### Nếu có thêm thời gian

Thêm kiểm tra tự động cho manifest để từ chối hoặc sửa đường dẫn persist không tồn tại, rồi kiểm tra load/search sau khi chuyển workspace. Đo bằng cách tạo manifest trên một thư mục tạm, load lại index và xác nhận query trả đúng paper ID mà không phụ thuộc đường dẫn tuyệt đối.

## 10. Cam kết của thành viên

- [X] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [X] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [X] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [X] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [X] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [X] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Dương Hà Đức Anh

**Ngày xác nhận:** 2026-09-26
