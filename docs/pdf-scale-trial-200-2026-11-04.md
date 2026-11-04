# Kết quả chạy 200 câu mới với OCR cold

Ngày 2026-11-04, runner v2 hoàn thành 200 câu mới và qua kiểm tra kỹ thuật.
Kết quả đủ để tiếp tục vận hành theo từng đợt nhằm tạo bản nháp có nguồn.
Chất lượng nội dung chưa đủ căn cứ để đưa toàn kho vào core chấm tự động.
Mọi record vẫn giữ `academic_review=PENDING`,
`grading_support=NOT_ASSESSED`, `publishable=false`.

## Phạm vi và điều kiện

Đầu vào là corpus đã ghép đề với lời giải gồm 3.695 lượt câu từ 12 PDF đóng
góp. Đây là giai đoạn sau nhập PDF và ghép cặp, không phải phép đo toàn bộ
luồng PDF thô đến chấm điểm. 200 ID được chọn không trùng 100 ID thử trước,
cân bằng 50 câu mỗi chương: đạo hàm, tích phân, thống kê, xác suất. Không
khẳng định các bài toán ở các PDF khác nhau đều khác nội dung.

Chọn mẫu theo chương, PDF và gợi ý bố cục từ text nguồn, trước khi suy luận.
Trong đầu ra thực tế, 49 câu có bảng được phát hiện, 105 câu có span nằm
trên nhiều trang. Các gợi ý bảng/hình không phải nhãn bố cục chuẩn.

Máy chạy CPU Intel Core i5-12450H, 8 lõi và 12 luồng logic, Windows 11;
RAM hệ điều hành nhìn thấy khoảng 51,14 GB thập phân. PP-FormulaNet_plus-M
và S chạy CPU, mỗi model ba luồng, tối đa hai worker. Model và package đã
có sẵn trên E. Cold ở đây nghĩa là không đọc hoặc nhập cache kết quả OCR,
kể cả cache trong cùng lượt. Không xóa cache file của hệ điều hành và không
khống chế power mode; không coi đây là benchmark phần cứng trong môi trường
thí nghiệm được kiểm soát hoàn toàn.

## Số đo thực tế

| Chỉ số | Kết quả |
| --- | --- |
| Record hoàn tất và qua schema | 200 trên 200 |
| Chương và PDF đóng góp | 4 chương và 12 PDF |
| Ảnh được tham chiếu và kiểm hash | 4.572, không lỗi |
| Thời gian xử lý được supervisor ghi nhận lũy kế | 2.939,851 giây, khoảng 49 phút |
| Peak RSS cây tiến trình | 3.777.806.336 byte, khoảng 3,78 GB thập phân hoặc 3,52 GiB |
| Dung lượng output tại thời điểm kiểm tra | 55.954.581 byte, khoảng 56 MB |
| Kết quả model được bộ đếm ghi nhận | 2.144, tổng hai model |
| Lượt model trả đầu ra bị từ chối | 1, đã giữ ảnh và ghi lỗi |
| Cache hit OCR và cache v1 nhập lại | 0 và 0 |
| Trang phân tích được giữ trong cache mỗi worker | Tối đa 8 |
| Nhóm xử lý trả lỗi hoặc bị timeout | 0 trên 20 nhóm của hai lần chạy có dữ liệu mới |
| Kiểm thử toàn bộ công cụ PDF | 417 test qua trong 23,38 giây |

Thời gian lũy kế gồm 427,756 giây cho 10 câu đầu của thử pause, 2.512,084
giây cho 190 câu còn lại, và 0,011 giây của vòng supervisor khi resume toàn
bộ đã hoàn tất. Nó không bao gồm thời gian để pipeline tạm dừng, toàn bộ
preflight, xuất cuối và QA. Lượt resume rỗng vẫn cần kiểm hash và xuất lại
file, vì vậy không được diễn giải 0,011 giây là thời gian đầy đủ của lệnh.

Mười câu đầu chạy trong một chunk để thử pause, phần còn lại chạy tối đa
hai chunk song song. Do đó không coi số đo này là một lượt 200 câu đồng
nhất chạy hai worker từ đầu đến cuối. Qwen vision, nhập PDF thô và chấm
điểm không nằm trong thời gian OCR cold. Không suy thời gian tuyến tính
từ số câu này sang tất cả trang PDF.

Bộ đếm `FormulaReader.calls` tăng sau khi có kết quả model hợp lệ. Lần trả
đầu ra không hợp lệ bị chặn trước khi tăng bộ đếm. Vì vậy có 2.144 kết quả
model được đếm và thêm một lần suy luận bị từ chối, tức 2.145 lần gọi mức
adapter trong lượt thử này. `total_model_calls` cũ trong report chỉ phản
ánh bộ đếm primary; khi đối chiếu phải xem thêm `secondary_model_calls`.
Báo cáo kiểm tra riêng ghi rõ sự khác nhau này.

## Phục hồi và tính toàn vẹn

Pipeline dừng có chủ đích sau 10 câu, xuất trạng thái `PAUSED_DRAFT`, rồi
chạy tiếp 190 câu còn lại. Cả 10 JSON record trước điểm dừng giữ nguyên hash.
Sau khi có 200 câu, chạy lại cùng selection xác nhận 200 record được resume,
không tạo chunk mới và không suy luận OCR lại. Đây là phép thử pause/resume
ở ranh giới nhóm; kiểm thử tự động còn có trường hợp worker treo, bị dừng
vì timeout và trả mã lỗi khác không.

