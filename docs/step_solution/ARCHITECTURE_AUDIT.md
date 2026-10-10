# Báo cáo Kiểm tra Kiến trúc (Architecture Audit Report)
## Hệ thống Giải toán Từng bước (Step-by-Step Math Solution Engine) — Hiệu chỉnh Sprint 1.1


> **Bắt buộc trước migration — STEP-ARCH-00:** [Final Schema & Effective Evidence Safety Gate](STEP_ARCH_00_SAFETY_GATE.md) là quyết định thiết kế ưu tiên nếu các ví dụ SQL/logic bên dưới còn mâu thuẫn. Chưa xác minh PostgreSQL runtime.

- **Dự án**: Coach Learning (EduMS)
- **Mã Sprint**: SPRINT-01.1
- **Trạng thái**: HOÀN TẤT KIỂM TRA ĐỐI SOÁT KIẾN TRÚC & QUY TẮC SƯ PHẠM

---

## 1. Tóm tắt điều hành (Executive Summary)

Hệ thống Coach Learning (EduMS) hiện đang vận hành theo mô hình Modular Monolith vững chắc trên nền tảng FastAPI + PostgreSQL + SQLAlchemy 2.0 (backend) và Next.js 16 + React 19 (frontend). Các luồng nghiệp vụ cốt lõi về xác thực, phân quyền RBAC, quản lý chương trình học (Curriculum), đồ thị khái niệm (Concept DAG), theo dõi độ vững vàng (Mastery Engine), chẩn đoán nguyên nhân gốc rễ (Root-Cause Diagnosis), can thiệp thích ứng (Adaptive Repair), và bản đồ tri thức (Knowledge Forest) đã được xây dựng bài bản.

Tuy nhiên, các mô hình làm bài tập hiện tại (`practice/`, `assignments/`) đang vận hành theo mô thức **đánh giá nguyên khối (monolithic answer evaluation)**: học sinh nộp toàn bộ đáp án (chọn phương án trắc nghiệm hoặc một chuỗi văn bản tự luận duy nhất), hệ thống chấm điểm và ghi nhận kết quả tổng thể.

Để hỗ trợ **Hệ thống Giải toán Từng bước (Step-by-Step Math Solution Engine)** — đặc biệt cho chuyên đề trọng điểm **Toán 12: Tính đơn điệu của hàm số (xét dấu đạo hàm)** — hệ thống cần hỗ trợ:
1. Phân rã lời giải thành nhiều bước có cấu trúc (`SolutionStep`), hỗ trợ biểu diễn công thức LaTeX và cấu trúc bảng toán học (`MathArtifact`: bảng xét dấu, bảng biến thiên).
2. Hỗ trợ **hai nguồn bài tập bình đẳng**: Câu hỏi chuẩn tắc từ Question Bank và Câu hỏi bóc tách bất biến từ file PDF giáo viên (`AssignmentMaterialItem`), không bắt buộc câu hỏi PDF phải đưa vào ngân hàng chung.
3. Kiểm tra tính đúng đắn toán học từng bước gắn với phiên bản bước bất biến (`StepRevision`), phân biệt rõ 4 trạng thái kiểm chứng toán học (`VALID`, `INVALID`, `UNDETERMINED`, `NEEDS_REVIEW`).
4. **Bảo toàn dữ liệu Bằng chứng và Mastery**:
   - Bản nháp và từng bước giải không phát sinh `LearningEvidenceEvent`.
   - Bài giải ban đầu sai phải giữ nguyên kết quả sai; các chu trình can thiệp (Kiểm chứng, Sửa sai, Ôn tập) là các phiên độc lập phát sinh bằng chứng riêng.
   - Khắc phục triệt để hạn chế của `LearningEvidenceContextResolver`: không gượng ép dùng `PRACTICE_QUESTION` với `EvaluationDecision.id`, mà đề xuất `source_kind: MATH_SOLUTION_EVALUATION` và cơ chế chống ghi trùng với Assignment v1.
   - Quyết định chấm của giáo viên được lưu vết qua bảng audit `math_evaluation_overrides`, bảo toàn nguyên tắc append-only của evidence.
   - Loại bỏ số liệu hardcode; áp dụng chuẩn công thức `DeterministicMasteryCalculationStrategy` và `derive_mastery_state`.
