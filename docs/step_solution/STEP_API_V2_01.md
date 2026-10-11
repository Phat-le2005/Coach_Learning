# STEP-API-V2-01 — Math Workspace API v2

## Phạm vi

API v2 cung cấp workspace để học sinh lưu và nộp lời giải từng bước. API chỉ quản lý bản nháp và revision; việc nộp bài chỉ chuyển attempt sang `SUBMITTED`. API không chấm toán, không gọi AI, không tạo evaluation, không ghi learning evidence và không cập nhật mastery.

API v2 là FastAPI sub-application độc lập, được mount tại `/api/v2`. OpenAPI v1 vẫn thuộc app cha và giữ nguyên contract đã đóng băng.

- Swagger: `GET /api/v2/docs`
- OpenAPI: `GET /api/v2/openapi.json`
- Contract checker: `python -m app.api.v2.check_contract`
- Frozen v1 checker: `python -m app.api.check_contract`

## Authentication và dữ liệu trả về

Mọi endpoint workspace yêu cầu access token Bearer của role `STUDENT`:

```http
Authorization: Bearer <access-token>
```

Student ID luôn được suy ra từ token và `StudentProfile`; client không được gửi `student_id`. Mọi thao tác đọc hoặc ghi đều kiểm tra attempt thuộc đúng student. Attempt/step/revision không thuộc người dùng được che dưới lỗi `404` hoặc từ chối trước khi truy cập nguồn assignment.

Mọi response thành công chứa lời giải có `Cache-Control: no-store` và `Pragma: no-cache`. DTO chỉ trả dữ liệu cần dựng workspace; không trả `correct_answer`, explanation chuẩn, rubric nội bộ, teacher-only data hoặc dữ liệu lớp khác.

## Endpoints

| Method | Path | Kết quả thành công |
|---|---|---|
| `POST` | `/api/v2/math-solutions/attempts` | `201`, tạo hoặc replay idempotent attempt |
| `GET` | `/api/v2/math-solutions/attempts/{attempt_id}` | `200`, mở lại attempt |
| `POST` | `/api/v2/math-solutions/attempts/{attempt_id}/steps` | `201`, thêm bước |
| `PATCH` | `/api/v2/math-solutions/attempts/{attempt_id}/steps/{step_id}` | `200`, autosave nội dung bước |
| `POST` | `/api/v2/math-solutions/attempts/{attempt_id}/steps/{step_id}/delete` | `200`, xóa mềm |
| `POST` | `/api/v2/math-solutions/attempts/{attempt_id}/steps/{step_id}/restore` | `200`, khôi phục bước |
| `POST` | `/api/v2/math-solutions/attempts/{attempt_id}/reorder` | `200`, đổi thứ tự toàn bộ bước active |
| `GET` | `/api/v2/math-solutions/attempts/{attempt_id}/steps/{step_id}/revisions` | `200`, lịch sử revision của bước |
| `POST` | `/api/v2/math-solutions/attempts/{attempt_id}/steps/{step_id}/rollback` | `200`, tạo revision mới từ revision cũ |
| `POST` | `/api/v2/math-solutions/attempts/{attempt_id}/submit` | `200`, chuyển sang `SUBMITTED` và khóa ghi |

## Tạo attempt

Self-practice dùng câu hỏi canonical đã `APPROVED` và PracticeSession `ACTIVE` thuộc student:

```json
{
  "source_kind": "CANONICAL",
  "context_type": "SELF_PRACTICE",
  "mode": "INDEPENDENT_SOLUTION",
  "create_idempotency_key": "workspace-2d1dcbd1",
  "question_id": "00000000-0000-0000-0000-000000000001",
  "practice_session_id": "00000000-0000-0000-0000-000000000002"
}
```

Classroom assignment dùng `student_assignment_id` cùng đúng một nguồn đã giao:

- Canonical Question Bank: `question_id` + `assignment_student_question_id`.
- Snapshot PDF: `student_assignment_material_item_id`; server kiểm tra StudentAssignment, enrollment, assignment window, classroom, subject, immutable assignment snapshot và source item.

`rubric_id` chỉ được nhận khi rubric `APPROVED` và khớp đúng source. Rubric không được trả trong response.

Response attempt gồm:

```json
{
  "id": "00000000-0000-0000-0000-000000000010",
  "status": "IN_PROGRESS",
  "context_type": "SELF_PRACTICE",
  "source_kind": "CANONICAL",
  "mode": "INDEPENDENT_SOLUTION",
  "attempt_revision_number": 3,
  "question_id": "00000000-0000-0000-0000-000000000001",
  "practice_session_id": "00000000-0000-0000-0000-000000000002",
  "student_assignment_id": null,
  "assignment_student_question_id": null,
  "student_assignment_material_item_id": null,
  "steps": [],
  "started_at": "2026-10-10T10:00:00Z",
  "updated_at": "2026-10-10T10:05:00Z",
  "submitted_at": null
}
```

