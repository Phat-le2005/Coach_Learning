# STEP-EVAL-01 — Bộ Đánh giá Bước giải 4 Tầng & Phân rã Lỗi Sư phạm (4-Tier Step Evaluation Engine)

Tài liệu thiết kế kiến trúc, triển khai và kiểm thử nghiệm thu động cơ đánh giá bước giải 4 tầng, phân rã quan niệm sai lệch sư phạm (Pedagogical Misconceptions) cho Chuyên đề Đơn điệu Hàm số (Toán lớp 12) trên nền tảng EduMS.

---

## 1. Mục tiêu và Nguyên tắc Bất biến (Core Invariant)

### Mục tiêu
Cung cấp khả năng phân tích và đánh giá tự động, khách quan, nhiều tầng đối với từng bước giải toán của học sinh:
- **Tầng 1 (Tham khảo Sư phạm)**: Nhận xét sư phạm trực quan, chi tiết cho học sinh.
- **Tầng 2 (Kiểm chứng Toán học Tất định - CAS Engine)**: Sử dụng SymPy để kiểm tra tính đúng đắn toán học thuần túy (đạo hàm, tìm nghiệm, xét dấu, tập xác định), phân loại thành 4 trạng thái: `VALID`, `INVALID`, `UNDETERMINED`, `NEEDS_REVIEW`.
- **Tầng 3 (Đối chiếu Rubric & Cho điểm)**: Khớp từng bước sửa đổi (`StepRevision`) với các tiêu chí trong `SolutionRubric`, nhận diện đường đi giải pháp và tính điểm trọng số.
- **Tầng 4 (Phân rã Quan niệm Sai lầm - Misconception Disentanglement)**: Phân tách rạch ròi 4 lớp sai lầm kinh điển mà các mô hình thông thường dễ nhầm lẫn.

