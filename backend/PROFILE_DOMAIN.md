# Profile domain

Đã triển khai StudentProfile, TeacherProfile, ParentProfile, ParentStudentRelationship và 6 endpoint GET/PATCH `/me`. Không có AcademicGoal hoặc frontend profile UI trong task này.

## Kiến trúc và lifecycle

Mỗi module `app/students`, `app/teachers`, `app/parents` có models, schemas, service và router riêng trong Modular Monolith. Router kiểm tra role bằng `require_role` đã có, rồi gọi service với `user.id` lấy từ access token đã được xác minh. Business logic và truy vấn database nằm trong service; không nhận user/profile ID từ client để chọn hồ sơ.

UserService tạo profile phù hợp trong cùng transaction với User: STUDENT → StudentProfile, TEACHER → TeacherProfile, PARENT → ParentProfile. ADMIN không có profile riêng. Profile creation thất bại sẽ rollback User; register và CLI provisioning đều dùng luồng này. Migration backfill các User đã có, gồm tài khoản inactive.

GET không tạo dữ liệu. Khi profile thiếu, GET/PATCH trả 404 `PROFILE_NOT_FOUND`. Việc quản trị/thay đổi role sau này cần đảm bảo profile phù hợp; task này không thêm role management hoặc tự sửa dữ liệu thiếu khi đọc.

## Entities và constraints

| Entity | Fields |
| --- | --- |
| StudentProfile | UUID `id`, UUID `user_id`, `grade_level`, nullable `school_name`, nullable DATE `date_of_birth`, `is_synthetic`, nullable `synthetic_profile`, `created_at`, `updated_at` |
| TeacherProfile | UUID `id`, UUID `user_id`, nullable `specialization`, `created_at`, `updated_at` |
| ParentProfile | UUID `id`, UUID `user_id`, `created_at`, `updated_at` |
| ParentStudentRelationship | UUID `parent_id`, UUID `student_id`, `relationship_type`, `is_active` |

Mỗi bảng profile có unique `user_id` và FK đến `users.id`, `ON DELETE CASCADE`. ID của profile và ID của User là hai định danh riêng. Student mặc định `grade_level=12`; database và request validator giới hạn lớp từ 1 đến 12. School name/specialization tối đa 200 ký tự, được trim; dùng null để bỏ giá trị, chuỗi trắng bị từ chối. Birth date không được ở tương lai theo ngày UTC của backend.

Timestamps do database khởi tạo. `updated_at` được SQLAlchemy cập nhật khi có UPDATE profile; client không được sửa timestamp. PATCH `{}` không thay đổi dữ liệu hoặc timestamp.

ParentStudentRelationship có composite primary key `(parent_id, student_id)`: một parent có nhiều student, một student có nhiều parent và không trùng cặp liên kết. Hai FK trỏ đến `parent_profiles.id`/`student_profiles.id`, không trỏ trực tiếp đến User. `relationship_type` là string tối đa 50 ký tự, không rỗng sau SQL trim; chưa đặt enum vì task chưa quy định danh mục. Ví dụ MOTHER/FATHER/GUARDIAN là dữ liệu hợp lệ. `is_active` mặc định true; có thể giữ liên kết inactive mà không xóa lịch sử liên kết. Index `student_id` phục vụ tra cứu chiều student → parents, chiều parent → students dùng composite PK.

ORM hỗ trợ hai chiều qua `StudentProfile.parent_relationships` và `ParentProfile.student_relationships`; các collection bao gồm cả liên kết active/inactive, caller cần filter `is_active` khi phục vụ quyền truy cập. Xóa User/profile sẽ cascade các liên kết thuộc profile đó, giữ những liên kết khác. Không có `parent_id` trong StudentProfile.

## API và authorization

Gửi `Authorization: Bearer <access token>`. Các API trả `Cache-Control: no-store`, không trả email/password/hash hoặc tự mở rộng dữ liệu quan hệ. Sai/mất token hoặc User inactive → 401; sai role → 403; thiếu profile → 404; input không hợp lệ → 422, dùng error envelope chung của ứng dụng.

| Method | Endpoint | Role | Dữ liệu được sửa |
| --- | --- | --- | --- |
| GET | `/students/me` | STUDENT | — |
| PATCH | `/students/me` | STUDENT | grade_level, school_name, date_of_birth |
| GET | `/teachers/me` | TEACHER | — |
| PATCH | `/teachers/me` | TEACHER | specialization |
| GET | `/parents/me` | PARENT | — |
| PATCH | `/parents/me` | PARENT | Không có writable field; chỉ nhận `{}` |

