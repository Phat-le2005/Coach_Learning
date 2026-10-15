# STEP-FE-MATH-INK-02 — Không gian làm bài Toán (Math Workspace Canvas UI)

Tài liệu kỹ thuật và kiến trúc cho giao diện viết tay giải toán trên nền tảng EduMS.

---

## 1. Mục tiêu và Kiến trúc

Gói công việc **STEP-FE-MATH-INK-02** hiện thực hóa giao diện tương tác giải bài toán viết tay số hóa, kết nối trực tiếp với backend **Math Ink v2** (được cung cấp từ `STEP-MATH-INK-01`).

### Bố cục không gian làm bài (Split 2-Column Layout)
- **Cột trái (35% chiều rộng):** Bảng hiển thị đề bài ([`ProblemPane`](file:///d:/CoachLearning/frontend/src/features/math-workspace/components/ProblemPane.tsx))
  - Hiển thị nội dung đề bài Toán, phân loại câu hỏi (Trắc nghiệm, Tự luận, Trả lời ngắn, Đúng/Sai).
  - Hiển thị danh sách các phương án A, B, C, D (đối với câu hỏi trắc nghiệm).
  - Có nút thu gọn/mở rộng (Collapse/Expand) để học sinh có thể chuyển nhanh sang chế độ tập trung toàn màn hình vào trang giấy A4.
- **Cột phải (65% chiều rộng):** Khung trang giấy A4 ([`MathCanvas`](file:///d:/CoachLearning/frontend/src/features/math-workspace/components/MathCanvas.tsx))
  - Khung giấy theo đúng tỷ lệ chuẩn A4 ($1 : \sqrt{2} \approx 1.414$, kích thước cơ sở $794 \times 1123\text{ px}$).
  - Tùy chọn 3 loại mặt giấy linh hoạt: **Lưới ô vuông ca-rô (Grid Caro)**, **Dòng kẻ ngang (Ruled Lines)**, hoặc **Giấy trơn (Plain)**.
  - Hỗ trợ High-DPI (`window.devicePixelRatio`) khử răng cưa và hiển thị sắc nét trên màn hình Retina / 4K.

---

## 2. Thanh công cụ (Workspace Toolbar)

Thanh công cụ [`WorkspaceToolbar`](file:///d:/CoachLearning/frontend/src/features/math-workspace/components/WorkspaceToolbar.tsx) cung cấp đầy đủ các thao tác cần thiết cho học sinh:
- **Bút viết (Pen):**
  - Chỉnh độ dày nét: 1px, 2px, 3px, 5px, 8px.
  - Bảng màu mực tiêu chuẩn: Đen (`#0f172a`), Xanh dương (`#2563eb`), Đỏ (`#dc2626`), Xanh lá (`#059669`), Cam (`#d97706`), Tím (`#7c3aed`).
- **Bút dạ quang (Highlighter):**
  - Tô nổi bật các bước quan trọng hoặc đề bài với độ trong suốt phù hợp, nét dày 12px, 18px, 24px.
- **Bút xóa nét (Stroke Eraser):**
  - Thuật toán tính khoảng cách Euclidean từ vị trí con trỏ/ngón tay tới các đoạn thẳng của nét vẽ ([`strokeIntersectsPoint`](file:///d:/CoachLearning/frontend/src/features/math-workspace/utils/ink-math.ts#L48-L70)), xóa trọn vẹn nét vẽ khi chạm phải mà không làm đứt gãy dữ liệu vector.
- **Lịch sử thao tác:** Hoàn tác (Undo) và Làm lại (Redo) với ngăn xếp lịch sử riêng biệt cho từng trang.
- **Xóa trang:** Xóa toàn bộ nét vẽ của trang hiện tại có hộp thoại xác nhận.
- **Thu phóng (Zoom & Pan):** Thu nhỏ đến 60%, phóng to đến 200%, hoặc đặt lại tỷ lệ 100%.
- **Phím tắt nhanh:**
  - `Ctrl+Z` / `Cmd+Z`: Hoàn tác (Undo).
  - `Ctrl+Y` / `Cmd+Shift+Z`: Làm lại (Redo).
  - `P`: Chuyển nhanh sang Bút viết.
  - `H`: Chuyển nhanh sang Bút dạ quang.
  - `E`: Chuyển nhanh sang Bút xóa.
  - `[` / `]`: Chuyển sang Trang trước / Trang sau.

---

## 3. Quản lý Đa trang (Multi-Page Navigation)

Thanh điều hướng [`PageNavigator`](file:///d:/CoachLearning/frontend/src/features/math-workspace/components/PageNavigator.tsx) hỗ trợ:
- Điều hướng: Nút chuyển trang trước (`<`), trang sau (`>`), hoặc nhấp trực tiếp vào số trang.
- Giới hạn: Tối đa **30 trang** (chỉ số 0 đến 29) đồng bộ với giới hạn của backend API.
- Thêm trang (`+ Thêm trang`) và Xóa trang (`Xóa trang` khi tổng số trang > 1).
- Trạng thái lưu trữ của từng trang được cách ly và quản lý độc lập.

---

## 4. Cơ chế Lưu trữ và Ngoại tuyến (Autosave & Offline Persistence)

- **Chuẩn hóa tọa độ:** Toàn bộ điểm vẽ được chuẩn hóa về dải $[0, 1]$ tương đối so với kích thước trang $W \times H$. Nét vẽ độc lập với độ phân giải màn hình của người dùng.
- **Lưu trữ cục bộ IndexedDB ([`MathInkOfflineStorage`](file:///d:/CoachLearning/frontend/src/features/math-workspace/storage/indexeddb.ts)):**
  - Ngay khi nhả bút (`pointerup`), nét vẽ mới được ghi nhận ngay lập tức vào IndexedDB (`edums_math_ink_v1`) trong vòng dưới 5ms.
  - Khi mất kết nối Internet, bản thảo vẫn được giữ an toàn trong trình duyệt với huy hiệu **"Đã lưu offline"**.
- **Autosave Debounce lên Backend:**
  - Sau 1.5 giây ngừng vẽ, hệ thống tự động gửi yêu cầu `PUT /api/v2/math-solutions/attempts/{attempt_id}/ink/pages/{page_index}` lên máy chủ.
  - Sử dụng khóa lũy thừa `client_action_id` (UUID v4) và `expected_document_revision` để kiểm soát concurrency và chống mất mát dữ liệu.
- **Xử lý xung đột (409 Conflict):**
  - Khi phát hiện xung đột phiên bản, hệ thống hiển thị huy hiệu cảnh báo kèm nút **"Tải bản mới nhất"** để người dùng chủ động nạp lại bản ghi máy chủ mà không làm hỏng dữ liệu cục bộ.

---

## 5. Danh sách File Triển khai

| Đường dẫn file | Mục đích / Chức năng |
| :--- | :--- |
| `frontend/src/lib/api/contracts.ts` | Bổ sung DTO interfaces và parsers cho Math Ink & Math Solutions V2 |
| `frontend/src/lib/api/client.ts` | Thêm các phương thức API client gọi endpoint `/api/v2/math-solutions/...` |
| `frontend/src/features/math-workspace/types.ts` | Khai báo kiểu dữ liệu, thông số A4 và trạng thái của Math Workspace |
| `frontend/src/features/math-workspace/utils/ink-math.ts` | Thuật toán chuẩn hóa tọa độ, tính khoảng cách và phát hiện va chạm nét vẽ |
| `frontend/src/features/math-workspace/storage/indexeddb.ts` | Bộ điều hợp IndexedDB lưu trữ bản nháp ngoại tuyến và theo dõi dirty state |
| `frontend/src/features/math-workspace/components/SyncStatusBadge.tsx` | Huy hiệu trạng thái đồng bộ và lưu trữ (Saved, Saving, Offline, Conflict, Error) |
| `frontend/src/features/math-workspace/components/WorkspaceToolbar.tsx` | Thanh công cụ Bút viết, Bút dạ, Bút xóa, Bảng màu, Kẻ ô, Thu phóng, Undo/Redo |
| `frontend/src/features/math-workspace/components/PageNavigator.tsx` | Thanh điều hướng chuyển trang, thêm trang và xóa trang |
| `frontend/src/features/math-workspace/components/ProblemPane.tsx` | Cột bên trái hiển thị đề bài toán, phương án trắc nghiệm và nút thu gọn |
| `frontend/src/features/math-workspace/components/MathCanvas.tsx` | Canvas vẽ nét A4 hiệu năng cao 60fps hỗ trợ cảm ứng lực PointerEvents |
| `frontend/src/features/math-workspace/MathWorkspace.tsx` | Component điều phối trung tâm quản lý trang, lịch sử và đồng bộ dữ liệu |
| `frontend/src/features/math-workspace/MathWorkspace.module.css` | Giao diện CSS Module thiết kế chuẩn tỷ lệ A4, bố cục 2 cột và theme EduMS |
| `frontend/src/app/student/attempts/[attemptId]/page.tsx` | Server Component định tuyến App Router cho học sinh làm bài |
| `frontend/tests/math-ink-contracts.test.ts` | Unit tests kiểm thử contract validation của Math Ink |
| `frontend/tests/math-ink-geometry.test.ts` | Unit tests kiểm thử hình học nét vẽ, tỷ lệ A4 và hit-testing |

---

## 6. Kết quả Kiểm định Chất lượng (Quality Gates)

- **Frontend Typecheck & Build (`npm run check`):** **PASSED** (0 lỗi TypeScript, bản build production sinh thành công toàn bộ routes kể cả `/student/attempts/[attemptId]`).
- **Frontend Unit Tests (`npm test`):** **101/101 PASSED (100%)** với thời gian chạy 337ms.
