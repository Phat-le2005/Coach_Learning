# Dữ liệu từ PDF phục vụ giao bài và core chấm Toán

Ngày 02/11/2026. Trạng thái: đề xuất thiết kế cho pilot PDF 57 trang; chưa phải schema API đang triển khai, chưa import hay mở khả năng chấm mới.

## 1. Quyết định chính

Mỗi bài cần một bản ghi có phiên bản gồm: đề và tài sản hiển thị; đáp án có kiểu; lời giải tham chiếu; đặc tả toán; rubric; liên kết học thuật; nguồn và trạng thái duyệt. Metadata nguồn và LaTeX trích xuất là đầu vào cho quá trình biên soạn bản ghi này. Sự tồn tại của một lời giải trong PDF chưa đủ để bật chấm tự động.

Tách ba trạng thái độc lập:

- **Extraction:** đã đọc/tách đủ nội dung và hình từ PDF chưa?
- **Academic review:** đề, đáp án, điều kiện toán, mapping và rubric đã được kiểm tra chưa?
- **Grading support:** core hiện có checker được kiểm thử cho loại câu và thao tác cần dùng chưa?

Một bài có thể đã sẵn sàng để giao/luyện nhưng chưa sẵn sàng để chấm từng bước.

## 2. Lưu ở đâu

| Loại dữ liệu | Trong pilot/Kaggle | Khi đưa vào ứng dụng |
| --- | --- | --- |
| PDF gốc, ảnh trang, crop nguồn, hình/bảng | File nguồn bất biến và assets; manifest có SHA-256 | Kho file/object storage; PostgreSQL lưu URI, hash, trang/bbox và quyền truy cập |
| Bản trích xuất và ứng viên | JSONL theo tài liệu/trang/bài, checkpoint và review log | Staging và review/promotion gate hiện có |
| Đề, đáp án, mapping, rubric đã duyệt | Export có phiên bản, kiểm tra schema | Mở rộng Question, SolutionRubric và các liên kết hiện có; đặc tả AnswerSpec/MathSpec có schema riêng |
| Kiến thức tham khảo | Knowledge card đã duyệt, điều kiện và nguồn | Document/DocumentChunk và pgvector hiện có; truy xuất theo role và concept |
| Bài làm, kết quả chấm | Không đặt vào bộ dữ liệu nguồn | SolutionAttempt, StepRevision, StepEvaluation, EvaluationDecision và LearningEvidence hiện có |

Kaggle xử lý offline; ứng dụng đọc dữ liệu đã được phát hành trong database/kho file. Embedding phục vụ tìm nguồn/gợi ý, không là tiêu chuẩn chứng minh đáp án đúng.

## 3. Nội dung cần biên soạn cho mỗi bài

1. **Student view:** đề đã kiểm tra, LaTeX hiển thị và hình/bảng được phép gửi cho học sinh. Ảnh chụp chứa đáp án đỏ, lời giải hoặc dấu đánh dấu lựa chọn cần được xử lý trước khi dùng làm đề.
2. **AnswerSpec:** NUMBER, EXPRESSION, SET, INTERVAL, OPTION hoặc BOOLEAN; đáp án chuẩn, quy tắc so sánh, đơn vị và yêu cầu làm tròn/sai số nếu đề có quy định. Kiểu này quyết định cách đọc câu trả lời; không chuẩn hóa dấu phẩy giống nhau cho một số thập phân và một khoảng.
3. **Reference solution:** một hoặc nhiều lời giải có nguồn, được duyệt; các mốc kết luận quan trọng. Chấp nhận cách giải khác tương đương khi checker đủ khả năng, thay vì bắt học sinh chép cùng chuỗi câu chữ.
4. **MathSpec:** biến, tham số và giả thiết; miền xác định; biểu thức/toán tử có cấu trúc; yêu cầu toán cần đạt. Ví dụ phân biệt biến tốc độ, hằng số dương và giới hạn miền trong bài toán thực tế. LaTeX là bản trình bày; biểu thức máy đọc phải qua parser giới hạn và kiểm tra miền.
5. **Rubric:** các tiêu chí và trọng số đã duyệt, điều kiện cần, loại checker và phiên bản checker. Không coi riêng việc có một bước mang nhãn DERIVATIVE_CALCULATION là bằng chứng tính đúng đạo hàm.
6. **Academic links:** concept_code, problem_type_code, learning_outcome_code thuộc taxonomy hiện có. Importer ánh xạ sang UUID của hệ thống; nhãn AI suy đoán vẫn là ứng viên cho tới khi duyệt.
7. **Provenance/review:** document hash, source spans riêng cho đề/đáp án/lời giải, tác giả biên soạn, người duyệt, trạng thái từng phần, phiên bản và lịch sử chỉnh sửa.

