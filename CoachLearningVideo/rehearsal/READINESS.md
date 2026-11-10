# Coach Learning — chuẩn bị tập quay, 2026-11-09

Đây là kết quả chuẩn bị và chạy thử; chưa phải video thành phẩm.

## Đã xác minh

- Sáu key người dùng cung cấp đều gọi generateContent thật thành công, HTTP 200 và trả JSON hợp lệ với gemini-3.6-flash. Kiểm tra metadata cho ba model trong key-pool-report.json; không suy diễn rằng mọi model đã được thử sinh nội dung.
- Key pool được parser của ứng dụng xác nhận đủ 6 credential; tên biến đúng quy ước GEMINI_KEY_*. Nhóm quota để unknown vì chưa biết nguồn project. Không cần thêm thông tin từ người dùng để tiếp tục.
- Khóa nằm trong backend/.env được Git bỏ qua; không được nhúng vào tài liệu, ảnh hoặc source video. Backend tập quay đã khởi động lại để áp dụng. Backend chính 8000 chưa được khởi động lại trong bước này.
- Dữ liệu riêng coach_video_qa_20261109 có tên học sinh, giáo viên Việt Nam và email @demo.com; không thay đổi database edums.
- Đã chạy giao diện kế hoạch, cây kiến thức, lý thuyết và Math View 3D; có ảnh riêng từng cảnh. Công thức mặt cong có tham số và lưu hình vào bài làm hoạt động.
- Desktop và thiết bị trình duyệt di động ghép nối thật; 23 nét viết đã được ACK/lưu. Đây là thao tác tự động bằng pointer, không mô tả thành bàn tay/thiết bị vật lý quay thật.
- OCR giao diện trả HTTP 200 sau 8.976 giây, giữ nguyên hai dòng y=x³−3x và y′=3x²+3. Hai bước được người dùng tự động đối chiếu/xác nhận rồi lưu thật.
- POST nhận xét thực tế trả ANSWER_GROUNDED_AI: bước 1 VALID, bước 2 INVALID; giải thích dấu của đạo hàm −3x là −3. is_final=false, final_score=null. Không gọi đây là điểm chính thức.
- PDF thật xử lý CPU mất 300.803 giây/trang; có một vùng cần đối chiếu nguồn. Không công bố bản nháp này như học liệu đã duyệt.
- Có hai mẫu nam Charon và Orus. Đánh giá tự động đề xuất Charon cho giọng Nam; chưa có xác nhận nghe bởi người dùng.

## Những vướng mắc đã xử lý

- Timeout Gemini 8 giây bị upstream từ chối; cấu hình riêng tăng timeout mỗi lần OCR lên 20 giây, tổng 60 giây.
- Tên biến tham chiếu pool ban đầu không đúng prefix được parser cho phép; đã đổi sang GEMINI_KEY_DEMO_* và kiểm tra parser thành công.
- Next.js dùng dependency junction khác ổ đĩa không biên dịch được. Bản runtime riêng chuyển vào .tmp/video-capture-frontend, chạy webpack trên 3150 và dùng backend 8050. Đây là snapshot phục vụ capture, không phải Git worktree.

## Cần khóa trước khi quay chính thức

- Màn hình phản hồi đã nghiệm thu và ảnh được kiểm tra trực quan sau khi mở toàn bộ nhận xét, thấy rõ lỗi dấu. Mở bằng nút kiểm tra trên thanh đầu trang. Có sự khác nhau với trạng thái khả dụng ở sidebar; không khẳng định toàn bộ các lối vào đã đúng. Bằng chứng cuối xem review-ui-report.json và scene-feedback.png.
- Cảnh giáo viên đã xác minh API/giao diện, 6 học sinh trong lớp và 5 học sinh được giao bài; bỏ qua hoạt cảnh chuyển phòng bằng nút có sẵn. Lần kiểm tra đầu chưa nộp cả bài nên 0 bài nộp; kết quả sau xem teacher-qa-report.json.
- Toàn bộ bài giao đã được nộp qua API thật, HTTP 200, SUBMITTED, chưa có điểm. Giữ nguyên câu viết tay và điền đáp án đúng cho hai câu còn lại. Bằng chứng whole-assignment-report.json.
- Chuẩn bị bài làm mới cho lần quay chính thức; không ghi đè hoặc xóa nét đã tập thử để giả thành luồng mới.
- Nhịp 180 giây và lời đọc V3 đã có ở NARRATION-V3.md, 557 từ theo cách đếm khoảng trắng. Chờ API/OCR được rút ngắn bằng dựng có nhãn, lời nói giữ tốc độ bình thường. Thời lượng cuối cần đo lại với audio thật.

Khởi động lại môi trường riêng khi cần: backend/.venv/Scripts/python.exe C:/CoachLearningVideo/rehearsal/launch-capture.py. Không chạy start.py cũ vì nó dùng chung frontend chính.

C?p nh?t cu?i: gi?o vi?n ?? th?y 1 b?i n?p, 0 b?i ???c duy?t ?i?m, Minh Anh ch? gi?o vi?n duy?t. ?i?m AI hi?n th? l? t?m th?i; kh?ng di?n gi?i th?nh ?i?m ?? duy?t.

L?i d?n V4 thay th? V3: ?? r?t l?i v? t?o b?n ??c ??y ?? theo timeline 180 gi?y. Ngu?n NARRATION-V4.md, narration-v4.json; b?n nghe voice-v4/narration-v4-paced-180s.mp3. Gi?ng Charon, kh?ng ch?nh t?c ??; QA t? ??ng trong voice-v4/FINAL-QA.json. Ch?a gh?p footage/video cu?i.
