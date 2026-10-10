# Đề xuất Kiến trúc Phiên bản Hóa API (API Versioning Proposal)
## Bảo vệ Frozen API v1 và Thiết lập API v2 cho Math Solution Engine

- **Dự án**: Coach Learning (EduMS)
- **Mã Sprint**: SPRINT-01 (ARCH-01 + DATA-READY-01)
- **Mã tài liệu**: API-VER-01
- **Trạng thái**: ĐỀ XUẤT KIẾN TRÚC (CHƯA THÊM PRODUCTION ENDPOINT)

---

## 1. Hiện trạng Kiểm tra Hợp đồng API v1 (API v1 Contract Audit)

### 1.1. Cơ chế Đóng băng Hiện tại (Current Freeze Mechanism)
Hệ thống hiện đang bảo vệ toàn vẹn hợp đồng API v1 bằng cơ chế song song:
1. **File lược đồ chuẩn tắc**: `backend/contracts/openapi-v1.json` (chứa toàn bộ định nghĩa endpoints, query params, request bodies và responses của API v1).
2. **File mã băm SHA-256**: `backend/contracts/openapi-v1.sha256` (lưu mã hash SHA-256 nhỏ gọn của schema được sinh bằng thuật toán sắp xếp khóa `sort_keys=True`).
3. **Công cụ xuất hợp đồng**: `backend/app/api/export_contract.py`:
   - Khởi tạo ứng dụng tạm với cấu hình kiểm thử (`app = create_app(settings)`).
   - Xuất schema `app.openapi()` ra file JSON và tính toán SHA-256.
4. **Công cụ kiểm tra hợp đồng**: `backend/app/api/check_contract.py`:
   - So sánh schema thời gian thực với `openapi-v1.json` và mã băm `openapi-v1.sha256`.
   - Nếu phát hiện bất kỳ sự khác biệt nào (contract drift), lệnh trả về mã lỗi 1 và hiển thị diff chi tiết.
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
- Hàm `app.openapi()` sẽ tự động đưa các endpoint mới vào schema tổng.
- File `openapi-v1.json` và mã hash `openapi-v1.sha256` sẽ ngay lập tức bị lệch (Drift detected).
- **Ràng buộc cấm**: Quy định dự án nghiêm cấm việc sửa đổi file checksum `openapi-v1.sha256` để "hợp thức hóa" contract drift của v1.

Do đó, **bắt buộc phải có một kiến trúc phiên bản hóa API độc lập** cho các chức năng mới.

---

## 2. Phân tích Các Phương án Phiên bản Hóa API (Comparison of Strategies)

### Phương án 1 (Khuyến nghị): Explicit URI Versioning `/api/v2` với Hợp đồng Riêng `openapi-v2.json`
- **Mô tả**:
  - Giữ nguyên toàn bộ `api_router` hiện tại phục vụ API v1 (tất cả các route gốc `/students`, `/teachers`, `/practice`, `/assignments`, `/mastery`... giữ nguyên tiền tố và ngữ nghĩa).
  - Tạo router phiên bản mới `api_v2_router` (hoặc mount tại tiền tố `/api/v2` hoặc tạo sub-app FastAPI).
  - Toàn bộ endpoints của `math_solutions` được đặt dưới `/api/v2/math-solutions/...`.
  - Hợp đồng mới được xuất ra file riêng: `backend/contracts/openapi-v2.json` và `backend/contracts/openapi-v2.sha256`.
  - Mở rộng script `check_contract.py` để kiểm tra độc lập cả hai hợp đồng:
    - Kiểm tra `openapi-v1.json` đối chiếu với v1 routes $\to$ Đảm bảo v1 không suy suyển.
    - Kiểm tra `openapi-v2.json` đối chiếu với v2 routes $\to$ Đảm bảo v2 không bị drift ngoài ý muốn.
- **Ưu điểm**:
  - **Bảo vệ tuyệt đối API v1**: Không chạm vào bất kỳ dòng nào của `openapi-v1.json` và `openapi-v1.sha256`.
  - **Tương thích hoàn hảo với frontend**: Next.js client có thể dùng `apiClientV1` cho các tính năng hiện tại và `apiClientV2` cho Solution Engine mà không bị xung đột.
  - **Hỗ trợ tự nhiên bởi FastAPI**: Dễ dàng tạo OpenAPI docs riêng cho `/docs/v1` và `/docs/v2`.
- **Nhược điểm**:
  - Cần cấu hình router v2 riêng và cập nhật nhẹ kịch bản export/check trong CI.

