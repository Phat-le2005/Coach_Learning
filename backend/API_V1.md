# EduMS Backend API v1 Specification & Contract Reference

Tài liệu này quy chuẩn toàn bộ giao thức giao tiếp của EduMS Backend phiên bản **API v1.0.0** dành cho đội ngũ phát triển Frontend, Mobile, và các dịch vụ tích hợp.

---

## 1. Thứ Bậc Thẩm Quyền Tài Liệu (Hierarchy of Authority)

Các tài liệu và thành phần đặc tả hợp đồng được quản lý theo thứ bậc ưu tiên sau:

1. `contracts/openapi-v1.json` (Nguồn chân lý chuẩn hóa máy đọc - Machine-readable Source of Truth)
2. `contracts/openapi-v1.sha256` (Mã băm toàn vẹn của hợp đồng đóng băng)
3. `app/api/version.py` (Hằng số phiên bản API `1.0.0`)
4. `backend/API_V1.md` (Tài liệu hướng dẫn con người, được xác minh tự động bằng kiểm thử)

> [!IMPORTANT]
> **Quy tắc bất biến**: Nếu có bất kỳ sự bất đồng nào giữa tài liệu mô tả ngôn ngữ tự nhiên và hợp đồng OpenAPI máy đọc, **OpenAPI luôn luôn chiến thắng (OpenAPI wins)**. Mọi endpoint dạng `METHOD /path` trong tài liệu này đều được bộ test tự động đối chiếu trực tiếp với snapshot OpenAPI đã đóng băng.

---

## 2. Nguyên Tắc Thiết Kế API & Định Tuyến (Routing Strategy)

### 2.1 Canonical Root-Path Strategy
- Hệ thống áp dụng chiến lược **Root Routing Chuẩn Hóa** (Canonical Root Routes). Các endpoint chính được nhóm theo domain chức năng trực tiếp từ gốc (`/auth`, `/students`, `/teachers`, `/teacher`, `/parent`, `/exams`, v.v.) thay vì sử dụng tiền tố URL `/api/v1/...`.
- Phiên bản API `1.0.0` được định danh chính thức trong siêu dữ liệu OpenAPI (`info.version`) và hằng số `app.api.version.API_VERSION`.
- Hợp đồng giao tiếp đóng băng tại tệp `backend/contracts/openapi-v1.json` và mã băm `backend/contracts/openapi-v1.sha256`.

### 2.2 Phương thức An toàn (Safe Methods) & Thao tác AI
- **GET (Idempotent & Safe)**: Toàn bộ thao tác truy vấn dữ liệu sử dụng phương thức `GET` không gây ra bất kỳ tác dụng phụ (side-effect) hay thay đổi trạng thái nào trong cơ sở dữ liệu.
- **POST (AI Generation & Mutations)**: Toàn bộ endpoint kích hoạt trí tuệ nhân tạo (AI generation, tóm tắt, giải thích, gợi ý) BẮT BUỘC sử dụng phương thức `POST` để đảm bảo tính an toàn giao dịch, kiểm soát tần suất gọi (rate limiting) và kiểm tra quota người dùng. Tuyệt đối không cung cấp thao tác sinh dữ liệu AI qua `GET`.

### 2.3 Ngữ nghĩa Lộ trình Học tập (Study Plan Semantics)
- `GET /students/me/today`: Đọc dữ liệu các nhiệm vụ học tập trong ngày (pure read).
- `POST /students/me/today/explanation`: Sinh nội dung giải thích lý do giao bài hôm nay bằng AI (AI generation).
- `GET /students/me/study-plan`: Đọc lộ trình học tập tổng thể hiện tại (pure read).
- `POST /students/me/study-plan/recalculate`: Yêu cầu hệ thống tính toán lại lộ trình học tập (explicit mutation).

### 2.4 Điểm tập hợp Trạng thái Học tập (Student Learning State Aggregation)
- `GET /students/me/learning-state`: Điểm tập hợp ưu tiên (Preferred Aggregation Endpoint) dành cho màn hình Student Home / Dashboard. Frontend nên bắt đầu tải dữ liệu tổng quan học sinh từ endpoint này thay vì gọi rải rác nhiều domain độc lập.

