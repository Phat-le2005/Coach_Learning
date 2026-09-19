# Foundation 01-09 audit

Audit này ghi lại quyết định kiến trúc trước khi triển khai Learning Core.

| Prompt | Kết quả | Lý do |
| --- | --- | --- |
| 01 Project Setup | KEEP | FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, cấu hình environment, logging, error envelope, CORS, health check và local startup đã đúng. |
| 02 Authentication/RBAC | KEEP | Argon2, access/refresh token, disabled-user guard, current-user dependency và reusable role dependencies đã có test. |
| 03 Profiles | KEEP | Ba profile tách riêng, `user_id` unique và parent-student dùng bảng quan hệ nhiều-nhiều. |
| 04 Academic Domain | MODIFIED | Bổ sung curriculum có version, Chapter, Topic, ProblemType, LearningOutcome và mapping; giữ Concept làm knowledge graph riêng. |
| 05 Classroom | KEEP | Quyền truy cập dựa trên TeacherClassroom/StudentEnrollment thật, không chỉ dựa trên role. |
| 06 Data Foundation | MODIFIED | Canonical curriculum chuyển sang JSON có manifest/provenance; SeedService gọi chung CurriculumImportService. |
| 07 Question Bank | MODIFIED | Question liên kết ProblemType, Concept và LearningOutcome; thêm source year và cognitive level. |
| 08 Question Import | MODIFIED | Pipeline kiểm tra curriculum version, ProblemType, Concept, LearningOutcome và lưu mapping đã validate. |
| 09 Synthetic Generator | MODIFIED | Attempt có ProblemType; SPECIFIC_GAP nhận target theo chapter/topic/problem type/concept và vẫn deterministic. |

## Phân loại thay đổi

- **KEEP:** core/database/auth/users/profile/classroom và các API tương thích hiện có.
- **MODIFY:** academic, curriculum data/import, question classification/import và synthetic targeting.
- **ADD:** curriculum hierarchy, mappings, import history, curriculum CLI và admin read/write API.
- **DEPRECATE:** dùng `ConceptRelation.PART_OF` để biểu diễn Chapter/Topic; module `data.seed.grade12_math` chỉ còn compatibility view đọc canonical JSON.
- **REMOVE_IF_SAFE:** không có cấu trúc nào được xóa trong migration này. Có thể xóa compatibility view sau khi mọi caller cũ chuyển sang CurriculumImportService.

Không có Practice Engine, Mastery, Digital Twin, Recommendation hoặc Prompt 10 trong thay đổi này.
