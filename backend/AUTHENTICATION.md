# Authentication và RBAC

Phạm vi tài liệu này: User account, đăng ký/đăng nhập, access token, refresh token và reusable authorization dependency. Profile domain đã được bổ sung ở task riêng, xem [PROFILE_DOMAIN.md](PROFILE_DOMAIN.md). Chưa triển khai giao diện authentication frontend.

## Kiến trúc

- `app/users`: User/Role, schema đầu vào/đầu ra, service tạo user và CLI provisioning.
- `app/auth`: router mỏng, request/response schemas, password/JWT utilities, AuthService, current-user/RBAC dependencies và models phiên đăng nhập.
- `app/core/exceptions.py`: application error dùng trong service, không phụ thuộc HTTP framework. Global handlers trả cùng error envelope với foundation.
- PostgreSQL là source of truth cho role, trạng thái active, phiên đăng nhập và refresh token. Không có LLM, cache hoặc worker trong luồng authentication.

User có `id` UUID, `email`, `password_hash`, `full_name`, `role`, `is_active`, `created_at`, `updated_at`. Email được normalize lowercase và có unique constraint; DB cũng kiểm tra email lowercase và bốn giá trị role. Timestamp được database khởi tạo; SQLAlchemy cập nhật `updated_at` khi update User.

Password được hash bằng Argon2id với salt ngẫu nhiên, 64 MiB memory, 3 iterations, parallelism 4. Password đăng ký có 12–128 ký tự, không trim hoặc truncate. Login trả cùng lỗi cho email không tồn tại, password sai và user inactive; dùng dummy hash để tránh bỏ qua bước verify khi không có user. Hash được nâng cấp ở login nếu parameters thay đổi.

Access JWT dùng thuật toán cố định HS256, xác minh signature/issuer/audience/expiry/nbf/iat và yêu cầu các claims định danh. Token không chứa role; dependency đọc role hiện tại từ User trong database. Access token có mặc định 15 phút, không vượt quá expiry của phiên.

Mỗi login tạo một `auth_sessions` và refresh token opaque ngẫu nhiên. `auth_refresh_tokens` chỉ lưu SHA-256 hash, thời điểm tạo và thời điểm consumed; không lưu token gốc. Token ngẫu nhiên có 384-bit entropy; SHA-256 ở đây dùng cho token ngẫu nhiên, không dùng để hash password.

Refresh khóa hàng phiên bằng `SELECT ... FOR UPDATE`, đọc lại trạng thái token sau khi lấy lock rồi consume token cũ/tạo token mới trong cùng transaction. Các token trong cùng phiên dùng chung lock. Reuse token consumed sẽ commit revocation của phiên và trả 401; mọi access/refresh token của phiên bị từ chối, các phiên login khác vẫn hoạt động. Rotation không kéo dài lifetime ban đầu của phiên, mặc định 7 ngày. Client cần gửi refresh tuần tự, lưu token mới và đăng nhập lại nếu nhận 401.

## Chính sách role

`Role` có `STUDENT`, `TEACHER`, `PARENT`, `ADMIN`. Public registration chỉ tạo `STUDENT`; bỏ trường role sẽ dùng mặc định này. Yêu cầu TEACHER/PARENT/ADMIN qua register bị từ chối 403. Tài khoản các role khác được tạo bằng CLI có quyền truy cập cấu hình database, không có API tự cấp quyền.

ADMIN không tự động bypass các dependency. Endpoint cần cho phép nhiều role phải khai báo rõ bằng `require_any_role`.

## Cấu hình

Các biến mới trong `backend/.env.example` và root `.env.example`:

```dotenv
JWT_SECRET_KEY=
JWT_ISSUER=edums
JWT_AUDIENCE=edums-api
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```

Key phải ngẫu nhiên, ít nhất 32 bytes. Workspace hiện đã sinh key riêng vào `backend/.env` và giữ các giá trị local đã có; key không được in vào tool output hoặc commit. Bản checkout mới cần sinh key rồi điền vào env. Ví dụ dùng `secrets.token_urlsafe(48)` trong Python; không dùng giá trị ví dụ làm secret thực tế.

