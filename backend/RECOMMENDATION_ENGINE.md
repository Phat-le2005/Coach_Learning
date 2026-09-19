# Deterministic Recommendation Engine

Recommendation Engine không gọi LLM và không ghi thêm mastery. Hai service tách riêng hai trách nhiệm:

- `LearningPriorityService` xếp hạng mục tiêu học tập từ relational source tables.
- `QuestionRecommendationService` chọn một câu hỏi `APPROVED` phù hợp với mục tiêu đã chọn.

## Learning priority

`get_priorities(student_id, subject_id, active_teaching_plan=None, academic_goal=None)` đọc theo batch:

- `StudentProblemTypeMastery` và `StudentConceptMastery`;
- `ProblemTypeConcept` và prerequisite trong `ConceptRelation`;
- câu hỏi `APPROVED`, `exam_weight` và classification mappings;
- diagnostic attempts gần đây;
- trạng thái review được derive bởi Mastery Engine.

Priority target là `PROBLEM_TYPE` hoặc `CONCEPT`. Thứ tự reason base cố định là:

1. `PREREQUISITE_REPAIR`;
2. `CURRENT_LESSON`;
3. `REVIEW_DUE`;
4. `DIAGNOSTIC_FOLLOWUP`;
5. `WEAK_PROBLEM_TYPE`;
6. `WEAK_CONCEPT`;
7. `DIFFICULTY_PROGRESSION`.

Điểm mastery dưới `0.4` target difficulty `0.3`; từ `0.4` đến dưới `0.75` target `0.55`; từ `0.75` target `0.8`. Tie-break dùng UUID ổn định nên cùng database state luôn cho cùng kết quả.

Repository hiện chưa có persisted `ReviewSchedule`, `AcademicGoal` hoặc active teaching plan. V1 dùng review state derive từ mastery; teaching plan và academic goal được truyền bằng typed context, không tạo dữ liệu giả làm source of truth.

## Question recommendation

`recommend(...)` chỉ xét câu hỏi:

- thuộc đúng Subject;
- trạng thái `APPROVED`;
- có đủ mapping ProblemType, Concept và LearningOutcome;
- khớp target được yêu cầu;
- không nằm trong 20 câu student vừa làm gần nhất.

Scoring deterministic gồm mapping weight, khoảng cách difficulty, cognitive level và `exam_weight`. Debug factors nằm trong internal candidate model và không được expose. Nếu không còn câu hỏi hợp lệ, service trả `None`; không fallback sang `DRAFT`, `REVIEW` hoặc câu vừa làm.

Task này không thêm API và không thêm database table.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest tests\recommendations -q
```

Tests bao phủ STRONG, WEAK, SPECIFIC_GAP, prerequisite repair, review due, active lesson, diagnostic follow-up, recent repeat exclusion, no-approved fallback và tính deterministic.