### 2.5 Ngữ nghĩa Hành động Kế tiếp khi Khắc phục Kiến thức (Repair Next Action Semantics)
- `GET /repair/adaptive/{adaptive_session_id}/next-action`: Đọc quyết định hành động kế tiếp đã được lưu vết trong phiên khắc phục (read persisted decision only).
- `POST /repair/adaptive/{adaptive_session_id}/next-action`: Phân tích trạng thái hiện tại và lưu vết quyết định hành động kế tiếp (resolve/persist decision).

### 2.6 Quy tắc Bộ đếm Thời gian & Hết giờ Thi (Exam Timer & Timeout)
- `POST /exams/attempts/{attempt_id}/finalize-timeout`: Chốt và chấm điểm lượt thi khi đã hết thời gian (idempotent).
- Quy tắc xác định hạn chót: `expires_at = started_at + duration_minutes`. Tại thời điểm `now >= expires_at`, lượt thi chính thức hết giờ.
- Hiển thị countdown sử dụng hàm làm tròn lên (`math.ceil`): còn `0.7` giây hiển thị `1`, chạm hoặc vượt deadline hiển thị `0`.
- Không áp dụng thời gian ân hạn (grace period); mọi nộp câu trả lời sau khi hết giờ đều bị từ chối bằng `409 EXAM_TIMED_OUT`.

---

## 3. Cấu Trúc Lỗi Chuẩn (Standard Error Envelope)

Mọi phản hồi lỗi HTTP (4xx, 5xx) tuân thủ cấu trúc thống nhất theo schema `ErrorResponse`:

```json
{
  "error": {
    "code": "EXAM_TIMED_OUT",
    "message": "Exam time has expired."
  }
}
```

