# Data Foundation

Data Foundation tách rõ bốn loại dữ liệu và không gọi LLM:

```text
data/
├── curriculum/       # canonical, versioned curriculum datasets
├── questions/        # curated question dataset placeholder
├── misconceptions/   # future curated taxonomy placeholder
├── seed/             # stable IDs và demo identities
├── fixtures/         # development scenarios
└── synthetic/        # deterministic behavioral simulation
```

Canonical curriculum Grade 12 Mathematics nằm tại
`data/curriculum/math/grade12/gdpt2018`. JSON manifest ghi dataset code/version,
curriculum version, source reference và verification state. Nội dung gồm 1 Subject,
6 Chapter, 8 Topic, 9 ProblemType, 14 Concept, 8 LearningOutcome, 12 ConceptRelation,
19 ProblemTypeConcept và 9 ProblemTypeLearningOutcome.

`CurriculumImportService` là đường ghi duy nhất cho canonical curriculum. Nó validate
schema, stable code, parent reference, graph cycle và version isolation trước khi import
trong một transaction. Lịch sử import cùng SHA-256 content hash được lưu tại
`curriculum_import_history`. Xem [Curriculum Foundation](CURRICULUM_FOUNDATION.md).

`SeedService` gọi curriculum importer rồi tạo demo identities và fixtures. Seed hiện có
1 admin, 2 teacher, 12 student, 4 parent, 2 classroom, 12 enrollment và 12 parent-student
relationship. UUIDv5 ổn định giúp chạy lặp không tạo duplicate. Python module
`data.seed.grade12_math` đã deprecated và chỉ đọc lại canonical JSON cho caller cũ.

## Commands

```powershell
$env:DEBUG = 'true'

# Validate only
.\.venv\Scripts\python.exe -m app.import_curriculum `
  --dataset MATH_G12_GDPT2018_CORE --dry-run

# Import canonical data
.\.venv\Scripts\python.exe -m app.import_curriculum `
  --dataset MATH_G12_GDPT2018_CORE

# Canonical data + development users/classes
.\.venv\Scripts\python.exe -m app.seed

# Confirmed development reset; forbidden in production
.\.venv\Scripts\python.exe -m app.seed reset `
  --confirm RESET-DEVELOPMENT-SEED
```

`SEED_DEMO_PASSWORD` phải có ít nhất 12 ký tự và chỉ được cấu hình qua environment.
Seed/reset bị chặn khi `APP_ENV=production`. Reset chỉ thay demo identities/fixtures;
canonical curriculum và import history không bị xóa.

## Idempotency and safety

- PostgreSQL advisory lock tuần tự hóa seed và curriculum import đồng thời.
- Natural-key/stable-ID conflict làm rollback toàn transaction.
- Import cùng dataset version nhưng content khác bị từ chối; không silently overwrite.
- Development reset không truncate/drop schema và không xóa record ngoài stable fixture IDs.
- Development reset xóa `QuestionAttempt` và `PracticeSession` của demo students trước khi xóa profile, tránh vi phạm FK `RESTRICT`; question bank không thuộc seed vẫn được giữ nguyên.
- Synthetic user/attempt có marker và production analytics dùng real-only query scope.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\data_foundation tests\curriculum -q
.\.venv\Scripts\python.exe -m alembic check
```

Migration hiện tại là `0009_curriculum_refactor`. Không có Mastery, Practice Engine hay
Recommendation trong Data Foundation này.
