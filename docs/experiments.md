# Chạy agent và thí nghiệm cơ bản

Chuẩn bị môi trường, dữ liệu và API theo [hướng dẫn cài đặt](setup.md). Chạy từ repo
root. Các thư mục kết quả mới phải chưa tồn tại để tránh ghi đè trace cũ.
Kết quả bài nộp ở `results/basic/`; các lệnh dưới dùng `results/reproduction/`
và một file chốt cấu hình mới để chạy lại. Chọn tên khác nếu các đường dẫn
đó đã tồn tại.

## Pipeline và cấu hình

Dense dùng BGE-M3/pgvector kế thừa Day 6. BM25 dùng `k1=1.2`, `b=0.75`,
tokenization Unicode NFC/casefold và tần suất toàn corpus; filter metadata
được áp dụng trước khi trả kết quả. Hybrid lấy 20 candidate mỗi retriever,
hợp nhất bằng `sum(1/(k + rank))`, deduplicate theo ID và giữ score/rank
thành phần. `k=1` trong cấu hình hiện tại; vòng trước dùng `k=60`. Hằng số
nhỏ tăng ảnh hưởng của kết quả đứng đầu từng retriever, nhằm tránh bỏ đoạn
BM25 tìm đúng nhưng dense xếp thấp. Không cộng trực tiếp cosine với BM25 score.

| Cấu hình | Retrieval | Top-k tool | Context (ký tự) | Tối đa search | Context policy |
|---|---|---:|---:|---:|---|
| `dense_baseline` | Dense | 3 | 800 | 1 | FIFO |
| `bm25` | BM25 | 3 | 800 | 1 | FIFO |
| `hybrid` | RRF dense + BM25 | 3 | 800 | 1 | FIFO |
| `hybrid_context` | RRF dense + BM25 | 5 | 2.400 | 2 | Ưu tiên lượt mới |

Cấu hình và giả thuyết ở [thiết lập thí nghiệm](../configs/experiments.json).
Ba dòng đầu kiểm soát context/tool budget khi so sánh phương pháp. Dòng cuối
thử đồng thời context lớn hơn, thêm lượt tìm và thay chính sách context;
không suy ra riêng tác động của từng thành phần từ thí nghiệm kết hợp này.

Kết quả cuối nằm ở `results/basic/dev_refined/` và `results/basic/test_refined/`.
Vòng tinh chỉnh chỉ đổi hằng số RRF từ 60 xuống 1 dựa trên lỗi dev `q20`;
code, model, prompt, context budget, corpus và benchmark giữ nguyên. Cấu hình
trước đó được lưu cùng [kết quả các vòng chạy](../results/basic/README.md).
Test được chạy lại sau khi chốt cấu hình mới và là bộ test đã xem ở vòng trước.

Agent dùng model thật chọn `search(query)` hoặc `finish(answer, citations,
abstain)`. Filter lấy từ input benchmark, không do gold hoặc model tự tạo.
Sau mỗi search, agent gửi lại một context tích lũy đã chọn, gồm ID, nguồn,
trang; text tool cũ được thay để không nhân ngân sách context theo lịch sử.
Budget tính cả header nguồn và ký tự phân cách. Mỗi case tối đa
`max_searches + 3` model calls, gồm khả năng sửa tool arguments/citation sai.

Code kiểm tra ID citation có trong context cuối và xuất hiện trong câu trả
lời. Sau search, schema strict của `finish` giới hạn citation bằng enum của
ID đang có trong context; feedback vẫn giữ kiểm tra ID đầy đủ, không tự sửa
ID viết thiếu. Nội dung nguồn vẫn cần được đọc để xác nhận có hỗ trợ câu
trả lời. Agent phải tìm trước khi trả lời; nếu không đủ evidence thì từ chối.
Nội dung tài liệu là dữ liệu tham khảo, không phải chỉ dẫn.

## Dev, nhãn đánh giá và chọn cấu hình

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m src.experiment run \
  --split dev --config all --output results/reproduction/dev
