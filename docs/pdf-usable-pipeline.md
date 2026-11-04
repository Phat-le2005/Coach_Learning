# Pipeline PDF sang metadata có thể đưa vào core

Chạy từ thư mục repo bằng một lệnh. Runtime và kết quả mặc định nằm trong
`C:\CoachLearningPdf`, độc lập với ổ đĩa chứa repo. Đầu vào là PDF gốc, không cần tự tạo
metadata, plan hoặc danh sách câu. Pipeline tự tách đề, đáp án, lời giải,
giữ ảnh nguồn, đọc nội dung native và phân loại cả câu.

```powershell
cd 'D:\Học\hackathon\Coach_Learning'
.\tools\pdf_metadata\build_dataset.ps1 `
  -Pdf '.\data\tu-luan-va-trac-nghiem-ung-dung-dao-ham-de-khao-sat-va-ve-do-thi-ham-so-toan-12-knttvcs9.pdf' `
  -Profile native -Open
```

Với PDF khác chỉ đổi `Pdf`. `native` là cấu hình nhanh, không gọi model OCR
hay API cloud. Công thức chưa chắc được giữ bằng ảnh. Dùng `-Profile ocr`
để bật OCR local khi cần; model không phê duyệt đúng sai học thuật. Giới hạn
mặc định là 1.800 giây cho cả cây tiến trình và 8.192 MiB RSS quan sát. Có
thể chỉnh bằng `Timeout`, `MemoryLimitMB`, `Workers`. Quá giới hạn lệnh trả
lỗi và giữ checkpoint; chạy lại cùng lệnh để tiếp tục.

Điểm sử dụng chính là **đối chiếu đáp án cuối theo đáp án in trong nguồn**.
Không bắt buộc chuyển sạch toàn bộ công thức trong lời giải để làm việc
này: đề và lời giải nguyên gốc vẫn có đủ ảnh. Tính năng chấm bước giải và
xác minh toàn bộ lập luận chưa được cấp trạng thái sẵn sàng.

## Các giai đoạn

1. Kiểm hash PDF và tạo namespace theo nguồn, cấu hình, code.
2. Đọc trang và ghép đề với lời giải qua trang/cột trong các bố cục hỗ trợ.
3. Dựng công thức có chứng cứ glyph/vector; công thức không chắc giữ ảnh.
4. Kiểm lại từ PDF gốc trước khi phân loại, bao gồm dấu trị tuyệt đối, dấu
   trừ, cấu trúc công thức và vị trí các phương án A–D.
5. Đọc đáp án số hoặc A–D có nhãn nguồn rõ ràng. Bản raw và bản trình bày
   phải trùng; không lấy số cuối lời giải để đoán đáp án.
6. Phân loại cả câu và xuất bộ dữ liệu. Trang không tách được câu vẫn có
   ảnh tham chiếu; không bịa câu hỏi, lời giải hoặc đáp án.

Lỗi vector trị tuyệt đối và các phân số nằm khác dòng với nhãn đáp án có
kiểm thử hồi quy trực tiếp từ PDF. Các cách viết/layout chưa hỗ trợ vẫn có
thể cần ảnh. Việc qua kiểm kỹ thuật không chứng minh mọi công thức đều đúng.

## File cuối và ý nghĩa nhóm

Sau khi chạy, console in đường dẫn chính xác. Con trỏ mới nhất của mỗi PDF
nằm ở `C:\CoachLearningPdf\pdf-jobs\<24 ký tự đầu SHA256>\dataset-final.json`.

| File | Mục đích |
| --- | --- |
| `metadata.final.jsonl` | Toàn bộ câu đã ghép và kết quả phân loại |
| `metadata.final.pretty.json` | Bản dễ đọc |
| `core_candidates.jsonl` | Câu có nguồn đầy đủ, ảnh kiểm hash, đáp án cuối đọc rõ và nhất quán |
| `image_reference.jsonl` | Xem từ ảnh nguồn, chưa có đáp án cuối máy đọc chắc |
| `held_items.jsonl` | Lỗi tính toàn vẹn, thiếu nguồn hoặc vấn đề buộc tạm loại |
| `held_source_occurrences.jsonl` | Những vùng nguồn chưa ghép thành cặp đề/lời giải |
| `held_pages.jsonl` | Trang tham chiếu chưa có câu được chấp nhận; không phải câu hỏi được tạo mới |
| `summary.json` | Số lượng từng nhóm, nguyên nhân, thời gian và hash nguồn |
| `index.html` | Giao diện xem từng câu và ảnh gốc |

Core chỉ lấy `core_candidates.jsonl` cho phạm vi đáp án cuối; không lấy mọi
record từ file tổng và bỏ qua `usage_group`. Khi `presentation_mode` là
`SOURCE_IMAGES`, sử dụng ảnh đề gốc thay vì coi text/LaTeX nháp là bản chuẩn.
Mỗi câu vẫn giữ đầy đủ lời giải nguồn, `text_review_reasons` và
`reference_solution.step_grading=NOT_ASSESSED`.

`answer_spec` hỗ trợ `NUMBER` với so sánh thập phân chính xác, hoặc
`MULTIPLE_CHOICE` với nhãn A–D. Cách ghi đơn vị, nhóm hàng nghìn mơ hồ,
biểu thức hoặc đáp án không trùng giữa hai lớp nguồn không được đoán. Những
câu đó chuyển sang ảnh tham khảo. Ảnh câu trắc nghiệm có thể chứa tô màu
đáp án ngay trong PDF; trường tương ứng được ghi và không tuyên bố sẵn sàng
cho kỳ thi kín đáp án.

## Nối hàm đối chiếu vào core

Đọc item từ dữ liệu phía server, chỉ nhận câu trả lời của học sinh:

```python
from pdfmeta.curation import compare_source_answer

result = compare_source_answer(server_owned_item, student_answer)
# MATCHES_SOURCE_ANSWER / DIFFERS_FROM_SOURCE_ANSWER
# INVALID_ANSWER_FORMAT / NOT_ASSESSED
```

Không nhận expected answer hoặc nguyên item do client tự khai. Hàm không
chạy eval, không cho model quyết định kết quả, không ghi điểm sản xuất.
`production_grade=false`, `score=null` thể hiện đây là đối chiếu theo khóa
đáp án nguồn. `academic_review=PENDING` và `publishable=false` vẫn được giữ;
đây không phải chứng nhận độc lập rằng đáp án của sách luôn đúng.

Để dùng lại một bộ đã transcription mà không OCR lại:

```powershell
$env:PYTHONPATH = 'tools\pdf_metadata'
& 'C:\CoachLearningPdf\pdf-pipeline-runtime\.venv\Scripts\python.exe' -B -m pdfmeta.curation `
  --transcripts '<thư mục transcription>' --output '<thư mục kết quả mới>' `
  --plan '<plan.json>' --katex 'frontend\node_modules\katex\dist'
```

PDF scan hoặc bố cục chưa ghép được có thể chỉ cho ra nguồn ảnh và hàng chờ.
Đó là kết quả có giới hạn được ghi rõ, không phải bộ câu hỏi đã có đáp án
được xác minh. Pipeline giữ PDF gốc và các bộ thử cũ.
