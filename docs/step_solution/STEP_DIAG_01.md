# STEP-DIAG-01 — Tích hợp Chẩn đoán, MATH_SOLUTION_EVALUATION & ReviewPolicy (Spaced Repetition)

Tài liệu thiết kế kiến trúc, triển khai và kiểm thử nghiệm thu tích hợp Động cơ Giải toán Từng bước với Hạ tầng Học tập Thông minh EduMS: Sổ cái Bằng chứng Bất biến (`LearningEvidenceEvent`), Chống Ghi trùng với Bài tập v1, Tính toán Năng lực Mastery Tất định và Lịch Ôn tập Ngắt quãng (2.0 ngày).

---

## 1. Mục tiêu và Nguyên tắc Bất biến (Core Invariants)

### Mục tiêu
Kết nối kết quả chấm điểm bước giải toán (`EvaluationDecision`) với luồng dữ liệu học tập thông minh của học sinh:
1. Phát sinh sự kiện bằng chứng học tập chuyên biệt `MATH_SOLUTION_EVALUATION` vào sổ cái bất biến `learning_evidence_events`.
2. Hỗ trợ bộ giải mã ngữ cảnh chẩn đoán (`LearningEvidenceContextResolver`) trích xuất đầy đủ thông tin cho cả 2 nhánh đề bài (Đề chuẩn tắc `CANONICAL` và Ảnh chụp tài liệu giáo viên `TEACHER_MATERIAL`).
3. Chống ghi trùng tuyệt đối (Anti-Double-Counting) với hệ thống Bài tập v1: Một câu hỏi làm qua Solution Engine chỉ sinh duy nhất 1 sự kiện evidence, không bị lặp lại khi nộp bài tập lớp.
4. Cập nhật năng lực Mastery theo công thức tăng trưởng tất định của `DeterministicMasteryCalculationStrategy`, tuyệt đối không dùng số liệu hardcode.
5. Thiết lập lịch ôn tập ngắt quãng chuẩn xác 2.0 ngày theo `ReviewPolicy` và `LearningFeedbackPolicy`.
6. Hỗ trợ giáo viên chấm lại qua bảng kiểm toán `math_evaluation_overrides`, bảo toàn tính append-only của sổ cái bằng chứng.

