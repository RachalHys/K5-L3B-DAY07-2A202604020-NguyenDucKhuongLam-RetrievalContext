# Báo cáo Day 7 — Agentic RAG

**Nguyễn Đức Khương Lâm · MSSV 2A202604020 · Phần cơ bản và nâng cao · 16/11/2026**

## Dữ liệu và benchmark

Bài làm kế thừa 5 tài liệu tiếng Anh của NINDS/NIH từ Day 6: *Stroke: Hope
Through Research*, *Post-Stroke Rehabilitation* (2020) và 3 fact sheet
*Know Stroke* (2024). Trong 83 trang PDF, 67 trang nội dung được chọn để
truy xuất, tạo 252 chunk theo đoạn/câu, mục tiêu 500 ký tự, overlap 0.
ID, text, nguồn, trang, offset và vector được giữ nguyên. Số trang trong
citation là trang PDF tính từ 1. [Danh mục nguồn](../../data/basic/manifest.json)
ghi địa chỉ tải, quyền sử dụng và các trang loại bỏ. Text do NINDS biên soạn
được phép sao chép với ghi nguồn; không suy rộng quyền sử dụng sang hình/logo.

Embedding dùng `BAAI/bge-m3`, 1.024 chiều, FP32 chuẩn hóa L2, tối đa 512
token, chạy CPU với 4 luồng. Query và tài liệu dùng cùng model và cách encode;
phiên bản được cố định trong [cấu hình dữ liệu](../../data/basic/provenance.json).
Vector lưu trong PostgreSQL 16/pgvector 0.8.7, database `day7_lab`, kết nối
local qua cổng 55434 và tìm bằng cosine. Agent dùng API `gpt-6-luna`,
Chat Completions, reasoning `none`, temperature 0, tối đa 1.200 output token/call.

[Benchmark](../../benchmark/README.md) có **22 câu dev** (20 có đáp án,
2 thiếu bằng chứng) và **7 câu test** (5 có đáp án, 2 thiếu bằng chứng).
Dev kế thừa các câu Day 6 đã rà soát; test hỏi thông tin mới, không dùng
lại test Day 6. Hai tập cùng corpus và có thể chung trang/chunk nhưng khác
mục tiêu câu hỏi. Câu hỏi được tách khỏi nhãn chấm để agent không nhận gold.

Mỗi câu có đáp án cần evidence nằm trọn trong chunk đúng nguồn và trang;
các đoạn gold là những phương án thay thế hợp lệ. Câu thiếu bằng chứng có
lý do, từ khóa và phạm vi nguồn đã kiểm tra, không chỉ dựa vào top-k. Filter
năm chỉ áp dụng khi câu hỏi nêu rõ năm. Chỉ dùng dev để chọn cấu hình.

## Retrieval và thử nghiệm

Ba phương pháp được so sánh trên cùng corpus, index và nhãn dev:

- **Dense:** BGE-M3 và cosine search qua pgvector.
- **BM25:** `k1=1.2`, `b=0.75`, chuẩn hóa Unicode NFC/casefold.
- **Hybrid:** lấy tối đa 20 candidate mỗi retriever, hợp nhất bằng RRF
  `Σ 1/(k + rank)`, loại ID trùng và giữ rank/score thành phần.

BM25 được thử để tìm các từ khóa chính xác mà dense bỏ sót. Hybrid kết hợp
hai thứ hạng; Hybrid + Context tăng lượng evidence và cho phép tìm bổ sung.
Đây là ba cấu hình cải thiện so với baseline.

| Cấu hình | Retrieval | Top-k | Context (ký tự) | Search tối đa | Chọn context |
|---|---|---:|---:|---:|---|
| Dense baseline | Dense | 3 | 800 | 1 | FIFO |
| BM25 | BM25 | 3 | 800 | 1 | FIFO |
| Hybrid | RRF | 3 | 800 | 1 | FIFO |
| Hybrid + Context | RRF | 5 | 2.400 | 2 | Ưu tiên lượt mới |

Budget tính cả text, thông tin nguồn và dấu phân cách. Cả bốn cấu hình dùng
filter từ câu hỏi và không dùng reranker. Ba cấu hình đầu giữ cùng budget
để so sánh phương pháp. Cấu hình cuối thay đồng thời top-k, budget, số lượt
tìm và cách chọn context, nên không tách riêng được tác động từng yếu tố.

