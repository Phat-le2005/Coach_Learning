# Báo cáo Kiểm tra Kiến trúc (Architecture Audit Report)
## Hệ thống Giải toán Từng bước (Step-by-Step Math Solution Engine)

- **Dự án**: Coach Learning (EduMS)
- **Mã Sprint**: SPRINT-01 (ARCH-01 + DATA-READY-01)
- **Ngày thực hiện**: 10/10/2026
- **Trạng thái**: HOÀN THÀNH KIỂM TRA (READ-ONLY AUDIT)

---

## 1. Tóm tắt điều hành (Executive Summary)

Hệ thống Coach Learning (EduMS) hiện đang vận hành theo mô hình Modular Monolith vững chắc trên nền tảng FastAPI + PostgreSQL + SQLAlchemy 2.0 (backend) và Next.js 16 + React 19 (frontend). Các luồng nghiệp vụ cốt lõi về xác thực, phân quyền RBAC, quản lý chương trình học (Curriculum), đồ thị khái niệm (Concept DAG), theo dõi độ vững vàng (Mastery Engine), chẩn đoán nguyên nhân gốc rễ (Root-Cause Diagnosis), can thiệp thích ứng (Adaptive Repair), và bản đồ tri thức (Knowledge Forest) đã được xây dựng bài bản.

Tuy nhiên, các mô hình làm bài tập hiện tại (`practice/`, `assignments/`) đang vận hành theo mô thức **đánh giá nguyên khối (monolithic answer evaluation)**: học sinh nộp toàn bộ đáp án (chọn phương án trắc nghiệm hoặc một chuỗi văn bản tự luận duy nhất), hệ thống chấm điểm và ghi nhận kết quả tổng thể.

Để hỗ trợ **Hệ thống Giải toán Từng bước (Step-by-Step Math Solution Engine)** — đặc biệt cho chuyên đề trọng điểm **Toán 12: Tính đơn điệu của hàm số (xét dấu đạo hàm)** — hệ thống cần hỗ trợ:
1. Phân rã lời giải thành nhiều bước có cấu trúc (`SolutionStep`), hỗ trợ biểu diễn công thức LaTeX và cấu trúc bảng toán học (`MathArtifact`: bảng xét dấu, bảng biến thiên).
2. Kiểm tra tính đúng đắn toán học từng bước, phân biệt rõ bước nào đúng (ví dụ: tính đạo hàm đúng) và bước nào sai (ví dụ: lập bảng xét dấu sai).
3. Đảm bảo an toàn dữ liệu: không phá vỡ API v1 đã đóng băng (`API-V1-FREEZE`), không làm nhiễu dữ liệu Mastery bởi các bước giải nháp, và phân định minh bạch giữa quy trình sư phạm (`RepairStep`) với bước toán học vi mô (`SolutionStep`).

---

## 2. Phân biệt Cốt lõi: `RepairStep` vs `SolutionStep`

Một trong những nhầm lẫn kiến trúc phổ biến là đồng nhất hóa quy trình can thiệp sửa sai với các bước giải trong một bài toán. Cần xác định ranh giới dứt khoát:

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
- **Chức năng đã có**:
  - `PracticeSession`: Quản lý phiên thực hành cá nhân (`session_type`, `student_id`, `subject_id`, `started_at`, `completed_at`, `status`).
  - `QuestionAttempt`, `QuestionGroupAttempt`: Lưu kết quả làm bài dạng đơn lẻ hoặc bài trắc nghiệm nhóm.
  - `AIOpenResponseEvaluationService`: Đánh giá phản hồi mở bằng AI cho toàn bộ câu trả lời dạng text.
  - Ràng buộc: `uq_question_attempts_session_question`, kiểm tra `score BETWEEN 0.0 AND 1.0`.
- **Khả năng tái sử dụng**:
  - Tái sử dụng `PracticeSession` làm container cấp phiên cho chế độ tự luyện (`SELF_PRACTICE`).
  - Tái sử dụng logic đo thời gian phản hồi (`response_time_seconds`) và đếm số lần yêu cầu gợi ý (`hint_count`).
- **Khoảng trống tính năng (Gaps)**:
  - Bảng `question_attempts` chỉ có một cột `student_answer: Text` nguyên khối.
  - Không có cấu trúc lưu danh sách bước, thứ tự bước, bảng xét dấu, lịch sử chỉnh sửa bước (revisions), hoặc rollback.
