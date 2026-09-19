# Question Bank

## Kiến trúc

Question Bank là một module trong backend Modular Monolith:

- `models.py` lưu `Question`, options, Concept/ProblemType/LearningOutcome mappings và các enum.
- `schemas.py` kiểm tra payload, giới hạn `difficulty`/`exam_weight`, cấu trúc option và trọng số concept.
- `service.py` giữ business rules, quyền theo người tạo, tìm kiếm và state transition.
- `router.py` chỉ nhận request, áp dụng RBAC và gọi service.

`QuestionConcept` là bảng liên kết nhiều-nhiều. Mỗi weight phải trong `(0, 1]`, concept không được lặp và tổng weight không vượt quá `1.0` (có sai số số thực nhỏ); tổng không bắt buộc bằng đúng `1.0`. Concept phải thuộc cùng subject với question.

`QuestionProblemType` cho phép nhiều mapping và tối đa một mapping chính. `QuestionLearningOutcome`
lưu yêu cầu cần đạt. Mọi target phải thuộc cùng Subject với Question. Question còn có
`source_year` nullable và `cognitive_level` nullable (`REMEMBER`, `UNDERSTAND`, `APPLY`,
`ANALYZE`).

Question nhiều lựa chọn có từ 2 đến 10 option, label và `order_index` không trùng. Các loại khác không nhận option. Khi gửi duyệt, `MULTIPLE_CHOICE` phải có đáp án trùng label, `TRUE_FALSE` phải có `TRUE` hoặc `FALSE`, `SHORT_ANSWER` phải có đáp án; `OPEN_RESPONSE` có thể không có đáp án cố định. Mọi question gửi duyệt phải có ít nhất một concept.

## Workflow và authorization

- `TEACHER` tạo question; server luôn đặt `DRAFT` và lấy `created_by` từ access token.
- Teacher chỉ thấy question của mình và question `APPROVED`; chỉ sửa bản `DRAFT` của mình.
- Chủ sở hữu gửi `DRAFT` sang `REVIEW`.
- `ADMIN` thấy toàn bộ, có thể sửa `DRAFT`/`REVIEW`, phê duyệt `REVIEW`, hoặc archive bằng PATCH chỉ chứa `{"status":"ARCHIVED"}`.
- State workflow không được đổi tùy ý qua PATCH.
- `QuestionService.get_approved_for_learning()` là cổng đọc dành cho learning engine và chỉ trả question `APPROVED`.

## API

| Method | Path | Role | Mô tả |
| --- | --- | --- | --- |
| `POST` | `/questions` | TEACHER | Tạo question `DRAFT` |
| `GET` | `/questions` | TEACHER, ADMIN | Danh sách có filter và visibility |
| `GET` | `/questions/{id}` | TEACHER, ADMIN | Chi tiết theo visibility |
| `PATCH` | `/questions/{id}` | TEACHER, ADMIN | Sửa theo ownership/status |
| `POST` | `/questions/{id}/submit-review` | TEACHER, ADMIN | `DRAFT -> REVIEW` |
| `POST` | `/questions/{id}/approve` | ADMIN | `REVIEW -> APPROVED` |

Filter của API danh sách: `subject`, `concept`, `problem_type`, `learning_outcome`,
`difficulty_min`, `difficulty_max`, `question_type`, `status`, `cognitive_level`, cùng
`offset` và `limit`.

## Migration và test

Revision `0006_question_bank` tạo `questions`, `question_options`, `question_concepts`, foreign key, unique/check constraints và index tìm kiếm. Migration đã được áp dụng lên PostgreSQL local:

```text
0009_curriculum_refactor (head)
```

Chạy lại từ `backend`:

```powershell
$env:DEBUG = 'true'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m pytest tests/questions -q
.\.venv\Scripts\python.exe -m pytest -q
```

Question Bank tests bao phủ create, validation, cả ba classification mappings, update,
ownership, visibility, RBAC, review/approval, approved-only learning lookup, filter,
database constraints và migration downgrade. Question Import có bộ test riêng.

## TODO ngoài phạm vi

Chưa triển khai UI, export, version history, review comments, moderation queue, media attachment và tích hợp Question Bank vào learning/exam engine. CSV/JSON import được mô tả tại [Question Import](QUESTION_IMPORT.md). Không có LLM trong module này.
