# EduMS Backend API v1 Specification & Contract Reference

Tài liệu này quy chuẩn toàn bộ giao thức giao tiếp của EduMS Backend phiên bản **API v1.0.0** dành cho đội ngũ phát triển Frontend, Mobile, và các dịch vụ tích hợp.

---

## 1. Nguyên Tắc Thiết Kế API & Định Tuyến (Routing Strategy)

### 1.1 Canonical Root-Path Strategy
- Hệ thống áp dụng chiến lược **Root Routing Chuẩn Hóa** (Canonical Root Routes). Các endpoint chính được nhóm theo domain chức năng trực tiếp từ gốc (`/auth`, `/students`, `/teachers`, `/parent`, `/exams`, v.v.) thay vì sử dụng tiền tố URL `/api/v1/...`.
- Phiên bản API `1.0.0` được định danh chính thức trong siêu dữ liệu OpenAPI (`info.version`) và hằng số `app.api.version.API_VERSION`.
- Hợp đồng giao tiếp đóng băng tại tệp `backend/contracts/openapi-v1.json` và mã băm `backend/contracts/openapi-v1.sha256`.

### 1.2 Phương thức An toàn (Safe Methods) & Thao tác AI
- **GET (Idempotent & Safe)**: Toàn bộ thao tác truy vấn dữ liệu sử dụng phương thức `GET` không gây ra bất kỳ tác dụng phụ (side-effect) hay thay đổi trạng thái nào trong cơ sở dữ liệu.
- **POST (AI Generation & Side-Effects)**: Toàn bộ endpoint kích hoạt trí tuệ nhân tạo (AI generation, tóm tắt, giải thích, overlay, gợi ý) BẮT BUỘC sử dụng phương thức `POST` để đảm bảo tính an toàn giao dịch, kiểm soát tần suất gọi (rate limiting) và kiểm tra quota người dùng. Tuyệt đối không cung cấp thao tác sinh dữ liệu AI qua `GET`.

---

## 2. Xác Thực & Bảo Mật (Authentication & Security)

- **Lược đồ bảo mật**: Chuẩn `HTTPBearer` (Header: `Authorization: Bearer <access_token>`).
- **Thời hạn Token**:
  - `access_token`: 15 phút.
  - `refresh_token`: 7 ngày.
- **Phân quyền vai trò (Role-Based Access Control)**:
  - `ADMIN`: Toàn quyền hệ thống.
  - `TEACHER`: Quản lý lớp học, học sinh thuộc lớp, tài liệu, đề thi, chấm bài tập.
  - `STUDENT`: Thực hiện bài thi, luyện tập thích ứng, nhận kế hoạch học tập cá nhân hóa.
  - `PARENT`: Truy cập Parent Portal xem tiến độ học tập của con em liên kết.
- **Bảo mật đề thi học sinh**:
  - Trong quá trình học sinh làm bài thi (`IN_PROGRESS`), danh sách câu hỏi trả về được làm sạch (`ExamQuestionSanitizedRead`), tuyệt đối không để lộ trường `correct_answer` hoặc `explanation`.

---

## 3. Cấu Trúc Lỗi Chuẩn (Standard Error Envelope)

Mọi phản hồi lỗi HTTP (4xx, 5xx) tuân thủ cấu trúc thống nhất theo schema `ErrorResponse`:

```json
{
  "error": {
    "code": "EXAM_TIMED_OUT",
    "message": "Exam attempt has timed out.",
    "details": {}
  }
}
```

