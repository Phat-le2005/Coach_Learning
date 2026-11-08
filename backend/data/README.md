# Milestone PA2: 345 câu và cây tri thức

Luồng: `/student/knowledge` → chọn dạng bài → luyện tập → nộp bài → chấm xác định
hoặc Gemini → quyết định chấm → evidence → mastery → cây tri thức.
Giữ database/schema, UUID và rubric câu hỏi hiện tại. Không nhập backlog HELD.

## Gói dữ liệu và cài đặt

Artifact riêng ở repo root: `.tmp/ocr-pa2-release/milestone-345.json`.
Gồm 345 đề, đáp án, lời giải, mapping theo code, rubric và provenance. Không chứa
tài khoản, API key, bài làm hay năng lực học sinh. Chuyển gói cùng mã nguồn cho
team; không commit private artifact vào Git. Máy nhận không cần đường dẫn OCR
`D:/...`; chỉ khi xây lại gói từ overlay mới cần các nguồn pretty JSON gốc.
Checksum bảo vệ toàn vẹn truyền file, không thay kiểm định toán học.

Máy nhận cần setup/migrate backend, PostgreSQL development/test, môn `MATH_G12`
phiên bản `GDPT2018_2018` và ADMIN đang hoạt động. Chạy trong `backend`:

```powershell
.venv/Scripts/python.exe -B scripts/deploy_ocr_pa2_release.py `
  --bundle ../.tmp/ocr-pa2-release/milestone-345.json `
  --apply --actor-id <ACTIVE_ADMIN_UUID> `
  --report ../.tmp/ocr-pa2-release/deploy-report.json
```

Bỏ `--apply` để chỉ kiểm cấu trúc gói offline. CLI local có thể bỏ `--actor-id`
để dùng ADMIN có sẵn, không tạo tài khoản. Toàn bộ cây và câu hỏi commit trong
một transaction. Cài lại bản không đổi trả `UNCHANGED`; không ghi đè câu đã sửa.

Tree installer dùng fixture: 6 chương, 25 chủ đề, 75 dạng bài, 89 concept,
34 chuẩn đầu ra. Bổ sung theo code trên ID hiện hữu; giữ node legacy, concept
PA2, bố trí cha và mapping cũ. Tổng node có thể cao hơn fixture. Không gọi script
kích hoạt thay thế cây cũ. Báo cáo apply ghi các tổng thực tế và phần giữ lại.

## Cấu hình chạy

Trong `backend/.env` riêng của máy chạy:

```dotenv
AI_PROVIDER=gemini
AI_API_KEY=<server-side-key>
AI_MODEL_FAST=<model-enabled-for-this-key>
```

Trong `frontend/.env.local`: `SELF_STUDY_PUBLISHED_SUBJECT_CODES=MATH_G12`.
Giữ cấu hình DB/JWT/origin hiện có; restart backend/frontend sau đổi environment.
Tầng 1 không cần Gemini. Tầng 2 cần Internet, khóa và quota. Không đặt key vào
biến `NEXT_PUBLIC_*`. Không có model/cache local hay Graphify trong runtime.

## Hai tầng và cập nhật năng lực

Tầng 1 kiểm toán bằng CAS/đại lượng đã duyệt, không dùng độ giống chuỗi làm điểm.
Cú pháp/khả năng chưa hỗ trợ chuyển Gemini. Lỗi nguồn/rubric trỏ nhầm không bị
bỏ qua để gọi AI.

Gemini nhận đề, đáp án/lời giải, rubric và bài làm đã xác nhận. Model trả đủ từng
bước, tiêu chí và từng numeric check, kèm trích dẫn/độ tin cậy. Cho phép cách giải
khác và nhiều bước cùng loại. Server tổng hợp theo trọng số rubric; năng lực
concept dùng đúng check/concept, không nhân điểm tổng sang tất cả kỹ năng.

Chỉ PA2 có rubric đã duyệt, tham chiếu/bài nộp không đổi, đủ coverage/citation,
không có `NEEDS_REVIEW`, mọi confidence từ 0.8 trở lên mới được phát điểm.
Đó là điều kiện vận hành, không chứng minh độ chính xác 80%. Trường hợp khác giữ
góp ý tạm thời, không cộng mastery PA2.

Lưu `StepEvaluation.evaluator_type=GEMINI_REFERENCE` và nhóm quyết định tự động
hiện có `AUTOMATED_CONSENSUS`, không migration. Evidence giữ nguồn Gemini, hash
tham chiếu/bài nộp và chi tiết rubric/check. API trả nguồn `ANSWER_GROUNDED_AI`
với `is_final=true` chỉ sau commit quyết định, evidence và mastery. Frontend
hiển thị riêng nguồn Gemini; giáo viên vẫn có luồng override hiện có.

Khóa bài làm và unique decision bảo vệ lần phát điểm. Cache góp ý có version
bài làm. Nguồn chưa có đáp án chỉ nhận góp ý không điểm. AI legacy ngoài PA2 giữ
hành vi cũ.

## Cây và giới hạn

Mastery API thêm `concept_ids` và `available_question_count` theo dạng bài.
Frontend dùng mapping thật. Nhánh chưa có câu vẫn hiện nhưng không gợi ý luyện
vào kho rỗng; chọn dạng bài không âm thầm mở câu thuộc dạng khác. Sau điểm chính
thức workspace làm mới bài làm/router; trang cây đọc mastery bằng `no-store`.

345 câu không phủ đủ 75 dạng bài. Node chưa có câu/evidence giữ trạng thái thật;
không tạo dữ liệu học sinh giả để làm cây xanh.

Đợt nối này không chạy ứng dụng, gọi Gemini hoặc QA bài làm theo yêu cầu người
dùng. Chỉ kiểm tra tĩnh Python/TypeScript và cài dữ liệu/cây. QA các lô trước
không phải bằng chứng đã thử end-to-end nhánh Gemini mới.
