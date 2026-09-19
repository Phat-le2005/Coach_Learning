# Synthetic Student Generator

Module này chỉ phục vụ development/test để tạo dữ liệu hành vi cho Teacher
Dashboard, Mastery, Recommendation và Analytics. Generator không gọi LLM, API
ngoài hay dùng Faker. Cùng `seed`, profile, chỉ số học sinh và catalog concept sẽ
tạo cùng chuỗi đúng/sai và response time.

## Mô hình dữ liệu

- `StudentProfile.is_synthetic` đánh dấu nguồn dữ liệu; `synthetic_profile` lưu
  `STRONG`, `AVERAGE`, `WEAK`, `SPECIFIC_GAP` hoặc `INCONSISTENT`.
- `StudySession` lưu khoảng thời gian học tùy chọn.
- `StudentAttempt` lưu problem type, concept, câu hỏi nếu có, kết quả đúng/sai, response time và
  thời điểm làm bài.
- Synthetic user bị đặt `is_active=false`, nên không thể đăng nhập.
- `app.attempts.analytics.real_attempts_query()` là scope dùng cho analytics
  production. Query kiểm tra cả profile và attempt để loại dữ liệu synthetic.

`StudentAttempt.question_id` có thể null. Generator ưu tiên liên kết câu hỏi
`APPROVED` theo ProblemType rồi fallback theo Concept; khi Question Bank chưa có dữ liệu,
attempt vẫn hợp lệ ở
mức concept để dashboard và thuật toán phía sau có dữ liệu thử nghiệm.

## Pattern hành vi

| Profile | Hành vi mô phỏng |
| --- | --- |
| `STRONG` | Xác suất đúng cao, phản hồi nhanh |
| `AVERAGE` | Kết quả và response time ở mức trung bình |
| `WEAK` | Xác suất đúng thấp, phản hồi chậm |
| `SPECIFIC_GAP` | Khá tổng thể nhưng yếu rõ rệt ở Subject/Chapter/Topic/ProblemType/Concept prerequisite đã chọn |
| `INCONSISTENT` | Xen kẽ session mạnh và yếu |

Mỗi học sinh mặc định có 48 attempts trong 8 study sessions. Khi không truyền
`--profile`, cohort được phân bổ tuần tự qua cả năm profile. Student được xếp
round-robin vào các lớp khối 12 hiện có. Grade 12 concepts phải được seed trước;
classroom và approved question là tùy chọn.

## Command

Chạy từ `backend` sau khi migration và seed catalog:

```powershell
$env:DEBUG = 'true'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.seed
.\.venv\Scripts\python.exe -m app.generate_synthetic_students --count 20 --seed 42
```

Tạo một cohort có lỗ hổng ở ProblemType cụ thể:

```powershell
.\.venv\Scripts\python.exe -m app.generate_synthetic_students `
  --count 15 --seed 2026 --profile SPECIFIC_GAP `
  --gap-problem-type OXYZ_LINE_PLANE_INTERSECTION
```

Các selector hierarchy được kết hợp theo phép giao. Ví dụ học sinh khá tổng thể nhưng
yếu dạng tham số đơn điệu và prerequisite `INEQUALITY_SOLVING`:

```powershell
.\.venv\Scripts\python.exe -m app.generate_synthetic_students `
  --count 20 --seed 42 --profile SPECIFIC_GAP `
  --gap-subject MATH_G12 `
  --gap-topic MONOTONICITY_TOPIC `
  --gap-problem-type PARAMETER_MONOTONICITY `
  --gap-prerequisite-concept INEQUALITY_SOLVING
```

`--gap-prerequisite-concept` dùng global `ConceptRelation(PREREQUISITE)` và áp dụng cho
concept gốc cùng các dependent concept bắc cầu. `--gap-concept` chỉ khớp chính xác một
Concept mapping. Hai lựa chọn concept này loại trừ lẫn nhau.

Không tạo study sessions:

```powershell
.\.venv\Scripts\python.exe -m app.generate_synthetic_students `
  --count 10 --seed 7 --profile WEAK --no-study-history
```

`--count` nhận 1–500. Chạy lại cùng định danh cohort sẽ tái sử dụng stable UUID,
thay thế riêng synthetic history của cohort đó và không tạo duplicate. Command
dùng PostgreSQL advisory lock để tuần tự hóa các lần chạy. Thao tác bị chặn trước
mọi database write khi `APP_ENV=production`.

## Migration và test

Revision `0008_synthetic_students` tạo marker, session và raw attempt facts. Revision
`0009_curriculum_refactor` thêm `problem_type_id` nullable vào attempt để generator nhắm
theo dạng bài mà không tạo Mastery state sớm.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\synthetic -q
```

PostgreSQL integration test dùng schema tạm và xác minh generator idempotent.
Suite synthetic kiểm tra deterministic seed, targeted gap, marker, real-only analytics
scope và PostgreSQL idempotency.

## Phạm vi còn lại

Module này chỉ tạo fact dữ liệu. Attempt API, answer payload chi tiết, mastery,
recommendation, analytics aggregation và dashboard chưa được triển khai trong
task này.
