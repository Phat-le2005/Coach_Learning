# Classroom domain

Classroom domain nằm trong `app/classes` của Modular Monolith. Router chỉ nhận request và áp dụng role dependency; `ClassroomService` tạo lớp, quản lý enrollment và thực hiện relationship authorization. PostgreSQL là source of truth. Module không dùng AI, cache hoặc background job và không thêm dependency/environment variable.

## Data model

| Table | Fields chính |
| --- | --- |
| `classrooms` | `id`, `name`, `academic_year`, `grade_level`, `created_by`, `created_at` |
| `teacher_classrooms` | composite PK `teacher_id + classroom_id`, `role` |
| `student_enrollments` | composite PK `student_id + classroom_id`, `status`, `joined_at` |

`TeacherClassroom.teacher_id` tham chiếu `TeacherProfile.id`; `StudentEnrollment.student_id` tham chiếu `StudentProfile.id`. `Classroom.created_by` tham chiếu `User.id` để audit. `created_by` không tự cấp quyền truy cập: quyền teacher luôn cần row thật trong `teacher_classrooms`.

Khi teacher tạo lớp, service tạo `Classroom` và assignment `OWNER` trong cùng transaction. `role` hiện là chuỗi không rỗng để hỗ trợ thêm vai trò lớp sau này; mọi assignment đều có quyền đọc/thêm học sinh trong phạm vi API hiện tại. Task này chưa có API gán thêm teacher.

Enrollment status là enum:

```text
ACTIVE
INACTIVE
COMPLETED
```

POST enrollment mặc định ACTIVE và có thể nhận một trong ba trạng thái. Composite primary key ngăn một student xuất hiện hai lần trong cùng lớp. Student vẫn thấy lịch sử lớp INACTIVE/COMPLETED kèm trạng thái; API không chỉ lọc ACTIVE.

Database kiểm tra foreign key, grade 1–12, name/academic year/teacher role không rỗng và enum status. Xóa profile hoặc classroom ở database cascade các assignment/enrollment liên quan; `created_by` dùng RESTRICT để giữ audit classroom.

## Authorization

Teacher endpoints trước tiên yêu cầu `Role.TEACHER`, sau đó lấy `TeacherProfile` từ current user và truy vấn `teacher_classrooms` theo cả `teacher_id` lẫn `classroom_id`.

- List chỉ join các lớp có assignment của teacher.
- Detail, roster và enroll kiểm tra classroom tồn tại, rồi kiểm tra assignment.
- Classroom không tồn tại trả 404 `CLASSROOM_NOT_FOUND`.
- Classroom tồn tại nhưng teacher không được phân công trả 403 `CLASSROOM_ACCESS_DENIED`.
- Việc `created_by` trùng current user nhưng không có assignment vẫn bị từ chối.

Student endpoint yêu cầu `Role.STUDENT`, lấy `StudentProfile` từ current user và join `student_enrollments` bằng profile ID. Student không thể truyền ID của người khác và không thấy lớp chưa enroll.

Current-user authentication vẫn kiểm tra access session, user active và role hiện tại từ database. Thiếu/sai token trả 401; sai role trả 403. Thiếu role profile trong dữ liệu bất thường trả 404 `PROFILE_NOT_FOUND` và không tự tạo dữ liệu.

## API

| Method | Endpoint | Authorization | Response |
| --- | --- | --- | --- |
| POST | `/teacher/classes` | TEACHER | 201 `TeacherClassroomRead` |
| GET | `/teacher/classes` | TEACHER + assignments | 200 list |
| GET | `/teacher/classes/{id}` | TEACHER + assignment | 200 detail |
| GET | `/teacher/classes/{id}/students` | TEACHER + assignment | 200 roster |
| POST | `/teacher/classes/{id}/students` | TEACHER + assignment | 201 student roster item |
| GET | `/students/me/classes` | STUDENT + own enrollments | 200 list |

Tạo lớp:

```json
{
  "name": "12A1",
  "academic_year": "2026-2027",
  "grade_level": 12
}
```

`name` dài 1–200 ký tự, `academic_year` 1–20 ký tự và được trim. `grade_level` phải là integer 1–12; string, boolean, float và field ngoài schema bị từ chối. Response thêm `teacher_role`; `created_by` do backend lấy từ access token. Roster trả thêm read-only `is_synthetic` và `synthetic_profile` để Teacher Dashboard phân biệt dữ liệu demo.

Thêm student bằng **StudentProfile ID**:

```json
{
  "student_id": "<student-profile-uuid>",
  "status": "ACTIVE"
}
```

Không truyền `status` thì mặc định ACTIVE. Student không tồn tại trả 404 `STUDENT_NOT_FOUND`; enrollment đã tồn tại trả 409 `STUDENT_ALREADY_ENROLLED`. Cả pre-check và composite PK xử lý duplicate; race trên PostgreSQL được chuyển thành cùng lỗi 409.

Roster trả `student_id`, `user_id`, `email`, `full_name`, grade/school/date of birth từ profile cùng `status`, `joined_at`. Chỉ teacher có assignment lớp mới đọc được roster.

Các list có thứ tự ổn định. API hiện trả toàn bộ dữ liệu phù hợp relationship; pagination sẽ được thêm khi quy mô/use case cụ thể yêu cầu.

## Migration và tests

Revision `0005_classrooms`, nối tiếp `0004_academic_domain`, tạo ba bảng cùng index/constraints và không seed lớp hoặc enrollment. Migration đã được áp dụng thành công trên PostgreSQL 17.11 local:

```text
0009_curriculum_refactor (head)
```

Chạy lại từ `backend`:

```powershell
$env:DEBUG = 'true'
.\.venv\Scripts\python.exe -m app.database.check
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m pytest -q
```

48 Classroom tests bao phủ create/list/detail/roster/enroll, ba status, validation, token và role matrix, profile thiếu, classroom/student không tồn tại, duplicate, created_by không cấp quyền, teacher assignment thật, student enrollment isolation, database constraints, migration downgrade/parity và duplicate enrollment đồng thời trên PostgreSQL.

Current backend verification: 322 tests pass with the PostgreSQL integration database; all 48 Classroom tests remain green. Two TestClient/AnyIO deprecation warnings remain and there are no failures.

## File tạo/sửa

Tạo:

- `app/classes/models.py`, `schemas.py`, `service.py`, `router.py`.
- `migrations/versions/0005_classrooms.py`.
- `tests/classes/__init__.py`, `conftest.py`, `test_api.py`, `test_migration.py`, `test_postgres.py`.
- `CLASSROOM_DOMAIN.md`.

Sửa:

- `app/api/router.py`: đăng ký teacher/student classroom routers.
- `app/application.py`: API version 0.5.0.
- `migrations/env.py`: nạp Classroom models vào metadata.
- `tests/auth/test_migration.py`: thêm ba bảng vào migration parity.
- `README.md`, `ACADEMIC_DOMAIN.md`, `AUTHENTICATION.md`, `PROFILE_DOMAIN.md`: cập nhật head/kết quả hiện tại.

## TODO ngoài phạm vi

Chưa có API gán/gỡ teacher, đổi enrollment status, remove student, sửa/xóa classroom, pagination hoặc Classroom UI. Các chức năng này chỉ triển khai trong task riêng; không tự triển khai bước tiếp theo.