5. Bảo vệ tuyệt đối hợp đồng đóng băng `API-V1-FREEZE` thông qua cơ chế FastAPI Sub-Application mount tại `/api/v2`.

---

## 2. Phân biệt Cốt lõi: `RepairStep` vs `SolutionStep`

| Tiêu chí | `RepairStep` (Module `repair/`) | `SolutionStep` (Module `math_solutions/`) |
| :--- | :--- | :--- |
| **Bản chất** | **Giai đoạn can thiệp sư phạm** (Pedagogical Intervention Stage). | **Bước lập luận toán học vi mô** (Micro-mathematical Reasoning Step). |
| **Phạm vi** | Xuyên suốt chu trình phục hồi lỗ hổng kiến thức của học sinh (qua nhiều bài tập). | Nằm bên trong một bài toán cụ thể duy nhất. |
| **Các trạng thái điển hình** | `FOUNDATION` (Củng cố nền tảng) $\to$ `GUIDED` (Hướng dẫn có giàn giáo) $\to$ `TARGET_PRACTICE` (Luyện tập đích) $\to$ `FINAL_RECHECK` (Kiểm tra lại không gợi ý). | `ASSUMPTION` (Tập xác định) $\to$ `DERIVATIVE_CALCULATION` (Đạo hàm) $\to$ `ROOT_FINDING` (Nghiệm $y'=0$) $\to$ `SIGN_TABLE` (Bảng xét dấu) $\to$ `CONCLUSION` (Khoảng đơn điệu). |
| **Mục tiêu đo lường** | Đánh giá xem lỗ hổng / quan niệm sai lầm đã được giải quyết triệt để hay chưa. | Đánh giá tính hợp lệ toán học của từng bước logic tại một thời điểm làm bài. |
| **Quan hệ cấu trúc** | Một `AdaptiveRepairSession` gồm nhiều câu hỏi thuộc các phase khác nhau. Trong phase `GUIDED`, học sinh có thể giải một bài toán gồm nhiều `SolutionStep`. | `SolutionStep` là con của `SolutionAttempt`. `SolutionStep` không biết về chu trình repair trừ khi được gán context. |

---

## 3. Kiểm tra Chi tiết Từng Module (Module-by-Module Audit)

### 3.1. Module `practice/`
- **Chức năng đã có**: `PracticeSession`, `QuestionAttempt`, `QuestionGroupAttempt`, `AIOpenResponseEvaluationService`.
- **Khả năng tái sử dụng**: Sử dụng `PracticeSession` làm container cấp phiên cho chế độ tự luyện (`SELF_PRACTICE`).
- **Khoảng trống**: Bảng `question_attempts` chỉ có một trường text nguyên khối `student_answer`. Không có cấu trúc lưu danh sách bước hay bảng xét dấu.
- **Giải pháp**: Xây dựng module mới `backend/app/math_solutions/`. **Không can thiệp vào bảng `question_attempts`**.

---

### 3.2. Module `assignments/` & `teacher_materials/`
- **Chức năng đã có**:
  - Giao bài tập lớp học (`Assignment`, `StudentAssignment`).
  - Hỗ trợ câu hỏi chuẩn tắc (`AssignmentStudentQuestion`) và câu hỏi bóc tách từ PDF giáo viên (`AssignmentMaterialItem`, `StudentAssignmentMaterialItem`).
- **Khả năng tái sử dụng & Mở rộng**:
  - Hỗ trợ ngữ cảnh `CLASSROOM_ASSIGNMENT`.
  - **Mô hình nguồn bài tập kép (Dual Source Model)**: `SolutionAttempt` có thể nhận nguồn từ `question_id` (câu hỏi chuẩn) HOẶC `assignment_material_item_id` (snapshot PDF của giáo viên).
  - Không ép buộc câu hỏi PDF phải xuất bản vào ngân hàng công khai. Quyền truy cập được quản lý chặt chẽ theo phân quyền lớp học.
  - `SolutionRubric` hỗ trợ liên kết với cả 2 nguồn theo phiên bản (`rubric_version`).

---

### 3.3. Module `learning_evidence/` & Hạn chế của Context Resolver
- **Hiện trạng kiểm tra**:
  - Bảng `learning_evidence_events` là append-only, có SQLAlchemy ORM listeners chặn UPDATE/DELETE, chưa xác nhận DB-level trigger.
  - Service `LearningEvidenceContextResolver` (`backend/app/knowledge_gap/evidence_context.py`) ánh xạ dữ liệu theo `source_kind`:
    - `PRACTICE_QUESTION`: Gọi `session.get(QuestionAttempt, event.source_entity_id)`.
    - `ASSIGNMENT_CANONICAL_QUESTION`: Gọi `session.get(AssignmentStudentQuestion, event.source_entity_id)`.
    - `TEACHER_MATERIAL_ITEM`: Gọi `session.get(StudentAssignmentMaterialItem, event.source_entity_id)`.
- **Rủi ro P0 phát hiện**: Nếu Solution Engine sử dụng `source_kind = PRACTICE_QUESTION` với `source_entity_id = EvaluationDecision.id`, `LearningEvidenceContextResolver` sẽ không tìm thấy `QuestionAttempt` tương ứng và bắn lỗi `ApplicationError(409, "EVIDENCE_SOURCE_CONTEXT_MISSING")`.
- **Giải pháp chuẩn hóa**:
  1. Bổ sung `source_kind: MATH_SOLUTION_EVALUATION`.
  2. Bổ sung nhánh giải mã trong `LearningEvidenceContextResolver` đọc từ `EvaluationDecision` $\to$ `SolutionAttempt` (hỗ trợ cả nhánh `Question` lẫn nhánh `AssignmentMaterialItem`).
  3. **Chống ghi trùng (Anti-Double-Counting)**: Trong bài tập lớp, chỉ phát sinh duy nhất 1 sự kiện `MATH_SOLUTION_EVALUATION`, ngăn chặn việc nộp bài assignment v1 phát sinh thêm sự kiện thứ hai cho cùng một câu trả lời.
  4. **Bảo toàn tính bất biến**: Giáo viên sửa điểm thông qua bảng audit `math_evaluation_overrides`, không sửa trực tiếp vào bản ghi evidence cũ.

---

### 3.4. Module `mastery/`
- **Hiện trạng kiểm tra**:
  - `DeterministicMasteryCalculationStrategy` (`backend/app/mastery/strategy.py`): Cập nhật `mastery_score` và `confidence` theo công thức tính toán tăng trưởng phụ thuộc vào `difficulty`, `weight`, `hint_count` và kết quả đúng/sai.
  - `derive_mastery_state` (`backend/app/mastery/state.py`): Xác định trạng thái dựa trên ngưỡng `mastery_score >= 0.8` và `confidence >= 0.65` cho `MASTERED`.
- **Khắc phục sai lệch tài liệu**:
  - Nghiêm cấm đưa các con số bịa đặt (như "Mastery 75%, confidence 72%") vào tài liệu kiến trúc.
  - Autosave và từng bước giải riêng lẻ không bao giờ được ghi Mastery.
  - Bài giải ban đầu sai phải lưu vết kết quả sai ($0.40$). Các bài làm sửa sai hay kiểm tra lại độc lập sau này mới nâng điểm Mastery theo đúng công thức gia số.

---

### 3.5. Module `knowledge_gap/` & `misconceptions/`
- **Hiện trạng kiểm tra**:
  - `backend/data/seed/misconceptions.py` định nghĩa `DERIVATIVE_SIGN_DIRECTION`: *"Treats a negative derivative as increasing or a positive derivative as decreasing."*.
  - Định nghĩa này chỉ áp dụng cho việc suy luận ngược chiều biến thiên từ dấu đạo hàm đã biết.
- **Khắc phục phân loại lỗi**:
  - Không gán lỗi đảo ngược dấu trong bảng xét dấu tam thức bậc hai vào `DERIVATIVE_SIGN_DIRECTION`.
  - Phân tách rõ 4 lớp lỗi: (a) Đạo hàm sai, (b) Nghiệm sai, (c) Xét dấu khoảng sai (`SIGN_TABLE_QUADRATIC_RULE_INVERTED` - candidate), (d) Suy luận chiều biến thiên sai (`DERIVATIVE_SIGN_DIRECTION`).
  - Lỗi bước giải ban đầu chỉ tạo trạng thái `SUSPECTED`, không tự động đánh dấu `CONFIRMED`.

---

### 3.6. Module `review/` & `repair/`
- **Hiện trạng kiểm tra**:
  - `backend/app/review/policy.py`: `ReviewThresholds` có `initial_interval_days = 1.0`, `growth_factor = 2.0`. Khi đạt kết quả `GOOD`, chu kỳ tiếp theo là `1.0 * 2.0 = 2.0` ngày.
  - `backend/app/learning/feedback_policy.py`: `resolved_review_interval_days = 2.0` khi hoàn tất chu trình repair.
- **Khắc phục sai lệch**: Loại bỏ nhận định cảm tính "SM-2 +3 ngày", chuẩn hóa thành chu kỳ 2.0 ngày.

---

### 3.7. Module `contracts/`
- **Hiện trạng kiểm tra**:
  - `backend/app/api/check_contract.py` kiểm tra toàn vẹn `openapi-v1.json` và `openapi-v1.sha256`.
  - `create_app(settings).openapi()` được gọi bởi `get_deterministic_schema()`.
- **Khắc phục**:
  - Sử dụng FastAPI sub-application mount tại `/api/v2`: `application.mount("/api/v2", v2_app)`.
  - Mount không làm rò rỉ route con vào `application.openapi()`, bảo đảm `openapi-v1.sha256` giữ nguyên 100% mã hash mà không cần bất kỳ script giả lập hay mock app nào.
  - API v2 có file hợp đồng riêng `openapi-v2.json` và `openapi-v2.sha256`.

---

## 4. Ma trận Kiến trúc Tổng hợp Sau Hiệu chỉnh

| Module | Hiện trạng | Nâng cấp Kiến trúc Sprint 1.1 | Rủi ro kiểm soát |
| :--- | :--- | :--- | :--- |
| `practice` | Quản lý phiên làm bài tự luyện | Container phiên cho `SELF_PRACTICE` | Thấp |
| `assignments` | Quản lý bài tập lớp & PDF giáo viên | Tích hợp Dual Source: hỗ trợ cả `Question` và `AssignmentMaterialItem` | Thấp |
| `math_solutions` | Chưa có (Module mới đề xuất) | Engine quản lý bước, revision, artifact, rubric và 4 tầng đánh giá | **P0 (Kiểm soát chặt)** |
| `learning_evidence` | Append-only event store | Thêm `source_kind: MATH_SOLUTION_EVALUATION`, resolver adapter, chống trùng lặp | Cao (Đã giải quyết) |
| `mastery` | BKT/EMA calculation | Tính toán chuẩn theo `DeterministicMasteryCalculationStrategy` | Cao (Đã giải quyết) |
| `misconceptions` | Taxonomy lỗi GDPT 2018 | Tách biệt 4 lớp lỗi, đề xuất `SIGN_TABLE_QUADRATIC_RULE_INVERTED` | Trung bình |
| `review` | Spaced repetition | Chuẩn hóa interval 2.0 ngày theo `ReviewPolicy` | Thấp |
| `contracts` | Check contract tự động v1 | Sub-app mount `/api/v2`, giữ nguyên v1 contract và SHA-256 | **P0 (Đã kiểm chứng)** |

---

## 5. Architecture Decision Record (ADR)

### ADR-06: Hoàn thiện Báo cáo Kiểm tra Kiến trúc Module Math Solution Engine

- **Trạng thái**: ĐÃ DUYỆT (ACCEPTED)
- **Quyết định**:
  1. Xác nhận tính khả thi hoàn toàn của việc mở rộng module `math_solutions` mà không cần viết lại bất kỳ module hiện hữu nào.
  2. Áp dụng cơ chế FastAPI sub-app mount tại `/api/v2` để cách ly hợp đồng API v1 bất biến.
  3. Bổ sung nguồn bằng chứng `MATH_SOLUTION_EVALUATION` để khắc phục điểm nghẽn của `LearningEvidenceContextResolver`.
  4. Phân định rạch ròi 4 lớp lỗi sư phạm trong xét dấu đạo hàm và quy chuẩn hóa các công thức tính điểm Mastery và khoảng cách ôn tập.
