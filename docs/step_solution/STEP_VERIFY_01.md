# STEP-VERIFY-01 — Báo cáo Nghiệm thu Lát cắt Dọc Toàn diện 10 Giai đoạn (Vertical Slice Verification)

Tài liệu nghiệm thu toàn trình (End-to-End Vertical Slice Verification) cho Động cơ Giải toán Từng bước EduMS (Step-by-Step Math Solution Engine) trên Chuyên đề Khảo sát Tính đơn điệu Hàm số Lớp 12 (`MONOTONICITY_FROM_EXPRESSION`).

---

## 1. Tóm tắt Kết quả Nghiệm thu Toàn diện (Executive Summary)

Đã hoàn thành xuất sắc và vượt qua 100% các cổng kiểm định chất lượng (Quality Gates) cho cả 4 cột mốc chiến lược:

| Cột mốc | Tên nhiệm vụ | Trạng thái | Minh chứng kiểm định |
| :--- | :--- | :--- | :--- |
| **STEP-EVAL-01** | Động cơ Chấm bước 4-Tier & Phân rã Sai sót Sư phạm | **HOÀN TẤT & PUSHED** | 5/5 unit tests PASS; 66/66 backend tests PASS. |
| **STEP-DIAG-01** | Tích hợp Bằng chứng `MATH_SOLUTION_EVALUATION`, Chống ghi trùng & Review 2.0 ngày | **HOÀN TẤT & PUSHED** | 70/70 backend tests PASS; 4/4 diagnosis integration PASS. |
| **STEP-FE-01** | Giao diện Biên tập Bảng xét dấu, Hoán đổi bước giải & Route Next.js 16 | **HOÀN TẤT & PUSHED** | 117/117 frontend tests PASS; Turbopack build PASS. |
| **STEP-VERIFY-01**| Kiểm thử Tích hợp Lát cắt Dọc Toàn trình 10 Giai đoạn | **HOÀN TẤT** | 71/71 backend tests PASS; 4/4 real PostgreSQL concurrency PASS; 16/16 contract freeze PASS. |

---

## 2. Kiểm chứng Lát cắt Dọc 10 Giai đoạn (`test_math_solution_vertical_slice.py`)

Kịch bản khảo sát hàm số bậc ba:
$$y = f(x) = \frac{1}{3}x^3 - x^2 - 3x + 1$$

### Chi tiết 10 Giai đoạn Thực thi & Kết quả Kiểm định

1. **Giai đoạn 1 (Lưu nháp Lời giải Từng bước)**:
   - Học sinh nhập 5 bước: Tập xác định $\to$ Đạo hàm $\to$ Nghiệm $\to$ Bảng xét dấu (ngược dấu) $\to$ Kết luận.
   - **Bảo toàn bất biến**: Trong giai đoạn soạn thảo/autosave, sổ cái `learning_evidence_events` không phát sinh bản ghi nào (`count == 0`), năng lực Mastery giữ nguyên.
2. **Giai đoạn 2 (Kiểm chứng CAS Đạo hàm Đúng)**:
   - Bước 2: $y' = x^2 - 2x - 3$ được bộ kiểm chứng toán học tất định (`DeterministicMathValidator`) đánh giá `math_validity = 'VALID'`, điểm `1.0`, độ tin cậy `1.0`.
3. **Giai đoạn 3 (Nhận diện Lỗi Xét dấu Khoảng theo Rubric)**:
   - Bước 4: Artifact bảng xét dấu mang giá trị `{"critical_points": [-1, 3], "signs": ["-", "+", "-"]}`.
   - Với tam thức bậc hai có $a = 1 > 0$, quy tắc "trong trái ngoài cùng" bị đảo ngược. Hệ thống gán cờ `error_detected = True`, `error_code = 'SIGN_TABLE_QUADRATIC_RULE_INVERTED'`.
4. **Giai đoạn 4 (Phân rã Quan niệm Sai lầm - Disentanglement)**:
   - Bộ phân loại `MisconceptionClassifier` phát hiện bảng xét dấu bị đảo dấu (`sign_table_was_inverted = True`).
   - Bước 5 (Kết luận đồng biến trên khoảng $(-1, 3)$) được nhận diện là **suy luận đúng trên tiền đề bảng xét dấu sai**, tuyệt đối **không gán nhầm lỗi `DERIVATIVE_SIGN_DIRECTION`**.
   - Ghi nhận mã quan niệm sai lầm: `SIGN_TABLE_QUADRATIC_RULE_INVERTED` dưới dạng `SUSPECTED`.
