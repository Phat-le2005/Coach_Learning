# Đề xuất Kiến trúc Phiên bản Hóa API (API Versioning Proposal)
## Bảo vệ Frozen API v1 và Thiết lập API v2 bằng FastAPI Sub-Application


> **Bắt buộc trước migration — STEP-ARCH-00:** [Final Schema & Effective Evidence Safety Gate](STEP_ARCH_00_SAFETY_GATE.md) là quyết định thiết kế ưu tiên nếu các ví dụ SQL/logic bên dưới còn mâu thuẫn. Chưa xác minh PostgreSQL runtime.

- **Dự án**: Coach Learning (EduMS)
- **Mã Sprint**: SPRINT-01.1 (Kiến trúc chuẩn hóa trước Migration)
- **Mã tài liệu**: API-VER-01
- **Trạng thái**: ĐỀ XUẤT KIẾN TRÚC ĐÃ HIỆU CHỈNH (ARCHITECTURAL SPECIFICATION)

---

## 1. Hiện trạng Kiểm tra Hợp đồng API v1 (API v1 Contract Audit)

### 1.1. Cơ chế Đóng băng Hiện tại (Current Freeze Mechanism)
Hệ thống hiện đang bảo vệ toàn vẹn hợp đồng API v1 bằng cơ chế song song nghiêm ngặt:
1. **File lược đồ chuẩn tắc**: `backend/contracts/openapi-v1.json` (chứa toàn bộ định nghĩa endpoints, query params, request bodies và responses của API v1).
2. **File mã băm SHA-256**: `backend/contracts/openapi-v1.sha256` (lưu mã hash SHA-256 nhỏ gọn của schema được sinh bằng thuật toán sắp xếp khóa `sort_keys=True`, loại bỏ khoảng trắng `separators=(',', ':')`).
3. **Công cụ xuất hợp đồng**: `backend/app/api/export_contract.py`:
   - Khởi tạo ứng dụng chuẩn thông qua cấu hình `app = create_app(settings)`.
   - Lấy lược đồ thông qua `app.openapi()`, xuất schema ra file JSON chuẩn và tính toán mã băm SHA-256.
4. **Công cụ kiểm tra hợp đồng**: `backend/app/api/check_contract.py`:
   - So sánh schema thời gian thực được sinh từ `get_deterministic_schema()` với `openapi-v1.json` và mã băm `openapi-v1.sha256`.
   - Nếu phát hiện bất kỳ sự khác biệt nào (contract drift), lệnh trả về mã thoát 1 và hiển thị diff chi tiết qua `sys.stderr`.
5. **Cổng kiểm soát CI**: File `.github/workflows/backend-data-validation.yml` chạy tự động lệnh:
   ```bash
   python -m app.api.check_contract
   ```
   Nếu hợp đồng bị thay đổi trái phép, toàn bộ pull request và pipeline sẽ bị chặn (FAIL).

### 1.2. Thách thức Kiến trúc khi Thêm Module Mới
Hiện tại trong `backend/app/application.py`:
```python
application.include_router(api_router)
```
Tất cả các route từ mọi module đều được gộp chung vào một router duy nhất `api_router` (`backend/app/api/router.py`).
Nếu chúng ta khai báo các endpoint mới của `math_solutions` trực tiếp vào `api_router`:
- Hàm `app.openapi()` của ứng dụng chính sẽ tự động gom các endpoint mới vào schema tổng.
- File `openapi-v1.json` và mã hash `openapi-v1.sha256` sẽ ngay lập tức bị lệch (Drift detected).
- **Ràng buộc cấm (`API-V1-FREEZE`)**: Quy định dự án nghiêm cấm việc sửa đổi file checksum `openapi-v1.sha256` để "hợp thức hóa" contract drift của v1.
- **Ràng buộc cấm giả lập cấu hình**: Không được phép thay thế cơ chế sinh hợp đồng v1 bằng một ứng dụng dummy/mock có cấu hình khác với `create_app(settings)` thực tế trong sản xuất.

---

## 2. Phân tích Các Phương án Kỹ thuật Phiên bản Hóa

### Phương án A (BỊ BÁC BỎ): Dùng dummy `FastAPI` instance trong script xuất hợp đồng
- **Cách làm**: Sửa `export_contract.py` để khởi tạo `app = FastAPI(title="EduMS v1", ...)` và chỉ include `api_router`, tách riêng khỏi `create_app()`.
- **Lý do bác bỏ**: Vi phạm nguyên tắc bảo toàn hợp đồng thực tế. Việc tạo một instance giả lập với metadata khác làm mất đi tính đại diện trung thực của ứng dụng runtime, che giấu các lỗi cấu hình middleware hoặc lifespan.

