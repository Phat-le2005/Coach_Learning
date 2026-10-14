# STEP-FE-01 — Giao diện Giải toán Theo bước, Biên tập Bảng xét dấu & Hoán đổi Thứ tự

Tài liệu thiết kế kiến trúc, triển khai giao diện người dùng và kiểm thử nghiệm thu thành phần Giải toán Theo bước (Step-by-Step Math Solver) cho học sinh khối 12 môn Toán (Chuyên đề Tính đơn điệu hàm số), tích hợp biên tập bảng xét dấu tương tác, quản lý lịch sử phiên bản và bảo vệ bất biến nộp bài.

---

## 1. Mục tiêu và Nguyên tắc Bất biến (Core Invariants)

### Mục tiêu
1. **Giao diện Giải toán Tương tác**: Cung cấp giao diện trực quan cho học sinh thêm mới, chỉnh sửa, xóa và hoán đổi vị trí các bước giải toán.
2. **Biên tập Bảng xét dấu Tương tác (`SignTableEditor`)**:
   - Nhập tọa độ điểm tới hạn $x$ (hỗ trợ cả số nguyên, số thực và ký hiệu LaTeX như `\sqrt{2}`).
   - Click một chạm để xoay vòng dấu đạo hàm $y'$ qua các trạng thái: `+` $\rightarrow$ `-` $\rightarrow$ `0` $\rightarrow$ `||` $\rightarrow$ `+`.
   - Đảo toàn bộ dấu đạo hàm (Invert All Signs) hỗ trợ nhận diện và sửa lỗi nhận thức ngược dấu phổ biến.
   - Luôn bảo toàn tính bất biến hình học: `signs.length === critical_points.length + 1`.
3. **Hoán đổi Thứ tự Bước giải (Step Reordering)**: Nút di chuyển lên/xuống (Move Up/Down) với kiểm tra biên tức thì, cập nhật mảng `step_ids` và gửi token lạc quan `expected_attempt_revision`.
4. **Lịch sử Phiên bản & Rollback (`RevisionViewerModal`)**: Xem danh sách các sửa đổi trước đó của từng bước giải và khôi phục (rollback) về phiên bản mong muốn.
5. **Định tuyến Chuẩn Next.js 16**: Trang `/student/practice/solutions/[attemptId]` với kiểm soát phân quyền (`requirePageRole("STUDENT")`), SSR prefetch và xử lý lỗi `PageState`.

### Nguyên tắc Bất biến Bắt buộc (Crucial Invariants)
> [!IMPORTANT]
> 1. **Khớp Chuẩn Schema Backend Evaluator**: Dữ liệu artifact bảng xét dấu sinh ra từ frontend phải tuân thủ nghiêm ngặt định dạng `{ critical_points: [-1, 3], signs: ["+", "-", "+"] }`, khớp 100% với mong đợi của `DeterministicMathValidator` và `MisconceptionClassifier`.
> 2. **Chống Tranh chấp Phiên bản (Optimistic Concurrency Control)**: Mọi thao tác đột biến bước giải (Thêm, Xóa, Sửa, Reorder, Rollback, Submit) đều gửi kèm `expected_attempt_revision` và `client_action_id` (UUIDv4) để chống race condition.
> 3. **Khóa Đóng băng khi Nộp bài (Read-Only Enforcement)**: Khi lượt làm bài chuyển sang trạng thái `SUBMITTED` hoặc `EVALUATED`, toàn bộ controls (thêm bước, sửa, xóa, reorder, đảo dấu) tự động chuyển sang chế độ chỉ xem (Read-Only).

---

## 2. Cấu trúc Mô-đun & Thành phần Triển khai

```
frontend/
├── src/
│   ├── app/
│   │   └── student/
│   │       └── practice/
│   │           └── solutions/
│   │               └── [attemptId]/
│   │                   └── page.tsx                # Trang SSR giải toán theo bước
│   └── features/
│       └── math-solver/
│           ├── types.ts                            # Định nghĩa kiểu dữ liệu frontend
│           ├── utils.ts                            # Hàm biến đổi trạng thái thuần túy
│           ├── MathSolutionSolver.tsx              # Component trung tâm quản lý luồng
│           ├── MathSolutionSolver.module.css       # Layout responsive & styling
│           └── components/
│               ├── SignTableEditor.tsx             # Bộ biên tập bảng xét dấu
│               ├── SignTableEditor.module.css
│               ├── StepCard.tsx                    # Thẻ hiển thị bước giải & actions
│               ├── StepCard.module.css
│               ├── RevisionViewerModal.tsx         # Modal lịch sử phiên bản & rollback
│               └── RevisionViewerModal.module.css
└── tests/
    └── math-solver.test.ts                         # Bộ test suite 14 unit tests
```