Key trống khiến authentication trả 503 `AUTH_NOT_CONFIGURED`, trong khi health vẫn hoạt động. Key quá ngắn bị configuration validation từ chối. Đổi key làm các access token cũ mất hiệu lực; refresh session vẫn tồn tại và có thể cấp access token mới.

Tạo key trực tiếp trong file local ở lần setup đầu (không overwrite key đã có):

```python
from pathlib import Path
import secrets

path = Path(".env")  # chạy trong backend
lines = path.read_text(encoding="utf-8").splitlines()
for index, line in enumerate(lines):
    if line == "JWT_SECRET_KEY=":
        lines[index] = "JWT_SECRET_KEY=" + secrets.token_urlsafe(48)
        break
else:
    if not any(line.startswith("JWT_SECRET_KEY=") for line in lines):
        lines.append("JWT_SECRET_KEY=" + secrets.token_urlsafe(48))
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

JWT secret chỉ thuộc backend; không dùng biến `NEXT_PUBLIC_*` để chứa key hoặc token.

## API

Các POST nhận JSON, không phải OAuth2 form. Swagger dùng HTTP Bearer: login rồi dán access token vào nút Authorize. Login/refresh response có `Cache-Control: no-store`, `Pragma: no-cache`; me có `Cache-Control: no-store`. CORS cho phép POST và Authorization từ origin đã cấu hình.

### POST /auth/register → 201

```json
{
  "email": "student@example.com",
  "password": "Example-Password-2026!",
  "full_name": "Nguyễn Minh Anh",
  "role": "STUDENT"
}
```

Password trên chỉ là dữ liệu ví dụ. Response là public User, không có password/password_hash. Đăng ký không tự login.

### POST /auth/login → 200

```json
{
  "email": "student@example.com",
  "password": "Example-Password-2026!"
}
```

Response:

```json
{
  "access_token": "<access JWT>",
  "refresh_token": "<opaque refresh token>",
  "token_type": "bearer",
  "expires_in": 900
}
```

### POST /auth/refresh → 200

```json
{"refresh_token":"<current refresh token>"}
```

Response cùng dạng TokenPair như login. Thay refresh token đã lưu bằng token mới; không gửi token cũ lần nữa.

### GET /auth/me → 200

Gửi `Authorization: Bearer <access token>`. Response: `id`, `email`, `full_name`, `role`, `is_active`, `created_at`, `updated_at`. Token thiếu/sai/hết hạn, phiên revoked/hết hạn hoặc user inactive đều bị từ chối.

| HTTP | Error code | Trường hợp |
| --- | --- | --- |
| 401 | `INVALID_CREDENTIALS` | Login sai hoặc inactive |
| 401 | `INVALID_TOKEN` | Token thiếu/sai/hết hạn/replay/phiên revoked |
| 403 | `ROLE_NOT_ALLOWED` | Public register yêu cầu role khác STUDENT |
| 403 | `FORBIDDEN` | User không có role endpoint yêu cầu |
| 409 | `EMAIL_ALREADY_REGISTERED` | Email trùng, gồm khác hoa/thường |
| 422 | `VALIDATION_ERROR` | Request không hợp lệ, gồm extra fields |
| 503 | `AUTH_NOT_CONFIGURED` | Chưa có signing key |

Lỗi 401 có `WWW-Authenticate: Bearer`. Không trả lại password, token input hoặc stack trace; logging chỉ ghi user/session ID và loại sự kiện.

## Dùng dependency trong module được giao sau này

```python
from typing import Annotated
from fastapi import Depends
from app.auth.dependencies import get_current_user, require_role, require_any_role
from app.users.models import Role, User

CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_role(Role.ADMIN))]
TeachingUser = Annotated[User, Depends(require_any_role(Role.TEACHER, Role.ADMIN))]
```

Đặt dependency ở parameter của endpoint hoặc `dependencies=[Depends(...)]` của router. Không lặp if/else checking role trong từng route. Resource-level authorization, ví dụ học sinh chỉ được xem dữ liệu của mình, cần thêm service/dependency tương ứng khi module đó được giao; role chưa thay thế quyền sở hữu resource.

## Migration, chạy local và provisioning

Trong `backend`, dùng Python của venv trên Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.database.check
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app
```

