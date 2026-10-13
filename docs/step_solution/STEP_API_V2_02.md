# STEP-API-V2-02 — Real Problem Delivery API for Math Workspace

## 1. Tổng quan & Phạm vi

Tài liệu này đặc tả và ghi nhận việc triển khai bộ API cung cấp đề bài thực tế (**Problem Delivery API**) cho **Math Solution Workspace** tại sub-application `/api/v2/math-solutions`.

Sau bản nâng cấp này, hệ thống hỗ trợ trọn vẹn vòng lặp học tập:
1. Học sinh truy cập nguồn bài tập được phân quyền (Tự luyện hoặc Bài tập lớp học).
2. Hệ thống phân phối đề bài (câu hỏi ngân hàng câu hỏi canonical hoặc mục đề cắt từ tài liệu PDF của giáo viên).
3. Học sinh tạo `SolutionAttempt` liên kết chính xác với nguồn đề đã cấp.
4. Học sinh thao tác và ghi lời giải từng bước qua API v2.
5. Học sinh tải lại Workspace (`reload`/`resume`) và xem đúng đề bài cùng toàn bộ tiến trình lời giải.
6. Học sinh nộp bài an toàn mà không làm rò rỉ đáp án hoặc cập nhật Mastery/Evidence sai thời điểm.

Tất cả các endpoint hoạt động dưới các nguyên tắc cốt lõi:
- **Zero Database Write Side-effects on Read**: Endpoint `GET /student-assignments/{id}/problems` là thuần túy đọc (pure read). Không tự ý khởi tạo bài làm, không đổi trạng thái ngầm, không tạo bản ghi mới khi đọc.
- **Explicit & Idempotent Materialization**: Khởi tạo phân bổ câu hỏi bài tập thông qua `POST /student-assignments/{id}/prepare` với cơ chế row locking (`with_for_update`). Cho phép retry nhiều lần mà không sinh câu hỏi trùng hoặc bốc thăm lại (no rerolls cho adaptive sets).
- **Atomic Validation Before Commit**: Xác thực toàn bộ câu hỏi canonical và snapshot tài liệu giáo viên trước khi commit giao dịch prepare. Nếu phát hiện snapshot hỏng hoặc câu hỏi không hợp lệ, transaction rollback hoàn toàn và không để lại dữ liệu dở dang.
- **Tuyệt đối không lộ đáp án & giải thích nội bộ (Response Redaction)**: DTO loại bỏ hoàn toàn `correct_answer`, `explanation`, `storage_key`, `is_correct`, internal rubrics, và metadata nhạy cảm của giáo viên.
- **Bắt buộc No-Store Cache-Control**: Mọi HTTP response (cả mã `200` lẫn các mã lỗi `401`, `403`, `404`, `409`, `422`) đều trả `Cache-Control: no-store` và `Pragma: no-cache`.
- **Standalone Question Enforcement**: Endpoint `next-problem` từ chối các câu hỏi chùm (`QuestionGroup`) với mã `422 QUESTION_GROUP_NOT_SUPPORTED`.

---

## 2. Kiến trúc & Sơ đồ Luồng Dữ liệu

```mermaid
flowchart TD
    subgraph Client ["Frontend: Math Workspace"]
        SP_UI["Self-Practice UI"]
        AS_UI["Classroom Assignment UI"]
        WS["Workspace Canvas (Steps & Artifacts)"]
    end

    subgraph ProblemDelivery ["API v2: Problem Delivery"]
        NP["GET .../practice-sessions/{id}/next-problem"]
        PREP["POST .../student-assignments/{id}/prepare"]
        PROBS["GET .../student-assignments/{id}/problems"]
        ATT_PROB["GET .../attempts/{id}/problem"]
        ATT_LIST["GET .../attempts"]
    end

    subgraph DataSources ["Data Layer"]
        QB[("Canonical Questions (Approved)")]
        PDF[("Teacher Material PDF Snapshots")]
        SA[("Student Assignments")]
        MSA[("Math Solution Attempts & Steps")]
    end

    SP_UI -->|1. Yêu cầu câu hỏi tiếp theo| NP
    NP -->|Lọc câu hỏi chưa làm| QB
    NP -->|Trả ProblemRead| SP_UI

    AS_UI -->|1. Chuẩn bị đề bài (Idempotent)| PREP
    PREP -->|Lock & Materialize| SA
    PREP -->|Sinh snapshot liên kết| QB
    PREP -->|Sinh snapshot liên kết| PDF

    AS_UI -->|2. Tải danh sách câu hỏi (Pure Read)| PROBS
    PROBS -->|Đọc snapshot đã prepare| SA
    PROBS -->|Trả ProblemRead[]| AS_UI

    SP_UI & AS_UI -->|3. Tạo Attempt| MSA
    WS -->|4. Đọc đề kèm lời giải| ATT_PROB
    WS -->|5. Quản lý danh sách Attempt| ATT_LIST
```

