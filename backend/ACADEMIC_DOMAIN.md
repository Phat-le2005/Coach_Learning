# Academic Domain

Academic Domain gồm hai lớp độc lập nhưng có mapping:

```text
Curriculum -> CurriculumVersion -> Subject -> Chapter -> Topic -> ProblemType
ProblemType <-> Concept -> ConceptRelation(PREREQUISITE, RELATED_TO)
ProblemType <-> LearningOutcome
```

`Concept` là đơn vị kiến thức/kỹ năng tái sử dụng, không đại diện Chapter, Topic hay
ProblemType. `ConceptRelation.PART_OF` chỉ được giữ để tương thích dữ liệu cũ và không
được canonical importer dùng để tạo curriculum hierarchy.

## Graph service

`ConceptGraphService` hỗ trợ direct prerequisites, recursive prerequisite tree,
dependents, descendants, self-reference guard và cycle detection. Graph nằm trong
PostgreSQL relational tables; route không chứa recursive traversal.

## Constraints

- Subject code unique trong CurriculumVersion.
- Chapter, Topic và ProblemType code unique trong parent trực tiếp.
- Concept và LearningOutcome code unique trong Subject.
- Mapping dùng composite primary key; weight trong `(0, 1]` khi có.
- Canonical academic foreign key ưu tiên `RESTRICT`; mapping owned bởi parent có thể
  cascade khi chính mapping không còn ý nghĩa.
- Stable code được chuẩn hóa uppercase; order index không âm.

## API

Subject/Concept/ConceptRelation API cũ được giữ tương thích:

- `POST/GET /admin/subjects`
- `POST/PATCH /admin/concepts[/{id}]`
- `POST /admin/concept-relations`
- `DELETE /admin/concept-relations/{id}`

Curriculum hierarchy API được mô tả tại
[Curriculum Foundation](CURRICULUM_FOUNDATION.md). Tất cả endpoint `/admin` yêu cầu
backend RBAC role `ADMIN`.

## Migration and tests

`0004_academic_domain` vẫn là migration gốc. `0009_curriculum_refactor` thêm versioned
hierarchy, mappings và chuyển Concept fields mô tả/grade/order thành nullable. Migration
gắn Subject cũ vào legacy curriculum version, giữ stable identifiers và không tự suy đoán
Chapter/Topic từ Concept.

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest tests\academic tests\curriculum -q
```

Mastery, student graph overlay và Recommendation chưa được triển khai.