### Các mã lỗi chuẩn thông dụng:
- `400 BAD_REQUEST`: Tham số yêu cầu không hợp lệ hoặc logic nghiệp vụ không thỏa mãn.
- `401 UNAUTHORIZED`: Thiếu token hoặc token không hợp lệ / hết hạn.
- `403 FORBIDDEN` / `EXAM_ATTEMPT_ACCESS_DENIED`: Người dùng không có quyền truy cập tài nguyên.
- `404 NOT_FOUND` / `ATTEMPT_NOT_FOUND`: Tài nguyên không tồn tại hoặc bị ẩn theo chính sách bảo mật.
- `409 CONFLICT` / `EXAM_TIMED_OUT`: Xung đột trạng thái giao dịch hoặc hết thời gian làm bài thi.
- `422 UNPROCESSABLE_ENTITY`: Lỗi xác thực cấu trúc dữ liệu đầu vào theo Pydantic schema.
- `503 SERVICE_NOT_READY`: Dịch vụ phụ thuộc (Database, AI) tạm thời không khả dụng.

---

## 4. Quy Chuẩn Phân Trang An Toàn (Bounded Pagination)

Mọi endpoint danh sách hỗ trợ phân trang đều áp dụng ràng buộc tham số chặt chẽ:
- `offset`: Số lượng bản ghi bỏ qua, `offset >= 0` (mặc định: `0`).
- `limit`: Số lượng bản ghi tối đa trả về, `1 <= limit <= 200` (mặc định thông thường: `20` hoặc `50`).

Hệ thống từ chối các yêu cầu có `limit > 200` hoặc `limit < 1` bằng lỗi `422 Unprocessable Entity` để bảo vệ tài nguyên máy chủ.

---

## 5. Tổng Quan Các Nhóm Endpoint Chính (Major Endpoint Groups)

### 5.1 Authentication (`/auth`)
- `POST /auth/register`: Đăng ký tài khoản người dùng mới.
- `POST /auth/login`: Xác thực và nhận cặp `access_token` / `refresh_token`.
- `POST /auth/refresh`: Cấp lại `access_token` từ `refresh_token` hợp lệ.
- `GET /auth/me`: Lấy thông tin tài khoản đang đăng nhập.

### 5.2 Students & Learning State (`/students`)
- `GET /students/me`: Lấy hồ sơ học sinh của tài khoản hiện tại.
- `GET /students/me/goals`: Danh sách mục tiêu học tập cá nhân.
- `POST /students/me/goals`: Tạo mục tiêu học tập mới.
- `PATCH /students/me/goals/{goal_id}`: Cập nhật mục tiêu học tập.
- `GET /students/me/learning-state`: Trạng thái học tập tổng hợp (nhiệm vụ hôm nay, chỉ số thành thạo, điểm yếu cần củng cố).
- `POST /students/me/today/explanation`: Giải thích kế hoạch học tập hôm nay bằng AI.

### 5.3 Parent Portal (`/parent`)
- `GET /parent/students`: Danh sách học sinh liên kết với tài khoản phụ huynh.
- `GET /parent/students/{student_id}/progress`: Tổng quan tiến độ học tập của học sinh.
- `GET /parent/students/{student_id}/weekly-data`: Dữ liệu phân tích chi tiết trong tuần.
- `POST /parent/students/{student_id}/ai-summary`: Báo cáo tổng kết tuần sinh bởi AI cho phụ huynh.

### 5.4 Teachers & Classroom Management (`/teachers`, `/classes`, `/teacher-materials`)
- `GET /teachers/me`: Hồ sơ giáo viên hiện tại.
- `POST /classes`: Tạo lớp học mới.
- `GET /classes/{class_id}`: Chi tiết lớp học và danh sách học sinh theo trạng thái enrollment.
- `POST /teacher-materials/upload`: Tải lên tài liệu giảng dạy (PDF, DOCX).
- `POST /teacher-materials/{material_id}/map`: Đề xuất ánh xạ khái niệm và chuẩn hóa câu hỏi tài liệu bằng AI.
- `POST /assignments`: Giao bài tập cho lớp học hoặc từng học sinh.
- `POST /assignments/{assignment_id}/grade`: Giáo viên chấm bài tập và ghi nhận bằng chứng thành thạo.

