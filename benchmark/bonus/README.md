# Benchmark bonus

Dev: 15 câu có đáp án và 3 câu thiếu evidence. Test: 24 câu có đáp án và
6 câu thiếu evidence. Cơ cấu và cách chấm được khóa trong [protocol](protocol.json).

`dev.json` và `test.json` chỉ chứa ID/câu hỏi. Thư mục `labels/` chứa đáp án,
nhóm chính, evidence theo trang/vùng, phép tính và cách kiểm tra câu thiếu
bằng chứng. Gold phục vụ đánh giá, không cung cấp cho agent/retriever.

Mỗi câu chỉ tính vào một nhóm chính. Câu multi-hop dùng ít nhất hai trang.
Nhãn được đối chiếu ảnh PDF gốc, chưa được chấm độc lập.
Tỷ lệ test tính trên toàn bộ 30 câu, bao gồm lỗi; ngưỡng bonus là 27/30.
