# Kế hoạch Triển khai Chi tiết (Implementation Backlog)
## Step-by-Step Math Solution Engine Roadmap (Hiệu chỉnh Sprint 1.1)


> **Bắt buộc trước migration — STEP-ARCH-00:** [Final Schema & Effective Evidence Safety Gate](STEP_ARCH_00_SAFETY_GATE.md) là quyết định thiết kế ưu tiên nếu các ví dụ SQL/logic bên dưới còn mâu thuẫn. Chưa xác minh PostgreSQL runtime.

- **Dự án**: Coach Learning (EduMS)
- **Mã Sprint**: SPRINT-01.1
- **Mã tài liệu**: BACKLOG-STEP-01
- **Trạng thái**: KẾ HOẠCH BÀN GIAO & LỘ TRÌNH THỰC THI CHUẨN XÁC

---

## 1. Bản đồ Phụ thuộc Nhiệm vụ (Task Dependency Graph)

```mermaid
flowchart TD
    subgraph Sprint 1.1 - Architecture Corrections
        AUDIT["SPRINT-01.1: Architecture Corrections & ADRs (Frozen Baseline)"]
    end

    subgraph Sprint 2 - Foundations & Data
        STEP_DATA["STEP-DATA-01: Biên soạn 18-20 câu Toán 12, Rubrics & Release Gates"]
        STEP_ARCH["STEP-ARCH-01: Alembic Schema math_solutions (Dual Source & Revision-bound Eval)"]
    end

    subgraph Sprint 3 - Core Engine & Evaluation
        STEP_CORE["STEP-CORE-01: Engine Core (Optimistic Locking, Deferrable Reorder, Idempotency)"]
        STEP_EVAL["STEP-EVAL-01: Đánh giá 4 tầng (CAS 4-state, Rubric Matcher, 4 Error Classes)"]
    end

    subgraph Sprint 4 - Diagnosis, Evidence & API v2
        STEP_DIAG["STEP-DIAG-01: Tích hợp Chẩn đoán, MATH_SOLUTION_EVALUATION & ReviewPolicy (2.0d)"]
        STEP_API["STEP-API-01: FastAPI Sub-App Mount /api/v2 & Dual Contract CI"]
    end

    subgraph Sprint 5 - Frontend & E2E Verification
        STEP_FE["STEP-FE-01: Next.js Step Solver, Sign Table Editor & Reorder UI"]
        STEP_VERIFY["STEP-VERIFY-01: Kiểm thử Tích hợp E2E Vertical Slice Toàn diện"]
    end

    AUDIT --> STEP_DATA
    AUDIT --> STEP_ARCH
    STEP_DATA --> STEP_CORE
    STEP_ARCH --> STEP_CORE
    STEP_CORE --> STEP_EVAL
    STEP_EVAL --> STEP_DIAG
    STEP_CORE --> STEP_API
    STEP_EVAL --> STEP_API
    STEP_API --> STEP_FE
    STEP_DIAG --> STEP_VERIFY
    STEP_FE --> STEP_VERIFY
```

---

## 2. Chi tiết Danh mục Nhiệm vụ (Task Specifications)

### 2.1. Nhóm Nền tảng & Dữ liệu (Sprint 2)

#### `STEP-DATA-01` — Biên soạn Bộ Câu hỏi Mẫu Toán 12 Đầy đủ Pool (18-20 câu) & Release Gates
- **Ưu tiên**: **P0 (Critical)**
- **Tiền đề**: Phê duyệt tài liệu `MATH12_DATA_READINESS.md` Sprint 1.1.
- **Mô tả**:
  Xây dựng bộ dữ liệu hạt nhân nguyên bản do nhóm biên soạn có hồ sơ xác minh quyền sử dụng và quyền phát hành, không mặc định sở hữu tuyệt đối cho dạng bài `MONOTONICITY_FROM_EXPRESSION` (Toán 12), đảm bảo đủ số lượng để không bị cạn pool (`BANK_EXHAUSTED`):
  - 6 bài toán giao bài lớp học (Assignment): đầy đủ 5 bước chuẩn và rubric có trọng số.
  - 2 - 3 bài toán kiểm chứng độc lập (Independent Verification): cô lập kỹ năng xét dấu tam thức bậc hai.
  - 8 bài toán sửa sai thích ứng (Adaptive Repair Pool): đa dạng hàm bậc 3, trùng phương, phân thức bậc 1/1.
  - 2 - 3 bài toán ôn tập giãn cách (Spaced Review Retrieval).
  - Tách biệt rõ định nghĩa quan niệm sai lầm: đề xuất mã ứng viên `SIGN_TABLE_QUADRATIC_RULE_INVERTED` qua hội đồng thẩm định học thuật (Domain Review).
  - Đầy đủ metadata về quyền tác giả (`RIGHTS_VERIFIED_INTERNAL_ORIGINAL`), mã biên soạn và biên bản nghiệm thu học thuật.
