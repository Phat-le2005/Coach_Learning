# Dữ liệu OCR đã kiểm tra: PA2

Luồng này giữ nền `Question → SolutionRubric → SolutionAttempt → LearningEvidenceEvent`.
Nó nhập một overlay đã biên tập từ `content.draft.pretty.json`; không nhập trực tiếp
JSONL hoặc tự phê duyệt toàn bộ kết quả OCR. Không có migration hay API mới.

## Phạm vi hiện có

Profile `cubic-monotonicity-v1` chấm hàm bậc ba không tham số, có hai nghiệm đạo hàm
thực phân biệt. Ba yêu cầu kết luận: đủ các khoảng đơn điệu (`all_intervals`), tổng
hai mốc của khoảng đồng biến cực đại (`inner_sum`), hoặc độ dài khoảng đó (`inner_width`).
Các câu được đưa vào chế độ trình bày lời giải `OPEN_RESPONSE` có chủ đích; nếu nguồn
là trả lời số, overlay phải ghi rõ việc chuyển sang bài làm từng bước.

Profile `numeric-reference-v1` bổ sung bốn task: `probability`,
`grouped_statistics`, `definite_integral`, `polynomial_extrema`. Nó kiểm từng đại
lượng và phép tính với tham chiếu đã duyệt, gồm phân số/căn số, cách làm tròn được
khai báo riêng và các đẳng thức dùng đại lượng trung gian. Nó không xác minh một
chứng minh tự do hoặc toàn bộ lập luận viết bằng lời. Các bài cần lập luận ấy được
cắt phần có thể kiểm định với ghi nhận rõ ràng, hoặc để ngoài lô.

Mỗi tiêu chí số dùng `checks: [{label, expected, ...}]` và một loại bước trong
`ASSUMPTION/CUSTOM/EXPLANATION/CONCLUSION`; các loại bước trong một rubric duy nhất.
`expected` là biểu thức số hữu hạn theo ngữ pháp giới hạn, không chạy Python/eval.
Có thể khai báo `rounded` cùng `decimal_places` (ROUND_HALF_UP) để chấp nhận đúng
cách làm tròn của đề. Một tiêu chí có nhiều đại lượng chấm điểm theo từng đại lượng.
`concept_code` ở từng check tách kỹ năng được đánh giá, chẳng hạn sai độ lệch chuẩn
không làm mất điểm kỹ năng phương sai đã đúng. Điểm check được lưu trong evidence.

Các nhãn xác suất dạng `P(A)`, `P(AB)`, `P(A|B)`, `P(A|~B)`; khi hiển thị dùng
`\overline{B}` cho biến cố đối. Thống kê dùng `N/R/Q1/Q3/IQR/XBAR/VAR/SD` và hậu tố
A/B cho hai mẫu; tích phân dùng `I/J/K/FA/FB/A/B/RESULT` và chỉ số 1–6 khi có nhiều
ý; cực trị dùng `X1/X2/Y1/Y2/XMAX/YMAX/XMIN/YMIN/A/B/RESULT`. Đề đã biên tập phải
định nghĩa nhãn và thứ tự mẫu, không để học sinh phải đoán tên biến của rubric.

Năm tiêu chí độc lập:

| Loại bước | Concept được đánh giá |
|---|---|
| `ASSUMPTION` | `FUNCTION_DOMAIN` |
| `DERIVATIVE_CALCULATION` | `DERIVATIVE_RULES` |
| `ROOT_FINDING` | `SIGN_ANALYSIS` |
| `VARIATION_TABLE` | `SIGN_ANALYSIS` |
| `CONCLUSION` | `MONOTONICITY_CRITERION` |

Bảng dùng đúng payload `version/points/intervals` của MathWorkspace; kiểm cả mốc,
dấu, chiều biến thiên và giá trị hàm số nếu học sinh nhập. Kết luận đủ các khoảng
không được hoàn tất bằng chỉ một khoảng đúng. Cú pháp/bước ngoài khả năng kiểm
chứng chuyển sang review. Nhiều bước cùng loại cũng cần review. Bước thiếu nhận
0 theo rubric; sai toán học được ghi nhận riêng với bước chưa kiểm chứng.

## Overlay riêng và preview không dùng DB

Lưu OCR, overlay và báo cáo trong `.tmp/` hoặc kho dữ liệu riêng, không commit.
Mỗi overlay có `version: 1`, `sources` chứa SHA-256 của từng file chuẩn và `items`.
Mỗi item cần:

- `dataset`, `source_id`, `source_record_sha256` (JSON chuẩn hóa bằng hàm `digest`).
- `question` theo `QuestionImportRecord`, `source: OCR_CURATED_PA2`,
  `source_reference: <dataset>:<source_id>`; đủ concept, dạng bài, chuẩn đầu ra.
- `task`, `criteria`: đủ năm loại bước ở bảng trên, ID duy nhất, trọng số dương tổng 1;
  mỗi tiêu chí có `concept_codes` như bảng.
- `review: {status: VERIFIED, reviewer: ..., notes: ...}` và `difficulty_basis`.
  Ghi đúng người/cách kiểm tra; kiểm tra kỹ thuật không phải chữ ký giáo viên.
- `corrections`: mỗi trường sửa có `field`, `before_sha256`, `after_sha256`, `reason`;
  các trường so với `question.markdown`, `solution.markdown`, `answer.markdown` gốc.
  Cần ghi cả thao tác tách đáp án cuối từ trường answer chứa nguyên lời giải.