---

### Phương án 2: Namespaced Feature Sub-path `/api/v1-ext/math-solutions` hoặc Router Cô lập
- **Mô tả**:
  - Đặt các endpoint giải toán dưới một sub-path mở rộng, ví dụ `/api/v1-ext/math-solutions/` hoặc `/api/solutions/v1/`.
  - Không tăng số phiên bản toàn cục lên v2 mà coi đây là một "extension namespace".
- **Ưu điểm**:
  - Giữ cảm giác hệ thống vẫn ở thế hệ v1, chỉ mở rộng thêm tính năng giải toán.
- **Nhược điểm**:
  - Vẫn làm thay đổi schema của `app.openapi()` nếu mount vào cùng ứng dụng gốc, buộc phải viết middleware lọc schema phức tạp.
  - Tiền tố `/api/v1-ext/` không theo quy ước chuẩn RESTful quốc tế, gây khó hiểu cho các nhà phát triển tích hợp sau này.

---

### Phương án 3: Header-based Versioning (`Accept: application/vnd.edums.v2+json`)
- **Mô tả**:
  - Sử dụng chung đường dẫn URL, phân biệt phiên bản thông qua HTTP Request Header `Accept` hoặc `X-API-Version`.
- **Ưu điểm**:
  - Giữ nguyên cấu trúc URL sạch.
- **Nhược điểm**:
  - FastAPI không hỗ trợ native việc sinh OpenAPI phân tách rõ ràng theo header mà cần can thiệp sâu vào OpenAPI generator nội bộ.
  - Gây khó khăn lớn cho việc caching ở tầng CDN/Reverse Proxy và khó kiểm thử thủ công qua Swagger UI hoặc browser thông thường.

---

## 3. Lựa chọn và Đề xuất Kiến trúc

### Quyết định: Chọn **Phương án 1 (URI Versioning `/api/v2` với contract `openapi-v2.json`)**

#### Lý do lựa chọn:
1. **Tuân thủ triệt để nguyên tắc `API-V1-FREEZE`**:
   Bằng cách tách biệt ứng dụng con hoặc router generator cho v1 và v2, file `contracts/openapi-v1.json` và mã băm `contracts/openapi-v1.sha256` được bảo toàn 100%, không xảy ra bất kỳ rủi ro nào với CI hiện có.
2. **Cách ly rủi ro (Fault Isolation)**:
   Mọi thay đổi, bổ sung hoặc thử nghiệm đối với Solution Engine trong tương lai chỉ tác động lên schema của v2, hoàn toàn không ảnh hưởng đến sự ổn định của các module hiện tại (`practice/`, `assignments/`, `mastery/`).
3. **Phù hợp với mô hình Modular Monolith**:
   Mô hình này cho phép backend phát triển thành các thế hệ API rõ ràng, minh bạch cho đội ngũ frontend và các đối tác tích hợp.

---

## 4. Kế hoạch Triển khai Chi tiết (Implementation Plan)

### 4.1. Cấu trúc Thư mục Đề xuất
```
backend/
├── app/
│   ├── api/
│   │   ├── check_contract.py         # Mở rộng để kiểm tra cả v1 và v2
│   │   ├── export_contract.py        # Mở rộng để xuất cả openapi-v1 và openapi-v2
│   │   ├── router.py                 # Router v1 hiện tại (GIỮ NGUYÊN)
│   │   ├── v2/
│   │   │   ├── __init__.py
│   │   │   └── router.py             # Router v2 tập hợp các feature v2
│   ├── math_solutions/
│   │   ├── router.py                 # Endpoints của Solution Engine
│   │   ├── schemas.py
│   │   └── service.py
├── contracts/
│   ├── openapi-v1.json               # ĐÓNG BĂNG (KHÔNG CHỈNH SỬA)
│   ├── openapi-v1.sha256             # ĐÓNG BĂNG (KHÔNG CHỈNH SỬA)
│   ├── openapi-v2.json               # HỢP ĐỒNG MỚI CHO V2
│   └── openapi-v2.sha256             # MÃ BĂM MỚI CHO V2
```

### 4.2. Thiết kế Mã nguồn Cụ thể (Kế hoạch khi kích hoạt STEP-API-01)

#### 1. Router v2 (`backend/app/api/v2/router.py`)
```python
from fastapi import APIRouter
from app.math_solutions.router import router as math_solutions_router

api_v2_router = APIRouter(prefix="/api/v2")
api_v2_router.include_router(math_solutions_router, prefix="/math-solutions", tags=["Math Solutions (v2)"])
```