Từ lỗi dev `q20`, hằng số RRF được giảm **60 → 1** để tăng ảnh hưởng của
kết quả đứng đầu mỗi retriever. Các thành phần khác giữ nguyên. Cách này
đưa đoạn BM25 tìm đúng vào context dù dense xếp thấp, không cần thêm model.

Bảng dưới là [kết quả vòng cuối](../../results/basic/README.md). Hit@1 và
Evidence Hit@3 chấm ranking trên **câu hỏi gốc**; Context Evidence Rate xét
context cuối sau các lượt tìm. Mẫu số chỉ gồm câu có đáp án. Thời gian và
chi phí được làm tròn, số liệu đầy đủ giữ trong kết quả từng run.

| Cấu hình | Split | Hit@1 | Evidence Hit@3 | Context Evidence Rate | Trung vị/câu (giây) | Chi phí cả split (USD) |
|---|---|---|---|---|---:|---:|
| Dense baseline | dev | 16/20 (80%) | 17/20 (85%) | 11/20 (55%) | 4,01 | 0,0038 |
| BM25 | dev | 16/20 (80%) | 18/20 (90%) | 16/20 (80%) | 3,57 | 0,0038 |
| Hybrid | dev | 16/20 (80%) | 19/20 (95%) | 14/20 (70%) | 3,77 | 0,0037 |
| Hybrid + Context | dev | 16/20 (80%) | 19/20 (95%) | 20/20 (100%) | 4,08 | 0,0055 |
| Dense baseline | test | 3/5 (60%) | 4/5 (80%) | 4/5 (80%) | 3,51 | 0,0011 |
| Hybrid + Context | test | 3/5 (60%) | 5/5 (100%) | 5/5 (100%) | 3,85 | 0,0019 |

Ưu tiên khi chọn cấu hình là điểm grounded answer trên đủ 20 câu dev có
đáp án, sau đó xét abstention, lỗi, citation, context, thời gian và chi phí.
Hybrid + Context đạt **2,00/2**, cao hơn BM25 1,75/2, hybrid 1,55/2 và dense
1,20/2. [Cấu hình được chọn](../../configs/selected.json) đã chốt trước khi
chạy lại bộ test của vòng trước; thay đổi RRF chỉ dựa trên dev.

| Lỗi dev | Nguyên nhân | Cải thiện và kết quả |
|---|---|---|
| `q09`: nhầm mục tiêu rehab với ví dụ chức năng | Context 800 ký tự bỏ danh sách mục tiêu; baseline chỉ đạt 1 điểm | Context lớn giữ đủ ba mục tiêu, đạt 2 điểm |
| `q13`: trả lời HDL/LDL nhưng thiếu evidence | Dense chỉ lấy đoạn ngưỡng lipid; citation không hỗ trợ tên good/bad cholesterol, đạt 0 điểm | Hybrid + Context lấy đúng đoạn định nghĩa, đạt 2 điểm |
| `q08`: citation viết thiếu ký tự | Model lặp ID sai đến hết lượt, gây lỗi agent | Giới hạn citation bằng ID trong context và phản hồi rõ ID đầy đủ; regression test và lần chạy thật xác nhận hết lỗi |
| `q20`: bỏ đoạn về gia đình/bạn bè | RRF 60 ưu tiên các đoạn khớp chung, thiếu evidence cần thiết; đạt 0 điểm | RRF 1 giữ đúng đoạn ngay lượt đầu, đạt 2 điểm với citation trực tiếp |

Riêng Hybrid + Context, đổi RRF nâng số câu đầy đủ từ **19/20 lên 20/20**,
citation hợp lệ từ **22/24 lên 24/24**, context đủ evidence từ **19/20 lên
20/20**. Số lượt tìm giảm từ 26 xuống 24; chi phí dev gần như không đổi,
khoảng 0,0055–0,0056 USD. Thời gian trung vị khoảng 4,01–4,08 giây/câu,
chưa đủ để kết luận chênh lệch tốc độ có ý nghĩa.

## Agent và đánh giá

Model điều phối `search(query)` và `finish(answer, citations, abstain)`.
Agent phải tìm trước khi kết thúc, tối đa 1–2 search và 4–5 model calls tùy
cấu hình. Context được dedup, giữ nguồn/trang và chọn theo FIFO hoặc lượt
mới. Text tool cũ được thay bằng context tích lũy để giữ đúng budget.
Citation phải nằm trong context cuối và khớp marker trong answer; khi thiếu
evidence, agent từ chối với danh sách citation rỗng. Tool arguments sai nhận
feedback; lỗi API, retrieval và hết lượt được lưu riêng. Nội dung nguồn là
dữ liệu tham khảo, không phải chỉ dẫn.