### Nguyên tắc Bất biến Bắt buộc (Crucial Invariants)
> [!IMPORTANT]
> 1. **Độc lập với Quá trình Soạn thảo (Draft Isolation)**: Động cơ đánh giá chỉ kích hoạt khi bài làm đã được nộp (`SUBMITTED`), gắn kết quả vào `StepRevision` và chuyển trạng thái sang `EVALUATED`. Tuyệt đối không can thiệp vào giai đoạn nháp của học sinh.
> 2. **Phân biệt rạch ròi giữa Lỗi Xét dấu Tam thức và Lỗi Chiều Biến thiên**:
>    - Khi học sinh sai ở bước lập bảng xét dấu ("trong cùng ngoài khác" thay vì "trong trái ngoài cùng" đối với $a > 0$), hệ thống **bắt buộc** phải phân loại là `SIGN_TABLE_QUADRATIC_RULE_INVERTED` với trạng thái ban đầu là `SUSPECTED`.
>    - Tuyệt đối không được gộp nhầm hoặc phán đoán sai thành `DERIVATIVE_SIGN_DIRECTION` (ngộ nhận $y' > 0$ thì nghịch biến).
> 3. **Bảo tồn Điểm Thực tế**: Không làm tròn giả tạo hay ép học sinh đạt 1.0 khi có bước sai. Trong kịch bản lát cắt dọc Toán 12, học sinh làm đúng 2/5 tiêu chí thì điểm số được ghi nhận chuẩn xác là $0.40$ và `is_correct = False`.

---

## 2. Kiến trúc 4 Tầng Chi tiết

### 2.1. Tầng 2: Kiểm chứng Toán học Tất định (`DeterministicMathValidator`)
- File triển khai: [`backend/app/math_solutions/validator.py`](file:///d:/CoachLearning/backend/app/math_solutions/validator.py)
- Sử dụng thư viện **SymPy** với bộ tiền xử lý công thức LaTeX chuẩn hóa:
  - Chuyển đổi phân số `\frac{a}{b}`, ký hiệu hàm số `$y' = $`, phép nhân ẩn (`3x^2`).
  - Phân tích tương đương đại số: `simplify(student_expr - expected_expr) == 0`.
- Hỗ trợ các phân loại bước giải:
  - `DERIVATIVE_CALCULATION`: So sánh biểu thức đạo hàm học sinh nhập với đạo hàm kỳ vọng.
  - `ROOT_FINDING`: Trích xuất tập nghiệm từ LaTeX/văn bản và so sánh dạng tập hợp (Set Equivalence) với tập nghiệm kỳ vọng.
  - `SIGN_TABLE`: Đối chiếu các điểm dừng và chuỗi dấu trong artifact payload `{"critical_points": [...], "signs": [...]}`.
  - `CONCLUSION`: Kiểm tra sự tương thích giữa dấu đạo hàm và kết luận đồng biến/nghịch biến.
- 4 Trạng thái trả về:
  - `VALID`: Biểu thức toán học hoàn toàn chính xác.
  - `INVALID`: Biểu thức toán học sai lệch rõ ràng.
  - `UNDETERMINED`: Định dạng không thể parse tự động an toàn (không làm sập hệ thống).
  - `NEEDS_REVIEW`: Cần giáo viên hoặc trọng tài kiểm tra lại.

### 2.2. Tầng 4: Phân rã Quan niệm Sai lầm (`MisconceptionClassifier`)
- File triển khai: [`backend/app/math_solutions/misconception_classifier.py`](file:///d:/CoachLearning/backend/app/math_solutions/misconception_classifier.py)
- Phân loại 4 nhóm sai lầm sư phạm cốt lõi:
  1. `DERIVATIVE_ARITHMETIC_SLIP`: Sai sót số học khi tính đạo hàm (ví dụ $3x^2 - 6x - 8$ thay vì $3x^2 - 6x - 9$).
  2. `ROOT_FINDING_ERROR`: Tính sai nghiệm phương trình đạo hàm bằng 0 dù đạo hàm tính đúng.
  3. `SIGN_TABLE_QUADRATIC_RULE_INVERTED`: Lỗi quy tắc xét dấu tam thức bậc hai (nhầm quy tắc "trong trái ngoài cùng" đối với hệ số $a > 0$, dẫn đến điền dấu `["-", "+", "-"]` thay vì `["+", "-", "+"]`). Cờ trạng thái: `SUSPECTED`.
  4. `DERIVATIVE_SIGN_DIRECTION`: Sai lầm về định lý đơn điệu (cho rằng $y' > 0$ thì hàm số nghịch biến hoặc ngược lại). Cờ trạng thái: `SUSPECTED`.

### 2.3. Tầng 3: Đối chiếu Rubric & Tính điểm (`SolutionRubricEvaluator`)
- File triển khai: [`backend/app/math_solutions/rubric_evaluator.py`](file:///d:/CoachLearning/backend/app/math_solutions/rubric_evaluator.py)
- Lấy danh sách tiêu chí từ `SolutionRubric` của câu hỏi.
- Ghép nối từng bước giải (`StepRevision`) với tiêu chí phù hợp nhất thông qua `rubric_criterion_id` hoặc suy luận theo `StepKind` và thứ tự bước.
- Tính điểm từng bước:
  $$\text{earned\_score} = \text{max\_score} \times \text{step\_score}$$
- Tính tổng điểm bài làm:
  $$\text{final\_score} = \sum \text{earned\_score}$$
  Chuẩn hóa và giới hạn trong đoạn $[0.0, 1.0]$.
  Cờ `is_correct = True` chỉ khi $\text{final\_score} \ge 0.99$.

### 2.4. Động cơ Điều phối Tổng thể (`MathEvaluatorService`)
- File triển khai: [`backend/app/math_solutions/evaluator_service.py`](file:///d:/CoachLearning/backend/app/math_solutions/evaluator_service.py)
- Phương thức chính: `evaluate_attempt(attempt_id: UUID) -> EvaluationDecision`
- Quy trình thực hiện:
  1. Nạp `SolutionAttempt`, kiểm tra trạng thái bài làm hợp lệ (`SUBMITTED` hoặc đang đánh giá).
  2. Nạp danh sách các bước đang hoạt động (không bị xóa mềm), lấy revision mới nhất (`current_revision`) của từng bước.
  3. Duyệt qua từng bước, chạy qua **Tầng 2 (Validator)** và **Tầng 4 (Classifier)**.
  4. Lưu bản ghi [`StepEvaluation`](file:///d:/CoachLearning/backend/app/math_solutions/models.py) liên kết trực tiếp với `step_revision_id`.
  5. Đưa toàn bộ kết quả qua **Tầng 3 (Rubric Evaluator)** để tính tổng điểm và tổng hợp danh sách quan niệm sai lệch.
  6. Khởi tạo bản ghi [`EvaluationDecision`](file:///d:/CoachLearning/backend/app/math_solutions/models.py) với quyết định `AUTOMATED_CONSENSUS`, ghi nhận điểm số thực tế và danh sách quan niệm sai lầm đã phát hiện.
  7. Cập nhật trạng thái `SolutionAttempt.status = SolutionAttemptStatus.EVALUATED`.

---

## 3. Kiểm thử Nghiệm thu & Lát cắt Dọc Toán 12

File kiểm thử: [`backend/tests/math_solutions/test_evaluator.py`](file:///d:/CoachLearning/backend/tests/math_solutions/test_evaluator.py)

### Kịch bản Lát cắt Dọc (Vertical Slice Monotonicity Scenario)
Bài toán: Tìm các khoảng đơn điệu của hàm số $y = x^3 - 3x^2 - 9x + 2$.
Học sinh thực hiện 5 bước:
1. **Bước 1**: Tập xác định $D = \mathbb{R}$ $\to$ `VALID` (Điểm $0.10 / 0.10$).
2. **Bước 2**: Đạo hàm $y' = 3x^2 - 6x - 9$ $\to$ `VALID` (Điểm $0.30 / 0.30$).
3. **Bước 3**: Tìm nghiệm $y' = 0 \iff x = -1 \text{ hoặc } x = 3$ $\to$ `VALID` (Khớp nghiệm).
4. **Bước 4**: Bảng xét dấu bị đảo ngược dấu: `{"signs": ["-", "+", "-"]}` thay vì `["+", "-", "+"]` $\to$ `INVALID`.
   - Nhận diện chính xác quan niệm sai lầm: `SIGN_TABLE_QUADRATIC_RULE_INVERTED` (trạng thái `SUSPECTED`).
5. **Bước 5**: Kết luận dựa trên bảng xét dấu sai $\to$ `INVALID`.

### Kết quả Kiểm thử
- $\text{final\_score} = 0.40$
- $\text{is\_correct} = \text{False}$
- Danh sách quan niệm sai lầm xác nhận: `["SIGN_TABLE_QUADRATIC_RULE_INVERTED"]`.
- Toàn bộ 5 test case trong `test_evaluator.py` đạt **100% PASS**:
  - `test_tier2_deterministic_validator_calculus_derivative`: PASS
  - `test_tier2_deterministic_validator_roots_and_sign_table`: PASS
  - `test_tier4_misconception_classifier_disentangles_4_classes`: PASS
  - `test_tier3_rubric_evaluator_scoring`: PASS
  - `test_e2e_vertical_slice_monotonicity_evaluation`: PASS
- Toàn bộ 66/66 test trong `tests/math_solutions/`: PASS
- Kiểm tra hợp đồng API v1 & v2: PASS
- Kiểm tra Frontend (103 unit tests & build Turbopack): PASS
