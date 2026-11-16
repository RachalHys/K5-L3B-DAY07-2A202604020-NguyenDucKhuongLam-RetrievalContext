# Corpus WHO cho bonus

Báo cáo WHO *Global report on hypertension* (2023), 291 trang. Xem
[manifest](manifest.json) và [hướng dẫn bonus](../../docs/bonus.md).

- `pages.json`: OCR từng từ và vùng, trang PDF/nhãn in, checksum ảnh.
- `index.json`: text và bookmark dùng BM25, liên kết các vùng của từng trang.
- `coverage.json`: phạm vi xử lý, trang loại khỏi index và thời gian.

Nội dung OCR/index trích từ báo cáo được cung cấp theo CC BY-NC-SA 3.0 IGO,
có ghi công WHO; đây là đầu ra xử lý của bài làm, không phải sản phẩm được WHO
chứng thực. PDF và ảnh gốc được tải/render cục bộ, không đưa vào Git. Nội dung
bên thứ ba vẫn tuân theo điều kiện của chủ sở hữu tương ứng. Lỗi OCR có thể
xuất hiện; phải kiểm tra ảnh trang gốc trước khi sử dụng số liệu.