## Step content và artifact

Mọi request thêm/sửa bước gửi token mutation cùng nội dung:

```json
{
  "expected_attempt_revision": 3,
  "client_action_id": "00000000-0000-0000-0000-000000000020",
  "step_type": "SIGN_TABLE",
  "content_latex": "f'(x)=3(x-1)(x+1)",
  "explanation_text": "Xét dấu đạo hàm trên các khoảng.",
  "artifact": {
    "artifact_type": "SIGN_TABLE",
    "payload": {
      "critical_points": [-1, 1],
      "signs": ["+", "-", "+"]
    }
  }
}
```

Artifact được giới hạn vào các loại persistence hiện có: `SIGN_TABLE`, `VARIATION_TABLE`, `INTERVAL_SET`, `SYSTEM_OF_EQUATIONS`. Payload là JSON có cấu trúc do frontend giữ; API không diễn giải hoặc tự chấm nội dung artifact trong phase này.

Reorder phải gửi mọi active step đúng một lần:

```json
{
  "expected_attempt_revision": 5,
  "client_action_id": "00000000-0000-0000-0000-000000000021",
  "step_ids": [
    "00000000-0000-0000-0000-000000000031",
    "00000000-0000-0000-0000-000000000030"
  ]
}
```

Rollback thêm `to_revision` (bắt đầu từ 1). Delete, restore và submit chỉ cần hai trường mutation token.

## Concurrency và idempotency

- Tạo attempt dùng `create_idempotency_key`, unique theo student.
- Replay cùng key và cùng payload trả lại attempt hiện có.
- Cùng create key nhưng payload/source khác trả `409 CREATE_KEY_REUSED`.
- Mọi mutation dùng UUID `client_action_id` và `expected_attempt_revision`.
- Replay cùng action ID và cùng payload trả đúng response snapshot đã lưu, không tạo dữ liệu lần hai.
- Action ID cũ với payload khác trả `409 ACTION_KEY_REUSED`.
- Revision không còn hiện hành trả `409 SOLUTION_REVISION_CONFLICT`.
- Attempt row được khóa trong transaction; operation journal và mutation commit/rollback cùng nhau.
- Sau submit, mọi mutation trả `409 SOLUTION_LOCKED`.

Frontend nên giữ một hàng đợi mutation cho mỗi attempt, chỉ gửi mutation kế tiếp sau khi nhận `attempt_revision_number` mới. Khi nhận revision conflict, frontend tải lại attempt, hiển thị trạng thái mới và yêu cầu người dùng áp dụng lại thay đổi thay vì ghi đè.

## Error envelope

API dùng error format chung của EduMS:

```json
{
  "error": {
    "code": "SOLUTION_REVISION_CONFLICT",
    "message": "Reload the latest solution before retrying."
  }
}
```

- `401`: token thiếu/hỏng/hết hạn.
- `403`: role sai hoặc source assignment/classroom không được phép.
- `404`: attempt/step/revision không tồn tại trong phạm vi owner.
- `409`: idempotency conflict, stale revision, assignment đóng hoặc solution đã khóa.
- `422`: body/schema/source combination không hợp lệ.

## CORS

Sub-application nằm sau CORS middleware của app cha. Runtime chỉ cho origin frontend đã cấu hình và các method/header hiện được phép (`GET`, `POST`, `PATCH`, `DELETE`; `Authorization`, `Content-Type`, `Accept`).

## Chức năng chưa hỗ trợ

- Chấm điểm lời giải, StepEvaluation hoặc EvaluationDecision.
- AI grading/hint cho workspace.
- LearningEvidence, Mastery, Misconception hoặc Knowledge Tree update từ bản nháp/submit.
- Teacher review API và rubric authoring API.
- Realtime collaborative editing.
- Frontend math workspace; FE-STEP-01 sẽ tích hợp contract này.

## Kiểm thử thực tế

Tại thời điểm triển khai STEP-API-V2-01:

- `python -m app.api.check_contract`: PASS, frozen API v1 không đổi.
- `python -m app.api.v2.check_contract`: PASS.
- `pytest tests/math_solutions -q` với PostgreSQL development qua isolated temporary schemas: `27 passed`.
- API tests bao phủ docs/OpenAPI/CORS, anonymous/teacher rejection, owner isolation, cross-class PDF rejection, lifecycle đầy đủ, retry/idempotency conflict, revision conflict, transaction rollback, response redaction và no-evidence/mastery invariants.

Kết quả full regression và CI được ghi trong Pull Request của task này sau khi chạy xong.