Trong môi trường kiểm thử và phát triển (non-production/test/development), khi xảy ra lỗi xác thực dữ liệu đầu vào (Validation Error), phản hồi có thể bổ sung mảng chi tiết `details`:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "details": [
      {
        "field": "query -> limit",
        "message": "Input should be less than or equal to 200"
      }
    ]
  }
}
```

> [!NOTE]
> Trong môi trường Production, mảng `details` tự động được ẩn để tránh rò rỉ cấu trúc hệ thống nội bộ.

Hệ thống kết hợp giữa mã trạng thái HTTP tiêu chuẩn và mã định danh lỗi nghiệp vụ ổn định (`error.code`):
- `400`: Lỗi yêu cầu nghiệp vụ (ví dụ: `EXAM_NOT_TIMED_OUT`, `STUDENT_NOT_FOUND`).
- `401`: Lỗi xác thực người dùng (ví dụ: `UNAUTHORIZED`, `TOKEN_EXPIRED`).
- `403`: Không có quyền truy cập (ví dụ: `EXAM_ATTEMPT_ACCESS_DENIED`, `CLASSROOM_ACCESS_DENIED`).
- `404`: Không tìm thấy tài nguyên (ví dụ: `ATTEMPT_NOT_FOUND`, `EXAM_NOT_FOUND`).
- `409`: Xung đột trạng thái giao dịch (ví dụ: `EXAM_TIMED_OUT`, `CONFLICT`).
- `422`: Lỗi cấu trúc schema tham số đầu vào (`VALIDATION_ERROR`).
- `503`: Dịch vụ phụ thuộc không sẵn sàng (`SERVICE_NOT_READY`).

---

## 4. Kiểm Tra Tình Trạng Hệ Thống (Health & Readiness)

- `GET /health`: Kiểm tra liveness của backend (trả về `200 OK` tức thời, độc lập với cơ sở dữ liệu và AI).
- `GET /ready`: Kiểm tra readiness của cơ sở dữ liệu PostgreSQL. Nếu database không kết nối được, trả về `503 SERVICE_NOT_READY`. Sự cố từ nhà cung cấp AI bên ngoài không làm ảnh hưởng đến trạng thái readiness toàn cục của backend.

---

## 5. Xác Thực & Bảo Mật (Authentication & Security)

- **Lược đồ bảo mật**: Chuẩn `HTTPBearer` (Header: `Authorization: Bearer <access_token>`).
- **Thời hạn Token mặc định**:
  - `access_token`: Cấu hình mặc định hiện hành 15 phút.
  - `refresh_token`: Cấu hình mặc định hiện hành 7 ngày.
  *(Lưu ý: Đây là giá trị cấu hình vận hành, không phải bất biến giao thức bất khả biến).*
- **Phân quyền vai trò (Role-Based Access Control)**:
  - `ADMIN`: Quản trị toàn hệ thống.
  - `TEACHER`: Giáo viên phụ trách lớp học, tài liệu, bài tập và đề thi.
  - `STUDENT`: Học sinh tham gia lớp, thực hiện bài tập, luyện tập và thi thử.
  - `PARENT`: Phụ huynh theo dõi tiến độ của học sinh được liên kết.
- **Bảo mật đề thi học sinh**:
  - Khi học sinh đang làm bài thi (`IN_PROGRESS`), danh sách câu hỏi trả về được làm sạch (`ExamQuestionSanitizedRead`), tuyệt đối không chứa trường `correct_answer` hoặc `explanation`.

---

## 6. Quy Chuẩn Phân Trang An Toàn (Bounded Pagination)

Mọi endpoint danh sách hỗ trợ phân trang đều áp dụng ràng buộc tham số chặt chẽ:
- `offset`: Số lượng bản ghi bỏ qua, `offset >= 0` (mặc định: `0`).
- `limit`: Số lượng bản ghi tối đa trả về, `1 <= limit <= 200` (mặc định thông thường: `20`, `50` hoặc `100`).

Hệ thống từ chối các yêu cầu có `limit > 200` hoặc `limit < 1` bằng lỗi `422 Unprocessable Entity` để bảo vệ tài nguyên máy chủ.

---

## 7. Tổng Quan Các Nhóm Endpoint Chính (Major Endpoint Groups)

### 7.1 Authentication (`/auth`)
- `POST /auth/register`: Đăng ký tài khoản người dùng mới.
- `POST /auth/login`: Xác thực và nhận cặp `access_token` / `refresh_token`.
- `POST /auth/refresh`: Cấp lại `access_token` từ `refresh_token` hợp lệ.
- `GET /auth/me`: Lấy thông tin tài khoản đang đăng nhập.

### 7.2 Students, Goals & Study Planning (`/students`)
- `GET /students/me`: Lấy hồ sơ học sinh của tài khoản hiện tại.
- `GET /students/me/goals`: Danh sách mục tiêu học tập cá nhân.
- `POST /students/me/goals`: Tạo mục tiêu học tập mới.
- `PATCH /students/me/goals/{id}`: Cập nhật mục tiêu học tập.
- `GET /students/me/learning-state`: Trạng thái học tập tổng hợp (nhiệm vụ hôm nay, chỉ số thành thạo, điểm yếu cần củng cố).
- `GET /students/me/today`: Nhiệm vụ học tập cần hoàn thành hôm nay.
- `POST /students/me/today/explanation`: Giải thích kế hoạch học tập hôm nay bằng AI.
- `GET /students/me/study-plan`: Lộ trình học tập tổng thể của học sinh.
- `POST /students/me/study-plan/recalculate`: Tính toán lại lộ trình học tập.
- `GET /students/me/classes`: Danh sách lớp học mà học sinh đang tham gia.

### 7.3 Parent Portal (`/parent`)
- `GET /parent/students`: Danh sách học sinh liên kết với tài khoản phụ huynh.
- `GET /parent/students/{student_id}/progress`: Tổng quan tiến độ học tập của học sinh.
- `GET /parent/students/{student_id}/weekly-data`: Dữ liệu phân tích chi tiết trong tuần.
- `POST /parent/students/{student_id}/ai-summary`: Báo cáo tổng kết tuần sinh bởi AI cho phụ huynh.

### 7.4 Teachers & Classroom Management (`/teachers`, `/teacher/classes`)
- `GET /teachers/me`: Hồ sơ giáo viên hiện tại.
- `PATCH /teachers/me`: Cập nhật thông tin giáo viên.
- `GET /teacher/classes`: Danh sách lớp học do giáo viên phụ trách.
- `POST /teacher/classes`: Tạo lớp học mới.
- `GET /teacher/classes/{id}`: Chi tiết lớp học.
- `GET /teacher/classes/{id}/students`: Danh sách học sinh trong lớp.
- `POST /teacher/classes/{id}/students`: Tiếp nhận học sinh vào lớp học.

### 7.5 Teacher Analytics & Classroom Insights (`/teacher/classes`)
- `GET /teacher/classes/{id}/analytics`: Báo cáo phân tích tổng quan của lớp học.
- `GET /teacher/classes/{id}/heatmap`: Bản đồ nhiệt mức độ thành thạo kiến thức của lớp.
- `GET /teacher/classes/{id}/alerts`: Cảnh báo học sinh có nguy cơ hổng kiến thức hoặc sa sút.
- `GET /teacher/classes/{id}/students/{student_id}/analytics`: Phân tích chuyên sâu học sinh cụ thể trong lớp.
- `GET /teacher/classes/{id}/assignments/{assignment_id}/analytics`: Thống kê kết quả theo từng bài tập của lớp.
- `POST /teacher/classes/{id}/copilot`: Trợ lý AI đồng hành phân tích và đề xuất can thiệp sư phạm.

### 7.6 Assignments Management (`/teacher/assignments`, `/students/me/assignments`)
- `GET /teacher/classes/{classroom_id}/assignments`: Danh sách bài tập được giao cho lớp.
- `POST /teacher/classes/{classroom_id}/assignments`: Tạo đợt giao bài tập mới cho lớp.
- `GET /teacher/assignments/{assignment_id}`: Chi tiết bài tập.
- `PATCH /teacher/assignments/{assignment_id}`: Chỉnh sửa cấu hình bài tập.
- `POST /teacher/assignments/{assignment_id}/publish`: Phát hành bài tập tới học sinh.
- `POST /teacher/assignments/{assignment_id}/close`: Đóng hạn nộp bài tập.
- `GET /teacher/assignments/{assignment_id}/submissions`: Danh sách bài nộp của học sinh.
- `POST /teacher/assignments/{assignment_id}/students/{student_id}/material-items/{student_material_item_id}/grade`: Giáo viên chấm điểm và xác nhận bằng chứng học tập.
- `GET /students/me/assignments`: Danh sách bài tập của học sinh.
- `GET /students/me/assignments/{assignment_id}`: Chi tiết bài tập học sinh cần làm.
- `POST /students/me/assignments/{assignment_id}/submit`: Nộp bài tập học sinh.

### 7.7 Mastery & Digital Twin (`/students/me`, `/teacher/students`)
- `GET /students/me/mastery`: Mức độ thành thạo tổng thể của học sinh.
- `GET /students/me/mastery/concepts/{concept_id}`: Mức độ thành thạo theo khái niệm cụ thể.
- `GET /students/me/mastery/problem-types/{problem_type_id}`: Mức độ thành thạo theo dạng bài toán.
- `GET /teacher/students/{student_id}/mastery`: Giáo viên tra cứu mức độ thành thạo của học sinh.
- `GET /students/me/digital-twin`: Bản sao số học tập phản ánh năng lực và dự báo kết quả của học sinh.
- `GET /teacher/students/{student_id}/digital-twin`: Giáo viên tra cứu bản sao số của học sinh.

### 7.8 Adaptive Practice, Hints & Knowledge Repair (`/practice`, `/repair`)
- `POST /practice/sessions`: Khởi tạo phiên luyện tập thích ứng theo vùng phát triển gần nhất.
- `POST /practice/questions/{question_id}/hint`: Yêu cầu gợi ý giàn giáo (scaffolded hint) theo từng bước tư duy.
- `POST /practice/attempts/{attempt_id}/ai-evaluate`: Đánh giá câu trả lời tự luận trong phiên luyện tập bằng AI.
- `POST /repair/sessions`: Khởi tạo phiên khắc phục lỗ hổng kiến thức.
- `GET /repair/sessions/{session_id}`: Chi tiết phiên khắc phục kiến thức.
- `POST /repair/sessions/{session_id}/steps/{step_number}/answer`: Nộp câu trả lời từng bước khắc phục.
- `POST /repair/sessions/{session_id}/complete`: Hoàn thành phiên khắc phục kiến thức.
- `GET /repair/adaptive/{adaptive_session_id}`: Trạng thái phiên khắc phục thích ứng.
- `GET /repair/adaptive/{adaptive_session_id}/next-action`: Đọc quyết định hành động kế tiếp đã lưu vết.
- `POST /repair/adaptive/{adaptive_session_id}/next-action`: Phân tích và quyết định hành động kế tiếp.
- `POST /repair/adaptive/{adaptive_session_id}/current/answer`: Trả lời câu hỏi hiện tại trong phiên thích ứng.
- `POST /repair/adaptive/{adaptive_session_id}/retry`: Thử lại bước chưa đạt yêu cầu.

### 7.9 AI Socratic Tutor vs Learning Memory Sessions (`/ai/tutor`, `/tutor/sessions`)
- **AI Socratic Tutor**:
  - `POST /ai/tutor`: Tương tác trực tiếp với gia sư ảo Socratic hỗ trợ giải đáp thắc mắc bài học.
- **Learning Memory / Tutor Sessions**:
  - `POST /tutor/sessions`: Khởi tạo phiên tương tác gia sư có lưu trữ bộ nhớ học tập dài hạn.
  - `POST /tutor/sessions/{session_id}/turn`: Gửi lượt trò chuyện trong phiên gia sư có ngữ cảnh bộ nhớ.
  - `POST /tutor/sessions/{session_id}/end`: Kết thúc phiên gia sư và chốt cập nhật bộ nhớ học tập.

### 7.10 Curriculum & Subjects (`/admin`)
- `GET /admin/curricula`: Danh mục các chương trình giáo dục.
- `GET /admin/curriculum-versions`: Danh sách các phiên bản chương trình giáo dục.
- `GET /admin/subjects`: Danh sách môn học trong chương trình.
- `GET /admin/subjects/{subject_id}/chapters`: Danh sách chương của môn học.
- `GET /admin/subjects/{subject_id}/curriculum-tree`: Cây phân cấp chương trình hoàn chỉnh theo môn học.

### 7.11 Question Bank & Quality Pipeline (`/questions`, `/question-supply`, `/question-acquisition`, `/question-validation`)
- `GET /questions`: Tra cứu ngân hàng câu hỏi theo môn học, dạng bài và mức độ nhận thức.
- `GET /question-supply/gaps`: Danh sách khoảng trống câu hỏi cần bổ sung.
- `GET /question-supply/gaps/{gap_id}`: Chi tiết khoảng trống câu hỏi cụ thể.
- `POST /question-supply/gaps/{gap_id}/reassess`: Đánh giá lại khoảng trống câu hỏi.
- `POST /question-supply/gaps/reassess-open`: Đánh giá lại toàn bộ khoảng trống đang mở.
- `POST /question-supply/gaps/{gap_id}/acquisition`: Lập yêu cầu thu thập câu hỏi bù đắp khoảng trống.
- `POST /question-supply/assess`: Đánh giá tổng thể độ phủ ngân hàng câu hỏi.
- `GET /question-acquisition/requests`: Danh sách yêu cầu thu thập tài liệu câu hỏi.
- `GET /question-acquisition/requests/{request_id}`: Chi tiết yêu cầu thu thập câu hỏi.
- `POST /question-acquisition/requests/{request_id}/sources`: Thêm nguồn tài liệu thu thập.
- `POST /question-acquisition/requests/{request_id}/artifacts/upload`: Tải lên tệp tài liệu câu hỏi thu thập.
- `POST /question-acquisition/requests/{request_id}/cancel`: Hủy yêu cầu thu thập câu hỏi.
- `POST /question-acquisition/sources/{source_id}/fetch`: Kích hoạt lấy dữ liệu từ nguồn thu thập.
- `POST /question-acquisition/sources/{source_id}/block`: Chặn nguồn tài liệu thu thập không hợp lệ.
- `POST /question-validation/acquisition-requests/{request_id}/batches`: Tạo lô thẩm định câu hỏi từ yêu cầu thu thập.
- `GET /question-validation/batches`: Danh sách các lô thẩm định câu hỏi.
- `GET /question-validation/batches/{batch_id}`: Chi tiết lô thẩm định câu hỏi.
- `POST /question-validation/batches/{batch_id}/candidates`: Đăng ký câu hỏi ứng viên vào lô thẩm định.
- `GET /question-validation/candidates/{candidate_id}`: Chi tiết câu hỏi ứng viên.
- `PATCH /question-validation/candidates/{candidate_id}`: Hiệu chỉnh nội dung hoặc phân loại câu hỏi ứng viên.
- `POST /question-validation/candidates/{candidate_id}/validate`: Chạy quy trình kiểm thử tự động cho câu hỏi ứng viên.
- `POST /question-validation/candidates/{candidate_id}/reviews`: Ghi nhận đánh giá chuyên môn của chuyên gia.
- `POST /question-validation/candidates/{candidate_id}/promote`: Phê duyệt đưa câu hỏi ứng viên vào ngân hàng chính thức.
- `POST /question-validation/candidates/{candidate_id}/reject`: Từ chối câu hỏi ứng viên không đạt chất lượng.

### 7.12 Teacher Materials (`/teacher-materials`)
- `POST /teacher-materials/upload`: Tải lên tài liệu giảng dạy của giáo viên (PDF, DOCX).
- `GET /teacher-materials`: Danh sách tài liệu giảng dạy đã tải lên.
- `GET /teacher-materials/{material_id}`: Chi tiết tài liệu giảng dạy.
- `GET /teacher-materials/{material_id}/items`: Danh sách các câu hỏi bóc tách từ tài liệu.
- `PATCH /teacher-materials/items/{item_id}`: Cập nhật nội dung câu hỏi bóc tách.
- `POST /teacher-materials/{material_id}/map`: Đề xuất ánh xạ khái niệm và chuẩn hóa câu hỏi bằng AI.
- `POST /teacher-materials/{material_id}/ready`: Xác nhận tài liệu đã sẵn sàng để giao bài tập.

### 7.13 Exams & Timed Simulation Engine (`/exams`)
- `GET /exams`: Danh sách đề thi đã xuất bản.
- `POST /exams`: Giáo viên tạo đề thi mới.
- `POST /exams/{exam_id}/start`: Bắt đầu hoặc tiếp tục lượt thi (bộ đếm giờ chính xác sub-second ceil).
- `GET /exams/attempts/{attempt_id}`: Trạng thái lượt thi hiện tại và danh sách câu hỏi đã được làm sạch.
- `POST /exams/attempts/{attempt_id}/answer`: Ghi nhận câu trả lời của học sinh.
- `POST /exams/attempts/{attempt_id}/submit`: Nộp bài thi (tính điểm xác định, cập nhật độ thành thạo nếu đúng hạn).
- `POST /exams/attempts/{attempt_id}/finalize-timeout`: Chốt và chấm lượt thi khi hết thời gian quy định (idempotent).
- `GET /exams/attempts/{attempt_id}/analytics`: Báo cáo phân tích kết quả bài thi theo chính sách quyền hạn nghiêm ngặt.
- `POST /exams/attempts/{attempt_id}/ai-explanation`: Phân tích chuyên sâu bài làm bằng AI sau khi kết thúc lượt thi.

### 7.14 University Admission Advisory (`/admission`, `/students/me`)
- `GET /admission/universities`: Tra cứu danh sách trường đại học và điểm chuẩn.
- `POST /admission/universities`: Quản trị viên thêm trường đại học mới.
- `GET /admission/universities/{id}/majors`: Danh sách ngành đào tạo của trường đại học.
- `POST /admission/majors`: Thêm ngành đào tạo đại học.
- `GET /admission/majors/{id}/rules`: Quy chế xét tuyển của ngành đào tạo.
- `POST /admission/rules`: Thiết lập quy chế xét tuyển.
- `POST /students/me/admission-assistant`: Trợ lý AI tư vấn chiến lược nguyện vọng và định hướng tuyển sinh đại học.
- `GET /students/me/admission-targets`: Danh sách mục tiêu nguyện vọng đại học của học sinh.
- `POST /students/me/admission-targets`: Thêm mục tiêu nguyện vọng đại học mới.
- `DELETE /students/me/admission-targets/{id}`: Xóa mục tiêu nguyện vọng đại học.
- `PATCH /students/me/admission-targets/{id}`: Cập nhật thông tin mục tiêu nguyện vọng đại học.

---

## 8. Hướng Dẫn Kiểm Tra & Đóng Băng Hợp Đồng

```bash
# Kiểm tra tính toàn vẹn hợp đồng so với mã nguồn:
python -m app.api.check_contract

# Khi có thay đổi schema chủ đích, cập nhật và đóng băng lại:
python -m app.api.export_contract
```