#### 2. Tích hợp trong `application.py`
```python
def create_app(settings: Settings | None = None) -> FastAPI:
    ...
    # v1 Router (Mount tại gốc hoặc theo prefix cũ)
    application.include_router(api_router)
    
    # v2 Router (Mount riêng biệt dưới /api/v2)
    application.include_router(api_v2_router)
    return application
```

#### 3. Bộ tạo Schema Độc lập (`export_contract.py`)
Để tạo schema v1 độc lập mà không chứa các route v2:
```python
def get_v1_deterministic_schema() -> dict[str, Any]:
    # Khởi tạo app chỉ include api_router v1
    app = FastAPI(title="EduMS v1", version="1.0.0")
    app.include_router(api_router)
    return app.openapi()

def get_v2_deterministic_schema() -> dict[str, Any]:
    # Khởi tạo app include api_v2_router
    app = FastAPI(title="EduMS v2", version="2.0.0")
    app.include_router(api_v2_router)
    return app.openapi()
```
Bằng kỹ thuật này:
- `openapi-v1.json` được sinh **chính xác 100% từ `api_router` v1**, giữ nguyên vẹn hash `openapi-v1.sha256` mà không bị lẫn route v2.
- `openapi-v2.json` được sinh độc lập từ `api_v2_router` với mã hash riêng.

#### 4. Kịch bản Kiểm tra Hợp đồng (`check_contract.py`)
Script sẽ chạy tuần tự hai vòng kiểm tra:
1. `verify_contract_v1()`: Đọc `openapi-v1.json` và `openapi-v1.sha256` $\to$ Báo lỗi nếu có drift v1.
2. `verify_contract_v2()`: Đọc `openapi-v2.json` và `openapi-v2.sha256` $\to$ Báo lỗi nếu có drift v2.

---

## 5. Danh mục Endpoints Đề xuất cho Solution Engine (API v2)

*(Dự kiến triển khai tại Sprint tiếp theo sau khi phương án được phê duyệt; KHÔNG thêm vào production lúc này)*:

| Phương thức | Đường dẫn | Chức năng | Phân quyền |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v2/math-solutions/attempts` | Khởi tạo phiên giải bài (`SolutionAttempt`) | `STUDENT` |
| `GET` | `/api/v2/math-solutions/attempts/{id}` | Lấy chi tiết bài làm, danh sách bước & feedback | `STUDENT`, `TEACHER` |
| `POST` | `/api/v2/math-solutions/attempts/{id}/steps` | Thêm bước giải mới vào bài làm | `STUDENT` |
| `PATCH` | `/api/v2/math-solutions/attempts/{id}/steps/{step_id}` | Cập nhật nội dung bước (tạo `StepRevision` mới) | `STUDENT` |
| `DELETE` | `/api/v2/math-solutions/attempts/{id}/steps/{step_id}` | Xóa mềm bước giải | `STUDENT` |
| `POST` | `/api/v2/math-solutions/attempts/{id}/reorder` | Sắp xếp lại thứ tự các bước | `STUDENT` |
| `POST` | `/api/v2/math-solutions/attempts/{id}/steps/{step_id}/rollback` | Khôi phục bước về một `revision_number` cũ | `STUDENT` |
| `POST` | `/api/v2/math-solutions/attempts/{id}/evaluate-step/{step_id}` | Yêu cầu đánh giá bước tức thì (chế độ Guided) | `STUDENT` |
| `POST` | `/api/v2/math-solutions/attempts/{id}/submit` | Nộp bài toàn bộ và kích hoạt chấm chung cuộc | `STUDENT` |
| `GET` | `/api/v2/math-solutions/rubrics/{question_id}` | Xem rubric chấm của câu hỏi | `TEACHER`, `STUDENT` |
| `POST` | `/api/v2/math-solutions/attempts/{id}/teacher-grade` | Giáo viên chấm bài / ghi đè điểm | `TEACHER` |

---

## 6. Cam kết Ràng buộc Kiến trúc

1. **Không can thiệp vào `contracts/openapi-v1.json` và `contracts/openapi-v1.sha256`**.
2. **Không sửa đổi mã băm để che giấu contract drift**.
3. **Chưa thêm bất kỳ production endpoint nào trong Sprint 1 này**. Việc hiện thực hóa các router v2 sẽ được tiến hành trong Sprint tiếp theo (`STEP-API-01`) theo đúng lộ trình backlog được phê duyệt.
