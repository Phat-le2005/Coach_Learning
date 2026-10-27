# EduMS — Local development

**Windows + Conda:** xem [hướng dẫn môi trường riêng cho project](docs/local-setup.md).
`environment.yml` cung cấp Python 3.12, Node.js 22, PostgreSQL 16 và extension
pgvector trong `.conda`; mở `Coach_Learning.code-workspace` để VS Code chọn đúng Python.
Các mục foundation bên dưới mô tả cả lịch sử phát triển; đối chiếu mã nguồn và
[README frontend](frontend/README.md) để xem luồng hiện tại.

Hệ thống quản lý giáo dục và hỗ trợ thi tuyển sinh đại học, chạy trực tiếp trên máy local. Đã triển khai foundation 01–09 cùng versioned Curriculum, knowledge graph và Question classification. Xem [Foundation Audit](backend/FOUNDATION_AUDIT.md), [Curriculum Foundation](backend/CURRICULUM_FOUNDATION.md), [Authentication](backend/AUTHENTICATION.md), [Profile](backend/PROFILE_DOMAIN.md), [Academic](backend/ACADEMIC_DOMAIN.md), [Classroom](backend/CLASSROOM_DOMAIN.md), [Data Foundation](backend/DATA_FOUNDATION.md), [Question Bank](backend/QUESTION_BANK.md), [Question Import](backend/QUESTION_IMPORT.md), [Synthetic Students](backend/SYNTHETIC_STUDENTS.md) và đặc tả hợp đồng đóng băng [API v1 Specification](backend/API_V1.md) ([OpenAPI Contract v1.0.0](backend/contracts/openapi-v1.json)).

## Kiến trúc

Backend là Modular Monolith. Các domain account, profile, academic, Classroom và Question Bank tách model/schema/service/router. `backend/data` quản lý seed catalog, development fixtures và deterministic synthetic generators; `SeedService` ghi dữ liệu trong một transaction. Không tự tạo bảng hoặc seed khi startup; schema đi qua Alembic và seed chỉ chạy bằng CLI tường minh.

`GET /health` là liveness check, trả `{"status":"ok"}` mà không gọi database hoặc AI. Engine kết nối khi được sử dụng. Session được đóng sau request và rollback khi có lỗi; service phải commit giao dịch tường minh. Kiểm tra PostgreSQL bằng command riêng `python -m app.database.check`.

Frontend dùng Next.js 16 App Router, React 19 và TypeScript strict, có đăng nhập qua BFF, phân quyền, Student Home, Knowledge Forest và Math Workspace. Xem [README frontend](frontend/README.md) để biết cấu hình session, API và OCR trong trình duyệt.

## Cấu trúc và danh sách file tạo