---

## 3. Chi tiết Kỹ thuật

### 3.1. Bộ Biên tập Bảng xét dấu (`SignTableEditor`)
- Chu trình xoay vòng dấu: `cycleSign(currentSign)` biến đổi tuần hoàn qua `["+", "-", "0", "||"]`.
- Thêm điểm tới hạn: `addCriticalPoint(current, pointInput)` tự động bổ sung dấu mặc định `+` để duy trì tỉ lệ $N$ điểm ứng với $N+1$ khoảng dấu.
- Xóa điểm tới hạn: `removeCriticalPoint(current, index)` gọt bỏ điểm và dấu tương ứng, đảm bảo tối thiểu còn 1 dấu.
- Đảo dấu tức thì: `invertSigns(signs)` đảo hoán đổi giữa `+` và `-`, giữ nguyên `0` và `||`.

### 3.2. Quản lý Thứ tự & Danh sách Bước (`StepCard` & `reorderStepsList`)
- Hàm `reorderStepsList(steps, stepId, direction)` bỏ qua các bước đã xóa (`is_deleted: true`), hoán vị 2 bước liền kề và trả về danh sách `stepIds` mới.
- Xử lý biên triệt để: Nút Move Up ở bước đầu tiên và Move Down ở bước cuối cùng tự động bị disable.

### 3.3. Trang Next.js 16 (`student/practice/solutions/[attemptId]/page.tsx`)
- Sử dụng async Server Component với `params: Promise<{ attemptId: string }>`.
- Xác thực bảo mật phân quyền qua `requirePageRole("STUDENT", targetPath)`.
- Nạp SSR song song dữ liệu `SolutionSolverAttempt` và `ProblemRead`.
- Xử lý thân thiện các trạng thái lỗi 404 (Không tìm thấy) và 403 (Không có quyền truy cập) bằng `PageState`.
- Tích hợp `SessionHeartbeat` nhằm duy trì phiên đăng nhập của học sinh trong suốt quá trình giải bài tập.

---

## 4. Kiểm thử Nghiệm thu & Kết quả Quality Gate

### 4.1. Unit Test Suite (`frontend/tests/math-solver.test.ts`)
Bao phủ toàn diện 14 kịch bản kiểm thử:
1. `SIGN_CYCLE`: Xác nhận đủ 4 ký hiệu chuẩn tắc `["+", "-", "0", "||"]`.
2. `cycleSign`: Kiểm tra chu trình chuyển tiếp dấu tuần hoàn.
3. `cycleSign` fallback: Xử lý an toàn khi gặp ký hiệu không xác định.
4. `invertSigns`: Đảo `+`/`-`, bảo tồn `0`/`||`, tính chất đối xứng kép (double inversion).
5. `addCriticalPoint` (numeric): Chèn điểm số và duy trì bất biến $N$ điểm $\rightarrow N+1$ dấu.
6. `addCriticalPoint` (string/latex): Không bị lỗi `NaN` khi nhập biểu thức LaTeX.
7. `removeCriticalPoint`: Xóa điểm và đồng bộ mảng dấu.
8. `removeCriticalPoint` (last point): Giữ ít nhất 1 dấu khi bảng trống.
9. `reorderStepsList` (Move Up): Hoán vị bước lên phía trước chính xác.
10. `reorderStepsList` (Move Down): Hoán vị bước xuống phía sau chính xác.
11. `reorderStepsList` (boundary): Chặn di chuyển vượt biên trên và biên dưới.
12. `reorderStepsList` (deleted): Bỏ qua các bước đã xóa khỏi thứ tự tương tác.
13. `canSubmitAttempt`: Kiểm tra điều kiện nộp bài (chặn nộp khi rỗng, đã nộp, hoặc chỉ có bước đã xóa).
14. Schema compatibility: Kiểm tra tính tương thích 100% với backend evaluator.

### 4.2. Kết quả Chạy Test Toàn diện
- **Frontend Test Suite**: **117/117 tests PASS** (Node test runner).
- **TypeScript Typecheck**: Hoàn tất thành công, 0 lỗi (`next typegen && tsc --noEmit`).
- **Turbopack Production Build**: Hoàn tất thành công (`next build`), tạo thành công route `/student/practice/solutions/[attemptId]`.
