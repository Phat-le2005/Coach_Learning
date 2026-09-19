# Question Data Import Pipeline

## Luồng xử lý

Pipeline chạy hoàn toàn deterministic, không gọi AI:

```text
upload -> parse -> schema validation -> subject/version validation
       -> problem type/concept/learning outcome validation
       -> duplicate detection -> preview -> confirm import
```

Preview lưu một `QuestionImportBatch` và các `QuestionImportRow` trong PostgreSQL. Dữ liệu confirm được đọc lại từ staging đã validate, không nhận lại nội dung question từ client. Confirm khóa batch, kiểm tra concept và duplicate lần cuối, sau đó tạo toàn bộ question trong một transaction.

Import thường tạo question `DRAFT`. Chỉ ADMIN được đặt `trusted_seed_data=true`; các dòng hợp lệ trong batch đó được tạo trực tiếp ở trạng thái `APPROVED`.

## API

| Method | Path | Role | Mô tả |
| --- | --- | --- | --- |
| `POST` | `/questions/import/preview` | TEACHER, ADMIN | Upload file multipart và tạo preview |
| `POST` | `/questions/import/{batch_id}/confirm` | Chủ batch | Import các dòng hợp lệ |

Preview nhận multipart field `file` và query parameter tùy chọn `trusted_seed_data=false`. File phải có phần mở rộng `.csv` hoặc `.json`, mã hóa UTF-8, tối đa 5 MiB và 5.000 dòng. Confirm idempotent: gọi lại một batch đã import trả report hiện tại và không tạo duplicate.

## Định dạng dữ liệu

JSON là một array các object, hoặc object chỉ chứa key `questions` có giá trị là array. Mỗi row dùng các field:

```json
{
  "subject_code": "MATH12",
  "curriculum_version_code": "GDPT2018_2018",
  "content": "Đạo hàm của x^2 là gì?",
  "question_type": "MULTIPLE_CHOICE",
  "difficulty": 0.4,
  "correct_answer": "B",
  "explanation": "Áp dụng quy tắc lũy thừa.",
  "source": "TEACHER",
  "source_reference": "Lesson 1",
  "source_year": 2026,
  "cognitive_level": "APPLY",
  "exam_weight": 0.6,
  "options": [
    {"label": "A", "content": "x", "order_index": 0},
    {"label": "B", "content": "2x", "order_index": 1}
  ],
  "concepts": [
    {"code": "DERIVATIVE", "weight": 0.7},
    {"code": "FUNCTION", "weight": 0.3}
  ],
  "problem_types": [
    {"code": "MONOTONICITY_FROM_EXPRESSION", "weight": 1.0, "is_primary": true}
  ],
  "learning_outcomes": [
    {"code": "LO_MONOTONICITY", "weight": 1.0}
  ]
}
```

CSV dùng cùng tên cột. `options`, `concepts`, `problem_types` và `learning_outcomes`
phải là JSON array hợp lệ. Các field optional có thể để trống.

Pipeline kiểm tra content, question type, option, correct answer, difficulty, exam weight,
source/provenance, subject/version code và mọi classification code. ProblemType, Concept và
LearningOutcome phải thuộc Subject tương ứng; pipeline không dùng AI để đoán mapping bị thiếu.
Question chưa có ProblemType vẫn được import ở `DRAFT`, không được coi là đã classify.

## Duplicate detection

`QuestionDuplicateDetector` là interface thay thế được. Phiên bản hiện tại là `ExactContentHashDuplicateDetector`:

1. chuẩn hóa Unicode NFKC;
2. gom whitespace;
3. chuyển về Unicode casefold;
4. tạo SHA-256 hash;
5. so sánh với Question Bank và các dòng trước trong file.

Hash được lưu cả trên `Question.content_hash` và staging. Detector chỉ query tập candidate hash qua index, không tải toàn bộ Question Bank vào RAM. Preview và confirm preload Subject, Concept, ProblemType và LearningOutcome theo batch thay vì query từng dòng. Confirm chạy detector lần nữa dưới PostgreSQL advisory lock, tránh hai batch đồng thời nhập cùng nội dung. Semantic duplicate detection có thể triển khai interface này ở task sau mà không thay đổi pipeline API.

## Import report

Mọi response trả:

```json
{"total": 4, "valid": 1, "invalid": 2, "duplicate": 1, "imported": 0}
```

Sau confirm, `valid` đếm các dòng vẫn hợp lệ hoặc đã import; `imported` cho biết số dòng đã tạo thành question. Dòng chuyển thành duplicate hoặc invalid trong lần kiểm tra cuối được phản ánh lại trong report.

## Migration và test

Revision `0007_question_import` tạo hai bảng staging, constraints, indexes và foreign keys. Revision `0012_question_content_hash` backfill SHA-256 cho question hiện có, đặt cột `content_hash` thành `NOT NULL` và tạo index. PostgreSQL local hiện ở:

```text
0012_question_content_hash (head)
```

Chạy lại:

```powershell
cd backend
$env:DEBUG = 'true'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest tests/questions/test_import.py tests/questions/test_import_migration.py -q
```

Tests bao phủ CSV, JSON, validation theo dòng, toàn bộ classification code, duplicate
trong file/database, preview/confirm, trusted seed, ownership, idempotency, rollback,
migration và confirm đồng thời trên PostgreSQL.

## TODO ngoài phạm vi

Chưa có semantic duplicate detector, background import job, import history UI, batch cleanup policy, downloadable error file, spreadsheet format hoặc mapping column tùy chỉnh.