```

Mỗi cấu hình tạo `run.json`, `traces.jsonl` và `summary.json`. Manifest ghi
model, tham số, phiên bản package, cấu hình embedding, hashes của code,
benchmark và input. Trace lưu ranking top-3 trên query gốc, từng model call
và usage, tool arguments/results, context, final answer, citation và lỗi.
Agent có thể viết lại query; ranking gốc và các lượt query mới được ghi riêng.

Sau khi đối chiếu nguồn, đặt `reviews.json` vào từng thư mục run. Mỗi phần tử
trong JSON array có `query_id`, `context_grade` 0/1/2, `citation_support`
(boolean cho từng citation), `answer_refused` và `reason`. `answer_refused`
chấm hành vi từ chối thực tế theo nội dung, độc lập với flag model tự khai;
trace gốc được giữ và summary liệt kê các ca không khớp flag. Câu có đáp án
thêm `answer_grade` 0/1/2; câu thiếu evidence thêm `abstention_correct`.
Với lỗi hệ thống, giữ
bản ghi và lý do lỗi, không tạo đáp án hoặc nhãn chất lượng giả.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m src.experiment review \
  --run results/reproduction/dev/hybrid_context
```

Chấm đủ 22 case và chạy `review` cho cả bốn cấu hình. Nhãn phải dựa trên
câu trả lời mới và nguồn thực tế, không sao chép nhãn của lần chạy cũ.
Sau đó chốt cấu hình:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m src.experiment select \
  --dev-root results/reproduction/dev --output configs/selected-reproduction.json
```

Tiêu chí chọn lần lượt là điểm grounded answer trên đủ 20 câu dev có đáp
án, abstention trên đủ 2 câu thiếu bằng chứng, số lỗi, citation, context,
thời gian và chi phí. Metric chất lượng chỉ tính câu chạy thành công và
báo số lỗi riêng; điểm chọn vẫn dùng toàn bộ lần thử. Báo cáo cần phân tích
ít nhất hai lỗi dev, kết quả trước/sau và cả cấu hình không cải thiện.

## Test sau khi đóng băng

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m src.experiment run \
  --split test --config comparison --selection configs/selected-reproduction.json \
  --output results/reproduction/test
```

Runner từ chối chạy test nếu thiếu selection hoặc code, cấu hình, model hay
benchmark đã thay đổi sau khi chốt. Chỉ chạy baseline và cấu hình được chọn;
nếu hai vai trò trùng cấu hình thì dùng chung kết quả. Chấm đủ 5 câu có đáp
án và 2 câu thiếu evidence cho mỗi cấu hình. Bổ sung `reviews.json`, rồi
dùng lệnh `review` như trên để tổng hợp. Không chỉnh pipeline bằng test;
nếu đã chỉnh thì cần test mới theo quy định.

Để chỉ kiểm tra kết quả bài nộp, không gọi API, có thể chạy `review` trên
các thư mục sẵn có, ví dụ `--run results/basic/test_refined/hybrid_context`.
Lệnh này tính lại summary từ trace và nhãn, không thay cấu hình hay đáp án.

Cold start/model loading được ghi riêng trong `setup_seconds`. Median
end-to-end gồm ranking gốc và toàn bộ agent cho từng query sau khi model
đã load. Thời gian ranking gốc, số search/model calls và token được báo
riêng. Chi phí API là ước tính từ usage và đơn giá chốt trong config, không
phải hóa đơn; phần chi phí không có usage được đánh dấu chưa đầy đủ.
Local embedding/retrieval không thu phí dịch vụ; điện/phần cứng không được
tính vào ước tính USD.

## Tài liệu tham khảo

- [Robertson & Zaragoza — BM25 and Beyond](https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf).
- [Cormack, Clarke & Büttcher — Reciprocal Rank Fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf).
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling),
  [GPT-6 Luna: khả năng và đơn giá](https://developers.openai.com/api/docs/models/gpt-6-luna).
