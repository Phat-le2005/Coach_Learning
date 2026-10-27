# Môi trường local riêng cho Coach Learning / EduMS

Project gồm backend FastAPI theo modular monolith, frontend Next.js 16 / React 19,
PostgreSQL, dữ liệu chương trình Toán 12 và ngân hàng câu hỏi. Backend có
auth/RBAC cho học sinh, giáo viên, phụ huynh, admin; curriculum/knowledge graph;
practice, diagnostic, mastery, recommendation, review, planning, digital twin;
assignment, exam, admission; tài liệu/RAG; Math Workspace, nét viết và kiểm tra
bước giải. API v1 dùng root routes, v2 phục vụ Math Workspace, v3 phục vụ AI review.
Frontend kết nối backend thật qua BFF và quản lý token trong HttpOnly cookie.

Mã nguồn, `backend/requirements.txt`, `frontend/package.json` và các workflow CI
là căn cứ lựa chọn runtime. Một số tài liệu foundation còn mô tả giai đoạn cũ.

## Thành phần cần có

| Thành phần | Cấu hình project | Cách cung cấp |
| --- | --- | --- |
| Python | 3.12 | Conda trong `.conda` |
| Backend | FastAPI, Uvicorn, SQLAlchemy, Alembic, Psycopg, Pydantic/settings, Argon2, PyJWT, email-validator, multipart, pgvector, pypdf, SymPy, Pillow | `backend/requirements-lock.txt` |
| Backend test | pytest, HTTPX | Cùng môi trường Python |
| Node.js / npm | Node.js 22 | Cùng môi trường Conda, theo nhánh runtime của CI |
| Frontend | Next.js 16, React/React DOM 19, TypeScript, KaTeX, Lucide, Motion, Three.js, ink-on, ONNX Runtime Web | `npm ci`, khóa bằng `frontend/package-lock.json` |
| Database | PostgreSQL 16 + extension `vector` | Gói Conda `postgresql` và `pgvector`; dữ liệu tại `.local/postgres` |
| OCR trình duyệt | Model CoMER + ONNX Runtime Web | Đã có trong `frontend/public/ocr`; không cần GPU |
| Gemini | API key và model được tài khoản hỗ trợ | Tự điền trong `backend/.env`; không cần Google SDK vì mã dùng HTTPX/REST |

Pillow là dependency bắt buộc vì API v3 import `PIL` khi khởi tạo app, dù
`MATH_OCR_PROVIDER=disabled`. Python `pgvector` và extension PostgreSQL `vector`
là hai thành phần khác nhau, cần cả hai cho migration RAG.

## Tái tạo trên Windows PowerShell

Chạy từ thư mục gốc project. Máy hiện tại có Conda tại `D:\Conda`; không cần
thay Python/Node toàn cục hoặc chạy `conda init` lên profile của người dùng.
PowerShell của máy hiện tại chặn script theo mặc định; lệnh `Set-ExecutionPolicy`
bên dưới chỉ áp dụng cho terminal đang mở.

```powershell
# Mở Anaconda PowerShell Prompt nếu terminal chưa nhận lệnh conda.
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONNOUSERSITE = '1'
$env:CONDA_PKGS_DIRS = Join-Path $env:TEMP 'edums-conda-pkgs'
conda env create --prefix .\.conda --file environment.yml
. .\scripts\activate.ps1

Set-Location frontend
npm.cmd ci
Set-Location ..

python scripts/local_setup.py init
Set-Location backend
python -m app.database.check
python -m alembic upgrade head
python -m app.seed
Set-Location ..
```

Helper chỉ tạo `backend/.env` và `frontend/.env.local` khi chưa tồn tại; sinh
ngẫu nhiên database password, JWT key, session secret và demo password. Cấu hình
đã tồn tại được giữ nguyên. Không copy `.env.example` đè lên `.env` sau khi setup.
Đọc `SEED_DEMO_PASSWORD` trong `backend/.env` bằng editor khi cần đăng nhập demo;
không gửi các secret vào chat hoặc commit Git.

Cluster local chỉ lắng nghe `127.0.0.1`, dùng SCRAM và port trong `backend/.env`
(mặc định 5432). Helper dừng nếu port đang được dịch vụ khác sử dụng. Nó không
cài Windows service và không tự khôi phục các file database dump ở root.
Migrations và seed được gọi tường minh, không chạy trong startup FastAPI.

