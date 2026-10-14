# STEP-MATH-OCR-03 — Nhận diện nét vẽ Toán học & Xác nhận bước giải (Human-in-the-Loop OCR)

Tài liệu thiết kế kiến trúc, triển khai và nghiệm thu tính năng OCR nhận diện nét vẽ viết tay toán học trên nền tảng EduMS.

---

## 1. Mục tiêu và Nguyên tắc Bất biến (Core Invariant)

### Mục tiêu
Cung cấp khả năng nhận diện quang học nét vẽ viết tay (Vector Ink) thành công thức toán học chuẩn LaTeX và phân loại bước giải, hỗ trợ học sinh lớp 12 chuyển đổi nhanh từ bài làm trên giấy A4 số sang các bước giải có cấu trúc được hệ thống chấm điểm và phân tích năng lực.

### Nguyên tắc Bất biến Bắt buộc (Crucial Invariant)
> [!IMPORTANT]
> **Nét vẽ OCR tuyệt đối KHÔNG ĐƯỢC tự động ghi vào `SolutionStep` hay sinh sự kiện `LearningEvidenceEvent` / `Mastery`**.
> Kết quả OCR chỉ mang tính chất gợi ý (Advisory Suggestion). Học sinh **bắt buộc** phải xem xét, có quyền chỉnh sửa công thức LaTeX và phần diễn giải, sau đó chủ động nhấn **"Xác nhận bước giải"** thì hệ thống mới tạo bản ghi bước giải chính thức thông qua endpoint `POST /api/v2/math-solutions/attempts/{attempt_id}/steps`.

---

## 2. Thiết kế Kiến trúc Backend (API v2)