```text
CoachLearning/
├── .gitignore
├── .env.example
├── README.md
├── backend/
│   ├── .env.example
│   ├── API_V1.md
│   ├── AUTHENTICATION.md
│   ├── PROFILE_DOMAIN.md
│   ├── ACADEMIC_DOMAIN.md
│   ├── CLASSROOM_DOMAIN.md
│   ├── DATA_FOUNDATION.md
│   ├── QUESTION_BANK.md
│   ├── QUESTION_IMPORT.md
│   ├── SYNTHETIC_STUDENTS.md
│   ├── contracts/            # openapi-v1.json, openapi-v1.sha256, README.md, API_V1_CHANGELOG.md
│   ├── requirements.txt
│   ├── requirements-lock.txt
│   ├── pytest.ini
│   ├── alembic.ini
│   ├── app/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── main.py
│   │   ├── application.py
│   │   ├── seed.py
│   │   ├── seed_service.py
│   │   ├── generate_synthetic_students.py
│   │   ├── synthetic_student_service.py
│   │   ├── api/                  # __init__.py, router.py, health.py, version.py, export_contract.py, check_contract.py
│   │   ├── core/                 # __init__.py, config.py, errors.py, exceptions.py, logging.py
│   │   ├── database/             # __init__.py, base.py, session.py, check.py
│   │   ├── auth/                 # __init__.py, models.py, schemas.py, security.py,
│   │   │                        # service.py, dependencies.py, router.py
│   │   ├── users/                # __init__.py, models.py, schemas.py, service.py, create_user.py
│   │   ├── students/             # __init__.py, models.py, schemas.py, service.py, router.py
│   │   ├── teachers/             # __init__.py, models.py, schemas.py, service.py, router.py
│   │   ├── parents/              # __init__.py, models.py (gồm relationship), schemas.py,
│   │   │                        # service.py, router.py
│   │   ├── subjects/             # __init__.py, models.py, schemas.py, service.py, router.py
│   │   ├── concepts/             # __init__.py, models.py, schemas.py, service.py,
│   │   │                        # graph_service.py, router.py
│   │   ├── classes/              # __init__.py, models.py, schemas.py, service.py, router.py
│   │   ├── questions/            # Question Bank + CSV/JSON import pipeline
│   │   ├── attempts/             # attempt/session facts và analytics scope
│   │   ├── learning/
│   │   ├── mastery/
│   │   ├── recommendations/
│   │   ├── diagnostics/
│   │   ├── review/
│   │   ├── planning/
│   │   ├── digital_twin/
│   │   ├── exams/
│   │   ├── admission/
│   │   ├── documents/
│   │   └── ai/
│   ├── data/                     # seed/, fixtures/, synthetic/
│   ├── migrations/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       ├── 0001_foundation.py
│   │       ├── 0002_auth_rbac.py
│   │       ├── 0003_profiles.py
│   │       ├── 0004_academic_domain.py
│   │       ├── 0005_classrooms.py
│   │       ├── 0006_question_bank.py
│   │       ├── 0007_question_import_pipeline.py
│   │       ├── 0008_synthetic_students.py
│   │       ├── 0009_curriculum_foundation_refactor.py
│   │       ├── 0010_practice_engine.py
│   │       ├── 0011_mastery_engine.py
│   │       ├── 0012_question_content_hash.py
│   │       ├── 0013_diagnostic_assessment.py
│   │       ├── 0014_student_academic_goals.py
│   │       ├── 0015_diagnostic_attempt_context.py
│   │       ├── 0016_teacher_teaching_plans.py
│   │       ├── 0017_quick_check.py
│   │       ├── 0018_spaced_review.py
│   │       └── 0019_study_planning_core.py
│   └── tests/
│       ├── conftest.py
│       ├── __init__.py
│       ├── migrations.py
│       ├── auth/                 # __init__.py, conftest.py, test_auth.py,
│       │                        # test_configuration.py, test_migration.py, test_rbac.py,
│       │                        # test_refresh.py, test_postgres_concurrency.py
│       ├── profiles/             # __init__.py, conftest.py, test_api.py,
│       │                        # test_migration.py, test_provisioning.py, test_relationships.py
│       ├── academic/             # __init__.py, conftest.py, test_api.py, test_graph.py,
│       │                        # test_migration.py, test_postgres.py
│       ├── classes/              # __init__.py, conftest.py, test_api.py,
│       │                        # test_migration.py, test_postgres.py
│       ├── planning/             # __init__.py, test_api.py, test_migration.py, test_service.py,
│       │                        # test_recommendation_integration.py, test_study_migration.py,
│       │                        # test_study_planning.py
│       ├── learning/             # __init__.py, test_migration.py, test_quick_check.py
│       ├── review/               # __init__.py, test_migration.py, test_spaced_review.py
│       ├── recommendations/      # __init__.py, conftest.py, test_services.py, test_learning_mix.py
│       ├── data_foundation/       # __init__.py, conftest.py, test_seed.py, test_postgres.py
│       ├── questions/             # Question Bank/import unit, migration và PostgreSQL tests
│       ├── synthetic/             # behavior, generator, migration và PostgreSQL tests
│       ├── test_health.py
│       └── test_foundation.py
└── frontend/
    ├── AGENTS.md                  # Next.js dev tự sinh quy ước dành cho coding agent
    ├── CLAUDE.md                  # Tham chiếu AGENTS.md, Next.js dev tự sinh
    ├── .env.example
    ├── package.json
    ├── package-lock.json
    ├── tsconfig.json
    ├── next-env.d.ts
    └── src/
        ├── app/
        │   ├── layout.tsx
        │   ├── globals.css
        │   ├── page.tsx
        │   ├── login/page.tsx
        │   ├── student/page.tsx
        │   ├── teacher/page.tsx
        │   ├── parent/page.tsx
        │   └── admin/page.tsx
        └── lib/api/client.ts
```