Grounded answer chấm 0/1/2: sai hoặc thiếu evidence / đúng một phần / đúng
và đủ. Context chấm 0/1/2: không có evidence / có nhưng thiếu / đầy đủ.
Citation được đối chiếu với nội dung nguồn; ID hợp lệ tự nó không chứng
minh câu trả lời đúng. Abstention chấm theo nội dung thực tế. Nhãn và lý do
được lưu từng câu, chưa có xác nhận của người chấm độc lập.

Cột điểm dưới đây ghi số câu ở mức **0/1/2**, sau dấu chấm phẩy là trung bình
trên thang 2. Tool use tính trên câu chạy thành công; tỷ lệ có citation
chỉ tính câu thực sự trả lời, không gồm từ chối.

| Cấu hình / split | Tool use | Search / model calls | Điểm 0/1/2; TB /2 | Citation hợp lệ | Câu trả lời có cite | Abstention đúng | Từ chối nhầm |
|---|---|---:|---|---|---|---|---|
| Dense baseline / dev | 22/22 (100%) | 22 / 46 | 7/2/11; 1,20 | 13/16 (81,2%) | 14/14 (100%) | 2/2 (100%) | 6/20 (30%) |
| BM25 / dev | 22/22 (100%) | 22 / 46 | 2/1/17; 1,75 | 18/18 (100%) | 18/18 (100%) | 2/2 (100%) | 2/20 (10%) |
| Hybrid / dev | 22/22 (100%) | 22 / 45 | 4/1/15; 1,55 | 16/16 (100%) | 16/16 (100%) | 2/2 (100%) | 4/20 (20%) |
| Hybrid + Context / dev | 22/22 (100%) | 24 / 48 | 0/0/20; 2,00 | 24/24 (100%) | 20/20 (100%) | 2/2 (100%) | 0/20 (0%) |
| Dense baseline / test | 7/7 (100%) | 7 / 14 | 1/0/4; 1,60 | 5/5 (100%) | 5/5 (100%) | 2/2 (100%) | 0/5 (0%) |
| Hybrid + Context / test | 7/7 (100%) | 9 / 16 | 0/0/5; 2,00 | 5/5 (100%) | 5/5 (100%) | 2/2 (100%) | 0/5 (0%) |

Đối chiếu cả 5 context test có đáp án: baseline có 4 câu mức 2, 1 câu mức 0,
không có mức 1; cấu hình chọn có 5 câu mức 2. Hybrid + Context cần search
thứ hai cho 2 câu dev và 2 câu test, các câu còn lại chỉ tìm một lượt. Vòng
cuối không có lỗi hệ thống. Lỗi agent ở vòng đầu vẫn được giữ; metric chất
lượng loại lỗi theo starter, còn điểm chọn cấu hình dùng đủ số lần thử.

| Ví dụ | Tool và evidence | Kết quả đánh giá |
|---|---|---|
| `q20` / Hybrid + Context | 1 search; Rehabilitation, trang 5, mục gia đình và bạn bè | Trả lời đúng vai trò hỗ trợ trong nhiều tháng phục hồi; answer 2, context 2, citation hỗ trợ đủ |
| `test03` / Hybrid + Context | 1 search; FAST, trang 1, mục Speech Difficulty | “Check whether speech is slurred or strange.”; answer 2, context 2 |
| `test03` / baseline | 1 search; chỉ có mục triệu chứng chung của FAST | Nêu trouble speaking/understanding thay slurred/strange; answer 0, context 0. Citation hỗ trợ thông tin đã nêu, nhưng thông tin không trả lời đúng câu hỏi |
| `test_u01` / Hybrid + Context | 2 search; nguồn có đường IV/thời gian dùng t-PA, thiếu liều mg/kg | Từ chối rõ không có liều trong nguồn, không đoán con số; abstention đúng |

Metric theo gold có thể bỏ sót evidence tương đương: dev `q04` của BM25
có định nghĩa qua thrombosis ngoài exact gold, context chấm 2 dù metric
tự động không hit. Nhãn gold được giữ nguyên, khác biệt được giải thích
trong nhãn chấm.