Đáp án, rubric và tham chiếu chấm là dữ liệu phía server. Response đề trước khi nộp chỉ chứa student view; không tải cả bản ghi JSON riêng tư xuống browser rồi ẩn bằng giao diện.

## 4. Định tuyến chấm theo khả năng từng bài

| Khả năng đề xuất | Điều kiện | Kết quả được phép |
| --- | --- | --- |
| DISPLAY_ONLY / TEACHER_REVIEW | Đề đủ điều kiện giao nhưng thiếu đáp án đã duyệt hoặc checker chưa hỗ trợ | Hiển thị và lưu bài làm; giáo viên đánh giá |
| ANSWER_ONLY | Đáp án và quy tắc so sánh đã duyệt, có checker phù hợp và các ca kiểm thử | Chấm đáp án cuối; không suy ra học sinh làm đúng toàn bộ phương pháp |
| STEP_VERIFIED | MathSpec và rubric đã duyệt; checker hỗ trợ đủ thao tác và có kiểm thử bước đúng/sai/cách giải khác | Kiểm chứng bước, tổng hợp rubric và quyết định chính thức theo chính sách được duyệt |

Đây là các nhãn khả năng đề xuất, không phải enum API hiện có. Cần kiểm tra trạng thái duyệt, hỗ trợ checker và phiên bản lúc runtime; không tin riêng một cờ do notebook xuất ra.

## 5. Các giới hạn đã kiểm tra trong repo

- `app/math_solutions/grading_context.py`: chấm bước hiện yêu cầu nguồn OPEN_RESPONSE được duyệt và rubric APPROVED gắn đúng nguồn. Rubric tự động hỗ trợ một tiêu chí cho mỗi loại ASSUMPTION, DERIVATIVE_CALCULATION, ROOT_FINDING, SIGN_TABLE, CONCLUSION; trọng số tổng 1.
- `app/math_solutions/evaluator_service.py`: từ chối mục tiêu ngoài phạm vi đa thức một biến được kiểm chứng; bước UNDETERMINED/NEEDS_REVIEW không tạo điểm cuối hay bằng chứng.
- `app/math_solutions/validator.py`: hiện lấy mục tiêu từ chuỗi nội dung và parser giới hạn. Đề xuất chuyển dần sang MathSpec đã duyệt, tách khỏi câu chữ của bài toán, thông qua adapter có kiểm tra tương thích.
- `app/practice/evaluation.py`: nhánh đáp án hiện so chuỗi sau NFKC/khoảng trắng/chữ hoa thường; chưa có bộ so sánh số, biểu thức, tập và khoảng tổng quát. Cần bổ sung AnswerSpec và checker tương ứng trước khi nhận các biểu diễn tương đương mới.
- `app/math_solutions/models.py`: đã có SolutionRubric với rubric_version, StepRevision và EvaluationDecision. Tận dụng các model này để mở rộng.
- `app/math_solutions/answer_grounded_ai.py`: AI review là tham khảo, không ghi điểm cuối, evidence hay mastery. Giữ ranh giới này khi thêm dữ liệu PDF.

