# Nhãn chương, bài và dạng cho JSON OCR đã xuất

Đầu ra hiện dùng [schema metadata cố định v1](pdf-metadata-schema-v1.md), được kiểm
tra trước khi ghi file. Phiên bản thuật toán v1/v2 trong các thử nghiệm bên dưới
không còn quyết định hình dạng metadata. Các trường tùy chọn luôn có giá trị
`null`, `[]` hoặc giá trị mặc định theo schema; `evidence` luôn là mảng.

`pdfmeta.method_labels` thêm trường `method` vào từng câu hỏi và xuất một bản
riêng. Không chạy OCR, không gọi model, không sửa đề/lời giải/ảnh nguồn, không
ghi database. Tất cả nhãn dạng/bài suy luận vẫn là ứng viên cần duyệt.

```powershell
$env:PYTHONPATH = 'tools/pdf_metadata'
$env:PYTHONUTF8 = '1'
& 'C:\CoachLearningPdf\pdf-pipeline-runtime\.venv\Scripts\python.exe' -B `
  -m pdfmeta.method_labels `
  --input 'C:\CoachLearningPdf\ocr-direct-full - Copy\content.draft.pretty.json' `
  --pages 'C:\CoachLearningPdf\ocr-direct-full - Copy\pages.ocr.pretty.json' `
  --output '.tmp\ocr-full-method-labels-20261107'
```

Đầu ra:

- `content.method.pretty.json`: giữ nội dung nguồn, thêm `method` và chuẩn hóa
  các khóa/kiểu dữ liệu theo schema cố định; trường riêng được giữ trong `extensions`.
- `methods.pretty.json`, `methods.jsonl`: nhãn riêng theo `question_id` và
  `collection_number`, thuận tiện ghép lại vào bản xuất gốc.
- `method-report.json`: độ phủ, hash đầu vào/quy tắc/taxonomy và các giới hạn.
- `document-taxonomy.json`: cây nhãn in sẵn có phạm vi riêng cho chính tài liệu.
- `schema-validation.json`: kết quả kiểm tra cấu trúc metadata cuối.

`method.chapter`, `method.lesson`, `method.exercise_type` chứa `code` và `name`.
`label_path` là tên các cấp đã gán. `candidates` giữ các khả năng khi một câu
có nhiều yêu cầu; không ép chọn duy nhất. `review_required` luôn là `true`.

Mặc định `--labels-from source-and-rules`: ưu tiên nhãn in sẵn của từng tài liệu,
rồi mới đề xuất nhãn chi tiết bằng các quy tắc nội bộ khi thiếu nhãn nguồn.
Thêm `--labels-from source` nếu chỉ muốn lấy nhãn từ cấu trúc in sẵn.

Nguồn có thể chứa chương/bài/dạng ngoài taxonomy có sẵn. Module tạo mã `DOC_*`
có phạm vi theo hash tài liệu và cha của nhãn. Cùng tên/số "Dạng 1" dưới hai
bài khác nhau được tách riêng. `source_number` và `source_label` giữ cách ghi
của tài liệu; `canonical_code` chỉ được bổ sung khi có đối chiếu phù hợp.
Không dùng số chương/bài/dạng làm mã chung giữa các sách.

Đọc tiêu đề từ native text, OCR markdown và `topic_context` đã xuất. `CHƯƠNG`
và `CHUYÊN ĐỀ` là chương; `BÀI`/`CHỦ ĐỀ` là bài/chủ đề; `DẠNG` và các tiêu đề
dạng viết hoa là dạng. Hỗ trợ tiêu đề nhiều dòng. Chỉ kế thừa qua trang liên
tục; gặp khoảng trống trang hoặc đổi chương thì xóa ngữ cảnh cấp dưới. Mục lục
không tạo nhãn cho câu. Với sách ghép, thay hash `TL ...` cũng xóa nhãn chi tiết
đã kế thừa từ tài liệu nguồn trước. Nhãn xuất hiện sau câu không áp ngược cho câu.

Nếu còn PDF text gốc, nên thêm `--source-pdf '<file.pdf>'`. Module kiểm tra
SHA-256 khớp nguồn JSON trước khi đọc glyph, ghép các text run bị tách trên cùng
dòng và xác định ngữ cảnh theo tọa độ câu. Cách này khắc phục tiêu đề OCR sai dấu,
WordArt bị tách ký tự và ngăn dạng kéo sang phần bài tập tổng hợp. Không chạy OCR.
Một bản ghi chỉ chứa tiêu đề bị assembler nhận thành câu được giữ nguyên và gắn
`record_kind: SOURCE_HEADING_NOT_EXERCISE`.