### Phương án B (BỊ BÁC BỎ): Gộp router v2 vào app gốc với tiền tố `APIRouter(prefix="/api/v2")`
- **Cách làm**: `application.include_router(api_v2_router)`.
- **Lý do bác bỏ**: Khi dùng `include_router`, FastAPI mặc định hợp nhất toàn bộ routes vào một cây tài liệu OpenAPI duy nhất (`application.openapi()`). Điều này làm hỏng 100% mã hash của `openapi-v1.sha256`.

### Phương án C (ĐƯỢC CHỌN - CHUẨN KIẾN TRÚC): FastAPI Sub-Application Mount tại `/api/v2`
- **Cách làm**:
  - Tạo một ứng dụng FastAPI con riêng biệt: `v2_app = create_v2_app(configuration)`.
  - Mount ứng dụng con vào ứng dụng chính: `application.mount("/api/v2", v2_app)`.
- **Cơ chế hoạt động sâu của FastAPI / Starlette**:
  1. **Tách biệt OpenAPI tự nhiên**: Starlette coi một mounted app là một ASGI endpoint độc lập. Bộ sinh OpenAPI mặc định của FastAPI (`application.openapi()`) **chỉ quét các route được đăng ký trực tiếp trên app cha, hoàn toàn không đào sâu vào mounted sub-apps**.
  2. **Bảo tồn tuyệt đối OpenAPI v1**: `create_app(settings).openapi()` tiếp tục trả về chính xác 100% schema của toàn bộ route v1 hiện hành mà không cần bất kỳ bộ lọc, mock app hay cấu hình phụ nào.
  3. **OpenAPI v2 độc lập**: Bản thân `v2_app` sở hữu OpenAPI schema riêng biệt, có tài liệu Swagger tại `/api/v2/docs` và schema tại `/api/v2/openapi.json`.
  4. **Không bị lặp tiền tố URL**: Trong `v2_app`, các route được định nghĩa theo đường dẫn tương đối (ví dụ: `@router.post("/math-solutions/attempts")`). Khi được mount tại `/api/v2`, đường dẫn tuyệt đối chuẩn xác là `/api/v2/math-solutions/attempts`, hoàn toàn triệt tiêu nguy cơ sinh trùng lặp `/api/v2/api/v2/...`.

---

## 3. Thiết kế Mã nguồn Chi tiết (Implementation Specification)

### 3.1. Cấu trúc Khởi tạo Ứng dụng v2 (`backend/app/api/v2/application.py`)
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import Settings
from app.core.errors import ErrorResponse, register_exception_handlers
from app.api.v2.router import api_v2_router