---

## 3. Đặc tả Chi tiết 5 Endpoint Mới

Mọi endpoint đều yêu cầu Header:
```http
Authorization: Bearer <student-access-token>
```

### 3.1. `GET /api/v2/math-solutions/practice-sessions/{practice_session_id}/next-problem`

Lấy câu hỏi đơn lẻ tiếp theo cho phiên tự luyện của học sinh.

- **Nghiệp vụ**:
  - Xác thực phiên tự luyện thuộc về học sinh đang đăng nhập và có trạng thái `ACTIVE`.
  - Tái sử dụng logic đủ điều kiện (`_eligible_questions`) của `PracticeService`.
  - Bỏ qua các câu hỏi đã có `QuestionAttempt` (v1) hoặc `SolutionAttempt` (v2).
  - Kiểm tra loại câu hỏi: Nếu thuộc `QuestionGroup`, trả `422 QUESTION_GROUP_NOT_SUPPORTED`.
  - Nếu hết câu hỏi phù hợp, trả `404 NO_QUESTIONS_AVAILABLE`.
- **Response thành công (`200 OK`)**:
```json
{
  "id": "8bb3805f-fc5b-4375-961d-a3d5ea9dc710",
  "source_kind": "CANONICAL",
  "context_type": "SELF_PRACTICE",
  "content": "Tìm khoảng đồng biến của hàm số $y = x^3 - 3x^2 + 2$.",
  "question_type": "MULTIPLE_CHOICE",
  "options": [
    {
      "id": "11111111-1111-1111-1111-111111111111",
      "label": "A",
      "content": "$(-\\infty; 0)$ và $(2; +\\infty)$",
      "order_index": 1
    },
    {
      "id": "22222222-2222-2222-2222-222222222222",
      "label": "B",
      "content": "$(0; 2)$",
      "order_index": 2
    }
  ],
  "order_index": null,
  "is_read_only": false,
  "question_id": "8bb3805f-fc5b-4375-961d-a3d5ea9dc710",
  "practice_session_id": "f5a4b3c2-d1e0-4987-a654-3210fedcba98",
  "assignment_id": null,
  "student_assignment_id": null,
  "assignment_student_question_id": null,
  "student_assignment_material_item_id": null,
  "source_metadata": null
}
```

---

### 3.2. `POST /api/v2/math-solutions/student-assignments/{student_assignment_id}/prepare`

Chuẩn bị (materialize) danh sách bài tập được giao cho học sinh.

- **Nghiệp vụ**:
  - Khóa dòng `student_assignment` bằng database transaction (`with_for_update`).
  - Kiểm tra trạng thái bài tập: Nếu chưa mở (`ASSIGNMENT_NOT_OPEN`), quá hạn nộp (`ASSIGNMENT_OUTSIDE_WINDOW`), hoặc đã nộp (`ASSIGNMENT_ALREADY_SUBMITTED`), trả mã lỗi `409`.
  - Hỗ trợ cả hai chế độ giao bài: `SAME_SET` (cùng đề cho cả lớp) và `ADAPTIVE_SET` (đề cá nhân hóa theo năng lực).
  - Hỗ trợ cả 2 nguồn tài liệu: Question Bank Canonical Questions và Teacher Material PDF Items.
  - Xác thực tính toàn vẹn của toàn bộ câu hỏi và snapshot trước khi commit (`atomic materialization`).
  - Idempotent: Nếu đã khởi tạo trước đó, trả lại trạng thái hiện tại ngay lập tức mà không xáo trộn lại câu hỏi.