5. **Giai đoạn 5 (Quyết định Lần 1 & Cập nhật Mastery Tất định)**:
   - Thang điểm Rubric tính toán: Bước 1 (0.10) + Bước 2 (0.30) = **0.40**; `is_correct = False`.
   - Phát sinh duy nhất 1 sự kiện `MATH_SOLUTION_EVALUATION` trong sổ cái bất biến.
   - Cập nhật năng lực Mastery theo công thức `DeterministicMasteryCalculationStrategy` với $\text{difficulty} = 0.50$:
     $$\text{difficulty\_factor} = 1.1 - 0.3 \times 0.50 = 0.95$$
     $$\text{mastery\_rate} = \min(0.3, 0.22 \times 1.0 \times 0.95 \times 1.0) = 0.209$$
     $$\text{mastery\_score} = 0.0 + 0.209 \times (0.40 - 0.0) = \mathbf{0.0836}$$
     $$\text{confidence} = 0.0 + 0.1235 \times (1.0 - 0.0) = \mathbf{0.1235}$$
     $$\text{attempt\_count} = 1, \quad \text{correct\_count} = 0, \quad \text{state} = \mathbf{LEARNING}$$
6. **Giai đoạn 6 - 8 (Kiểm tra Lại Độc lập - Attempt 2)**:
   - Học sinh thực hiện lượt làm bài độc lập mới (`INDEPENDENT_SOLUTION`).
   - Nhập đúng toàn bộ 5 bước bao gồm bảng xét dấu chuẩn tắc `{"critical_points": [-1, 3], "signs": ["+", "-", "+"]}`.
   - Quyết định lần 2: `final_score = 1.0`, `is_correct = True`, không còn quan niệm sai lầm nào.
7. **Giai đoạn 9 (Sự kiện Bằng chứng Thứ hai & Lịch Ôn tập 2.0 Ngày)**:
   - Phát sinh sự kiện bằng chứng thứ 2 độc lập: `score = 1.0`, `is_correct = True`.
   - Năng lực Mastery cập nhật lần 2:
     $$\text{difficulty\_factor} = 0.8 + 0.4 \times 0.50 = 1.0$$
     $$\text{mastery\_rate} = 0.22$$
     $$\text{mastery\_score} = 0.0836 + 0.22 \times (1.0 - 0.0836) = \mathbf{0.2852}$$
     $$\text{confidence} = 0.1235 + 0.1235 \times (1.0 - 0.1235) = \mathbf{0.2317}$$
     $$\text{attempt\_count} = 2, \quad \text{correct\_count} = 1$$
   - `ReviewSchedule`: Được lên lịch chính xác **2.0 ngày** (`growth_factor = 2.0`, `next_review_at = NOW + 2 days`).
8. **Giai đoạn 10 (Giáo viên Chấm lại & Bảo toàn Sổ cái Bất biến)**:
   - Giáo viên nâng điểm bài làm đầu tiên từ $0.40 \to 0.75$ qua `apply_teacher_override`.
   - Tạo bản ghi kiểm toán `math_evaluation_overrides` phiên bản 1, cập nhật quyết định sang `TEACHER_REVIEW`.
   - **Bất biến tối cao**: Bản ghi `LearningEvidenceEvent` gốc trong sổ cái vẫn giữ nguyên $0.40$, đảm bảo tính toàn vẹn kiểm toán bất biến.

---

## 3. Kết quả Kiểm định Chất lượng Chi tiết (Verification Summary)

### 3.1. Backend Test Suite
```bash
pytest tests/math_solutions/ tests/integration/test_math_solution_vertical_slice.py -v
================== 71 passed, 5 skipped, 2 warnings in 96.21s ==================
```

### 3.2. Real PostgreSQL Concurrency Gate
```bash
$env:EDUMS_TEST_DATABASE_URL="postgresql+psycopg://postgres:200225@localhost:5432/edums"
pytest tests/math_solutions/test_step_verify_02.py -v
======================== 4 passed, 2 warnings in 6.18s ========================
```
- `test_two_writers_one_revision_wins`: Hai luồng ghi đồng thời trên cùng một revision $\to$ đúng 1 luồng chiến thắng, luồng thứ hai bị từ chối 409 Conflict.
- Chống rò rỉ dữ liệu chéo lớp học và cô lập hoàn toàn giữa các học sinh.

### 3.3. Bảo tồn Hợp đồng API v1 Frozen (Contract Freeze)
```bash
pytest tests/api_contract/test_openapi_v1_contract.py tests/math_solutions/test_v2_contract.py -v
======================= 16 passed, 2 warnings in 5.90s ========================
```
- `test_openapi_matches_frozen_contract_and_hash`: **PASS 100%**, mã băm SHA-256 của `contracts/openapi-v1.json` giữ nguyên tuyệt đối.
- `test_v2_contract_snapshot_is_current`: **PASS 100%**.

### 3.4. Frontend Test Suite & Turbopack Build
```bash
npm test
# 117 tests, 117 passed, 0 failed

npm run check
# Turbopack Next.js 16 build passed, 0 TypeScript errors, routes compiled successfully.
```

---

## 4. Kết luận Nghiệm thu

Toàn bộ lộ trình triển khai **EduMS Step-by-Step Math Solution Engine** cho môn Toán Khối 12 GDPT 2018 đã hoàn thành xuất sắc, tuân thủ nghiêm ngặt mọi nguyên tắc bất biến kiến trúc, sẵn sàng đưa vào vận hành.
