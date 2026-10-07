# EduMS API v1 Changelog

Tất cả các thay đổi về cấu trúc giao tiếp, schema, endpoint, parameter của EduMS API v1 được ghi nhận tại đây.

---

## [1.0.0] - 2026-10-07

### Đóng băng chính thức API v1 (API-V1-FREEZE)
Hoàn thành giai đoạn kiểm tra an ninh, cô lập dữ liệu và giao dịch (Backend Hardening), chính thức đóng băng hợp đồng giao diện API phiên bản 1.0.0.

#### Định danh & Cấu hình Gốc
- **Chiến lược định tuyến**: Giữ nguyên đường dẫn gốc chuẩn hóa (Canonical Root Routing) thay vì tiền tố URL `/api/v1` nhằm tương thích trực tiếp các client và tooling hiện hành. Phiên bản `1.0.0` được khai báo trong siêu dữ liệu OpenAPI (`info.version`) và `app.api.version.API_VERSION`.
- **Cơ chế xác thực**: Sử dụng lược đồ bảo mật chuẩn `HTTPBearer` với JSON Web Token (Access Token 15 phút, Refresh Token 7 ngày).
- **Mô hình phản hồi lỗi đồng nhất**: Mọi lỗi HTTP trả về cấu trúc chuẩn `ErrorResponse` bao gồm `error.code`, `error.message`, `error.details`.
- **Phân trang có giới hạn an toàn**: Toàn bộ endpoint hỗ trợ phân trang áp dụng ràng buộc `offset >= 0` và `limit` từ `1` đến `200`.

#### Phạm vi Domain & Endpoints Chính Thức
1. **Authentication (`/auth`)**:
   - Đăng ký, đăng nhập, cấp lại token (refresh), lấy thông tin người dùng hiện hành (`/auth/me`).
2. **Student & Academic Goals (`/students`)**:
   - Hồ sơ học sinh, quản lý mục tiêu học tập (`/students/me/goals`).
   - Khảo sát trạng thái học tập tích hợp (`/students/me/learning-state`).
   - Giải thích kế hoạch ngày (`/students/me/today/explanation` - phương thức `POST`).
3. **Teacher (`/teachers`)**:
   - Hồ sơ giáo viên, quản lý lớp học và tài liệu chuyên môn.
4. **Parent Portal (`/parent`)**:
   - Danh sách học sinh liên kết (`/parent/students`).
   - Tiến độ học tập tổng hợp (`/parent/students/{student_id}/progress`).
   - Dữ liệu học tập tuần (`/parent/students/{student_id}/weekly-data`).
   - Báo cáo tổng hợp AI hàng tuần (`/parent/students/{student_id}/ai-summary` - phương thức `POST`).
5. **Curriculum, Subjects & Knowledge Graph (`/curriculum`, `/subjects`, `/concepts`)**:
   - Cây chương trình GDPT 2018 theo môn, khối lớp và học kỳ.
   - Đồ thị tri thức, quan hệ tiên quyết và phân tích khoảng trống kiến thức.
6. **Question Bank & Quality Gates (`/questions`, `/question-supply`, `/question-acquisition`, `/question-validation`)**:
   - Ngân hàng câu hỏi phân tầng theo năng lực và mức độ nhận thức (Nhận biết, Thông hiểu, Vận dụng, Vận dụng cao).
   - Quy trình nhập liệu, OCR trích xuất, đối soát bản thảo và xác thực chất lượng câu hỏi.
7. **Adaptive Practice, Hints & Mastery (`/practice`, `/repair`, `/hints`, `/mastery`, `/digital-twin`)**:
   - Luyện tập thích ứng, gợi ý giải bài theo từng nấc tư duy (Scaffolded Hints).
   - Đánh giá độ thành thạo theo mô hình BKT, bản sao học tập (Digital Twin).
8. **Exams & Simulation Engine (`/exams`)**:
   - Đề thi chuẩn hóa, thi thử bấm giờ với bộ đếm thời gian chính xác tới phần nhỏ của giây (sub-second ceil).
   - Bắt đầu lượt thi (`/exams/{exam_id}/start`), nộp câu trả lời (`/answer`), nộp bài (`/submit`), xử lý hết giờ (`/exams/attempts/{attempt_id}/finalize-timeout`).
   - Lọc bảo mật đề thi: Không để lộ đáp án (`correct_answer`) hay lời giải (`explanation`) khi học sinh đang làm bài.
   - Thống kê phân tích bài thi (`/exams/attempts/{attempt_id}/analytics`) với chính sách kiểm soát quyền chặt chẽ (Admin/Student sở hữu/Teacher phụ trách lớp học hoạt động).
   - Giải thích AI sau bài thi (`/exams/attempts/{attempt_id}/ai-explanation` - phương thức `POST`).
9. **Teacher Materials & Homework (`/teacher-materials`, `/teacher/assignments`, `/students/me/assignments`)**:
   - Tải lên tài liệu giáo viên, bóc tách câu hỏi, gán nhãn chuyên môn (AI Mapping - `POST`).
   - Quản lý bài tập, chấm điểm snapshot bất biến và cập nhật bằng chứng năng lực.
10. **Tutor & Personalized Memory (`/ai/tutor`, `/tutor/sessions`)**:
    - Trợ lý gia sư AI tương tác nhiều lượt, quản lý bộ nhớ học tập dài hạn (Learning Memory).
11. **University Admission Support (`/admission`, `/students/me`)**:
    - Phân tích điểm chuẩn, tổ hợp xét tuyển và tư vấn chiến lược nguyện vọng đại học.

#### Công cụ Quản lý Contract & Hoàn thiện Tài liệu
- Đóng băng hợp đồng OpenAPI 1.0.0 với mã băm chuẩn xác: `01b558addf218c6d47a0e22d7ccd04f6d246170e8661b8d5c0fb844ea513e008`.
- Khởi tạo `export_contract` độc lập hoàn toàn với biến môi trường cục bộ và tệp `.env` (`_env_file=None`).
- Hiệu chỉnh toàn bộ các dẫn chiếu endpoint trong tài liệu hướng dẫn khớp 100% với snapshot OpenAPI máy đọc.
- Bổ sung bộ test kiểm tra tự động các cặp `METHOD /path` trong `API_V1.md`.
