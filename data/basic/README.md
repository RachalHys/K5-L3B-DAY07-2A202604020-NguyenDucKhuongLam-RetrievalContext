# Corpus cơ bản

Kế thừa corpus NINDS/NIH về đột quỵ từ Day 6: 5 PDF, 83 trang vật lý,
67 trang nội dung, 252 chunk theo paragraph/sentence (500 ký tự, overlap 0).
Các chunk giữ nguyên text, ID, nguồn, trang PDF vật lý và offset ký tự.

| File | Nội dung |
|---|---|
| `manifest.json` | Nguồn, quyền sử dụng, checksum PDF, trang chọn và loại trừ |
| `pages.jsonl` | Text và metadata của 67 trang đã xử lý ở Day 6 |
| `chunks.json` | Chunk theo schema Day 7 |
| `dense_vectors.npz` | `ids` và `vectors`, đúng thứ tự chunk; FP32, L2, 1.024 chiều |
| `provenance.json` | Commit Day 6, cấu hình embedding/chunking và checksum artifact |

Embedding dùng `BAAI/bge-m3`, `encode()`, tối đa 512 token, không thêm query
instruction. Revision cố định trong [cấu hình model](provenance.json).
Vector tài liệu được giữ nguyên; query mới
được encode bằng cùng model/cấu hình. Day 6 chọn C (chunk B + filter năm);
Day 7 dùng lại chunk B, chỉ áp dụng filter khi query/người dùng có yêu cầu.

Text do NINDS biên soạn được dùng theo quyền ghi trong manifest, có ghi nguồn
NINDS/NIH. Không suy rộng quyền này cho ảnh/logo của bên thứ ba. PDF gốc giữ
cục bộ tại `data/raw/stroke-awareness/`, không đưa vào Git; manifest có URL và
SHA-256 để truy cập đúng bản. Xem [cách tái tạo](../../docs/setup.md).