- **Tệp bị ảnh hưởng / Tạo mới**:
  - `backend/data/curriculum/math/grade12/gdpt2018/math_solutions_seed.json`
  - `backend/data/seed/authored_questions_m12.json`
- **Tiêu chí nghiệm thu**:
  1. Đạt tối thiểu 18 câu hỏi chuẩn GDPT 2018, vượt qua 5 cổng kiểm soát chất lượng dữ liệu.
  2. Bảng xét dấu `SIGN_TABLE` đạt 100% JSON schema validation.
  3. Có chữ ký nghiệm thu học thuật của ít nhất 2 giáo viên chuyên môn độc lập.

---

#### `STEP-ARCH-01` — Khung Kiến trúc & Migration Schema cho `math_solutions`
- **Ưu tiên**: **P0 (Critical)**
- **Tiền đề**: Phê duyệt tài liệu `ERD.md` và `SOLUTION_ENGINE_DESIGN.md` Sprint 1.1.
- **Mô tả**:
  Tạo cấu trúc module `backend/app/math_solutions/`, xây dựng các model SQLAlchemy 2.0 theo đúng thiết kế:
  - `SolutionAttempt`: Hỗ trợ Dual Source (`question_id` vs `assignment_material_item_id` / `student_assignment_material_item_id`), `attempt_revision_number`, `idempotency_key`.
  - `SolutionStep`: Chỉ mục sắp xếp `uq_math_solution_step_active_index` với cấu hình Postgres `NON-DEFERRABLE (partial unique index; immediate uniqueness check)`.
  - `StepRevision`: Gắn snapshot artifact, lý do sửa đổi và khóa idempotency.
  - `MathArtifact`: Khóa ngoại 1-1 trỏ vào `step_revision_id` bất biến.
  - `SolutionRubric`: Khóa ngoại hỗ trợ cả câu hỏi chuẩn và snapshot tài liệu PDF giáo viên (`rubric_version`).
  - `StepEvaluation`: Khóa ngoại bắt buộc trỏ vào `step_revision_id`, trường `is_valid_math` là enum 4 trạng thái (`VALID`, `INVALID`, `UNDETERMINED`, `NEEDS_REVIEW`).
  - `EvaluationDecision` và `EvaluationOverride`: Lưu vết toàn bộ lịch sử can thiệp của giáo viên.
- **Tệp bị ảnh hưởng / Tạo mới**:
  - `backend/app/math_solutions/models.py`
  - `backend/app/math_solutions/schemas.py`
  - `backend/migrations/versions/xxxx_create_math_solutions_tables.py`
- **Tiêu chí nghiệm thu**:
  1. Migration chạy thành công hai chiều (`alembic upgrade head` và `alembic downgrade -1`).
  2. Toàn bộ ràng buộc `CHECK`, `UNIQUE DEFERRABLE`, khóa ngoại hoạt động chuẩn xác trên PostgreSQL.
  3. Không thay đổi hoặc gây regression cho bất kỳ bảng hiện hữu nào.

---

### 2.2. Nhóm Động cơ Cốt lõi & Đánh giá (Sprint 3)

