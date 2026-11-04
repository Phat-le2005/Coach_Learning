# Chấm thử đạo hàm từ PDF — 03/11/2026

## Kết quả và phạm vi

Đã tạo một tầng chấm thử riêng sau file cuối của pipeline. Mẫu gồm 12 câu 154, 171, 172, 173, 175–182 trong PDF đạo hàm: 10 câu đủ nhất quán để chấm trong sandbox, 2 câu giữ lại vì mâu thuẫn nguồn. Hàm số, miền xét, yêu cầu đề và các mệnh đề cần kiểm đã được chép và đối chiếu trực tiếp với ảnh trang PDF 3, 12–16; bộ kiểm tính lại bằng code.

Đây là mẫu phát triển có chủ đích và có chú giải thủ công, chưa phải mẫu ngẫu nhiên, held-out hoặc quy trình tự động duyệt một PDF mới. Rubric 10 điểm là đề xuất có phiên bản `calculus-independent-claims/v1`, chưa được giáo viên phê duyệt. Điểm luôn mang `production_grade=false`; không ghi database, điểm chính thức hay mastery của học sinh.

## Cách chạy và xem

Từ thư mục `E:\HocTap\Hackathon-SGU2026\Coach_Learning`:

```powershell
.\tools\pdf_metadata\trial_grading.ps1 `
  -Job '.tmp\pdf-jobs\5db1fc66ab0a42553e882981' -Open
```

Lệnh dùng Python trong `.tmp/pdf-pipeline-runtime/.venv` trên E, dựng rubric, chạy các tình huống và mở trang xem. Không tải model, không chạy Qwen/Gemini và không gọi API. Dashboard có nút **Xem điểm chấm thử**.

- Trang ổn định: http://127.0.0.1:8789/artifacts/5db1fc66ab0a42553e882981/grading-trial/review.html
- Con trỏ kết quả: `.tmp/pdf-jobs/5db1fc66ab0a42553e882981/grading-trial.json`.
- Gói hiện tại: `grading-trial/versions/00d29365610de618/questions.sandbox-rubric.jsonl`, tính từ thư mục job.
- Cùng thư mục phiên bản có `policy.json`, `annotations.snapshot.json`, `scenario-cases.jsonl`, `scenario-results.jsonl`, `evaluation.json`, ảnh nguồn và `review.html`.

Phiên bản có thể đổi khi code/chú giải/file cuối đổi. Đọc con trỏ `grading-trial.json` thay vì gắn cứng thư mục phiên bản. Adapter từ chối package bị sửa, nguồn/file cuối/ảnh bằng chứng đổi, hoặc code tính toán khác phiên bản đã dựng.

## Nối adapter với core thử nghiệm

Adapter thật là `pdfmeta.grading_trial.build.check(job, request)`, hoặc CLI:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'tools\pdf_metadata'
& .tmp\pdf-pipeline-runtime\.venv\Scripts\python.exe -B -m pdfmeta.grading_trial check `
  --job '.tmp\pdf-jobs\5db1fc66ab0a42553e882981' `
  --request '.tmp\pdf-grading-pilot-20261103\requests\alternative-method.json'
```

Đầu vào gồm `question_id`, `domain`, `steps` và tùy chọn `method`. Mỗi step có `criterion_id`, `value`. Ví dụ câu 179 dùng miền R trừ -3; các tiêu chí `numerator_derivative`, `denominator_derivative`, `critical_rule`, `line`, `final` mô tả cách dùng tỉ số đạo hàm. Khi không chỉ định method, các ID có cấu trúc giúp chọn đúng một cách; trộn phương pháp mơ hồ cần đối chiếu thêm. Request không được tự cấp đáp án chuẩn, trọng số hoặc checker.

Đầu vào này đã có cấu trúc. Chưa có adapter biến mọi bài viết tay hoặc văn xuôi tự do của học sinh thành các mệnh đề chứng minh. Tầng OCR/phân tích bài làm vẫn cần kiểm riêng trước khi nối vào chấm thật.

## Rubric và hành vi

Ba cách giải được hỗ trợ khi phù hợp với bài:

1. Đạo hàm → nghiệm → khoảng đồng biến hoặc tọa độ cực trị → đường thẳng/độ dài → kết quả.
2. Với hàm bậc ba: chia hàm cho đạo hàm, kiểm đẳng thức `F=qF′+r`, rồi dùng phần dư để tìm đường thẳng cực trị.
3. Với hàm bậc hai trên bậc nhất: kiểm đạo hàm tử/mẫu và hệ thức `F=u′/v′` tại điểm đạo hàm bằng 0. Code kiểm điều kiện sử dụng của hệ thức trước khi tạo rubric.