`.conda`, `.local`, `backend/.venv`, `backend/.env`, `frontend/.env.local`, `node_modules`, `.next` và test caches là dữ liệu local được ignore. `.env.example` được theo dõi trong Git.

## Yêu cầu và dependency

- Python 3.12 trở lên; package backend chỉ cài trong virtual environment.
- Node.js 20.9 trở lên và npm; môi trường kiểm chứng dùng Node.js 22.
- PostgreSQL cùng extension **vector**; cấu hình Conda và Docker của project dùng PostgreSQL 16. Gói Python `pgvector` không thay thế extension phía database. Helper `scripts/local_setup.py` quản lý cluster local riêng trong `.local/postgres`.
- Backend: FastAPI, Uvicorn, SQLAlchemy 2, Alembic, Psycopg 3 binary, Pydantic 2, Pydantic Settings, Argon2-cffi, PyJWT, email-validator, python-multipart, pgvector, pypdf, SymPy và Pillow. Tests: pytest và HTTPX.
- Frontend: Next.js 16, React 19, React DOM 19. Development: TypeScript, `@types/node`, `@types/react`, `@types/react-dom`.

`requirements.txt` chứa dependency trực tiếp với giới hạn phiên bản; `requirements-lock.txt` chứa toàn bộ phiên bản đã cài. Frontend khóa phiên bản trong `package-lock.json`.

## PostgreSQL local

Khởi động PostgreSQL bằng service của hệ điều hành hoặc công cụ quản trị sẵn có. Trong `psql` hoặc pgAdmin Query Tool, dùng tài khoản quản trị để chạy:

```sql
CREATE DATABASE edums;
```

Template dùng `DATABASE_USER=postgres` để setup local. Điền mật khẩu thực tế vào `backend/.env`, không gửi mật khẩu vào chat hoặc commit file env. Có thể dùng tài khoản riêng không có superuser như sau trong phiên `psql` của tài khoản quản trị:

```sql
CREATE ROLE edums_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
```

Đặt mật khẩu tương tác bằng `\password edums_app`. Nếu database chưa được tạo:

```sql
CREATE DATABASE edums OWNER edums_app;
```

Nếu đã tạo theo cách đầu tiên, với database riêng của EduMS:

```sql
ALTER DATABASE edums OWNER TO edums_app;
```

Kết nối vào `edums` rồi chạy:

```sql
GRANT USAGE, CREATE ON SCHEMA public TO edums_app;
```

Đổi `DATABASE_USER=edums_app` và điền mật khẩu trong `backend/.env`. Backend không yêu cầu superuser. Role chạy Alembic cần quyền DDL; việc tách migration role và runtime role cho production thuộc task deployment sau này.

Nếu `psql` chưa có trong PATH, dùng SQL Shell, pgAdmin hoặc executable trong thư mục `bin` của bản PostgreSQL đã cài.

## Environment variables

Backend đọc `backend/.env` theo đường dẫn mã nguồn. Environment của process có độ ưu tiên cao hơn file; dùng `EDUMS_DEBUG` cho cấu hình debug của ứng dụng. Root `.env.example` chỉ là bản tham khảo tổng hợp, không được tự động load. Frontend đọc `frontend/.env.local`.

