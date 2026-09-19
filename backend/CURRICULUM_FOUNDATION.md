# Curriculum foundation

Academic foundation tách hai cấu trúc dữ liệu:

```text
Curriculum -> CurriculumVersion -> Subject -> Chapter -> Topic -> ProblemType
Concept -> ConceptRelation(PREREQUISITE, RELATED_TO)
```

`ProblemTypeConcept` nối dạng bài với kiến thức/kỹ năng. `ProblemTypeLearningOutcome`
nối dạng bài với yêu cầu cần đạt. Question có mapping độc lập tới ProblemType, Concept và
LearningOutcome. Chapter/Topic không được biểu diễn bằng `ConceptRelation.PART_OF`.
Dataset `1.1.0` đánh dấu `INEQUALITY_SOLVING` là prerequisite của
`PARAMETER_REASONING`, đồng thời giữ quan hệ `RELATED_TO` có chủ đích.

## Canonical dataset

Dataset mẫu nằm tại:

```text
data/curriculum/math/grade12/gdpt2018/
├── manifest.json
├── subject.json
├── chapters.json
├── topics.json
├── problem_types.json
├── concepts.json
├── learning_outcomes.json
├── concept_relations.json
├── problem_type_concepts.json
└── problem_type_learning_outcomes.json
```

Manifest lưu stable dataset code, dataset version, curriculum/version code, subject,
grade, nguồn tham chiếu và trạng thái xác minh. `verified_at=null` có nghĩa dataset chưa
được đánh dấu là đã qua quy trình xác minh nội dung. Development fixtures và synthetic
data nằm ở thư mục riêng, không phải canonical curriculum.

## Import

Chạy từ `backend`:

```powershell
$env:DEBUG = 'true'
.\.venv\Scripts\python.exe -m app.import_curriculum `
  --dataset MATH_G12_GDPT2018_CORE --dry-run
.\.venv\Scripts\python.exe -m app.import_curriculum `
  --dataset MATH_G12_GDPT2018_CORE
```

Pipeline thực hiện schema validation, reference validation, duplicate-code validation,
cycle detection, preview và transaction import. Stable UUID được sinh từ stable code.
`curriculum_import_history` lưu manifest, content hash, counts và thời điểm import. Chạy
lại cùng dataset/version/hash trả `already_imported=true` và không tạo duplicate.

Seed development gọi chính importer này trước khi tạo demo user/classroom:

```powershell
.\.venv\Scripts\python.exe -m app.seed
```

## Legacy migration

Migration `0009_curriculum_refactor` tạo một curriculum/version `LEGACY` và gắn mọi
Subject cũ vào version này. Importer chỉ nhận lại stable identity cũ cho dataset có
`legacy_identity_compatible=true`; domain service không tự suy đoán curriculum thật từ
tên Subject. Existing `PART_OF` được giữ để tương thích và cần admin phân loại thủ công;
canonical importer từ chối dùng `PART_OF` làm curriculum hierarchy.

## Admin API

- `POST/GET /admin/curricula`
- `POST/GET /admin/curriculum-versions`
- `POST /admin/chapters`
- `GET /admin/subjects/{subject_id}/chapters`
- `POST /admin/topics`
- `GET /admin/chapters/{chapter_id}/topics`
- `POST /admin/problem-types`
- `GET /admin/topics/{topic_id}/problem-types`
- `GET /admin/problem-types/{problem_type_id}`
- `POST /admin/learning-outcomes`
- `GET /admin/subjects/{subject_id}/learning-outcomes`
- `POST /admin/problem-type-concepts`
- `POST /admin/problem-type-learning-outcomes`
- `GET /admin/subjects/{subject_id}/curriculum-tree`

Các route chỉ điều phối; validation quan hệ và query tree nằm trong CurriculumService.