- **Giải pháp**: **Mở rộng bằng module mới** (`backend/app/math_solutions/`). Không sửa bảng `question_attempts`.
- **Rủi ro regression & Dữ liệu**:
  - `QuestionAttempt` có ràng buộc toàn vẹn dữ liệu chặt chẽ và kết nối trực tiếp với logic tính điểm phiên. Sửa đổi `QuestionAttempt` sẽ làm hỏng contract API v1 và gây lỗi runtime cho các endpoint tự luyện hiện tại.

---

### 3.2. Module `assignments/`
- **Chức năng đã có**:
  - Quản lý bài tập lớp học do giáo viên giao (`Assignment`, `StudentAssignment`).
  - Quản lý danh sách câu hỏi: câu hỏi chuẩn hóa (`AssignmentQuestion`, `AssignmentStudentQuestion`) và câu hỏi bóc tách từ tài liệu giáo viên (`AssignmentMaterialItem`, `StudentAssignmentMaterialItem`).
  - Quản lý trạng thái nộp bài: `NOT_STARTED` $\to$ `IN_PROGRESS` $\to$ `SUBMITTED` $\to$ `GRADED`.
- **Khả năng tái sử dụng**:
  - Tái sử dụng ngữ cảnh giao bài lớp học (`CLASSROOM_ASSIGNMENT`), quan hệ lớp học (`classroom_id`), học sinh (`student_id`), môn học (`subject_id`).
- **Khoảng trống tính năng**:
  - `AssignmentStudentQuestion` và `StudentAssignmentMaterialItem` chỉ lưu chuỗi đáp án cuối cùng. Không hỗ trợ giao diện giải theo bước hay chấm điểm từng bước.
- **Giải pháp**: Module `math_solutions/` sẽ liên kết khóa ngoại tùy chọn tới `student_assignment_id` và `assignment_question_id` (hoặc `student_assignment_material_item_id`).
- **Rủi ro regression & Dữ liệu**:
  - Khi học sinh nộp bài giải từng bước trong bài tập lớp, điểm số tổng kết chỉ được cập nhật vào trường `score` của `AssignmentStudentQuestion` thông qua service adapter, không can thiệp trực tiếp vào state machine của assignment.

---

### 3.3. Module `teacher_materials/`
- **Chức năng đã có**:
  - Tải lên tài liệu giảng dạy của giáo viên (PDF/DOCX), bóc tách thành các mục câu hỏi `TeacherMaterialItem`.
  - Phân loại đánh giá: `OBJECTIVE_AUTO`, `OPEN_RESPONSE`, `TEACHER_REVIEW`.
  - Ánh xạ tự động hoặc thủ công sang Concept và ProblemType.
- **Khả năng tái sử dụng**:
  - Tái sử dụng định danh câu hỏi tự luận và cơ chế ánh xạ mục tài liệu với taxonomy kiến thức.
- **Khoảng trống tính năng**:
  - Chưa có bảng tiêu chí chấm (Rubric) chi tiết theo bước cho các bài tự luận của giáo viên.
- **Giải pháp**: Module `math_solutions/` cung cấp bảng `SolutionRubric` độc lập có thể gắn với `teacher_material_item_id`.
- **Rủi ro**:
  - Tài liệu giáo viên thường có công thức và hình vẽ không đồng nhất. Cần chuẩn hóa cấu trúc `MathArtifact` để tránh lỗi parse khi hiển thị.

---

### 3.4. Module `questions/`
- **Chức năng đã có**:
  - Quản lý ngân hàng câu hỏi canonical (`Question`, `QuestionGroup`), `QuestionType` (`MULTIPLE_CHOICE`, `TRUE_FALSE`, `SHORT_ANSWER`, `OPEN_RESPONSE`).
  - Quản lý độ khó, `content_hash` (SHA-256 chống trùng lặp), liên kết Concept/ProblemType/LearningOutcome.
  - Phân tầng gợi ý (`QuestionHint`).
- **Khả năng tái sử dụng**:
  - Tái sử dụng thực thể `Question` làm bài toán gốc cần giải.
- **Khoảng trống tính năng**:
  - Trường `explanation` trong `Question` chỉ là một chuỗi văn bản tự do, không có cấu trúc các bước giải chuẩn (`CanonicalSolutionSteps`), không có các nhánh giải tương đương (ví dụ: cách giải dùng đạo hàm so với cách dùng bất đẳng thức).
- **Giải pháp**: Thiết kế thực thể `SolutionRubric` và `CanonicalSolutionStep` trong module `math_solutions/` trỏ khóa ngoại về `questions.id`.
- **Rủi ro**:
  - Không được sửa đổi bảng `questions` hiện hữu vì ảnh hưởng đến toàn bộ các module `practice`, `exams`, `assignments`.

