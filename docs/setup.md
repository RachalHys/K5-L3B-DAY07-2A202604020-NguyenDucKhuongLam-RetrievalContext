# Cài đặt và kế thừa Day 6

Chạy lệnh từ repo root trên Linux/WSL, với Docker Compose và Python 3.12.
Lock file kế thừa stack inference đã dùng ở Day 6; một số dependency yêu cầu
Python 3.12 dù đề bài cho phép từ 3.11.

```bash
uv venv .venv --python /usr/bin/python3.12
uv pip sync --python .venv/bin/python --torch-backend cpu requirements.lock
cp -n .env.example .env
docker compose up -d --wait
.venv/bin/python -m src.retrieval load
```

Chỉ tạo `.env` khi chưa có; nếu đổi mật khẩu local, cập nhật đồng thời
`POSTGRES_PASSWORD` và `DATABASE_URL`. Không đưa `.env` lên Git. PostgreSQL
16/pgvector 0.8.7 dùng cổng local `55434`, database `day7_lab`, table
`day7_chunks`, volume riêng `day7_retrieval_context_pg_data`. Không cần bật
database Day 6 hoặc thay đổi dữ liệu trong đó. Truy vấn dùng exact cosine.

## Dữ liệu và model

`data/basic/` chứa snapshot cần cho retrieval: chunk, text trang, vector tài
liệu và cấu hình/checksum. Chạy trực tiếp từ snapshot này không cần checkout
Day 6, không cần encode lại tài liệu. PDF gốc phục vụ kiểm chứng citation:

```bash
.venv/bin/python -m src.fetch_sources --scope basic
```

URL NINDS có thể chặn tải tự động. Nếu đã có repo Day 6 và PDF gốc, tái xuất
snapshot và sao chép PDF bằng lệnh sau (chỉ đọc repo nguồn):

```bash
.venv/bin/python -m src.day6 --repo /duong/dan/toi/repo-day6
.venv/bin/python -m src.retrieval load
```

Script xác minh checksum và sự tương thích giữa prepared snapshot/model/vector,
giữ thứ tự ID/vector, copy chunk B và 67 trang. Benchmark Day 7 được biên soạn
riêng trong `benchmark/basic/`; xuất lại corpus không ghi đè benchmark.
Snapshot chỉ giữ các artifact cần cho retrieval. Commit và cấu hình nguồn
ở `data/basic/provenance.json`; corpus được kiểm tra checksum, chuẩn vector
và text/offset trước khi nạp database.

Query encoder dùng BGE-M3 từ Hugging Face, đúng revision trong provenance;
model không lưu trong Git. Lần đầu, chạy một query có mạng để tải model vào
cache chung; runner benchmark yêu cầu cache đầy đủ và chạy encoder offline:

```bash
.venv/bin/python -m src.retrieval search \
  --query 'Which stroke warning signs are described in these documents?'
```

Sau đó thêm `--offline` để kiểm tra chạy hoàn toàn bằng model local:

```bash
.venv/bin/python -m src.retrieval search \
  --query 'Which stroke warning signs involve speech and the face?' --offline
.venv/bin/python -m src.retrieval search \
  --query 'Which warning signs are listed in the 2024 fact sheets?' \
  --filter '{"publication_year": 2024, "document_type": "fact_sheet"}' --offline
```

Kết quả có ID, text, nguồn, trang, metadata và cosine score. Đây là smoke
check kết nối và query embedding thật, chưa phải benchmark chất lượng agent.
Encoder dùng CPU/FP32, 4 PyTorch threads và tối đa 512 token như Day 6; không
cần GPU để thực hiện bước này. BGE-M3 encode query và tài liệu; agent LLM
điều phối tool và sinh câu trả lời theo [pipeline thực nghiệm](experiments.md).

## LLM API

Điền `OPENAI_API_KEY` vào `.env` cục bộ. Các tham số không chứa secret:

```dotenv
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-6-luna
LLM_REASONING_EFFORT=none
```

HTTP client dùng Python standard library và Chat Completions với function
calling, `temperature=0`, tối đa 1.200 output tokens mỗi call, `store=false`.
GPT-6 Luna hỗ trợ function calling qua endpoint này khi reasoning effort là
`none`; xem [tài liệu model](https://developers.openai.com/api/docs/models/gpt-6-luna).
Không cần cài OpenAI SDK. Model/API key phải có quyền truy cập; lỗi HTTP,
quota hoặc timeout được lưu riêng, không thay bằng mock hoặc provider khác.

Xem [cách chạy agent, benchmark và chốt cấu hình](experiments.md). Đổi model
sau khi chọn cấu hình làm mất điều kiện so sánh test; runner kiểm tra các
tham số public của model trước khi chạy. Không đưa `.env` hoặc key vào Git.

## Kiểm tra và tổ chức

```bash
uv pip check --python .venv/bin/python
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
docker compose ps
```

- `src/`: corpus, dense/BM25/hybrid retrieval, agent và đánh giá.
- `data/basic/`: snapshot NINDS dùng trong benchmark cơ bản.
- `data/raw/`: PDF gốc lưu cục bộ, được Git bỏ qua; nguồn và checksum nằm
  trong manifest để tải lại khi cần.
- `benchmark/`: đầu vào câu hỏi, nhãn đánh giá và protocol; xem phạm vi trong
  `benchmark/README.md` trước khi dùng.
- `docs/`: cách cài đặt/chạy; báo cáo cuối theo mẫu trong `report/individual/`.

Kết quả các lần chạy thật, trace và nhãn đánh giá ở
[results/basic](../results/basic/README.md).