- **Response thành công (`200 OK`)**:
```json
{
  "student_assignment_id": "c1f7b889-7cfc-4029-9e80-77a82fb99ef1",
  "status": "IN_PROGRESS",
  "item_count": 2,
  "problems": [
    {
      "id": "8bb3805f-fc5b-4375-961d-a3d5ea9dc710",
      "source_kind": "CANONICAL",
      "context_type": "CLASSROOM_ASSIGNMENT",
      "content": "Cho hàm số $y=f(x)$...",
      "question_type": "MULTIPLE_CHOICE",
      "options": [
        {
          "id": "11111111-1111-1111-1111-111111111111",
          "label": "A",
          "content": "Đồng biến trên $(1; 3)$",
          "order_index": 1
        }
      ],
      "order_index": 0,
      "is_read_only": false,
      "question_id": "8bb3805f-fc5b-4375-961d-a3d5ea9dc710",
      "practice_session_id": null,
      "assignment_id": "a0a0a0a0-bbbb-cccc-dddd-eeeeeeeeeeee",
      "student_assignment_id": "c1f7b889-7cfc-4029-9e80-77a82fb99ef1",
      "assignment_student_question_id": "e229c9db-0a42-49ce-b8eb-710899aa1234",
      "student_assignment_material_item_id": null,
      "source_metadata": null
    },
    {
      "id": "d4e5f6a7-8901-2345-6789-abcdefabcdef",
      "source_kind": "TEACHER_MATERIAL",
      "context_type": "CLASSROOM_ASSIGNMENT",
      "content": "Câu 2 (Trích đề PDF): Xét tính đơn điệu...",
      "question_type": "OPEN_RESPONSE",
      "options": [],
      "order_index": 1,
      "is_read_only": false,
      "question_id": null,
      "practice_session_id": null,
      "assignment_id": "a0a0a0a0-bbbb-cccc-dddd-eeeeeeeeeeee",
      "student_assignment_id": "c1f7b889-7cfc-4029-9e80-77a82fb99ef1",
      "assignment_student_question_id": null,
      "student_assignment_material_item_id": "d4e5f6a7-8901-2345-6789-abcdefabcdef",
      "source_metadata": {
        "title": "Phiếu bài tập Đạo hàm",
        "subject_id": "33333333-3333-3333-3333-333333333333",
        "grade_level": null,
        "page_start": 2,
        "page_end": 2
      }
    }
  ]
}
```

---

### 3.3. `GET /api/v2/math-solutions/student-assignments/{student_assignment_id}/problems`

Đọc danh sách toàn bộ bài tập thuộc về một `StudentAssignment`.

- **Nghiệp vụ**:
  - **Pure Read**: Tuyệt đối không ghi, không sửa đổi dữ liệu hoặc thay đổi trạng thái bài nộp.
  - Kiểm tra trạng thái chuẩn bị: Nếu bài tập chưa được `prepare`, trả `409 ASSIGNMENT_NOT_PREPARED`.
  - Trả về danh sách `ProblemRead[]` theo đúng thứ tự (`order_index`).
  - Cờ `is_read_only` được tính tự động: `true` nếu bài tập đã nộp (`SUBMITTED`/`GRADED`) hoặc đã qua hạn chót (`due_at`).
- **Response thành công (`200 OK`)**:
  - Trả về danh sách mảng `ProblemRead[]` như mô tả trong cấu trúc mục 3.2.

---

### 3.4. `GET /api/v2/math-solutions/attempts/{attempt_id}/problem`

Lấy nội dung đề bài tương ứng với một `SolutionAttempt` cụ thể.

- **Nghiệp vụ**:
  - Dùng để phục hồi đề bài khi học sinh tải lại (F5 / deep link) trang Workspace.
  - Kiểm tra quyền sở hữu của học sinh (`403` / `404`).
  - Tính toán `is_read_only`: `true` nếu attempt đã ở trạng thái `SUBMITTED`, hoặc assignment gốc đã khóa.