Mỗi cách có tổng 10 điểm; một cách hợp lệ không bị buộc trình bày tọa độ/nghiệm của cách khác. Bộ kiểm giữ miền gốc khi rút gọn, nhận biểu thức hữu tỉ tương đương, kiểm nghiệm trong miền và bỏ điểm dừng không phải cực trị bằng xét dấu. Đường thẳng kết luận phải xác định trên R; không được thêm lỗ miền dù hàm gốc có điểm loại.

Thiếu hoặc sai miền xét không sinh tổng điểm số. Bước không hỗ trợ trả `NOT_ASSESSED`, giữ cận dưới/trên điểm. Bước cần có nhưng không nộp nhận 0 cho tiêu chí đó; không tự suy ra chứng minh chỉ vì đáp án cuối đúng. Tiêu chí được tính độc lập; kết quả sau đúng nhưng tiền đề thiếu/sai có `dependency_warnings`. Đây chưa phải bộ hiểu đầy đủ mạch chứng minh hoặc chính sách điểm kéo theo của giáo viên.

Kết quả làm tròn nhận giá trị chính xác hoặc đúng số đã làm tròn theo đề, dùng half-up. Ví dụ yêu cầu 2 chữ số thì 4.47 được nhận, 4.474 không được coi đúng chỉ nhờ khoảng dung sai rộng. Grammar giới hạn biểu thức hữu tỉ một biến bậc tối đa 8, độ dài và kích thước số; không eval text. Các dạng ngoài phạm vi giữ lại để xử lý riêng.

Hai câu bị giữ lại vẫn giữ nguyên nguồn: câu 173 có mệnh đề khoảng đồng biến không khớp đạo hàm/bảng; câu 182 có tọa độ cực trị bị đổi chéo giá trị tung độ. Đáp án cuối in đúng không đủ để biến toàn bộ lời giải thành chuẩn chấm. Chú giải ghi vấn đề riêng, không ghi đè nguồn.

## Bằng chứng đã chạy

- **149/149 tình huống tổng hợp** đạt kỳ vọng: bài đúng, tương đương, sai dấu/số mũ/kết quả, thiếu bước/miền, lỗ miền mới, đổi thứ tự và phương pháp hợp lệ khác. Nhãn gồm trạng thái, điểm và tiêu chí chịu ảnh hưởng; không phải accuracy trên bài học sinh thật.
- **302 tests** của toàn bộ `tools/pdf_metadata/tests` qua. Bao gồm các giới hạn parser/domain, giữ nguồn, từ chối đáp án/trọng số giả và package cũ/bị sửa.
- Gọi adapter thật: câu 175 đúng nhận 10, sai dấu đạo hàm nhận 8 kèm cảnh báo tiền đề; câu 179 giải tỉ số đạo hàm nhận 10; câu 173 nhận `HELD_SOURCE_CONFLICT`, điểm null.
- Kiểm Edge desktop và 390 px: 12 thẻ câu, 149 tình huống, lọc đúng 2 câu giữ lại; 15/15 ảnh tải được, không lỗi JavaScript/HTTP và không tràn ngang ở trạng thái mobile đã thử. Rubric và phản hồi cách giải khác đã được mở, chụp và xem trực tiếp.
- Trong 68 tiêu chí của cách trực tiếp, 8 ghép được bằng đồng nhất công thức với step cũ. Các tiêu chí còn lại có thể chỉ ghép theo loại bước hoặc được suy ra bằng code; không gọi tất cả là đã đối chiếu chính xác từng bước nguồn.

File kiểm chứng phát triển nằm tại `.tmp/pdf-grading-pilot-20261103/`. PDF/ZIP gốc, file cuối acquisition và các artifact cũ không bị sửa. Kiểm này không bật inference; server Qwen không chạy sau lượt thử.

## Bước triển khai sau

Có thể dùng adapter và trang này để thử nối core trong môi trường sandbox. Trước khi mở rộng chấm, cần một tập bài làm học sinh độc lập có các cách giải khác nhau, nhãn đúng/sai từng bước và rubric được thống nhất; đo riêng độ đúng OCR, phân loại bước và chấm. Muốn tự xử lý PDF khác cần tạo function/domain/task có bằng chứng nguồn rồi kiểm tự động; mẫu 12 câu hiện tại chưa thay thế tầng đó. Hàng đợi PDF có thể thu thập bản nháp lớn, nhưng chưa đủ bằng chứng để gọi toàn bộ 3.478 trang là dữ liệu chấm sạch.