Trên test, Hybrid + Context trả lời đầy đủ thêm một câu so với baseline,
tăng thời gian khoảng **0,34 giây/câu** và chi phí khoảng **68%**. Chi phí
test tương ứng khoảng 0,0019 và 0,0011 USD; tổng các vòng được lưu khoảng
**0,056 USD**. Đây là ước tính từ token API, chưa tính điện/phần cứng và
không gồm kiểm tra kết nối ban đầu. Thời gian tải model được ghi riêng.

[Trace và nhãn chấm](../../results/basic/README.md) lưu query gốc/viết lại,
model/tool calls, context, answer, citation, lỗi, token, thời gian và chi phí.
[Hướng dẫn cài đặt](../../docs/setup.md) và [lệnh chạy thực nghiệm](../../docs/experiments.md)
cho phép tái lập. Đã chạy **41 unit tests, toàn bộ pass**, kiểm tra text của
67 trang với PDF gốc và đối chiếu 252 chunk/vector với database.

Kết quả cho thấy Hybrid + Context phù hợp nhất trong các cấu hình đã thử.
Phạm vi đánh giá còn nhỏ, chủ yếu là câu tra cứu trên cùng corpus; test là
lần chạy lại và nhãn chưa được chấm độc lập. Điểm dev phục vụ chọn tham số,
không thay thế đánh giá trên dữ liệu mới. Các thay đổi context chưa có
thí nghiệm tách riêng từng yếu tố; model alias và query do model viết cũng
có thể làm kết quả thay đổi giữa các lần chạy.

## Thử thách nâng cao

### Tài liệu và xử lý

Phần nâng cao dùng báo cáo WHO *Global report on hypertension: the race
against a silent killer* (2023), **291 trang**, ISBN 9789240081062. Tài liệu
có 7 bảng chính, nhiều biểu đồ, bản đồ triển khai HEARTS và sơ đồ quy trình.
[Nguồn và quyền sử dụng](../../data/bonus/manifest.json) ghi giấy phép
CC BY-NC-SA 3.0 IGO; nội dung bên thứ ba có điều kiện riêng. PDF và ảnh được
tải/render cục bộ, không phân phối lại trong repo.

Toàn bộ 291 trang được render ở 144 dpi bằng PyMuPDF 1.26.7 và OCR tiếng Anh
bằng Tesseract 5.3.4. **284 trang được index**, gồm đủ 194 hồ sơ quốc gia;
7 trang bị loại là bìa, trang trắng, tiêu đề lặp và ảnh minh họa không có
thông tin truy vấn. [Thống kê xử lý](../../data/bonus/coverage.json) ghi
chi tiết từng trang. Thời gian chuẩn bị khoảng **134 giây** trên CPU.

OCR trên ảnh hiển thị tránh lấy các lớp text template bị che trong PDF.
Mỗi trang giữ từ OCR, vị trí, confidence, nhãn trang in và checksum ảnh.
Trang được chia thành ba vùng ngang có tọa độ chuẩn hóa để trích dẫn.
BM25 tìm trang theo OCR; query có số bảng/hình/box được tra thêm bookmark.
Agent tự chọn query hoặc đọc trang theo tham chiếu, sau đó xem crop gốc
có ID vùng để kiểm tra số liệu, đơn vị và chú giải. Citation như
`[who-p022-bottom]` xác định trang PDF và phần ba dưới của trang.

Không huấn luyện thêm model hoặc dùng bảng đáp án để điều khiển retrieval.
Agent kế thừa API `gpt-6-luna`, tăng giới hạn lên 1.800 output tokens/call;
OCR chỉ phục vụ tìm kiếm, ảnh gốc là bằng chứng khi đọc nội dung trực quan.

### Benchmark và chọn cấu hình

[Benchmark nâng cao](../../benchmark/bonus/README.md) được chia và khóa trước
thử nghiệm: dev **18 câu** gồm 15 có đáp án và 3 thiếu evidence; test **30 câu**
gồm 24 có đáp án và 6 thiếu evidence. Mỗi câu có một nhóm chính. Dev/test
có thể dùng chung hình hoặc bảng nhưng hỏi các mục tiêu khác nhau; câu
multi-hop cần ít nhất hai trang. Input tách khỏi đáp án, vùng evidence,
điều kiện, phép tính và cách kiểm tra trường hợp thiếu bằng chứng.

Chấm mỗi câu đạt hoặc không đạt theo đề: đúng và đủ, đúng điều kiện/đơn vị,
citation hỗ trợ toàn bộ câu trả lời; trả lời một phần và lỗi hệ thống tính
không đạt. Câu thiếu evidence đạt khi từ chối rõ, không suy đoán. Tất cả câu
đều nằm trong mẫu số. Nhãn được đối chiếu ảnh PDF gốc.