- **Response thành công (`200 OK`)**:
  - Trả về đúng đối tượng `ProblemRead` tương ứng với nguồn đề của attempt.

---

### 3.5. `GET /api/v2/math-solutions/attempts`

Lấy danh sách các bài làm (attempts) có phân trang và bộ lọc linh hoạt.

- **Query Parameters**:
  - `page`: Số trang (mặc định: `1`, tối thiểu: `1`).
  - `size`: Kích thước trang (mặc định: `20`, giới hạn `1` – `100`).
  - `question_id`: Lọc theo câu hỏi canonical.
  - `practice_session_id`: Lọc theo phiên tự luyện.
  - `student_assignment_id`: Lọc theo bài tập được giao.
  - `status`: Lọc theo trạng thái (`IN_PROGRESS`, `SUBMITTED`).
- **Response thành công (`200 OK`)**:
```json
{
  "items": [
    {
      "id": "99887766-5544-3322-1100-aabbccddeeff",
      "status": "IN_PROGRESS",
      "context_type": "SELF_PRACTICE",
      "source_kind": "CANONICAL",
      "mode": "INDEPENDENT_SOLUTION",
      "attempt_revision_number": 2,
      "question_id": "8bb3805f-fc5b-4375-961d-a3d5ea9dc710",
      "practice_session_id": "f5a4b3c2-d1e0-4987-a654-3210fedcba98",
      "student_assignment_id": null,
      "assignment_student_question_id": null,
      "student_assignment_material_item_id": null,
      "steps": [],
      "started_at": "2026-10-12T14:10:00Z",
      "updated_at": "2026-10-12T14:15:00Z",
      "submitted_at": null
    }
  ],
  "total": 1,
  "page": 1,
  "size": 20,
  "total_pages": 1
}
```

---

## 4. Hướng dẫn Tích hợp Phía Frontend

### 4.1. Vòng lặp Tự luyện (Self-Practice Flow)
1. **Lấy câu hỏi tiếp theo**:
   Gọi `GET /api/v2/math-solutions/practice-sessions/{session_id}/next-problem`.
   - Nếu nhận `200`: Hiển thị đề bài (`content`, `options`).
   - Nếu nhận `404 (NO_QUESTIONS_AVAILABLE)`: Hiển thị thông báo hoàn thành buổi luyện tập.
2. **Khởi tạo bài làm**:
   Tạo client idempotency key (ví dụ: `uuid()`).
   Gọi `POST /api/v2/math-solutions/attempts` với:
   ```json
   {
     "source_kind": "CANONICAL",
     "context_type": "SELF_PRACTICE",
     "mode": "INDEPENDENT_SOLUTION",
     "create_idempotency_key": "<uuid>",
     "question_id": "<question_id>",
     "practice_session_id": "<session_id>"
   }
   ```
3. **Thao tác giải toán & Lưu vết**:
   Gọi các API thêm/sửa/xóa bước lời giải như đã quy định trong `STEP_API_V2_01`.

### 4.2. Vòng lặp Bài tập Lớp học (Classroom Assignment Flow)
1. **Chuẩn bị danh sách bài**:
   Khi học sinh vào trang bài tập, frontend gửi:
   `POST /api/v2/math-solutions/student-assignments/{assignment_id}/prepare`
2. **Tải danh sách bài tập**:
   Gọi `GET /api/v2/math-solutions/student-assignments/{assignment_id}/problems`.
   Duyệt danh sách hiển thị cây bài tập (Question Navigator).
3. **Mở hoặc tiếp tục giải từng bài**:
   Kiểm tra `GET /api/v2/math-solutions/attempts?student_assignment_id={assignment_id}`:
   - Nếu bài đã có attempt: Mở attempt bằng `GET /attempts/{attempt_id}` và tải đề bằng `GET /attempts/{attempt_id}/problem`.
   - Nếu chưa có attempt: Tạo attempt mới với nguồn tương ứng (`CANONICAL` hoặc `TEACHER_MATERIAL`).