Migration `0002_auth_rbac` nối tiếp `0001_foundation`, tạo `users`, `auth_sessions`, `auth_refresh_tokens` cùng constraints/indexes. Head hiện là `0008_synthetic_students`; `0003_profiles` bổ sung ba loại profile và parent relationship. UserService tạo profile phù hợp cùng transaction với User; register STUDENT có grade mặc định 12. Migration online trên PostgreSQL 17.11 local đã được xác nhận; SQLite chỉ thuộc tests, không phải fallback runtime.

Tạo ADMIN qua terminal quản trị có database credential:

```powershell
.\.venv\Scripts\python.exe -m app.users.create_user --email admin@example.com --full-name "EduMS Admin" --role ADMIN
```

CLI hỏi password và confirmation bằng getpass, không nhận password qua argument. Có thể thay role bằng TEACHER/PARENT/STUDENT. Linux/macOS dùng `python -m ...` sau khi activate venv. Nếu process kế thừa `DEBUG` không đúng boolean, dùng `$env:DEBUG = 'true'` trong terminal backend như README hướng dẫn.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip check
```

Tests API dùng real SQLAlchemy sessions trên SQLite riêng, tạo schema bằng chính migration, không cần `.env` hoặc PostgreSQL. Bao phủ register, duplicate email, password hash, login đúng/sai/inactive, JWT policies, me, ma trận 4 role, role changes/deactivation, rotation/replay/expiry, CORS, secret-safe logging và migration upgrade/downgrade/model parity.

SQLite không thực thi PostgreSQL row locks. Có 3 test tùy chọn trên PostgreSQL cho concurrent refresh/replay và duplicate registration. Trong terminal test, đặt `EDUMS_TEST_DATABASE_URL` dùng scheme `postgresql+psycopg`, credential riêng và database test. Sau đó chạy:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/auth/test_postgres_concurrency.py
```

Mỗi case tạo schema `edums_test_<uuid>` riêng, chạy migration trong schema này và xóa chính schema đó lúc teardown. Không drop database hoặc đổi bảng ứng dụng; role test cần quyền tạo schema. Không commit hoặc log test connection URL. Thiếu biến này thì 3 case được skip, không được tính là đã kiểm chứng concurrency PostgreSQL. Ba case đã pass trên PostgreSQL 17.11 local.

## File tạo/sửa

Tạo: `app/core/exceptions.py`; `app/users/{models,schemas,service,create_user}.py`; `app/auth/{models,schemas,security,service,dependencies,router}.py`; `migrations/versions/0002_auth_rbac.py`; `tests/__init__.py`; `tests/auth/{__init__,conftest,test_auth,test_configuration,test_migration,test_rbac,test_refresh,test_postgres_concurrency}.py`; `AUTHENTICATION.md`.

Sửa: `app/core/{config,errors}.py`, `app/{application,api/router}.py`, `app/{auth,users}/__init__.py`, `migrations/env.py`, `tests/conftest.py`, `requirements.txt`, `requirements-lock.txt`, `backend/.env.example`, root `.env.example`, root `README.md`; cập nhật `backend/.env` local bằng key ngẫu nhiên, không commit.

## TODO

Chạy migration online và 3 concurrency tests khi có PostgreSQL. Chưa triển khai auth UI/token storage frontend, logout API, email verification, password reset/change, rate limiting, quản trị user/role qua API, cleanup expired sessions hoặc permission của các module nghiệp vụ ngoài profile `/me`. Không tự triển khai bước tiếp theo.

## Tham chiếu

- [argon2-cffi password hashing](https://argon2-cffi.readthedocs.io/en/stable/howto.html)
- [PyJWT validation](https://pyjwt.readthedocs.io/en/stable/usage.html)
- [RFC 9700 refresh token protection](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14)