#### `STEP-CORE-01` — Động cơ Quản lý Bước giải, Reordering & Concurrency Control
- **Ưu tiên**: **P0 (Critical)**
- **Tiền đề**: `STEP-ARCH-01`, `STEP-DATA-01`.
- **Mô tả**:
  Xây dựng service lõi quản lý bài làm và các bước:
  - Khởi tạo `SolutionAttempt` với kiểm tra chặt chẽ quyền sở hữu lớp học hoặc phiên tự luyện.
  - Thêm, sửa, xóa mềm và sắp xếp lại bước giải: thực thi cơ chế đổi thứ tự hai pha hoặc deferrable commit, không bao giờ vi phạm ràng buộc duy nhất.
  - Cơ chế khóa lạc quan dựa trên `attempt_revision_number`.
  - Khóa chống trùng lặp `idempotency_key`.
  - Khóa ghi sau khi nộp bài (Post-Submission Write Lock): cấm chỉnh sửa khi trạng thái là `SUBMITTED` hoặc `EVALUATED`.
  - Cơ chế bảo mật che giấu tiêu chí Rubric đối với học sinh trước khi nộp bài.
- **Tệp bị ảnh hưởng / Tạo mới**:
  - `backend/app/math_solutions/service.py`
  - `backend/app/math_solutions/step_manager.py`
  - `backend/tests/math_solutions/test_step_service.py`
- **Tiêu chí nghiệm thu**:
  1. Swap thứ tự các bước trong cùng transaction chạy thành công 100% không bắn lỗi DB.
  2. Hai request autosave gửi đồng thời được xử lý đúng chuẩn Khóa lạc quan (request chậm nhận HTTP 409).
  3. 0 bằng chứng Mastery nào bị phát sinh trong quá trình học sinh soạn thảo nháp.

---

#### `STEP-EVAL-01` — Bộ Đánh giá Bước giải 4 Tầng & Phân rã Lỗi Sư phạm
- **Ưu tiên**: **P1 (High)**
- **Tiền đề**: `STEP-CORE-01`.
- **Mô tả**:
  Xây dựng hệ thống đánh giá bước giải gắn liền với `StepRevision`:
  - Tầng 1: Đánh giá tham khảo sư phạm (`SolutionFeedback`).
  - Tầng 2: Kiểm chứng toán học tất định (CAS Parser) trả về 4 trạng thái (`VALID`, `INVALID`, `UNDETERMINED`, `NEEDS_REVIEW`).
  - Tầng 3: Đối chiếu `SolutionRubric` tự động theo từng tiêu chí, nhận diện nhánh giải tương đương.
  - Tầng 4: Bộ phân loại lỗi phân biệt rạch ròi 4 lớp sai sót (tính đạo hàm sai, nghiệm sai, bảng xét dấu sai, chiều biến thiên sai). Gắn đúng cờ giả thuyết sơ bộ (`SUSPECTED`).
- **Tệp bị ảnh hưởng / Tạo mới**:
  - `backend/app/math_solutions/validator.py`
  - `backend/app/math_solutions/rubric_evaluator.py`
  - `backend/app/math_solutions/misconception_classifier.py`
  - `backend/tests/math_solutions/test_evaluator.py`
- **Tiêu chí nghiệm thu**:
  1. Đạo hàm đúng của hàm bậc ba được gắn cờ `VALID` (score 1.0).
  2. Bảng xét dấu bị đảo ngược được nhận diện chính xác là lỗi xét dấu tam thức bậc hai (không gắn nhầm vào `DERIVATIVE_SIGN_DIRECTION`).
  3. Xử lý chuẩn xác các trường hợp biểu thức toán học không thể phân tích tự động mà không làm sập tiến trình (trả về `UNDETERMINED`).

---

### 2.3. Nhóm Tích hợp Chẩn đoán, Evidence & API v2 (Sprint 4)

