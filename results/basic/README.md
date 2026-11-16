# Kết quả thực nghiệm cơ bản

- [Báo cáo và bảng so sánh](../../report/individual/2A202604020_NguyenDucKhuongLam.md).
- `dev_initial/`: vòng dev đầu, giữ cả lỗi citation và toàn bộ kết quả trước sửa.
- `dev/`, `test/`: kết quả trước khi tinh chỉnh RRF, với `k=60`.
- `dev_refined/`: bốn cấu hình sau khi đổi hằng số RRF thành `k=1` từ lỗi dev `q20`.
- `test_refined/`: baseline và cấu hình chọn sau khi chốt lại trên dev; kiểm tra lại cùng bộ test.
- [Cấu hình đã chốt](../../configs/selected.json): cấu hình, thời điểm chốt và hashes
  code/config/model/protocol, trace và nhãn dev được dùng để chọn.

Mỗi thư mục cấu hình có:

| File | Nội dung |
|---|---|
| `run.json` | Cấu hình, môi trường, model, thời gian và hashes phục vụ tái lập |
| `traces.jsonl` | Mỗi dòng là một câu, gồm ranking gốc, model/tool calls, context, answer, citation, lỗi, token và chi phí |
| `reviews.json` | Nhãn answer/context, abstention, từng citation và lý do đối chiếu nguồn |
| `summary.json` | Evidence metrics, nhãn tổng hợp, thời gian, token, cost và lỗi |

Các run cũ được giữ đủ, kể cả lỗi, để đối chiếu trước/sau. Có thể xem
[thiết lập trước tinh chỉnh](../../configs/experiments-before-refinement.json) và
[cấu hình được chọn ở vòng trước](../../configs/selected-before-refinement.json).
Bước tinh chỉnh chỉ đổi hằng số RRF dựa trên dev; `test_refined` chạy lại
bộ test đã xem, sau khi chốt cấu hình mới. Không dùng test để chỉnh pipeline.

Nhãn `human_verified=false` thể hiện chưa có xác nhận của người chấm độc lập.
`source_inspection` ghi nhận việc đối chiếu citation với nguồn. Trong vòng
dev đầu có một lỗi hết lượt agent. Trường `agent.provider_errors` của starter
đếm mọi trace có status `error`; trường `error_type` trong trace phân biệt
nguyên nhân. Lỗi này không bị loại khỏi bằng chứng thực nghiệm.

Xem [hướng dẫn chạy và chấm](../../docs/experiments.md). Chọn thư mục output
mới khi tái lập; runner không ghi đè các kết quả này.