### 5.5 Curriculum, Subjects & Knowledge Graph (`/curriculum`, `/subjects`, `/concepts`)
- `GET /curriculum`: Danh mục chương trình GDPT 2018 theo môn và khối lớp.
- `GET /subjects`: Danh sách môn học.
- `GET /concepts`: Danh mục khái niệm kiến thức và cây tiên quyết.
- `GET /concepts/{concept_id}/graph`: Đồ thị quan hệ kiến thức lân cận.

### 5.6 Question Bank & Quality Pipeline (`/questions`, `/question-supply`, `/question-acquisition`, `/question-validation`)
- `GET /questions`: Tra cứu ngân hàng câu hỏi theo môn học, dạng bài và mức độ nhận thức.
- `POST /question-supply/items`: Đề xuất câu hỏi vào kho.
- `POST /question-acquisition/jobs`: Nhập câu hỏi từ tệp tin hoặc nguồn ngoài.
- `POST /question-validation/items/{item_id}/review`: Kiểm định chất lượng nội dung và chuẩn hóa đáp án.

### 5.7 Exams & Timed Simulation Engine (`/exams`)
- `POST /exams`: Giáo viên tạo đề thi mới.
- `GET /exams`: Danh sách đề thi đã xuất bản.
- `POST /exams/{exam_id}/start`: Bắt đầu hoặc tiếp tục lượt thi (bộ đếm giờ chính xác sub-second ceil).
- `GET /exams/attempts/{attempt_id}`: Trạng thái lượt thi hiện tại và danh sách câu hỏi đã được làm sạch.
- `POST /exams/attempts/{attempt_id}/answer`: Ghi nhận câu trả lời của học sinh.
- `POST /exams/attempts/{attempt_id}/submit`: Nộp bài thi (tính điểm xác định, cập nhật độ thành thạo nếu đúng hạn).
- `POST /exams/attempts/{attempt_id}/finalize-timeout`: Chốt lượt thi khi hết thời gian quy định (idempotent).
- `GET /exams/attempts/{attempt_id}/analytics`: Báo cáo phân tích kết quả bài thi theo chính sách quyền hạn nghiêm ngặt.
- `POST /exams/attempts/{attempt_id}/ai-explanation`: Phân tích chuyên sâu bài làm bằng AI sau khi kết thúc lượt thi.

### 5.8 Adaptive Practice, Mastery & Digital Twin (`/practice`, `/repair`, `/hints`, `/mastery`, `/digital-twin`)
- `POST /practice/sessions`: Khởi tạo phiên luyện tập thích ứng theo vùng phát triển gần nhất.
- `POST /hints/request`: Nhận gợi ý giải bài theo từng cấp độ tư duy.
- `GET /mastery/student`: Báo cáo độ thành thạo hiện tại của học sinh theo từng khái niệm.
- `GET /digital-twin/summary`: Bản sao học tập phản ánh toàn diện năng lực và dự đoán kết quả thi.

### 5.9 AI Tutor & Learning Memory (`/tutor`)
- `POST /tutor/sessions`: Tạo phiên tương tác với trợ lý học tập AI.
- `POST /tutor/chat`: Trò chuyện giải đáp thắc mắc bài học.
- `GET /tutor/memories`: Danh sách ghi nhớ học tập được AI trích xuất và xác nhận.

### 5.10 University Admission Advisory (`/admission`)
- `GET /admission/universities`: Tra cứu danh sách trường đại học và lịch sử điểm chuẩn.
- `POST /students/me/admission-assistant`: Trợ lý AI tư vấn chiến lược nguyện vọng và định hướng tuyển sinh đại học.

---

## 6. Hướng Dẫn Kiểm Tra & Đóng Băng Hợp Đồng

```bash
# Kiểm tra tính toàn vẹn hợp đồng so với mã nguồn:
python -m app.api.check_contract

# Khi có thay đổi schema chủ đích, cập nhật và đóng băng lại:
python -m app.api.export_contract
```
