# Benchmark cơ bản

`basic/` là benchmark tiếng Anh cho corpus NINDS/NIH kế thừa Day 6:
5 tài liệu, 67 trang nội dung, 252 chunk B. Phạm vi nguồn và trang được chọn
ở [manifest](../data/basic/manifest.json).

| Split | Có đáp án | Thiếu bằng chứng | Tổng |
|---|---:|---:|---:|
| Dev | 20 | 2 | 22 |
| Test | 5 | 2 | 7 |
| **Toàn bộ** | **25** | **4** | **29** |

## File và đầu vào agent

| File | Nội dung |
|---|---|
| `basic/dev.json`, `basic/test.json` | Chỉ có `id`, `split`, `question`, `filter` |
| `basic/labels/dev.json`, `basic/labels/test.json` | Answerability, đáp án, gold, yêu cầu chấm hoặc lý do thiếu evidence |
| `basic/protocol.json` | Phiên bản, checksum, nguồn, split, quy tắc chấm và chọn cấu hình |

Agent và retrieval chỉ đọc `load_inputs(split)` từ `src.benchmark`. Hàm này
không mở file nhãn, không đọc split còn lại và từ chối trường ngoài schema.
`load_cases(split)` ghép input với nhãn **chỉ phục vụ đánh giá**; không truyền
các bản ghi đã ghép vào agent, query rewriting hoặc retrieval tool.

Filter duy nhất được cung cấp là `publication_year` khi năm đó xuất hiện
trực tiếp trong câu hỏi. Không lấy source ID, trang, đáp án hoặc gold để tạo
filter. Query gốc phải được giữ trong trace; query viết lại được ghi riêng.

## Evidence và cách chấm

Mỗi gold là một evidence thay thế đủ hỗ trợ đáp án, nằm trọn trong một chunk
đúng nguồn và trang PDF vật lý. Không có câu multi-hop bắt buộc trong bộ cơ
bản này. Hit@1/Evidence Hit@3 xét ranking gốc; Context Evidence Rate xét
context cuối gửi model. Mẫu số là số câu có đáp án của split tương ứng.

Dev kế thừa 20 câu Day 6 đã được rà soát theo yêu cầu Day 7. Nguồn câu hỏi,
evidence thay thế và các điều chỉnh khi biên soạn nằm trong `protocol.json`.

Nhãn có `answer_requirements` để chấm đủ các ý, điều kiện, mốc thời gian và
đơn vị. Chấm context/câu trả lời 0/1/2, citation có hỗ trợ nội dung và
abstention theo [BENCHMARK.md](../BENCHMARK.md). Khớp ID hoặc nguyên văn không
thay thế kiểm tra ý nghĩa và nguồn của câu trả lời.

Chấp nhận cách diễn đạt tương đương và câu trả lời ngắn trong phạm vi câu
hỏi; không bắt buộc lặp lại điều kiện đã có ở câu hỏi. Giữ đúng mức xấp xỉ,
đơn vị và các lựa chọn OR của nguồn. Metric tự động dùng bộ gold cố định;
chấm câu trả lời/citation dựa trên context và nguồn thực tế. Nếu phát hiện
evidence hợp lệ ngoài các quote đã ghi, báo riêng sự khác biệt giữa kiểm tra
tự động và đối chiếu nguồn, không sửa nhãn test theo kết quả chạy.

Với câu thiếu bằng chứng, nhãn ghi phần thông tin thiếu, các nguồn đã rà
soát, từ khóa và đoạn liên quan. Việc rà soát bao phủ mọi trang được chọn của
các nguồn nằm trong filter, không chỉ top-k truy xuất. Không đưa các câu này
vào mẫu số retrieval metrics; câu trả lời phải từ chối và không suy đoán.

Gold đã được kiểm tra với text/trang PDF gốc; các trang có bố cục hoặc ngữ
cảnh cần lưu ý được xem thêm bản render. Trạng thái `human_verified: false`
trong protocol ghi rõ chưa có người chấm xác nhận; kiểm tra bằng code không
phải nhãn chất lượng của agent.

## Split và đóng băng

Test gồm 7 câu mới, không dùng lại các câu test Day 6 `q21`–`q25` hoặc đổi
cách hỏi cùng một đáp án dev. Hai split cùng corpus và có thể chung trang/
chunk nhưng hỏi các thông tin khác nhau; đây là holdout theo câu hỏi, không
phải đánh giá trên tài liệu chưa thấy. Bộ test nhỏ gồm 5 câu có đáp án và
2 câu thiếu bằng chứng.

`protocol.json` cố định checksum của input, nhãn và corpus trước thí nghiệm.
Chỉ dùng dev để chỉnh retrieval, prompt, context và hành vi agent. Tiêu chí
chọn lần lượt là chất lượng câu trả lời có căn cứ, abstention đúng, số lỗi,
citation hỗ trợ nội dung, context đủ evidence, độ trễ và chi phí. Điểm chọn
cấu hình chia tổng điểm trả lời cho đủ 20 câu dev có đáp án, và số abstention
đúng cho đủ 2 câu dev thiếu evidence; câu lỗi không đóng góp điểm. Các điểm
chọn này được báo riêng với metric chất lượng trên các câu chạy thành công,
kèm số lỗi và mẫu số, để việc loại lỗi không làm tăng điểm chọn. Chốt cấu hình
baseline/cấu hình chọn trước khi chạy toàn bộ test. Nếu đã dùng test để
chỉnh, cần bộ test mới và công bố thay đổi.

Protocol v2 được chốt trước khi chạy benchmark; hashes và lịch sử biên soạn
được lưu trong `protocol.json`.

## Kiểm tra dữ liệu

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m src.benchmark --split all --check-pdfs
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m src.benchmark --split dev
```

Lệnh đầu phục vụ kiểm tra khi biên soạn: checksum, schema, split, số lượng,
filter, source/page, mọi gold thay thế và text của toàn bộ 67 trang chọn so
với PDF gốc. Khi làm dev, lệnh thứ hai không mở input hoặc nhãn test.
Các lệnh chỉ kiểm tra dữ liệu, không gọi model/retriever và không tạo metrics
chất lượng. Kết quả agent thật được lưu ở [results/basic](../results/basic/README.md).
