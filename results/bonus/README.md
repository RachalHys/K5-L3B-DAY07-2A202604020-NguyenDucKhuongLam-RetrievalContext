# Kết quả thử thách nâng cao

Báo cáo WHO 291 trang được xử lý riêng với phần cơ bản. Bộ dev có 18 câu;
test có 30 câu, chấm đạt/không đạt theo [ADVANCED.md](../../ADVANCED.md).

| Vòng / cấu hình | Đạt / tổng | Tỷ lệ | Lỗi hệ thống |
|---|---:|---:|---:|
| Dev ban đầu / OCR text | 11/18 | 61,1% | 7 |
| Dev ban đầu / Page vision | 12/18 | 66,7% | 3 |
| Dev sau sửa / OCR text | 14/18 | 77,8% | 0 |
| Dev sau sửa / Page vision | 18/18 | 100% | 0 |
| Test / Page vision đã chốt | **29/30** | **96,7%** | **0** |

Vòng đầu được giữ tại `dev_initial/`. Lỗi dev dẫn tới hai thay đổi chung:
tra cứu số bảng/hình/box từ bookmark trước khi bổ sung BM25, và gửi crop có
nhãn vùng thay cho chỉ ảnh cả trang. Đồng thời cho phép citation trong câu
từ chối để chỉ ra panel thiếu dữ liệu, phù hợp tiêu chí abstention của đề.
Không thay đổi benchmark; chưa dùng test khi thực hiện các sửa đổi này.

[Selection](../../configs/bonus-selected.json) khóa code, corpus, cấu hình,
model và benchmark trước test. Mỗi thư mục run chứa `run.json`,
`traces.jsonl`, `usage.json`, `reviews.json` và `summary.json`.

Kết quả test theo nhóm: bảng 6/6, ảnh/sơ đồ 4/5, biểu đồ 5/5, multi-hop 4/4,
text 4/4, thiếu evidence 6/6. Câu ảnh về bước 1 của phác đồ Sri Lanka được
chấm không đạt: thuốc và liều đúng, nhưng câu trả lời thêm tần suất dùng
thuốc chưa kiểm chứng chắc chắn từ phần chữ nhỏ. Hai câu từ chối có citation
chưa trỏ trực tiếp vùng phù hợp nhất; nhãn giải thích riêng. Tiêu chí câu
thiếu evidence của đề không bắt buộc citation và không có số liệu thiếu căn
cứ trong các câu đó.

Test dùng 69 model calls, median khoảng 7,98 giây/câu, chi phí ước tính
0,0478 USD. Tổng 102 lần thử benchmark dùng 281 calls, khoảng 0,1402 USD;
không gồm kiểm tra kết nối ban đầu.
Chi phí tính từ usage API, không phải hóa đơn và chưa gồm phần cứng/điện.

Đáp án và citation được đối chiếu ảnh PDF gốc. Nhãn chưa được chấm độc lập; trường `human_verified` được đặt là `false`.
Base64 ảnh không lặp trong trace: checksum từng ảnh/crop và metadata đủ để
tái tạo từ PDF gốc bằng phiên bản render đã khóa. [Cách chạy](../../docs/bonus.md).