#### `STEP-DIAG-01` — Tích hợp Chẩn đoán, `MATH_SOLUTION_EVALUATION` & ReviewPolicy
- **Ưu tiên**: **P0 (Critical)**
- **Tiền đề**: `STEP-EVAL-01`.
- **Mô tả**:
  Kết nối động cơ giải toán với hạ tầng học tập thông minh:
  - Ban hành `EvaluationDecision` với điểm số thực tế của bài giải đầu (giữ nguyên kết quả sai, e.g. score $0.40$, `is_correct = False`).
  - Đăng ký giá trị enum mới `MATH_SOLUTION_EVALUATION` trong `LearningEvidenceSourceKind`.
  - Cập nhật `LearningEvidenceContextResolver` để giải mã context cho cả 2 nhánh (Canonical Question và Teacher Material Snapshot).
  - Cơ chế chống ghi trùng với Assignment v1: chỉ phát sinh đúng 1 sự kiện evidence cho 1 lượt làm bài.
  - Tính toán Mastery theo đúng công thức gia số của `DeterministicMasteryCalculationStrategy`.
  - Tích hợp chu kỳ ôn tập ngắt quãng chuẩn xác: 2.0 ngày theo `ReviewPolicy` và `LearningFeedbackPolicy`.
  - Hỗ trợ ghi vết giáo viên can thiệp điểm số qua bảng `math_evaluation_overrides`, bảo toàn tính append-only của evidence.
- **Tệp bị ảnh hưởng / Tạo mới**:
  - `backend/app/learning_evidence/models.py`
  - `backend/app/knowledge_gap/evidence_context.py`
  - `backend/app/math_solutions/evidence_adapter.py`
  - `backend/tests/math_solutions/test_diagnosis_integration.py`
- **Tiêu chí nghiệm thu**:
  1. `LearningEvidenceContextResolver.resolve(event_id)` giải mã thành công 100% cho `MATH_SOLUTION_EVALUATION`.
  2. Không phát sinh trùng lặp bằng chứng giữa Solution Engine và Assignment v1.
  3. Mastery tăng trưởng đúng từng bước số học theo công thức, không dùng số liệu hardcode.
  4. Lịch ôn tập được tạo chính xác là 2.0 ngày.

---

#### `STEP-API-01` — FastAPI Sub-Application Mount tại `/api/v2` & Bảo vệ API-V1-FREEZE
- **Ưu tiên**: **P0 (Critical)**
- **Tiền đề**: `STEP-CORE-01`, `STEP-EVAL-01`.
- **Mô tả**:
  Triển khai API v2 chuẩn kiến trúc:
  - Tạo sub-application `create_v2_app(settings)` và mount tại `application.mount("/api/v2", v2_subapp)`.
  - Giữ nguyên toàn bộ mã nguồn và cách sinh hợp đồng v1 hiện tại (`create_app(settings).openapi()`).
  - Xuất hợp đồng độc lập `contracts/openapi-v2.json` và `contracts/openapi-v2.sha256`.
  - Mở rộng kịch bản `check_contract.py` kiểm tra song song hai hợp đồng.
  - Đảm bảo các route trong `v2_app` không bị lặp tiền tố URL `/api/v2`.
- **Tệp bị ảnh hưởng / Tạo mới**:
  - `backend/app/api/v2/application.py`
  - `backend/app/api/v2/router.py`
  - `backend/app/math_solutions/router.py`
  - `backend/app/api/export_contract.py`
  - `backend/app/api/check_contract.py`
  - `backend/contracts/openapi-v2.json`
  - `backend/contracts/openapi-v2.sha256`
- **Tiêu chí nghiệm thu**:
  1. Lệnh `.venv\Scripts\python -m app.api.check_contract` báo PASS cho cả v1 và v2.
  2. File `contracts/openapi-v1.json` và checksum SHA-256 hoàn toàn nguyên vẹn 100%.
  3. Tất cả các endpoint v2 truy cập bình thường qua tiền tố sạch `/api/v2/math-solutions/...`.

---

### 2.4. Nhóm Giao diện & Kiểm thử Tích hợp E2E (Sprint 5)

#### `STEP-FE-01` — Frontend Step Solver, Sign Table Editor & Reorder UI
- **Ưu tiên**: **P1 (High)**
- **Tiền đề**: `STEP-API-01`.
- **Mô tả**:
  Xây dựng giao diện giải toán từng bước trên Next.js 16:
  - Feature mới: `frontend/src/features/math-solver/`.
  - Trình soạn thảo công thức toán LaTeX (KaTeX rendering).
  - Trình biên soạn Bảng xét dấu trực quan (`SignTableEditor`): chọn khoảng nghiệm, điền dấu $+$, $-$, $0$, $\parallel$.
  - Danh sách bước giải hỗ trợ kéo thả sắp xếp (Drag & Drop Reordering).
  - Nút xem lịch sử phiên bản bước (Revision Viewer) và nút Rollback bước.
