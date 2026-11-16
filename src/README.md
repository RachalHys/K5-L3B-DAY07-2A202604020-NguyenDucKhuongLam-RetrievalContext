# Code Day 7

| Module | Chức năng |
|---|---|
| `day6.py` | Xuất snapshot từ repo Day 6 và kiểm tra chunk, vector, nguồn |
| `fetch_sources.py` | Tải PDF theo manifest, kiểm tra checksum và số trang |
| `retrieval.py` | Query encoder BGE-M3, dense qua pgvector, BM25 và hybrid RRF |
| `benchmark.py` | Đọc input không có gold và kiểm tra benchmark, evidence, PDF gốc |
| `llm.py` | HTTP API client, usage, chi phí ước tính và lỗi không chứa key |
| `agent.py` | Vòng tool calling, context, citation và abstention |
| `evaluation.py` | Tính metrics và tổng hợp nhãn đánh giá theo nguồn |
| `experiment.py` | Chạy dev, chọn/đóng băng cấu hình và đánh giá test |

Chạy agent qua `.venv/bin/python -m src.experiment` từ repo root;
xem [cài đặt và các lệnh CLI](../docs/setup.md). Adapter retrieval nhận query và
filter, trả chunk theo schema Day 7, không nhận gold/đáp án chuẩn.