ADMIN không bypass `/me` của role khác. Parent không đọc/sửa Student qua `/students/me`; task này chưa cung cấp API child data hoặc permission dựa trên verified relationship.

PATCH chỉ áp dụng các trường client đã gửi bằng `model_dump(exclude_unset=True)` hoặc kiểm tra `model_fields_set`, giữ những trường không có trong request. `id`, `user_id`, timestamps, role, email, is_active và extra fields đều bị từ chối. `grade_level` có thể bỏ qua khi PATCH nhưng không thể null. School/birth date/specialization có thể null để xóa giá trị.

Ví dụ PATCH student:

```json
{
  "grade_level": 12,
  "school_name": "THPT Nguyễn Trãi",
  "date_of_birth": "2008-06-15"
}
```

`is_synthetic` và `synthetic_profile` là read-only system fields; profile API
không cho user tự thay đổi marker này. Xem [Synthetic Student Generator](SYNTHETIC_STUDENTS.md).

Xóa school name nhưng giữ những trường khác:

```json
{"school_name": null}
```

PATCH teacher:

```json
{"specialization": "Toán học"}
```

ParentProfile hiện chỉ có ID và timestamps, nên PATCH `{}` trả hồ sơ hiện tại mà không có database UPDATE. Gửi `student_id` hoặc danh sách students vào PATCH parent bị từ chối; endpoint này không cho tự gán quan hệ phụ huynh–học sinh.

## Migration và chạy local

`0003_profiles` nối tiếp `0002_auth_rbac`, tạo 4 bảng, các constraints/indexes và backfill profile theo User.role. UUID backfill dùng built-in `gen_random_uuid()` của PostgreSQL 13+, không cần thêm extension. Profile của Student cũ dùng grade mặc định 12; các trường optional còn trống để người dùng cập nhật.

Trong `backend`, sau khi cấu hình PostgreSQL và signing key như README/Auth docs:

```powershell
$env:DEBUG = 'true'  # dùng nếu terminal kế thừa DEBUG không đúng kiểu boolean
.\.venv\Scripts\python.exe -m app.database.check
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m app
```

Linux/macOS: activate venv, dùng `python -m ...`. Không thêm dependency hoặc environment variable trong task này. Xem SQL offline bằng `python -m alembic upgrade head --sql`.

## Tests và kết quả

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest tests/profiles
.\.venv\Scripts\python.exe -m pip check
```

Test DB fixtures được chia sẻ giữa auth/profiles, tạo schema bằng cả migration chain. SQLite tests có equivalent UUID function riêng cho backfill, không có SQLite fallback trong runtime. Các test mới kiểm tra:

- Auto provisioning đúng role, unique user_id, grade constraints và rollback User khi profile thất bại.
- GET/PATCH từng role, thiếu/sai token, inactive User, owner isolation, chặn mass assignment, partial update/null và timestamps.
- Many-to-many hai chiều, duplicate pair, FK profile IDs, type không rỗng, inactive relationship và DB cascade.
- Backfill User active/inactive, profile UUID có thể truy vấn lại, downgrade giữ User, model/migration parity và SQL backfill dùng schema riêng cho source/destination trong PostgreSQL tests.

Profile tests remain part of the full migration/API suite and also run against isolated
PostgreSQL schemas when `EDUMS_TEST_DATABASE_URL` is configured.

## File tạo/sửa

Tạo: `app/{students,teachers,parents}/{models,schemas,service,router}.py`; `migrations/versions/0003_profiles.py`; `tests/migrations.py`; `tests/profiles/{__init__,conftest,test_api,test_migration,test_provisioning,test_relationships}.py`; `PROFILE_DOMAIN.md`.

Sửa: `app/{students,teachers,parents}/__init__.py`; `app/users/service.py`; `app/api/router.py`; `app/application.py` (metadata/CORS PATCH); `migrations/env.py`; `tests/conftest.py`; `tests/auth/{conftest,test_migration,test_postgres_concurrency}.py`; root `README.md`; `AUTHENTICATION.md`.

## TODO

Chưa triển khai relationship CRUD/verification API, quyền truy cập child data, profile UI, admin profile management hoặc AcademicGoal. Không tự triển khai bước tiếp theo.

## Tham chiếu

- [FastAPI partial updates](https://fastapi.tiangolo.com/tutorial/body-updates/)
- [PostgreSQL UUID functions](https://www.postgresql.org/docs/13/functions-uuid.html)