| Biến | Giá trị template | Mục đích |
| --- | --- | --- |
| `APP_NAME` | `EduMS` | Tên ứng dụng/OpenAPI |
| `APP_ENV` | `development` | `development`, `test`, `production` |
| `EDUMS_DEBUG` | `true` | Development logging/reload; không bật traceback response |
| `DATABASE_HOST` | `localhost` | PostgreSQL host |
| `DATABASE_PORT` | `5432` | PostgreSQL port |
| `DATABASE_NAME` | `edums` | Database, phải được cấu hình |
| `DATABASE_USER` | `postgres` | User trong template, phải được cấu hình |
| `DATABASE_PASSWORD` | trống | Mật khẩu local; chưa điền credential thực tế |
| `BACKEND_HOST` | `127.0.0.1` | Host của launcher `python -m app` |
| `BACKEND_PORT` | `8000` | Port của launcher `python -m app` |
| `FRONTEND_URL` | `http://localhost:3000` | CORS origin chính xác, không có path/wildcard |
| `JWT_SECRET_KEY` | trống | Backend signing key, ít nhất 32 bytes; trống thì auth trả 503 |
| `JWT_ISSUER` | `edums` | Issuer được verify trong access JWT |
| `JWT_AUDIENCE` | `edums-api` | Audience được verify trong access JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token TTL, từ 1–60 phút |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Session lifetime cố định, từ 1–30 ngày |
| `SEED_DEMO_PASSWORD` | trống | Password local cho demo users; tối thiểu 12 ký tự |
| `API_BASE_URL` | `http://127.0.0.1:8000` | URL backend phía server của frontend BFF |
| `AUTH_SESSION_SECRET` | trống | Secret ký session BFF, ít nhất 32 ký tự; tạo trong `.env.local` |
| `SELF_STUDY_PUBLISHED_SUBJECT_CODES` | `MATH_G12` | Allowlist môn tự học của frontend |

SQLAlchemy tạo URL bằng `URL.create` từ settings để xử lý ký tự đặc biệt trong credential. Trong env có thể đặt chuỗi mật khẩu trong dấu nháy. Không có database URL hard-code hoặc cấu hình database riêng ở Alembic.

Next.js nhúng biến `NEXT_PUBLIC_*` vào client bundle. Sau khi đổi URL, restart dev server hoặc build lại. Nếu dùng origin frontend khác, cập nhật `FRONTEND_URL` và restart backend.

## Setup backend từ đầu

Trên Windows PowerShell, sau khi đã tạo `.venv` và điền `backend/.env`, có thể khởi động an toàn từ thư mục gốc bằng:

```powershell
.\backend\run_dev.ps1
```

Launcher ưu tiên `.conda/python.exe` của project, rồi mới dùng `backend/.venv/Scripts/python.exe` nếu chưa có Conda. Không chạy `uvicorn app.main:app --reload` trực tiếp nếu chưa activate môi trường, vì Windows có thể gọi Uvicorn/Python toàn cục và báo thiếu package.

Từ root:

```text
cd backend
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

Windows Command Prompt:

```bat
.venv\Scripts\activate.bat
copy .env.example .env
```

Linux/macOS:

```bash
source .venv/bin/activate
cp .env.example .env
```

Chỉ copy env ở lần setup đầu, giữ cấu hình đã chỉnh ở các lần sau. Điền thông tin PostgreSQL của máy và sinh `JWT_SECRET_KEY` ngẫu nhiên trong `backend/.env` theo [hướng dẫn authentication](backend/AUTHENTICATION.md#cấu-hình), rồi chạy:

```text
python -m pip install -r requirements.txt
python -m app.database.check
python -m alembic upgrade head
python -m app
```

Để tái lập bộ phiên bản đã cài, thay command install bằng `python -m pip install -r requirements-lock.txt`.

`python -m app` đọc host/port từ settings và bật reload khi `APP_ENV=development`, `EDUMS_DEBUG=true`. Có thể dùng Uvicorn trực tiếp với host/port tương ứng cấu hình local:

```text
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Nếu PowerShell chặn activation, gọi Python trong venv trực tiếp, không cần đổi execution policy:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.database.check
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app
```

Backend dùng `EDUMS_DEBUG` và bỏ qua biến `DEBUG` của các công cụ khác. Không cần thay đổi environment toàn máy.

Backend: http://127.0.0.1:8000/health. Swagger: http://127.0.0.1:8000/docs. OpenAPI: http://127.0.0.1:8000/openapi.json.

### API Contract (Phiên bản v1.0.0)

API contract được đóng băng chính thức tại phiên bản `1.0.0` theo kiến trúc Canonical Root Routing. Tài liệu chi tiết tại [API v1 Specification](backend/API_V1.md), schema [OpenAPI Contract v1.0.0](backend/contracts/openapi-v1.json) và [Changelog](backend/contracts/API_V1_CHANGELOG.md).

- **Kiểm tra tính toàn vẹn contract (Check CLI)**:
  ```powershell
  python -m app.api.check_contract
  ```
- **Xuất / Đóng băng lại contract (Export CLI)**:
  ```powershell
  python -m app.api.export_contract
  ```
- **Kiểm thử hồi quy contract tự động**:
  ```powershell
  pytest tests/api_contract/ -v
  ```

## Alembic

Trong `backend`, sau khi activate venv và cấu hình PostgreSQL:

```text
python -m alembic upgrade head
python -m alembic current
python -m alembic history
```

`0001_foundation` là baseline rỗng. `0002_auth_rbac` tạo account/auth sessions. `0003_profiles` tạo profile/parent relationship và backfill theo role. `0004_academic_domain` tạo subject/concept graph. `0005_classrooms` tạo classroom, teacher assignment và student enrollment. `0006_question_bank` tạo question, option và concept weights. `0007_question_import` tạo staging cho preview/confirm import. `0008_synthetic_students` thêm marker synthetic, study sessions và attempt facts. `0009_curriculum_foundation_refactor` thêm versioned curriculum hierarchy, ProblemType/LearningOutcome mappings, Question classifications và ProblemType trên synthetic attempt. Các migration không seed dữ liệu nghiệp vụ. Upgrade ghi nhận `alembic_version` và dùng cùng `Settings` với backend.

Khi task được giao có thay đổi model, import model vào `migrations/env.py`, tạo migration và review trước khi chạy:

```text
python -m alembic revision --autogenerate -m "describe schema change"
python -m alembic upgrade head
```

Revision thủ công: `python -m alembic revision -m "describe schema change"`. Xem SQL offline: `python -m alembic upgrade head --sql`; command offline không xác minh kết nối PostgreSQL.

## Development seed

Đặt `SEED_DEMO_PASSWORD` trong `backend/.env`, rồi chạy:

```powershell
cd backend
$env:EDUMS_DEBUG = 'true'
.\.venv\Scripts\python.exe -m app.seed
```

Command idempotent; development reset cần confirmation và bị chặn trong production:

```powershell
.\.venv\Scripts\python.exe -m app.seed reset --confirm RESET-DEVELOPMENT-SEED
```

Xem dataset, stable IDs và safety tại [DATA_FOUNDATION.md](backend/DATA_FOUNDATION.md).

## Synthetic students

Sau khi seed catalog, tạo cohort deterministic cho dashboard/analytics bằng:

```powershell
.\.venv\Scripts\python.exe -m app.generate_synthetic_students --count 20 --seed 42
.\.venv\Scripts\python.exe -m app.generate_synthetic_students --count 10 --seed 7 --profile SPECIFIC_GAP
```

Generator bị chặn trong production. Synthetic user không thể đăng nhập; profile,
attempt và study session đều có marker để analytics loại dữ liệu giả. Xem pattern,
idempotency và tùy chọn study history tại [SYNTHETIC_STUDENTS.md](backend/SYNTHETIC_STUDENTS.md).

## Setup frontend

Mở terminal thứ hai từ root:

```text
cd frontend
npm install
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env.local
npm.cmd run dev
```

Windows Command Prompt:

```bat
copy .env.example .env.local
npm run dev
```

Linux/macOS:

```bash
cp .env.example .env.local
npm run dev
```

Nếu PowerShell chặn `npm.ps1`, dùng `npm.cmd install`, `npm.cmd ci` hoặc `npm.cmd run ...`. Các terminal khác dùng `npm` bình thường. Để cài theo lock dùng `npm ci`.

Mở http://localhost:3000:

| Route | Nội dung |
| --- | --- |
| `/` | EduMS |
| `/login` | Login |
| `/student` | Student Dashboard |
| `/teacher` | Teacher Dashboard |
| `/parent` | Parent Dashboard |
| `/admin` | Admin Dashboard |

Các khu vực hiện tại có kiểm tra session/role. Backend kiểm tra quyền truy cập dữ liệu; frontend dùng HttpOnly cookie qua BFF. Cấu hình `AUTH_SESSION_SECRET` và `SELF_STUDY_PUBLISHED_SUBJECT_CODES` theo [README frontend](frontend/README.md).

Health client sẵn có:

```typescript
import { getHealth } from "@/lib/api/client";
const health = await getHealth();
```

Có thể truyền `AbortSignal` để hủy request. Thiếu backend URL sẽ báo lỗi cấu hình, không tự dùng URL fallback hard-code.

## Tests và kiểm chứng

Trong `backend`, dùng venv:

```text
python -m pytest
python -m pip check
```

Tests mặc định không cần PostgreSQL hoặc file `.env`. SQLAlchemy/SQLite test được tạo bằng migration thật. Tests bao phủ auth/RBAC, profile, academic graph, Classroom authorization, Data Foundation, Question Bank, Question Import và Synthetic Student Generator. Có 10 PostgreSQL integration tests tùy chọn; các test này chạy toàn bộ migration chain trong schema PostgreSQL tạm và bao gồm kiểm tra idempotency của synthetic generator.

Trong `frontend`:

```text
npm run typecheck
npm run build
```

Frontend đã có test qua Node.js test runner (`npm test`). Backend health có thể kiểm tra bằng:

```text
curl http://127.0.0.1:8000/health
```

Kết quả mong đợi: `{"status":"ok"}`. Để xác minh database, phải chạy riêng `python -m app.database.check` và `python -m alembic upgrade head`.

Logging ghi startup, shutdown và loại unexpected exception. Launcher tắt access log; SQL parameter logging tắt, exception message/locals không được ghi để tránh lộ credential. Response lỗi thống nhất:

```json
{"error":{"code":"INTERNAL_SERVER_ERROR","message":"An unexpected error occurred."}}
```

Traceback không được trả cho client kể cả `DEBUG=true`. Lỗi validation không echo input. Khi phát triển có thể dùng debugger để xem chi tiết nội bộ.

## TODO ngoài phạm vi

AcademicGoal và các learning domain tiếp theo chưa được triển khai. Question export, semantic duplicate detection, review comments, tích hợp Question Bank vào learning/exam engine, extended Classroom management và business UI nằm ngoài task này. Docker/deployment cũng nằm ngoài phạm vi hiện tại.

## Kết quả kiểm chứng trong workspace

- Backend dependency install thành công; `pip check` không có xung đột.
- Default suite: 339 passed, 10 PostgreSQL tests skipped. With the PostgreSQL integration database: 349 passed. Two TestClient/AnyIO deprecation warnings remain; there are no failures.
- Backend chạy bằng `python -m app`; health, Swagger và OpenAPI trả HTTP 200.
- Frontend dependency install thành công; TypeScript check và production build thành công.
- `npm run dev` chạy thành công; đủ 6 route trả HTTP 200 và đúng tên khu vực.
- Health client gọi live backend từ giá trị đọc trong `.env.local`, nhận `status=ok`; kiểm chứng đổi URL và thiếu URL cũng thành công.
- Alembic nhận diện head `0016_teacher_teaching_plans`; `alembic check` không phát hiện operation mới. Migration chain được kiểm thử upgrade/downgrade trên SQLite và PostgreSQL, khớp ORM metadata và giữ nguyên bảng của revision trước khi downgrade riêng từng domain.
- PostgreSQL local `edums` đã ở `0016_teacher_teaching_plans (head)`. Tất cả 10 PostgreSQL integration tests pass. Curriculum import và development seed chạy lặp không tạo duplicate.

## MVP Demo Walkthrough & Critical Path Verification

Hệ thống CoachLearning / EduMS hỗ trợ kịch bản demo và kiểm chứng trọn vẹn chuỗi hành trình cốt lõi (42 milestones critical path) xuyên suốt toàn bộ nền tảng mà không sử dụng mock/fake flow.

### 1. Chuỗi hành trình 42 mắt xích (Critical Flow Map)

```text
[1. Admin import CurriculumVersion: MATH_G12_GDPT2018_CORE]
  ↓