- `delivery_adaptation` mô tả việc cắt/chuyển cách trình bày khi có.

Với profile số, thay yêu cầu năm loại bước bằng 2–4 tiêu chí có ID/loại bước duy
nhất, có ít nhất kết luận và một tiêu chí trung gian. Concept phải thuộc task đã
định nghĩa trong `numeric_reference.py`, có đủ QuestionConcept mapping; không gán
điểm tổng sang các kỹ năng không được kiểm tra.

Đề/lời giải/đáp án phải qua kiểm tra ngoặc LaTeX, delimiter và TeX nằm ngoài vùng
toán. Các kiểm tra này không thay kiểm tra toán học hoặc render. Người biên tập phải
đối chiếu crop và render bằng renderer frontend trước khi xác nhận. Capability này
chưa phục vụ ảnh nguồn trực tiếp: chuyển bảng thành text đã kiểm tra, giữ ảnh gốc riêng;
không dùng crop chứa lời giải làm ảnh đề. Không tự vá công thức mơ hồ.

MathRenderer hỗ trợ bảng Markdown có tiêu đề và hàng phân cách; các ô được escape
HTML. Lô hiện tại dùng ô văn bản/số, công thức đặt ngoài bảng. Chưa hỗ trợ đầy đủ
Markdown hoặc công thức trong ô bảng.

Chạy từ `backend` (PowerShell):

```powershell
.venv/Scripts/python.exe -B scripts/import_curated_ocr.py `
  --overlay ../.tmp/ocr/curated-overlay.json `
  --source "chapter=<OCR_ROOT>/chapter/content.draft.pretty.json" `
  --report ../.tmp/ocr/offline-preview.json
```

Có thể lặp `--source`. Chế độ mặc định chỉ đọc file và ghi báo cáo, không tạo engine,
không gọi `QuestionImportService.preview` vì phương thức đó mặc định ghi import batch.
`ready` là số item của overlay đủ điều kiện, `not_selected` không đồng nghĩa dữ liệu hỏng.

## Apply và tính nhất quán

Thêm `--apply --actor-id <ACTIVE_ADMIN_UUID>` để dùng DB được cấu hình. Dịch vụ
curated dùng importer hiện có với `commit=False`: kiểm catalog/trùng → tạo DRAFT
→ gắn rubric → APPROVED trong cùng một transaction. Sai một hàng thì rollback cả
lô. Chạy lại bản không đổi trả `UNCHANGED`; thay đổi nội dung, rubric, difficulty,
exam weight hoặc mapping thì dừng để review, không ghi đè câu cũ.

CLI mặc định `--batch-size 200`, có thể nhận một overlay lớn hơn và xử lý lần lượt.
Mỗi batch là một transaction; báo cáo được ghi ngay sau từng batch đã commit. Nếu
batch sau lỗi, batch trước vẫn có báo cáo để chạy tiếp bằng cùng overlay. Parallel
CPU được dùng cho sàng lọc/tính toán/render; DB dùng khóa import và không ghi song
song các batch chồng lên nhau.

Nếu DB development còn cây sơ khai, cờ tường minh `--add-missing-cubic-catalog`
chỉ bổ sung bốn concept trên, hai LO `M12_DERIV_LO_01/02` và quan hệ cần thiết.
Overlay phải nêu `curriculum_version_code`. Cờ này không thay cây, sửa PT mapping,
vô hiệu hóa dạng bài hoặc sửa tên/định nghĩa đã có. Không restore dump để nhập lô.

`--add-missing-probability-catalog` thêm các kỹ năng và dạng bài xác suất cần thiết.
`--add-missing-reviewed-catalog grouped_statistics|definite_integral|polynomial_extrema`
(có thể lặp) chỉ thêm phần taxonomy tương ứng từ fixture đã có trong repo. Các cờ
này dùng trong transaction của batch và giữ nguyên hàng/mapping đã có. Difficulty
không có trong OCR: dùng default PT có ghi nguồn; khi PT không có default, ghi rõ
ước lượng biên tập tạm thời, chưa hiệu chuẩn theo kết quả học sinh.

Rubric khóa hash đề/đáp án/lời giải và trọng số concept. Sửa tham chiếu phải review
lại rubric. Evidence lưu `criterion_concept_outcomes` version 1: tính điểm concept
từ đúng tiêu chí, gộp một đóng góp/concept/bài làm. Publisher, replay và chẩn đoán
cùng đọc định dạng này. Điểm tổng vẫn cập nhật ProblemType như trước.

Teacher override chỉ có điểm tổng sẽ thay thế kết quả cũ, nhưng để concept chưa xác
định: không suy diễn điểm từng kỹ năng. Evidence cũ không có metadata mới vẫn giữ
cách tính cũ. AI provisional của `OCR_CURATED_PA2` không tự cập nhật mastery.
Nhánh Gemini đủ điều kiện được phát điểm/evidence theo rubric như tầng 1;
xem [triển khai milestone 345](OCR_PA2_RELEASE.md).

Chưa mở rộng QuestionGroup, chấm phụ thuộc giữa các bước, chứng minh tự do hoặc
grader tổng quát. Mỗi câu đưa thêm vẫn cần đối chiếu nguồn, đáp án, tiêu chí và mapping.