---

### 3.5. Module `curriculum/` & `concepts/`
- **Chức năng đã có**:
  - Cây phân cấp chương trình GDPT 2018: Subject $\to$ Chapter $\to$ Topic $\to$ ProblemType $\to$ LearningOutcome.
  - Đồ thị tri thức khái niệm: `Concept` và quan hệ tiên quyết `ConceptRelation` (`PREREQUISITE`, `PART_OF`, `RELATED_TO`).
- **Khả năng tái sử dụng**:
  - Dạng bài `MONOTONICITY_FROM_EXPRESSION` (Toán 12) và khái niệm `DERIVATIVE`, `INEQUALITY_SOLVING`.
- **Khoảng trống tính năng**:
  - Chưa có định danh cho các thao tác vi mô (micro-skills) ở cấp độ từng bước (ví dụ: "Kỹ năng tính đạo hàm hàm phân thức", "Kỹ năng xét dấu nhị thức bậc nhất").
- **Giải pháp**: Trong `math_solutions/`, mỗi `SolutionStep` có thể gắn với mã `skill_code` và tham chiếu tới `concept_id` / `problem_type_id` đã có.
- **Rủi ro**:
  - Tuyệt đối không thêm tùy tiện hàng trăm micro-concept vào bảng `concepts` v1 vì sẽ phá vỡ tính ổn định của Concept DAG và Knowledge Forest tree layout.

---

### 3.6. Module `mastery/`
- **Chức năng đã có**:
  - Lưu trữ điểm năng lực học sinh: `StudentConceptMastery`, `StudentProblemTypeMastery`.
  - Công thức tổng hợp điểm vững vàng và 6 trạng thái học tập (`NOT_STARTED`, `WEAK`, `LEARNING`, `PRACTICING`, `MASTERED`, `REVIEW_DUE`).
- **Khả năng tái sử dụng**:
  - Tái sử dụng công thức tổng hợp và logic tính trạng thái hiển thị lên Knowledge Forest.
- **Khoảng trống tính năng**:
  - Hiện tại chỉ tính toán dựa trên kết quả toàn bài (đúng/sai/điểm 0-1). Chưa phân tích được sự chênh lệch năng lực giữa các bước trong một bài (ví dụ: đạo hàm vững 90% nhưng xét dấu chỉ đạt 20%).
- **Giải pháp**: Module `math_solutions/` chỉ phát ra bằng chứng `LearningEvidenceEvent` khi toàn bộ bài toán có quyết định đánh giá chính thức (`EvaluationDecision`). Không ghi nhận Mastery trực tiếp từ các bước giải riêng lẻ.
- **Rủi ro regression & Dữ liệu**:
  - **P0 Risk**: Nếu mỗi lần học sinh gõ một bước giải hoặc autosave mà hệ thống tự động cập nhật Mastery, dữ liệu điểm số sẽ bị bùng nổ sai lệch, học sinh chưa giải xong đã bị tính là đang học hoặc yếu.

---

### 3.7. Module `learning_evidence/`
- **Chức năng đã có**:
  - Bảng bất biến `learning_evidence_events` (chỉ cho phép INSERT, chặn UPDATE và DELETE bằng SQLAlchemy event).
  - Ràng buộc duy nhất `uq_learning_evidence_source` trên `(source_kind, source_entity_id)`.
  - Phân bổ trọng số Concept và ProblemType.
- **Khả năng tái sử dụng**:
  - Điểm tiếp nhận trung tâm để nuôi dưỡng Digital Twin, Mastery và Knowledge Gap.
- **Khoảng trống tính năng**:
  - Enum `LearningEvidenceSourceKind` hiện tại chỉ gồm: `PRACTICE_QUESTION`, `ASSIGNMENT_CANONICAL_QUESTION`, `TEACHER_MATERIAL_ITEM`. Chưa có nguồn đại diện cho bài giải từng bước.
- **Giải pháp**: Khi `EvaluationDecision` được ban hành, sử dụng một adapter chuyển đổi hoặc phát sinh sự kiện hợp lệ qua source hiện có hoặc bổ sung giá trị enum khi migration mới được phê duyệt.
- **Rủi ro**:
  - Vi phạm ràng buộc duy nhất nếu phát sinh nhiều evidence event cho cùng một `source_entity_id`.

---