def create_v2_app(settings: Settings) -> FastAPI:
    """Tạo FastAPI sub-application độc lập cho API v2."""
    v2_app = FastAPI(
        title=f"{settings.app_name} API v2",
        version="2.0.0",
        description="EduMS API v2 — Step-by-Step Math Solution Engine & Advanced Learning Services.",
        debug=False,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        responses={
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    v2_app.state.settings = settings
    register_exception_handlers(v2_app)
    v2_app.include_router(api_v2_router)
    return v2_app
```

### 3.2. Router v2 (`backend/app/api/v2/router.py`)
```python
from fastapi import APIRouter
from app.math_solutions.router import router as math_solutions_router

api_v2_router = APIRouter()
# Không đặt prefix="/api/v2" ở đây vì mount("/api/v2", ...) đã cung cấp tiền tố gốc
api_v2_router.include_router(
    math_solutions_router,
    prefix="/math-solutions",
    tags=["Math Solutions (v2)"],
)
```

### 3.3. Tích hợp Mount trong `backend/app/application.py`
```python
def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else get_settings()
    application = FastAPI(
        title=configuration.app_name,
        version=API_VERSION,
        description="EduMS education management and university entrance exam support API.",
        debug=False,
        lifespan=lifespan,
        responses={
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    application.state.settings = configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[configuration.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Accept", "Content-Type", "Authorization"],
    )
    register_exception_handlers(application)
    
    # 1. API v1 hiện hành (giữ nguyên gốc)
    application.include_router(api_router)
    
    # 2. Mount API v2 sub-application tại /api/v2
    # LƯU Ý: mount() không đưa route con vào application.openapi() -> Bảo toàn v1 freeze!
    from app.api.v2.application import create_v2_app
    v2_subapp = create_v2_app(configuration)
    application.mount("/api/v2", v2_subapp)
    
    return application
```

---

## 4. Quản lý Hợp đồng Song song (Dual Contract Lifecycle)

### 4.1. Cấu trúc Lưu trữ Hợp đồng
```
backend/contracts/
├── openapi-v1.json        # [FROZEN] Khóa cứng toàn bộ API v1
├── openapi-v1.sha256      # [FROZEN] Checksum bất biến của v1
├── openapi-v2.json        # [ACTIVE] Hợp đồng mới của API v2
└── openapi-v2.sha256      # [ACTIVE] Checksum tự động của v2
```

### 4.2. Cơ chế Sinh Schema Chuẩn tắc (`backend/app/api/export_contract.py`)
```python
def get_deterministic_schema() -> dict[str, Any]:
    """Sinh lược đồ OpenAPI v1 chuẩn từ ứng dụng thực tế.
    Nhờ cơ chế mount, lược đồ này hoàn toàn không chứa route v2."""
    settings = get_contract_settings()
    app = create_app(settings)
    return app.openapi()

def get_v2_deterministic_schema() -> dict[str, Any]:
    """Sinh lược đồ OpenAPI v2 chuẩn từ sub-application v2."""
    from app.api.v2.application import create_v2_app
    settings = get_contract_settings()
    v2_app = create_v2_app(settings)
    return v2_app.openapi()
```

### 4.3. Kịch bản Kiểm tra Hợp đồng (`backend/app/api/check_contract.py`)
Script kiểm tra thực hiện hai pha độc lập:
1. **Pha 1 — Kiểm tra v1 (`verify_v1_contract()`)**:
   - Chạy `get_deterministic_schema()`.
   - Đối chiếu với `openapi-v1.json` và `openapi-v1.sha256`.
   - Nếu có bất kỳ sự thay đổi nào $\to$ Báo lỗi thất bại ngay lập tức (FAIL).
2. **Pha 2 — Kiểm tra v2 (`verify_v2_contract()`)**:
   - Chạy `get_v2_deterministic_schema()`.
   - Đối chiếu với `openapi-v2.json` và `openapi-v2.sha256`.
   - Kiểm soát contract drift của các tính năng mới mà không đụng chạm đến v1.

---

## 5. Kế hoạch Regression Chứng minh Tính Toàn vẹn (Regression Proof Plan)

Kế hoạch kiểm thử regression xác minh 4 luận điểm kỹ thuật bắt buộc:

| Mục tiêu chứng minh | Phương pháp kiểm thử | Kết quả kỳ vọng |
| :--- | :--- | :--- |
| **1. OpenAPI v1 giữ nguyên nội dung và checksum** | Chạy `.venv\Scripts\python -m app.api.check_contract` sau khi mount sub-app v2 rỗng/có route. | Trả về mã thoát 0: `API v1 contract verification PASSED`. File `openapi-v1.sha256` không lệch 1 bit. |
| **2. API v2 có hợp đồng độc lập** | Gọi `GET /api/v2/openapi.json` trên test client; chạy `verify_v2_contract()`. | Schema v2 chỉ chứa các thẻ `Math Solutions (v2)` và các endpoint `/math-solutions/...`, có mã hash v2 riêng biệt. |
| **3. Các endpoint v1 giữ nguyên hành vi** | Chạy toàn bộ test suite hiện có của backend: `pytest tests/`. | 100% tests của `auth/`, `students/`, `practice/`, `assignments/`, `mastery/` vượt qua bình thường, đường dẫn và quyền truy cập không đổi. |
| **4. Mount không sinh tiền tố lặp** | Kiểm tra danh sách URLs bằng `TestClient(app)`: gọi `POST /api/v2/math-solutions/attempts`. | Request được route chính xác tới handler v2; không tồn tại các path dạng `/api/v2/api/v2/...` hay `/api/v2/v2/...`. |

---

## 6. Architecture Decision Record (ADR)

### ADR-01: Lựa chọn Kiến trúc Phiên bản hóa API cho Sprint 1.1

- **Trạng thái**: ĐÃ DUYỆT (ACCEPTED)
- **Bối cảnh**: Hệ thống yêu cầu đóng băng vĩnh viễn hợp đồng API v1 (`API-V1-FREEZE`), nghiêm cấm cập nhật checksum `openapi-v1.sha256`. Module mới `math_solutions` yêu cầu mở rộng các endpoint RESTful hiện đại.
- **Quyết định**: Sử dụng FastAPI Sub-application mount tại `/api/v2` thay vì gộp chung APIRouter vào root app.
- **Hệ quả tích cực**:
  - Bảo vệ 100% hợp đồng v1 mà không cần can thiệp logic sinh schema giả lập.
  - Tách biệt hoàn toàn OpenAPI docs cho v1 và v2.
  - Không sinh tiền tố lặp, đảm bảo URL RESTful tiêu chuẩn.
  - Phù hợp với kiến trúc Modular Monolith mở rộng dài hạn.
- **Hệ quả cần quản lý**: Cần duy trì 2 file hợp đồng (`openapi-v1.json` và `openapi-v2.json`) trong CI pipeline.


---
### Ghi chú STEP-ARCH-00 — shared schemas
Mount API v2 tách OpenAPI route tree nhưng **không cô lập enum/schema dùng chung với API v1**. Việc thêm `MATH_SOLUTION_EVALUATION` vào `LearningEvidenceSourceKind` có thể gây OpenAPI v1 drift. Phải chạy exact hash contract checker từ `create_app(settings)`, tách internal persistence/v2 DTO nếu cần, không re-freeze v1 để che drift. Test mount, CORS, auth, responses 422/500, không lộ rubric.
