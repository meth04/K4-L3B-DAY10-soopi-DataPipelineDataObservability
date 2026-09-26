# K4-L3B-Day10 — Data Pipeline & Data Observability for RAG

> **Hình thức:** Teamwork | **Thời lượng:** 240 phút  
> **Lịch học (Lớp B - Ca Sáng):** Thứ 7 (26/09/2026) 09:00 – 13:00  
> ⏰ **Hạn nộp LMS:** 23:59:59 cùng ngày

---

## 🧭 Đọc gì, theo thứ tự nào?

| # | Tài liệu | Mô tả |
|:---:|---|---|
| 1️⃣ | **Codelab trên VLearn LMS** | Hướng dẫn từng bước + nộp bài (mở trên trình duyệt) |
| 2️⃣ | [CHECKPOINTS.md](docs/CHECKPOINTS.md) | Phân bổ thời gian 240 phút & deliverables từng mốc |
| 3️⃣ | [RUBRIC.md](docs/RUBRIC.md) | Tiêu chí chấm điểm (100 chuẩn + 10 bonus) |
| 4️⃣ | [SUBMISSION.md](docs/SUBMISSION.md) | Nội quy, deadline, bảo mật & checklist nộp bài |
| 5️⃣ | [TEAM.md](docs/TEAM.md) | Điền thông tin nhóm & báo cáo cá nhân |

---

## 🚀 Cài đặt & Chạy

```bash
uv sync                       # hoặc: python -m pip install -e ".[dev]"
cp .env.example .env          # điền API key nếu dùng provider thật (mặc định: mock)

uv run python script/run_phase1.py            # Baseline pipeline
uv run python script/run_corruption_flow.py   # Corruption → Repair → So sánh
uv run python script/run_dashboard.py         # Sinh dashboard HTML (bonus B1)
uv run pytest tests -q                        # Bộ test tự động (bonus B3)
```

> Mặc định `LLM_PROVIDER=mock` để chạy offline hoàn toàn, không cần API key.

---

## 🏗️ Kiến trúc luồng dữ liệu

```text
Crossref API (hoặc snapshot offline)
    → src/ingestion/crossref.py      raw response + raw records
    → src/ingestion/cleaning.py      cleaned dataframe + text_for_embedding + age_days
    → src/retrieval/index.py         ChromaDB + MiniLM embeddings
    → src/evaluation/                test set 10 câu + Hit Rate / Token F1 / LLM Judge
    → src/observability/quality.py   Great Expectations 1.x + Freshness SLA
    → src/ingestion/corruption.py    6 kịch bản làm bẩn dữ liệu
    → src/observability/self_healing.py  tự động phát hiện & phục hồi
    → src/observability/reporting.py báo cáo 3 trạng thái
```

---

## 📦 Artifacts sinh ra

| Đường dẫn | Nội dung |
|---|---|
| `data/raw/` | `crossref_response.json`, `crossref_records.json` |
| `data/clean/` | `papers_clean.{csv,json}` + biến thể corrupted/repaired |
| `data/chroma/` | 3 collection: `papers-baseline`, `papers-corrupted`, `papers-repaired` |
| `data/eval/` | `test_set.json` (10 câu hỏi / 4 nhóm nghiệp vụ) |
| `data/quality/` | Báo cáo GX 1.x, freshness, self-healing log |
| `data/results/` | `baseline_metrics.json`, `corrupted_metrics.json`, `repaired_metrics.json`, `corruption_log.json` |
| `data/reports/` | `phase1_report.md`, `corruption_report.md`, `observability_dashboard.html` |

---

## 🎁 Tính năng vượt chuẩn (Bonus)

- **B1 — Dashboard:** `script/run_dashboard.py` sinh `data/reports/observability_dashboard.html`
  (trạng thái quality gate, biểu đồ freshness, so sánh 3 trạng thái, log corruption & self-healing).
- **B2 — Self-healing:** `src/observability/self_healing.py` tự phát hiện vi phạm quality gate và
  tự động repair idempotent từ raw snapshot, ghi log kiểm chứng.
- **B3 — Test suite + CI:** `tests/` (pytest) + `.github/workflows/ci.yml` chạy test và cả hai
  pipeline end-to-end trên mỗi lần push.

---

## 📁 Cấu trúc repo

```text
├── data/            # artifacts (raw → clean → results → reports)
├── docs/            # CHECKPOINTS, RUBRIC, SUBMISSION, TEAM
├── report/          # group_report.md + báo cáo cá nhân
├── script/          # run_phase1.py, run_corruption_flow.py, run_dashboard.py
├── src/
│   ├── core/            # config, utils
│   ├── ingestion/       # crossref, cleaning, corruption
│   ├── retrieval/       # embeddings, index, qa, agent, llm
│   ├── evaluation/      # metrics, testset
│   ├── observability/   # quality, reporting, self_healing, dashboard
│   └── pipelines/       # phase1, corruption_flow
└── tests/           # pytest suite
```