200 checkpoint cùng hash record và ảnh được xác minh. PDF nguồn, metadata,
plan không thay đổi. 7.519 file trong hai output thử v1/v2 cũ khớp snapshot
trước lượt mới. Các file tổng hợp và danh mục của lượt mới được cập nhật
theo thiết kế; chúng không phải record bất biến.

## Chất lượng nội dung và lỗi còn lại

| Chỉ số nội dung | Kết quả |
| --- | --- |
| Vùng công thức | 3.587 |
| Vùng có LaTeX để hiển thị bản nháp | 2.463 |
| Vùng giữ ảnh thay thế | 1.124, khoảng 31,3 phần trăm |
| Bảng và ô bảng | 72 bảng, 1.009 ô |
| Ô bảng vẫn dùng ảnh | 120 |
| Câu có cờ cần kiểm tra nguồn | 197 |
| Câu mang trạng thái text và LaTeX nháp, không có cờ trong tầng này | 3 |
| Câu được xác nhận học thuật hoặc cho phép chấm | 0 |

Không so phần trăm giữ ảnh của 200 câu này với 100 câu trước như một phép
đo cải thiện độ chính xác: hai mẫu khác nhau và chưa có gold độc lập. Ba câu
không có cờ kỹ thuật vẫn chưa được xác minh đúng về toán học.

Lỗi model duy nhất nằm ở collection 1589, ID
`95d86a9f7884138e:q79:n358`, vùng `solution-00-000`:
`ValueError: INVALID_FORMULA_MODEL_OUTPUT`. LaTeX vùng này là null, ảnh
`assets/q1589/solution-00-formula-000.png` còn nguyên. Không nối nội dung
model không hợp lệ vào lời giải để làm expected cho core.

Câu chậm nhất quan sát là collection 3344, khoảng 403,156 giây. Chi phí từng
câu biến thiên nhiều theo nguồn và nội dung. Chưa có profile hàm đủ chi tiết
để quy toàn bộ thời gian của câu đó cho riêng một model hoặc riêng layout.
RAM không tăng theo tổng số record trong lượt thử này; tăng RAM không tự
giải quyết chi phí suy luận và các nguồn khó.

## Những cải tiến đã kiểm tra

Lệnh `transcribe_corpus.ps1 -Version v2` chạy được selection mới, selection
đã khóa, loại ID cũ và chế độ cold. Tiến trình nhóm có giới hạn thời gian,
RSS quan sát và dung lượng trống; chỉ dừng cây tiến trình được sở hữu. Cache
trang có giới hạn và model được giải phóng theo vòng đời nhóm. JSON tổng
hợp được stream ở cuối lượt, còn record và checkpoint được ghi từng câu.
Thiếu record hoặc lỗi nhóm trả trạng thái không hoàn tất và exit khác không.

Hàng đợi PDF thô ghi rõ lý do hoãn theo ngân sách. Tài liệu lớn hơn ngân sách
có thể được chạy nguyên file theo chính sách tường minh, giữ lời giải qua
trang. Kiểm thử dùng PDF hai trang với ngân sách một trang xác nhận cả
hai nhánh chạy và hoãn. Không đánh đồng việc này với chạy OCR v2 theo trang.

Chế độ `-All -PlanOnly -SkipQwen` lập kế hoạch được 3.695 câu với phân bố
thật 1.448 đạo hàm, 1.691 tích phân, 274 thống kê, 282 xác suất. Không ép quota
50 câu hoặc bội số bốn ở chế độ toàn kho. Chưa khởi chạy inference toàn kho.

Startup vision đã được thử riêng sau khi kết thúc OCR: server local 8792
đạt health và truy vấn models có xác thực, không gửi yêu cầu suy luận.
Server do lượt thử tạo ra đã được dừng, port không còn listen. Phép thử này
không đo lại độ chính xác hoặc chi phí Qwen đọc ảnh.

## Đầu ra và bước tiếp

Namespace output trên E:
`.tmp/pdf-jobs/4ebd40c425c242baa4faf416/transcription-v2-scale-200-cold-20261104`.
`scale-validation.json` chứa số đo lũy kế, kiểm hash và giới hạn bằng chứng.
`batch-state.json` chứa ba invocation. `benchmark.json` là invocation gần
nhất, ở đây là lượt resume rỗng; không lấy thời gian hoặc RSS invocation đó
làm số đo của cả 200 câu. Dùng `content.draft.pretty.json` hoặc `review.html`
để xem nội dung. Dùng [hướng dẫn vận hành](pdf-scale-runner-2026-11-04.md)
để chạy lại với đúng scope.

Hướng tiếp theo là lọc ở cấp câu thành ứng viên core, tham khảo ảnh và tạm
loại khỏi bộ dùng. Giữ PDF gốc và toàn bộ chứng cứ. Chỉ tách step và chạy
checker cho nhóm đủ điều kiện. Có thể mở rộng tạo bản nháp bằng các đợt có
giới hạn; chưa coi việc hoàn thành kỹ thuật là điều kiện phê duyệt toàn bộ
3.695 câu cho core.