[2. Subject MATH_G12] → [3. Chapters] → [4. Topics] → [5. ProblemTypes]
  ↓
[6. ProblemTypes map Concepts + LearningOutcomes] → [7. Valid Acyclic Concept Graph (DAG)]
  ↓
[8. Question Bank: Questions map ProblemType + Concepts + Outcomes + Hints]
  ↓
[9. Teacher tạo Classroom 12A1] → [10. Student ghi danh (Enrollment)]
  ↓
[11. Teacher kích hoạt TeachingPlan dạng bài mục tiêu]
  ↓
[12. Student đặt AcademicGoal (Kỳ thi THPT Quốc Gia, thời lượng học/ngày)]
  ↓
[13. Student làm Diagnostic Assessment]
  ↓
[14. StudentProblemTypeMastery tạo] → [15. StudentConceptMastery tạo] → [16. Topic/Chapter Aggregation]
  ↓
[17. Digital Twin phản ánh đồng bộ cả ProblemType và Concept]
  ↓
[18. Study Plan tự động tạo daily tasks bám sát TeachingPlan]
  ↓
[19. Student học active ProblemType] → [20. Student làm Quick Check]
  ↓
[21. Student trả lời sai] → [22. QuestionAttempt lưu trữ]
  ↓
[23. Mastery Engine cập nhật điểm tinh thông ProblemType + Concept]
  ↓
