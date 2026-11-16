# Thử thách nâng cao

## Tài liệu và phạm vi

Dùng *Global report on hypertension: the race against a silent killer*, WHO,
2023, ISBN 9789240081062, gồm 291 trang PDF. Nguồn, URL tải và checksum nằm
trong [manifest](../data/bonus/manifest.json). Giấy phép CC BY-NC-SA 3.0 IGO
ở trang PDF 4; thành phần bên thứ ba có điều kiện riêng. Repo không phân phối
PDF hoặc ảnh crop; ảnh được tái tạo cục bộ từ bản gốc.

Index bao phủ nội dung hữu ích của toàn tài liệu, gồm 194 hồ sơ quốc gia.
Trang bìa, trang trắng, tiêu đề lặp và ba ảnh minh họa không có thông tin truy
vấn được loại khỏi tìm kiếm. Chi tiết từng trang và thời gian xử lý nằm trong
[coverage](../data/bonus/coverage.json). Số trang citation là trang PDF tính từ 1;
nhãn trang in được giữ riêng.

## Pipeline

1. Render từng trang ở 144 dpi bằng PyMuPDF; OCR tiếng Anh bằng Tesseract.
   OCR trên ảnh hiển thị tránh lấy text template bị che trong PDF.
2. Lưu từ OCR, vị trí pixel, confidence, text theo ba vùng ngang và checksum
   ảnh. Mỗi vùng chiếm một phần ba chiều cao trang; tọa độ chuẩn hóa theo
   `[x0, y0, x1, y1]`, gốc trên trái. Heading từ bookmark PDF hỗ trợ tìm kiếm.
3. BM25 (`k1=1.2`, `b=0.75`) tìm các trang liên quan; số bảng/hình/box được nêu trong query được
   tra trực tiếp từ bookmark PDF trước khi bổ sung các trang theo BM25. Agent chọn query, có thể tìm tiếp hoặc đọc
   trang theo tham chiếu trong tài liệu. Context có giới hạn số trang.
4. Cấu hình vision gửi thêm ba crop của ảnh trang gốc, mỗi crop có ID vùng để model đọc bảng, biểu đồ, bản đồ
   và sơ đồ. OCR chỉ giúp tìm trang, không được coi là đáp án đã kiểm chứng.
5. Agent trả lời với citation như `[who-p022-bottom]`, hoặc từ chối khi thiếu
   evidence. Citation phải nằm trong context đã đọc và hỗ trợ đủ các ý/hop.

Không huấn luyện model, không tạo bảng đáp án theo câu hỏi và không nạp gold
vào runtime. Phần bonus dùng BM25 và page vision; không yêu cầu thêm dense
retrieval vì yêu cầu ba phương pháp đã được thực hiện ở phần cơ bản.

## Cài đặt và chạy

Dùng môi trường phần cơ bản và cài dependency bổ sung:

```bash
uv pip install --python .venv/bin/python -r requirements-bonus.txt
.venv/bin/python -m src.fetch_sources --scope bonus
```

Snapshot OCR và index đã có trong repo, nên chạy benchmark không cần OCR lại.
Ảnh trang sẽ được render từ PDF, xác minh với checksum đã lưu. Để tái tạo index,
cài Tesseract 5.3.4 với dữ liệu tiếng Anh và chạy:

```bash
# Ubuntu 24.04; có thể cài bằng trình quản lý gói của hệ thống.
sudo apt-get install tesseract-ocr tesseract-ocr-eng
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m bonus.run prepare --workers 8
```

Có thể đặt `TESSERACT_BIN`, `TESSDATA_PREFIX` và `LD_LIBRARY_PATH` nếu cài
Tesseract trong thư mục người dùng. Máy chạy bài dùng gói Ubuntu 24.04 được
trích vào cache người dùng; không cần quyền root hay GPU. OCR dùng một thread
mỗi process. PyMuPDF 1.26.7 render PNG; thay phiên bản có thể đổi checksum ảnh.

API và model kế thừa `.env` của phần cơ bản. Không đưa file này lên Git.
Cấu hình public và giá dùng ước tính chi phí nằm trong
[configs/bonus.json](../configs/bonus.json). Mỗi model call tối đa 1.800 output
tokens, temperature 0, reasoning `none`, `store=false`.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m bonus.run run --split dev --config ocr_text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m bonus.run run --split dev --config page_vision
# Đối chiếu từng câu với PDF và điền reviews.json trong thư mục kết quả.
.venv/bin/python -m bonus.run select
.venv/bin/python -m bonus.run run --split test --config page_vision
.venv/bin/python -m bonus.run review --directory results/bonus/test/page_vision
```

Runner không ghi đè một lần chạy đã có. Khi tái lập, chuyển bộ kết quả cũ ra
ngoài repo trước khi chạy. `select` chốt theo tỷ lệ đạt dev, số lỗi và chi phí;
test bị chặn nếu code, dữ liệu, cấu hình, model hoặc benchmark thay đổi sau đó.

## Benchmark và bằng chứng

[Benchmark bonus](../benchmark/bonus/protocol.json) gồm dev 18 câu và test
30 câu. Input chỉ có ID và câu hỏi; đáp án, nhóm, vùng evidence, phép tính
và cách kiểm tra thiếu evidence nằm riêng trong `benchmark/bonus/labels/`.
Mỗi câu có một nhóm chính; multi-hop kết hợp ít nhất hai trang. Dev/test
khác mục tiêu trả lời, dù có thể dùng chung bảng hoặc hình.

Chấm đạt/không đạt theo ADVANCED.md: câu trả lời phải đúng, đủ, đúng điều kiện
và có citation hỗ trợ toàn bộ; lỗi hệ thống và câu trả lời một phần tính không
đạt. Tất cả câu đều nằm trong mẫu số. Đối chiếu vùng gốc khi chấm, không chỉ
so khớp OCR hoặc tin nhãn model.

Trace lưu đầy đủ model request/response, tool calls, ranking, context OCR,
trang đã xem, citation, latency và usage. Base64 từng crop được thay bằng checksum
trong bản lưu để tránh lặp dữ liệu; `pages.json`, PDF gốc và lệnh render đủ
để tái tạo chính xác crop đã gửi (cắt theo bbox vùng ở 144 dpi). Trace không chứa header Authorization.
Giá ước tính dùng token usage API, gồm image input tokens mà provider báo;
không gồm phần cứng hoặc điện. Giới hạn ảnh nhỏ/mờ và OCR được phân tích
trong báo cáo cá nhân.

Kiểm tra bộ nộp và tái tạo checksum crop:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m bonus.verify
```