### 3.8. Module `knowledge_gap/` & `misconceptions/`
- **Chức năng đã có**:
  - Danh mục quan niệm sai lầm: `MisconceptionDefinition`, `StudentMisconception` với 3 trạng thái (`SUSPECTED`, `CONFIRMED`, `RESOLVED`).
  - Hệ thống chẩn đoán nguyên nhân gốc rễ: `RootCauseDiagnosis` với trạng thái `HYPOTHESIS`, `STRONG_HYPOTHESIS`.
  - Mã lỗi định sẵn: `DERIVATIVE_SIGN_DIRECTION` (thuộc Concept `DERIVATIVE`, ProblemType `MONOTONICITY_FROM_EXPRESSION`).
- **Khả năng tái sử dụng**:
  - Cực kỳ phù hợp để nhận diện lỗi xét dấu đạo hàm trong chuyên đề Tính đơn điệu.
- **Khoảng trống tính năng**:
  - Hiện tại matcher chỉ chạy trên chuỗi văn bản tự do cuối cùng. Khi học sinh làm tự luận theo bước, lỗi xảy ra ở bước lập bảng xét dấu, trong khi bước tính đạo hàm hoàn toàn đúng.
- **Giải pháp**: `StepEvaluation` trong `math_solutions/` sẽ liên kết trực tiếp với `misconception_definition_id` tại đúng bước phát hiện lỗi.
- **Rủi ro**:
  - Không được vội vàng xác nhận `CONFIRMED` khi chỉ mới phát hiện 1 lỗi ở 1 bước giải. Phải tuân thủ quy tắc: bước giải sai kích hoạt `SUSPECTED`, sau đó yêu cầu câu hỏi kiểm chứng độc lập để chuyển sang `CONFIRMED`.

---

### 3.9. Module `repair/` & `review/`
- **Chức năng đã có**:
  - `AdaptiveRepairSession`: Lộ trình sửa sai thích ứng 4 pha (`FOUNDATION` $\to$ `GUIDED` $\to$ `TARGET_PRACTICE` $\to$ `FINAL_RECHECK`).
  - `ReviewSchedule`: Quản lý chu kỳ ôn tập ngắt quãng theo thuật toán SM-2 (`review_interval_days`, `next_review_at`).
- **Khả năng tái sử dụng**:
  - Kích hoạt can thiệp sửa sai cho học sinh khi phát hiện quan niệm sai lầm về bảng xét dấu; lên lịch ôn tập sau khi sửa sai thành công.
- **Khoảng trống tính năng**:
  - Hiện tại các item trong `AdaptiveRepairSession` chỉ là các câu hỏi dạng monolithic.
- **Giải pháp**: Trong pha `GUIDED` của repair, cho phép sử dụng chế độ `GUIDED_LEARNING` của `SolutionAttempt`.

---

### 3.10. Module `ai/`
- **Chức năng đã có**:
  - `AIGateway`: Định tuyến nhà cung cấp (Mock, Gemini), đếm token, kiểm soát timeout và rate limit.
  - `PromptRegistry`: Quản lý phiên bản prompt tập trung.
  - Pydantic validation cho đầu ra có cấu trúc (`OpenResponseEvaluationOutput`).
- **Khả năng tái sử dụng**:
  - Tái sử dụng toàn bộ hạ tầng gọi mô hình ngôn ngữ lớn để phục vụ đánh giá bước giải và sinh phản hồi gợi ý sư phạm.
- **Khoảng trống tính năng**:
  - Chưa có prompt chuyên biệt cho đánh giá bước giải toán học, bảng xét dấu và kiểm chứng logic toán.
- **Giải pháp**: Bổ sung prompt mới trong `app/ai/prompts/` và đăng ký vào `PromptRegistry`. Không thay đổi AI provider hay cấu hình gateway.

---

### 3.11. Frontend (`frontend/src/features/`)
- **Chức năng đã có**:
  - `knowledge-forest`: Bản đồ cây tri thức sống động, điều hướng camera, drawer chi tiết.
  - `student-home`: Bảng điều khiển học tập, danh sách môn học, hành động ưu tiên.
- **Khoảng trống tính năng**:
  - Chưa có công cụ biên soạn công thức toán học trực quan (LaTeX editor / math input).
  - Chưa có component tương tác cho bảng xét dấu (Sign Chart Component: khoảng, dấu $+$, $-$, $0$, $\parallel$).
  - Chưa có component quản lý cây bước giải (thêm, sửa, xóa, sắp xếp lại thứ tự bước, xem lịch sử revision).
- **Giải pháp**: Thiết kế feature mới `frontend/src/features/math-solver/` độc lập.

---