[24. KnowledgeGapService phân tích] → [25. Phát hiện lỗ hổng Concept tiên quyết]
  ↓
[26. Student xin Hint] → [27. Hệ thống Hint trả gợi ý bậc thang (Scaffolded, không lộ đáp án)]
  ↓
[28. Lỗi sai lặp lại] → [29. MisconceptionService ghi nhận bằng chứng & xác nhận CONFIRMED]
  ↓
[30. Repair Session kích hoạt 5 bước chuẩn sư phạm (Review → Easy → Guided → Medium → Recheck)]
  ↓
[31. Student hoàn thành 5 bước Repair] → [32. Mastery Engine ghi nhận tăng trưởng độ tinh thông]
  ↓
[33. Recommendation Engine đề xuất câu hỏi tiếp theo phù hợp năng lực]
  ↓
[34. Teacher Heatmap cập nhật ma trận năng lực theo ProblemType/Concept]
  ↓
[35. Tín hiệu tiên quyết (Prerequisite Signals)] → [36. Intervention Alerts kích hoạt]
  ↓
[37. Teacher Copilot phân tích, giải thích trạng thái lớp & đề xuất hành động sư phạm]
  ↓
[38. Parent Dashboard tổng hợp dữ liệu học tập tuần] → [39. Parent AI Summary tóm tắt khách quan]
  ↓
[40. Student làm bài thi mô phỏng chuẩn hóa (Exam Simulation)]
  ↓
[41. Exam Analytics phân tích kết quả đa chiều (Chương / Chủ đề / Dạng bài / Tiên quyết)]
  ↓
[42. AI Exam Analysis giải thích kết quả chi tiết, bảo toàn điểm số tuyệt đối]
```

### 2. Các bảo đảm kiến trúc và bất biến (Architectural Invariants)

- **Zero Fake Flow**: 100% các bước sử dụng trực tiếp session cơ sở dữ liệu và domain service thật.
- **Learning Core Resilience**: Toàn bộ hoạt động cốt lõi (chấm điểm, đánh giá chẩn đoán, Quick Check, tính độ tinh thông, phiên sửa sai, thi mô phỏng) hoạt động độc lập 100% khi AI gặp sự cố. Copilot, Parent Summary và Exam Explanation tự động rơi về chế độ tất định an toàn.
- **Synthetic Data Isolation**: Dữ liệu giả lập mang cờ `is_synthetic=True` được tách biệt hoàn toàn khỏi báo cáo phân tích thực tế của giáo viên thông qua bộ lọc `include_synthetic=False` mặc định.
- **Single Source of Truth**: Bảo toàn tính duy nhất và toàn vẹn tham chiếu cho chương trình học, ngân hàng câu hỏi và dữ liệu độ tinh thông.

### 3. Hướng dẫn chạy kiểm thử & xác minh

Trong thư mục `backend`, kích hoạt virtualenv:

```powershell
cd backend

# Chạy kiểm thử tích hợp chuỗi hành trình cốt lõi và các bất biến
.\.venv\Scripts\pytest tests/integration/test_mvp_critical_path.py -v

# Chạy khung đánh giá chất lượng toàn diện (7 nhóm đánh giá)
.\.venv\Scripts\python -m app.evaluate

# Chạy toàn bộ regression test suite
.\.venv\Scripts\pytest tests/ -q
```

## Tham chiếu

- [FastAPI: Settings and Environment Variables](https://fastapi.tiangolo.com/advanced/settings/)
- [Next.js: Installation](https://nextjs.org/docs/app/getting-started/installation)
- [Alembic: Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