Các nhãn suy luận được đề xuất bằng quy tắc trên đề bài, đối chiếu với taxonomy nội bộ
`backend/data/fixtures/curriculum/math_g12_full_tree_v0_1`. Đây là taxonomy phát
triển của dự án, không phải số bài/chương theo một bộ sách cụ thể. Đáp án lựa
chọn được loại khỏi đoạn nhận diện để giảm nhiễu. Các quy tắc hiện bao phủ
chương đạo hàm và nguyên hàm/tích phân; chương khác có thể chỉ nhận nhãn chương.
Đã bổ sung ứng viên cho thống kê ghép nhóm và các phương pháp xác suất được gọi
tên rõ trong đề/lời giải nguồn. Khi căn cứ nằm trong lời giải, `evidence[].field`
ghi `solution.markdown`; đây vẫn là nhãn cần duyệt, không phải xác nhận toán học.
Không dùng xác suất hay confidence số giả định để thay thế kiểm định học thuật.
Nếu tài liệu không giữ tiêu đề và nội dung nằm ngoài quy tắc, module giữ cấp
chưa biết thay vì tự tạo dạng mới từ suy đoán. `--taxonomy-root` vẫn hỗ trợ
taxonomy khác; quy tắc không có trong taxonomy được chọn sẽ được bỏ qua và ghi cờ.

Bản thử v1 ngày 2026-11-07 gồm 2.290 câu: 1.484 câu thuộc phần đạo hàm và 806 câu
thuộc phần tích phân. Đây là phần xuất từ 1.800 trang đầu, trong khi PDF khai báo
2.947 trang; không coi đây là toàn bộ sách. Bản xuất có 1.728 câu nhận một nhãn
bài ứng viên, 1.429 câu nhận một nhãn dạng ứng viên; 420 câu chỉ có chương,
các câu đa mục tiêu giữ các nhãn ứng viên và cờ cần duyệt.

Mọi ID và nội dung gốc được đối chiếu lại sau khi chuẩn hóa cấu trúc;
hash file nguồn giữ nguyên. Các đường dẫn ảnh tương đối vẫn thuộc thư mục
bản xuất gốc, được ghi tại `source_artifacts_root` trong báo cáo. Không sao chép
model, PDF hay toàn bộ kho ảnh sang thư mục nhãn.

Bản v2 đã thử độc lập trên PDF xác suất 5 trang: 7/7 câu có đủ chương/bài/dạng
từ nguồn với `--labels-from source`. Trên snapshot JSON thống kê đang xuất, 84/86
câu có nhãn nguồn và 63/86 câu có dạng; hai câu chưa đủ căn cứ giữ chưa phân loại.
Đây là snapshot, không phải kết quả OCR toàn bộ 95 trang. Bản Toan12 v2 nằm ở
`.tmp/ocr-full-method-labels-dynamic-20261107/`, tách khỏi bản v1 để đối chiếu.

## Hai JSON thống kê và xác suất

Kết quả ngày 2026-11-07 ở `.tmp/method-labels-two-files-20261107/`, mỗi nguồn
có thư mục riêng. Đã đối chiếu PDF theo hash và vùng nhìn thấy trên toàn bộ
95 trang thống kê, 73 trang xác suất; không chạy lại model.

- Thống kê: 86 bản ghi, gồm 84 câu và 2 tiêu đề Bài 1/Bài 2; cả 86 có chương/bài.
  83/84 câu có dạng hoặc ứng viên dạng. Một câu tính tứ phân vị chưa có loại
  tương ứng đủ chắc trong taxonomy, được gắn cờ giữ lại để duyệt.
- Xác suất: 121 câu, tất cả có chương/bài; 94 câu có dạng hoặc ứng viên dạng.
  27 câu còn thiếu căn cứ cho dạng cụ thể, không kế thừa sai Dạng 5 từ phần trước.

`exercise_type` là nhãn chính khi chọn được; `exercise_type_candidates` giữ
các lựa chọn và `inference_candidates` giữ quy tắc/căn cứ khi chưa đối chiếu được
bài nguồn với taxonomy chung. `integrity-check.json` xác nhận mọi trường gốc,
ID, số lượng và hash JSON giữ nguyên. Hai bản ghi tiêu đề không bị xóa.