### 3.12. Hợp đồng API (`backend/contracts/`)
- **Chức năng đã có**:
  - `openapi-v1.json` và `openapi-v1.sha256`.
  - Script kiểm tra tự động `check_contract.py` trong CI pipeline.
- **Ràng buộc nghiêm ngặt**:
  - `API-V1-FREEZE` là bất biến. Không được phép thêm, sửa hoặc xóa bất kỳ endpoint hay schema nào trong OpenAPI v1.
- **Giải pháp**: Thiết kế API v2 với router độc lập và contract file riêng (`openapi-v2.json`).

---

## 4. Ma trận Kiến trúc Tổng hợp

| Module | Đã có | Khả năng tái sử dụng | Khoảng trống | Hướng xử lý | Mức độ rủi ro |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `practice` | Quản lý phiên thực hành, câu trả lời đơn lẻ | Container phiên tự luyện (`SELF_PRACTICE`) | Không có khái niệm bước giải, bảng xét dấu | Giữ nguyên; liên kết từ module mới | Thấp |
| `assignments` | Giao bài lớp học, chấm bài, deadline | Container bài tập lớp (`CLASSROOM_ASSIGNMENT`) | Nộp bài nguyên khối, không có bước giải | Giữ nguyên; liên kết từ module mới | Thấp |
| `questions` | Ngân hàng câu hỏi, độ khó, gợi ý | Bài toán gốc, đề bài, metadata | Thiếu rubric từng bước, thiếu lời giải mẫu có cấu trúc | Tạo `SolutionRubric` ở module mới trỏ FK | Trung bình |
| `curriculum` & `concepts` | Phân cấp GDPT 2018, Concept DAG | Mapping Dạng bài & Khái niệm Toán 12 | Thiếu taxonomy micro-skills từng bước | Gắn thẻ kỹ năng vào step | Rất thấp |
| `mastery` | Tính toán điểm năng lực và 6 trạng thái | Công thức tính điểm & hiển thị Knowledge Tree | Chỉ nhận kết quả toàn bài, không nhận bước | Chỉ nhận evidence từ quyết định cuối cùng | **P0 (Cao nếu làm sai)** |
| `learning_evidence` | Bảng event bất biến append-only | Cổng nạp dữ liệu chuẩn cho Digital Twin/Mastery | Enum chưa có nguồn cho bài giải bước | Sinh event khi có `EvaluationDecision` | Cao |
| `misconceptions` | Taxonomy lỗi, trạng thái SUSPECTED/CONFIRMED | Nhận diện lỗi `DERIVATIVE_SIGN_DIRECTION` | Matcher hiện chỉ đọc text cuối cùng | Gắn lỗi trực tiếp vào `StepEvaluation` | Trung bình |
| `repair` & `review` | Adaptive repair 4 pha, Spaced repetition SM-2 | Tổ chức can thiệp và lên lịch ôn tập sau sửa lỗi | Chưa hỗ trợ bài tập giải từng bước trong pha Guided | Tích hợp mode `GUIDED_LEARNING` | Thấp |
| `ai` | Gateway, PromptRegistry, Pydantic validation | Gọi LLM đánh giá và sinh gợi ý có cấu trúc | Thiếu prompt đánh giá bước giải toán | Đăng ký prompt mới vào registry | Thấp |
| `contracts` | Check contract tự động, bảo vệ freeze | Cơ chế kiểm soát contract drift | Chỉ hỗ trợ 1 file `openapi-v1.json` | Mở rộng kiểm tra đa contract cho API v2 | **P0 (Cao nếu sửa SHA v1)** |

---

## 5. Kết luận Kiến trúc

Kiến trúc hiện tại của EduMS **hoàn toàn có thể hỗ trợ tốt Hệ thống Giải toán Từng bước** mà **không cần viết lại bất kỳ module cốt lõi nào**, với điều kiện tuân thủ nguyên tắc:
1. **Module hóa độc lập**: Xây dựng toàn bộ logic giải toán từng bước trong module mới `backend/app/math_solutions/`.
2. **Không làm ô nhiễm Mastery**: Bản nháp và từng bước giải không được tạo bằng chứng Mastery độc lập; chỉ quyết định đánh giá cuối cùng (`EvaluationDecision`) mới phát sinh `LearningEvidenceEvent`.
3. **Phân tách ranh giới rõ ràng**: Phân biệt tuyệt đối giữa `RepairStep` (giai đoạn can thiệp) và `SolutionStep` (bước giải toán).
4. **Bảo vệ API-V1-FREEZE**: Thiết lập API v2 độc lập với file hợp đồng và regression test riêng.