Project hiện tại nằm trong đường dẫn có dấu (`D:\Học\...`). Cấu hình Conda và
script activation bật `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`. Helper database
tạo một directory junction tên không dấu trong `%TEMP%` trỏ tới project để
PostgreSQL Windows tìm đúng executable. Junction chỉ là đường dẫn thay thế;
database thật vẫn ở `.local/postgres`. Helper tự tạo lại junction nếu thư mục
tạm đã được dọn. Cache Conda cũng dùng đường dẫn không dấu trong `%TEMP%`, tránh
trường hợp libmamba báo thiếu package dù package có trên Conda Forge.
`PYTHONNOUSERSITE=1` tắt package trong user-site của Python khác trên máy, để
Conda không dùng nhầm hoặc cố gỡ thư viện ngoài project khi chạy pip.

Nếu Conda solver không tìm được phiên bản cũ trong metadata rút gọn, dùng danh
mục đầy đủ khi tạo phần runtime, rồi cài Python dependency theo lock:

```powershell
# Cache không dấu tránh lỗi libmamba khi project nằm dưới đường dẫn có dấu.
$env:CONDA_PKGS_DIRS = Join-Path $env:TEMP 'edums-conda-pkgs'
& D:\Conda\Scripts\conda.exe create --prefix .\.conda --override-channels -c conda-forge --repodata-fn repodata.json --solver libmamba 'python=3.12.*' 'nodejs=22.23.4' 'postgresql=16.*' 'pgvector=0.8.*' pip -y
. .\scripts\activate.ps1
python -m pip install -r backend/requirements-lock.txt
```

## Chạy mỗi lần làm việc

Terminal 1, tại root:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
. .\scripts\activate.ps1
python scripts/local_setup.py start
.\backend\run_dev.ps1
```

Terminal 2, tại root:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
. .\scripts\activate.ps1
Set-Location frontend
npm.cmd run dev
```

Mở <http://localhost:3000/login>; backend docs tại <http://127.0.0.1:8000/docs>.
Local HTTP dùng `npm run dev`. `npm run start` chạy chế độ production và bắt buộc
cookie Secure theo mã nguồn, kể cả khi `.env.local` có `SESSION_COOKIE_SECURE=false`;
khi phục vụ production cần HTTPS.
Nếu PowerShell chặn script, có thể dùng `Set-ExecutionPolicy -Scope Process Bypass`
cho terminal hiện tại, rồi chạy lại. Không cần đổi execution policy toàn máy.

```powershell
# Sau khi tắt backend/frontend bằng Ctrl+C:
python scripts/local_setup.py stop
# Kiểm tra database riêng của project:
python scripts/local_setup.py status
```

Tài khoản demo được tạo bởi `python -m app.seed`:
`student01.demo@example.com`, `teacher.math01.demo@example.com`,
`parent01.demo@example.com`, `admin.demo@example.com`.
Seed tạo curriculum, user và classroom; không mặc nhiên nhập toàn bộ ngân hàng
câu hỏi được duyệt. Trang luyện tập cần câu hỏi APPROVED hợp lệ trong database.

## VS Code và extension

Mở `Coach_Learning.code-workspace`. Workspace chọn `.conda/python.exe`, thêm
`backend` vào Python analysis path, cấu hình pytest và dùng TypeScript của project.
Nếu editor từng nhớ Python khác, chạy **Python: Select Interpreter** và chọn
`.conda\python.exe`.

Extension đề xuất: **Python** (`ms-python.python`), **Pylance**
(`ms-python.vscode-pylance`), **Python Debugger** (`ms-python.debugpy`). VS Code
đã có hỗ trợ TypeScript/JavaScript/JSON. Extension editor không bắt buộc để chạy
ứng dụng. Không cần Jupyter, Anaconda Extension Pack hoặc ESLint để khởi động
project hiện tại; project chưa khai báo cấu hình ESLint.