### Nguyên tắc Bất biến Bắt buộc (Crucial Invariants)
> [!IMPORTANT]
> 1. **Bảo tồn Hợp đồng API v1 Frozen**: Enum `LearningEvidenceSourceKind` được mở rộng giá trị `MATH_SOLUTION_EVALUATION` ở tầng cơ sở dữ liệu và miền nghiệp vụ. Tại tầng schema của API v1 ([`app/knowledge_gap/schemas.py`](file:///d:/CoachLearning/backend/app/knowledge_gap/schemas.py)), định nghĩa enum được cô lập cứng với 3 giá trị ban đầu để giữ nguyên 100% checksum SHA-256 của `contracts/openapi-v1.json`.
> 2. **Chống Ghi trùng Hai Luồng (Single Evidence Source of Truth)**: Khi học sinh hoàn thành bài toán trong bài tập lớp (`CLASSROOM_ASSIGNMENT`), sự kiện bằng chứng duy nhất được phát sinh là `MATH_SOLUTION_EVALUATION`. Khi nộp toàn bộ bài tập v1, hệ thống kiểm tra và bỏ qua việc phát sinh thêm sự kiện `ASSIGNMENT_CANONICAL_QUESTION` hoặc `TEACHER_MATERIAL_ITEM`.
> 3. **Bằng chứng Bất biến (Append-Only Ledger)**: Mọi điều chỉnh điểm số từ giáo viên (`apply_teacher_override`) chỉ ghi thêm phiên bản vào bảng `math_evaluation_overrides`, tuyệt đối không cập nhật hay xóa bản ghi `LearningEvidenceEvent` gốc.

---

## 2. Kiến trúc và Triển khai Chi tiết

### 2.1. Mở rộng Nguồn Bằng chứng (`LearningEvidenceSourceKind`)
- File triển khai: [`backend/app/learning_evidence/models.py`](file:///d:/CoachLearning/backend/app/learning_evidence/models.py)
  ```python
  class LearningEvidenceSourceKind(StrEnum):
      PRACTICE_QUESTION = "PRACTICE_QUESTION"
      ASSIGNMENT_CANONICAL_QUESTION = "ASSIGNMENT_CANONICAL_QUESTION"
      TEACHER_MATERIAL_ITEM = "TEACHER_MATERIAL_ITEM"
      MATH_SOLUTION_EVALUATION = "MATH_SOLUTION_EVALUATION"
  ```
- Cô lập schema v1 tại [`backend/app/knowledge_gap/schemas.py`](file:///d:/CoachLearning/backend/app/knowledge_gap/schemas.py) giúp ngăn chặn drift schema OpenAPI v1.

### 2.2. Giải mã Ngữ cảnh Chẩn đoán (`LearningEvidenceContextResolver`)
- File triển khai: [`backend/app/knowledge_gap/evidence_context.py`](file:///d:/CoachLearning/backend/app/knowledge_gap/evidence_context.py)
- Phương thức `resolve(event_id)` xử lý nhánh `MATH_SOLUTION_EVALUATION`:
  - Đọc `EvaluationDecision` từ `event.source_entity_id`.
  - Đọc `SolutionAttempt` tương ứng và xác thực quyền sở hữu của học sinh (`student_id`).
  - Nạp danh sách các bước giải hoạt động (`SolutionStep`) và format thành chuỗi văn bản diễn giải cấu trúc của học sinh (`student_response`).
  - **Nhánh 1 (Canonical Question)**: Nạp `Question` gốc, đối chiếu `subject_id`, gán `canonical_question` và nội dung câu hỏi.
  - **Nhánh 2 (Teacher Material Snapshot)**: Nạp `AssignmentMaterialItem` bất biến, gán `assignment_material_snapshot_id` và nội dung đề bài giáo viên.

### 2.3. Bộ Chuyển tiếp Bằng chứng Giải toán (`MathSolutionEvidenceAdapter`)
- File triển khai: [`backend/app/math_solutions/evidence_adapter.py`](file:///d:/CoachLearning/backend/app/math_solutions/evidence_adapter.py)
- **Phương thức `emit_evidence_for_decision(decision_id)`**:
  1. Kiểm tra tính lũy đẳng (Idempotency): Nếu quyết định đã có `learning_evidence_event_id` hoặc đã tồn tại sự kiện trong database, trả về sự kiện cũ ngay lập tức.
  2. Tổng hợp phân loại mục tiêu học tập (Concepts & Problem Types) kèm trọng số từ câu hỏi hoặc tài liệu bài giảng.
  3. Phát sinh sự kiện qua `LearningEvidencePublisher.publish()`, tự động cập nhật bảng Mastery của học sinh bằng `DeterministicMasteryCalculationStrategy`.
  4. Đồng bộ kết quả làm bài sang `AssignmentStudentQuestion` hoặc `StudentAssignmentMaterialItem` đối với bài tập trên lớp, kích hoạt cờ đã làm để Assignment v1 không sinh bằng chứng thứ hai.
  5. Khởi tạo / cập nhật `ReviewSchedule` cho dạng bài chính với chu kỳ ngắt quãng chính xác là **2.0 ngày** (`occurred_at + timedelta(days=2.0)`).
- **Phương thức `apply_teacher_override(...)`**:
  - Ghi nhận phiên bản chỉnh sửa vào `math_evaluation_overrides`.
  - Cập nhật điểm và trạng thái trên `EvaluationDecision` với nguồn `TEACHER_REVIEW`.
  - Bảo tồn nguyên vẹn sự kiện trong sổ cái `learning_evidence_events`.

### 2.4. Cơ chế Chống Ghi trùng tại Nghiệp vụ Bài tập v1
- File triển khai: [`backend/app/assignments/service.py`](file:///d:/CoachLearning/backend/app/assignments/service.py)
- Trong phương thức nộp bài tập `submit_assignment`:
  - Trước khi gọi `self.evidence_publisher.publish` cho câu hỏi chuẩn tắc, truy vấn kiểm tra xem câu hỏi có `SolutionAttempt` ở trạng thái `EVALUATED` và đã liên kết `learning_evidence_event_id` hay không.
  - Nếu đã tồn tại, bỏ qua việc phát sinh bằng chứng `ASSIGNMENT_CANONICAL_QUESTION`.
- Trong phương thức chấm tài liệu giáo viên `_publish_material_evidence`:
  - Kiểm tra xem mục bài tập có `SolutionAttempt` đã đánh giá hay không.
  - Nếu đã tồn tại, bỏ qua việc phát sinh bằng chứng `TEACHER_MATERIAL_ITEM`.

---

## 3. Kiểm thử Nghiệm thu & Bảo vệ Toàn diện

File kiểm thử tích hợp: [`backend/tests/math_solutions/test_diagnosis_integration.py`](file:///d:/CoachLearning/backend/tests/math_solutions/test_diagnosis_integration.py)

### 4 Test Cases Trọng điểm
1. `test_learning_evidence_resolver_canonical_branch`:
   - Xác thực `LearningEvidenceContextResolver.resolve()` giải mã thành công 100% cho `MATH_SOLUTION_EVALUATION` từ câu hỏi chuẩn tắc.
   - Các bước giải được định dạng chính xác dạng chuỗi `Step 1 [ASSUMPTION]...` phục vụ chẩn đoán nguyên nhân gốc rễ.
2. `test_learning_evidence_resolver_material_snapshot_branch`:
   - Xác thực `LearningEvidenceContextResolver.resolve()` giải mã thành công 100% cho `MATH_SOLUTION_EVALUATION` từ ảnh chụp PDF giáo viên.
   - Gắn đúng `assignment_material_snapshot_id` và trích xuất nội dung snapshot bất biến.
3. `test_anti_double_counting_and_mastery_calculation`:
   - Xác thực tính lũy đẳng: Gọi `emit_evidence_for_decision` 2 lần chỉ trả về 1 sự kiện duy nhất.
   - Đồng bộ điểm sang `AssignmentStudentQuestion`.
   - Mastery tăng trưởng đúng công thức tất định: Bài làm sai với điểm thực tế $0.40$ đưa điểm Mastery lên $0.0836$ ($\in [0.05, 0.15]$), không dùng số hardcode.
   - Lịch ôn tập `ReviewSchedule` được tạo chính xác là 2.0 ngày.
4. `test_teacher_override_audit_ledger`:
   - Giáo viên can thiệp sửa điểm từ $0.40$ lên $0.75$.
   - Bản ghi `EvaluationOverride` được tạo với `override_version = 1`, `projection_status = "APPLIED"`.
   - Quyết định cập nhật nguồn `TEACHER_REVIEW`.
   - Bản ghi `LearningEvidenceEvent` giữ nguyên điểm gốc $0.40$ (bất biến append-only).

### Kết quả Kiểm thử Toàn diện
- Toàn bộ 4/4 test trong `test_diagnosis_integration.py`: **100% PASS**.
- Toàn bộ 70/70 test trong `tests/math_solutions/`: **100% PASS**.
- Toàn bộ 2/2 test concurrency trên PostgreSQL thực tế: **100% PASS**.
- Hợp đồng API v1 (`check_contract.py`): **PASS** (Zero schema drift).
- Hợp đồng API v2 (`app.api.v2.check_contract`): **PASS**.
- Frontend: 103/103 unit tests PASS, build Next.js Turbopack PASS.