4. **Xử lý trạng thái khóa**:
   Nếu `is_read_only == true`, frontend chuyển giao diện sang chế độ chỉ đọc (vô hiệu hóa các nút thêm/sửa bước và nút nộp bài).

---

## 5. Ranh giới Bảo mật & Mã Lỗi Chuẩn

API sử dụng Error Envelope chung:
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable explanation"
  }
}
```

| HTTP Status | Error Code | Điều kiện kích hoạt |
|---|---|---|
| `401 Unauthorized` | `UNAUTHORIZED` | Token thiếu, hết hạn hoặc chữ ký JWT không hợp lệ. |
| `403 Forbidden` | `FORBIDDEN` | Tài khoản không phải role `STUDENT`, hoặc cố truy cập bài tập/phiên làm bài của học sinh khác / ngoài lớp học ghi danh. |
| `404 Not Found` | `NOT_FOUND` / `NO_QUESTIONS_AVAILABLE` | Thực thể không tồn tại trong database, hoặc phiên tự luyện không còn câu hỏi nào hợp lệ để phân phối. |
| `409 Conflict` | `ASSIGNMENT_NOT_PREPARED` | Cố đọc danh sách câu hỏi khi chưa gọi `prepare`. |
| `409 Conflict` | `ASSIGNMENT_NOT_OPEN` | Cố gọi `prepare`, tạo attempt hoặc mutate khi bài tập chưa đến thời điểm mở (`start_at`). |
| `409 Conflict` | `ASSIGNMENT_OUTSIDE_WINDOW` | Cố gọi `prepare`, tạo attempt hoặc mutate bước sau thời điểm hạn nộp (`due_at`). |
| `409 Conflict` | `ASSIGNMENT_ALREADY_SUBMITTED` | Cố gọi `prepare` hoặc mutate khi bài tập của học sinh đã nộp hoặc đã chấm. |
| `409 Conflict` | `MATERIAL_SNAPSHOT_MISMATCH` / `MATERIAL_SNAPSHOT_INVALID` | Snapshot tài liệu giáo viên bị hỏng, rỗng hoặc không khớp với bài giao. |
| `409 Conflict` | `CANONICAL_QUESTION_INVALID` | Câu hỏi canonical bị thu hồi trạng thái `APPROVED` hoặc không khả dụng. |
| `422 Unprocessable` | `QUESTION_GROUP_NOT_SUPPORTED` | Cố tải câu hỏi chùm (QuestionGroup) qua endpoint bài toán đơn lẻ. |

---

## 6. Các Giới Hạn Đã Biết (Known Limitations)

1. **Hiển thị File PDF Giáo viên**: Endpoint trả về metadata định vị (`title`, `page_start`, `page_end`). Frontend sử dụng API v1 có kiểm soát quyền (`GET /api/teacher-materials/{id}/file`) để tải stream tài liệu nếu cần preview trang PDF.
2. **Hỗ trợ QuestionGroup**: Nhóm câu hỏi đọc hiểu/ngữ cảnh chung (`QuestionGroup`) chưa được đưa vào Math Workspace giai đoạn này. Sẽ cần vertical slice mở rộng để biểu diễn cấu trúc đề nhiều cấp.
3. **AI Evaluation & Hinting**: Chưa kích hoạt tự động chấm hay gợi ý AI trong quá trình nộp bài.
4. **Dữ liệu Toán 12**: Data ngân hàng câu hỏi phụ thuộc vào dữ liệu có sẵn của hệ thống; việc bổ sung bài toán sẽ do sprint sư phạm tiếp theo đảm nhiệm.

---

## 7. Kết quả Kiểm thử & Nghiệm thu

- `python -m app.api.check_contract`: **PASSED** (Hợp đồng API v1 giữ nguyên vẹn 100%, 0 checksum drift).
- `python -m app.api.v2.check_contract`: **PASSED** (Hợp đồng API v2 đạt 14 endpoints chuẩn hóa).
- `pytest tests/math_solutions/test_v2_problem_delivery.py`: **14/14 PASSED**.
- `pytest tests/math_solutions/`: **46 PASSED, 2 SKIPPED**.