### 2.1. Pattern Adapter (`MathOCRAdapter`)
- Thiết kế theo mẫu Adapter linh hoạt ([`MathOCRAdapter`](file:///d:/CoachLearning/backend/app/math_ocr/adapter.py)):
  - Giao diện trừu tượng `recognize(strokes, hint_topic) -> OCRRecognizeResponse`.
  - Triển khai [`MockMathOCRAdapter`](file:///d:/CoachLearning/backend/app/math_ocr/adapter.py#L21) phục vụ testing tự động, phát triển ngoại tuyến và CI deterministic (hỗ trợ các chủ đề trọng điểm Toán 12: Đạo hàm, Tích phân/Nguyên hàm, Hình học không gian Oxyz, Xác suất có điều kiện).
  - Khả năng mở rộng sang các dịch vụ Vision/LLM OCR trong môi trường production.

### 2.2. Dịch vụ Nghiệp vụ ([`MathOCRService`](file:///d:/CoachLearning/backend/app/math_ocr/service.py))
- Kiểm tra quyền sở hữu (Actor Student Ownership): trả về 403 nếu không phải học sinh, trả về 404 nếu attempt không tồn tại hoặc không thuộc học sinh hiện tại.
- Nạp danh sách nét vẽ của trang chỉ định từ [`MathInkService.get_page()`](file:///d:/CoachLearning/backend/app/math_ink/service.py).
- Hỗ trợ lọc nét vẽ theo `stroke_ids` (nếu học sinh chọn vùng vẽ cụ thể).
- Kiểm tra nghiêm ngặt: Nếu trang hoặc vùng chọn không có nét vẽ nào, ném lỗi nghiệp vụ `422 NO_STROKES_FOR_OCR` ("Không tìm thấy nét vẽ nào trên trang này để thực hiện nhận diện.").

### 2.3. Endpoint API v2 ([`math_ocr_router`](file:///d:/CoachLearning/backend/app/math_ocr/router.py))
- Tuyến đường: `POST /api/v2/math-solutions/attempts/{attempt_id}/ocr/recognize`
- Request body ([`OCRRecognizeRequest`](file:///d:/CoachLearning/backend/app/math_ocr/schemas.py#L7-L11)):
  ```json
  {
    "page_index": 0,
    "stroke_ids": null,
    "hint_topic": "CALCULUS_INTEGRAL"
  }
  ```
- Response body ([`OCRRecognizeResponse`](file:///d:/CoachLearning/backend/app/math_ocr/schemas.py#L14-L21)):
  ```json
  {
    "latex": "\\int (3x^2 - 2x + 1) \\, dx = x^3 - x^2 + x + C",
    "confidence": 0.96,
    "suggested_step_type": "EXPLANATION",
    "explanation_text": "Áp dụng công thức nguyên hàm cơ bản từng số hạng.",
    "detected_symbols": ["\\int", "3x^2", "-2x", "+1", "dx", "x^3", "C"]
  }
  ```
- Cập nhật định tuyến API v2 và đồng bộ hợp đồng OpenAPI:
  - File hợp đồng: [`backend/contracts/openapi-v2.json`](file:///d:/CoachLearning/backend/contracts/openapi-v2.json)
  - Hash SHA-256 xác thực: `2c046bd166ff4f3bb9ae3dc52001b1743286e88ec32f32649e47fec408cd7dc0`

---

## 3. Thiết kế Giao diện Người dùng (Frontend UI/UX)

### 3.1. Hộp thoại Xác nhận Bước giải ([`OcrConfirmModal`](file:///d:/CoachLearning/frontend/src/features/math-workspace/components/OcrConfirmModal.tsx))
- Hiển thị trực quan ngay sau khi nhận diện hoàn tất:
  - **Huy hiệu độ tin cậy (Confidence Badge):** ví dụ `96% tin cậy` với mã màu trực quan (Xanh lá $\ge 90\%$, Vàng $\ge 75\%$, Đỏ $< 75\%$).
  - **Ký hiệu toán học phát hiện:** Hiển thị danh sách chip ký hiệu nhận diện được.
  - **Công thức LaTeX (Chỉnh sửa được):** Ô nhập văn bản monospace cho phép học sinh sửa chữa bất kỳ sai lệch nào.
  - **Xem trước công thức (Live Math Preview):** Hiển thị khối công thức rendered sắc nét theo thời gian thực.
  - **Phân loại bước giải (`StepKind`):** Menu thả xuống cho phép chọn loại bước:
    - `DERIVATIVE_CALCULATION` (Tính đạo hàm)
    - `ROOT_FINDING` (Tìm nghiệm phương trình)
    - `SIGN_TABLE` (Bảng xét dấu)
    - `VARIATION_TABLE` (Bảng biến thiên)
    - `CONCLUSION` (Kết luận)
    - `EXPLANATION` (Diễn giải / Lập luận)
    - `ASSUMPTION` (Giả thiết / ĐK xác định)
    - `CUSTOM` (Bước giải tự do)
  - **Lời giải thích / Diễn giải:** Textarea cho phép bổ sung ghi chú hoặc lý do của bước giải.
  - **Banner nhắc nhở nguyên tắc bất biến:** Thông báo rõ ràng cho học sinh rằng nét vẽ chưa được lưu thành bước giải chính thức.
  - **Nút hành động:**
    - `Hủy bỏ`: Đóng hộp thoại, không thay đổi bất kỳ trạng thái nào của bài giải.
    - `Xác nhận bước giải`: Gửi mutation `createMathStep` lên backend, cập nhật revision của attempt và đóng hộp thoại.

### 3.2. Thanh công cụ ([`WorkspaceToolbar`](file:///d:/CoachLearning/frontend/src/features/math-workspace/components/WorkspaceToolbar.tsx))
- Nút bấm **"Nhận diện AI"** với icon `Sparkles`, tự động kích hoạt trạng thái loading với spinner khi đang xử lý.
- Tự động disabled khi trang chưa có nét vẽ nào (`strokeCount === 0`) nhằm ngăn chặn request vô hiệu.

### 3.3. Điều phối Quy trình ([`MathWorkspace`](file:///d:/CoachLearning/frontend/src/features/math-workspace/MathWorkspace.tsx))
1. **Lưu vết trước khi nhận diện (Flush dirty):** Nếu trang đang có nét vẽ mới chưa được đồng bộ mạng (`isDirty === true`), hệ thống tự động đẩy lưu trữ lên backend trước khi gọi `/ocr/recognize` để đảm bảo backend nhận diện phiên bản nét vẽ mới nhất.
2. **Xác nhận người dùng:** Hiển thị `OcrConfirmModal` để học sinh kiểm duyệt.
3. **Thêm bước giải chính thức:** Sau khi học sinh xác nhận, gọi `POST /api/v2/math-solutions/attempts/{attempt_id}/steps` với `expected_attempt_revision` và `client_action_id` mới.

---

## 4. Báo cáo Kết quả Kiểm thử (Quality Gates)

| Quality Gate | Trạng thái | Chi tiết kết quả |
| :--- | :---: | :--- |
| **API v1 Freeze Checker** | **PASS** | `python -m app.api.check_contract` đạt exit code 0 |
| **API v2 Contract Checker** | **PASS** | `python -m app.api.v2.check_contract` đạt exit code 0 |
| **Backend Math OCR Tests** | **PASS** | 4/4 tests trong `tests/math_solutions/test_math_ocr.py` |
| **Backend Math Solutions Regression** | **PASS** | 61 passed, 5 skipped trong `tests/math_solutions/` |
| **PostgreSQL Real Concurrency** | **PASS** | 2/2 tests chạy trên database PostgreSQL thật |
| **Frontend Unit Tests** | **PASS** | 103/103 tests passed trong `npm test` |
| **Frontend Typecheck & Build** | **PASS** | Next.js 16.3.8 Turbopack production build pass không lỗi |