- **Tệp bị ảnh hưởng / Tạo mới**:
  - `frontend/src/features/math-solver/MathSolutionSolver.tsx`
  - `frontend/src/features/math-solver/components/SignTableEditor.tsx`
  - `frontend/src/features/math-solver/components/StepCard.tsx`
  - `frontend/src/app/student/practice/solutions/[attemptId]/page.tsx`
  - `frontend/src/lib/api/v2-client.ts`
- **Tiêu chí nghiệm thu**:
  1. Bảng xét dấu hiển thị chuẩn xác, responsive trên mobile (360px và 390px).
  2. Kéo thả đổi vị trí bước cập nhật API tức thì và lưu revision log.
  3. Trình soạn thảo LaTeX mượt mà, không bị giật lag khi gõ công thức.

---

#### `STEP-VERIFY-01` — Kiểm thử Tích hợp E2E Toàn diện Lát cắt Dọc Toán 12
- **Ưu tiên**: **P0 (Critical)**
- **Tiền đề**: Hoàn thành toàn bộ các nhiệm vụ trên.
- **Mô tả**:
  Kiểm thử tích hợp tự động không mock runtime toàn bộ kịch bản 10 giai đoạn:
  - Học sinh giải bài Tính đơn điệu: Đạo hàm đúng $\to$ Bảng xét dấu sai.
  - Hệ thống nhận diện lỗi xét dấu khoảng, ban hành quyết định lần 1 với điểm thực tế ($0.40$), ghi nhận giả thuyết `SUSPECTED`.
  - Học sinh hoàn thành câu kiểm chứng độc lập $\to$ Trải qua phase Guided $\to$ Hoàn thành bài toán kiểm tra lại mới với điểm 1.0.
  - Hai bằng chứng độc lập được phát sinh; Mastery tăng trưởng theo đúng công thức; lịch ôn tập được tạo là 2.0 ngày.
  - Trạng thái lá trên Knowledge Forest đồng bộ chính xác.
- **Tệp bị ảnh hưởng / Tạo mới**:
  - `backend/tests/integration/test_math_solution_vertical_slice.py`
  - `frontend/tests/math-solution-e2e.test.ts`
- **Tiêu chí nghiệm thu**:
  1. Test suite E2E chạy hoàn tất với mã thoát 0.
  2. Kiểm tra trực quan bằng ảnh chụp màn hình trình duyệt thực tế.
  3. 0 regression trên toàn bộ test suite backend và frontend.

---

## 3. Architecture Decision Record (ADR)

### ADR-07: Khóa Lộ trình Triển khai Chuẩn xác Step-by-Step Math Solution Engine

- **Trạng thái**: ĐÃ DUYỆT (ACCEPTED)
- **Quyết định**:
  1. Khóa cứng danh mục nhiệm vụ từ `STEP-DATA-01` đến `STEP-VERIFY-01` theo thứ tự phụ thuộc chặt chẽ.
  2. Đưa toàn bộ các ràng buộc kiến trúc Sprint 1.1 (Dual Source, Sub-App Mount v2, Deferrable Reorder, `MATH_SOLUTION_EVALUATION`, ReviewPolicy 2.0 ngày) vào tiêu chí nghiệm thu bắt buộc của từng task.
  3. Sẵn sàng khởi động Sprint 2 ngay sau khi Sprint 1.1 hoàn tất cam kết tài liệu.


---
### STEP-ARCH-00 — blocker trước STEP-ARCH-01
Phải chạy SQL probe trên Postgres và triển khai thiết kế bảng `math_solution_operations` (tổng cộng 10 bảng). Kiểm tra correction replay/rebuild và classroom ownership, cùng frozen API v1 shared enum impact; khi chưa PASS, chưa migrate production.