Tham khảo [Python environments trong VS Code](https://code.visualstudio.com/docs/python/environments)
và [Python extension](https://github.com/microsoft/vscode-python).

## Chức năng tùy chọn

- **Gemini / AI review:** điền `AI_API_KEY` và các `AI_MODEL_*` hợp lệ cho tài khoản.
  Môi trường local giữ provider `gemini` theo template; thiếu key không có kết quả
  AI thật. Không tự đổi thành mock để giả lập hoạt động thành công.
- **OCR backend CPU:** nếu cần provider `local_rapid`, cài
  `python -m pip install -r backend/requirements-ocr-cpu.txt`, rồi từ `backend`
  chạy `python -m scripts.prepare_ocr_cpu_model --download`. Đặt
  `MATH_OCR_PROVIDER=local_rapid` và `MATH_OCR_MODEL_DIR` trỏ tới thư mục checkpoint
  đã xác minh. Không cần phần này cho OCR CoMER trong browser.
- **OCR pix2tex:** dùng `backend/requirements-ocr-local.txt` trong môi trường riêng
  nếu cần thử PyTorch; không cài chung mặc định vì nặng và có thể xung đột dependency.
- **Sinh lại PDF OCR test:** script cũ `backend/scripts/generate_ocr_test_pdf.py`
  còn import `fitz` (PyMuPDF) và hard-code đường dẫn máy cũ. Đây không phải luồng
  runtime; cần sửa đường dẫn và cài dependency riêng trước khi sử dụng script này.

Không cần Redis, Celery, CUDA hoặc Docker cho cấu hình local này. Nếu dùng Docker
thay database Conda, `docker-compose.yml` đã có image `pgvector/pgvector:pg16`;
không chạy hai database trên cùng port.

## Kiểm tra sau setup

```powershell
. .\scripts\activate.ps1
python -m pip check
Set-Location backend
python -m app.database.check
python -m alembic current
python -m app.api.check_contract
python -m pytest tests/test_health.py tests/test_foundation.py tests/auth/test_configuration.py -q
Set-Location ..\frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

`GET /health` chỉ kiểm tra process. `GET /ready` và `app.database.check` kiểm tra
kết nối database; đăng nhập còn cần schema, seed, JWT key và session secret.
Các test PostgreSQL tùy chọn cần `EDUMS_TEST_DATABASE_URL` trỏ tới database test
riêng. Không dùng database đang có dữ liệu quan trọng để thử migration/test.

Môi trường, local config, database, model tải thêm và cache đều được Git ignore
(`.conda`, `.local`, `.env*`, `node_modules`, `.tmp`).

Nguồn về extension database: [pgvector upstream](https://github.com/pgvector/pgvector)
và [gói Conda Forge cho Windows](https://anaconda.org/conda-forge/pgvector).

## Kết quả kiểm chứng trên máy này — 25/10/2026

| Kiểm tra | Kết quả |
| --- | --- |
| Runtime trong `.conda` | Python 3.12.15, Node.js 22.23.4, npm 10.9.9, PostgreSQL 16.15, pgvector database 0.8.6 |
| Python isolation | User-site bị tắt; mọi đường dẫn `site-packages` thuộc môi trường project |
| Backend dependency | 45/45 phiên bản khớp lockfile; `pip check` không có dependency hỏng |
| PostgreSQL thực | Kết nối thành công, extension `vector` hoạt động |
| Alembic | Áp dụng đủ 48 migration, head `0048_math_ink_retention_index` |
| Seed | 19 user demo, curriculum Toán 12, 2 lớp và dữ liệu liên quan |
| Backend smoke tests | 23 passed; 2 cảnh báo deprecation từ Starlette/AnyIO, không có test lỗi |
| API contracts | v1 và v2 passed |
| Frontend | 167 tests passed; typecheck và production build thành công |
| OCR browser assets | SHA-256 encoder, decoder và vocabulary khớp README của asset |
| HTTP backend | `/health`, `/ready`, `/docs`, `/api/v2/docs`, `/api/v3/docs` đều 200 |
| HTTP frontend development | Đăng nhập, session, trang chính STUDENT/TEACHER/PARENT/ADMIN đều 200; Knowledge Forest và trang danh sách bài làm đều 200 |

Kiểm chứng chưa bao gồm toàn bộ regression suite, Gemini thật, OCR backend bằng
checkpoint tải thêm, hoặc nhập ngân hàng câu hỏi. Database mới chỉ có development
seed; chưa khôi phục các file dump ở root. Các tiến trình phục vụ kiểm thử được
tắt sau khi xác minh; dùng lệnh ở phần “Chạy mỗi lần làm việc” để khởi động lại.