File pilot bắt đầu ở phần trả lời ngắn. Không đổi tất cả SHORT_ANSWER sang OPEN_RESPONSE chỉ để đi qua bộ chấm bước. Nhánh chấm đáp án và nhánh tự luận cần định tuyến và kiểm thử riêng.

## 6. Ví dụ từ Câu 152

Nguồn là PDF mẫu có SHA-256 `5db1fc66ab0a42553e882981d1b22935967295b9a73cd2c96840e6ee5dd76927`, trang PDF 1–2. Ảnh nguồn ghi đáp án 15; phần này mới được đọc từ nguồn, chưa phải duyệt học thuật.

Bài có biến tốc độ v, mô hình thời gian di chuyển và biểu thức hữu tỉ. Vì vậy, có đáp án số không chứng minh bộ chấm bước đa thức hiện tại xử lý được toàn bài.

Đường triển khai đề xuất:

1. Kiểm tra lại đề, hình, đáp án và lời giải gốc.
2. Sau duyệt, tạo AnswerSpec số và ca thử cho câu trả lời hợp lệ/không hợp lệ theo định dạng đề.
3. Giao bài với khả năng chấm đáp án nếu nhánh đó đã kiểm thử.
4. Giữ chấm bước ở trạng thái chưa hỗ trợ, cho tới khi có checker mô hình hóa, miền và hữu tỉ phù hợp. Các bước chưa chứng minh được chuyển người duyệt; không gán sai chỉ vì không khớp mẫu.

## 7. Luồng runtime đề xuất

```text
PDF -> staging -> duyệt nội dung -> biên soạn AnswerSpec/MathSpec/rubric
    -> kiểm tra khả năng chấm -> phát hành bản có phiên bản
    -> giao bài và gắn cố định bản đề/spec/rubric
    -> OCR/bài làm thành các step revision đã xác nhận
    -> core kiểm chứng + rubric -> quyết định đủ điều kiện
    -> evidence -> mastery/cây tri thức
```

Đóng băng bản đề, nguồn đáp án, math spec, rubric và phiên bản engine cho mỗi lần giao/chấm. Chỉnh đáp án về sau tạo phiên bản mới, giữ khả năng truy lại kết quả cũ. Snapshot bài tập lớp hiện có là nền tảng; nguồn canonical cần đánh giá bổ sung liên kết phiên bản thay vì chỉ đọc Question đang có thể sửa.

Một lần chấm lưu step revision, verdict, rule/checker version, lý do, bằng chứng, rubric match và decision. Thao tác replay không phát thêm evidence. Điểm, decision và evidence dùng transaction phía backend theo luồng hiện có.

## 8. Thứ tự triển khai pilot

1. Chốt schema version cho một bản ghi bài toán và quy tắc phân chia dữ liệu được phép gửi học sinh/phía server.
2. Dùng PDF 57 trang tạo 120 mục ứng viên có nguồn; chưa mặc định là 120 bài đủ điều kiện chấm.
3. Duyệt trọn 10 bài: đề, đáp án, tài sản, taxonomy, mức hỗ trợ. Chuẩn bị ca đúng/sai/nhập khác định dạng/thiếu điều kiện cho từng bài.
4. Nối import và chấm đáp án theo kiểu trên một đường chạy thật.
5. Chọn 3–5 bài nằm trong phạm vi core hiện có, biên soạn rubric phù hợp và thử kiểm chứng bước. Mục tiêu chọn bài là dựa trên nội dung đã kiểm tra, không khẳng định file mẫu chắc chắn có đủ bài phù hợp.
6. Khi giao–làm–chấm–xem lại và kiểm tra quyền/phiên bản hoạt động, mở rộng từng nhóm dạng bài. Các bài ngoài phạm vi ở nhánh duyệt/giáo viên.

Các con số trong mục này là mục tiêu đề xuất, không phải kết quả pipeline/chấm đã đạt.