| Cấu hình dev | Trang/search | Tool tối đa | Context tối đa | Đạt / tổng | Median/câu | Chi phí |
|---|---:|---:|---:|---:|---:|---:|
| OCR text | 2 | 3 | 4 trang | 14/18 (77,8%) | 6,39 giây | 0,0142 USD |
| Page vision | 3 | 4 | 6 trang | **18/18 (100%)** | 7,93 giây | 0,0264 USD |

Dev ban đầu có lỗi do kiểm tra citation trong câu từ chối quá chặt, tìm
nhầm hình và xác định sai vùng trên ảnh cả trang. Sau khi sửa, hai cấu hình
được chạy lại trên cùng benchmark. Tra cứu bookmark khắc phục lỗi tìm hình;
crop có nhãn giúp chọn đúng vùng. Vision đọc được số trong biểu đồ bong bóng
và phân biệt số liệu cả hai giới với nam/nữ mà OCR text nhầm. Ví dụ, OCR
trả 9% và 11% cho tỷ lệ kiểm soát ở Azerbaijan/Viet Nam, trong khi ảnh gốc
cho cả hai giới là 14% và 13%.

Chọn Page vision theo tỷ lệ đạt dev, sau đó số lỗi và chi phí. Code, corpus,
model, cấu hình và benchmark được [khóa trước test](../../configs/bonus-selected.json).
Không chỉnh pipeline bằng kết quả test.

### Kết quả test

| Nhóm test | Đạt / tổng | Tỷ lệ | Nhận xét |
|---|---:|---:|---|
| Bảng | 6/6 | 100% | Đúng ô, đơn vị và phép tính |
| Ảnh, sơ đồ | 4/5 | 80% | Một câu thêm chi tiết chưa kiểm chứng được |
| Biểu đồ | 5/5 | 100% | Đọc đúng giá trị, chú giải và xu hướng |
| Multi-hop | 4/4 | 100% | Kết hợp đủ evidence từ hai trang |
| Text | 4/4 | 100% | Giữ đúng định nghĩa và điều kiện |
| Thiếu bằng chứng | 6/6 | 100% | Từ chối đúng, không đoán số liệu |
| **Toàn bộ** | **29/30** | **96,7%** | **0 lỗi hệ thống; vượt ngưỡng 90%** |

Ví dụ, agent đọc 45 và 106 triệu người ở hai bong bóng African Region,
tính tăng 61 triệu; kết hợp bảng chi phí với bảng lợi ích để tính đúng
thương số có đơn vị. Với Monaco thiếu dữ liệu hoặc giá mua thuốc cụ thể
của Telangana không được công bố, agent từ chối thay vì suy từ số liệu gần đó.

Câu chưa đạt đọc đúng losartan 50 mg và amlodipine 5 mg nhưng thêm “once
daily”; phần chữ nhỏ trong sơ đồ không đủ rõ để kiểm chứng chắc chắn chi
tiết này. Hai câu từ chối còn trích vùng chưa sát panel/hàng liên quan nhất,
được ghi rõ trong nhãn; không phát sinh khẳng định số liệu thiếu căn cứ.

Test dùng **69 model calls**, median **7,98 giây/câu**, chi phí khoảng
**0,0478 USD**. Tổng các vòng benchmark nâng cao khoảng **0,1402 USD**;
không gồm kiểm tra kết nối ban đầu. Vision tăng chi phí dev
nhưng khắc phục các lỗi đọc số và bố cục của OCR. Không cần GPU.

[Trace và nhãn từng câu](../../results/bonus/README.md) giữ cả lỗi dev ban đầu,
context, tool calls, câu trả lời, citation, usage và thời gian. Checksum crop
thay cho base64 lặp trong trace; PDF, tọa độ vùng và renderer đủ để tái tạo
ảnh đã gửi. [Hướng dẫn bonus](../../docs/bonus.md) trình bày lệnh chạy và kiểm tra.

Kết quả đáp ứng ngưỡng bonus trên bộ test đã công bố. Giới hạn còn lại là
hình raster nhỏ, OCR chưa hoàn hảo và vùng citation khá rộng. Benchmark do
bài làm biên soạn trên cùng tài liệu, nhiều câu nêu số bảng/hình, nhãn chưa
được chấm độc lập; kết quả không đại diện cho mọi tài liệu đa phương thức.
