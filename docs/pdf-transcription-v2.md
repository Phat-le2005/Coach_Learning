# Thử nghiệm nội dung toán v2

Ngày 2026-11-04 có thêm runner tổng quát cho corpus đã ghép cặp, không cần
kết quả v1 làm đầu vào. Lệnh và giới hạn vận hành mới nằm trong
[hướng dẫn chạy theo từng đợt](pdf-scale-runner-2026-11-04.md). Phần lệnh
và kết quả 100 câu bên dưới mô tả thử nghiệm cố định trước đó. Khi code đã
thay đổi, cần dùng output mới để tránh trộn checkpoint của hai cấu hình.

Lượt mở rộng 200 câu mới có [báo cáo riêng](pdf-scale-trial-200-2026-11-04.md),
bao gồm phép đo cold, kiểm thử pause/resume và giới hạn chất lượng nội dung.

V2 là tầng đọc nội dung có tọa độ nguồn, trước bước tách lời giải để chấm.
V1, PDF gốc và metadata gốc được giữ nguyên. Chưa có đánh giá độ chính xác
toán học bằng bộ đáp án chuẩn; các bản xuất vẫn `publishable: false`,
`academic_review: PENDING`, `grading_support: NOT_ASSESSED`.

## Luồng xử lý

1. Khóa danh sách câu, SHA-256 PDF, metadata, model và mã xử lý.
2. Mở PDF gốc, đọc glyph với font thật, giữ định danh từng glyph.
3. Tìm bảng trên toàn trang bằng cạnh có mực. Loại khung nền trắng, sau đó
   đối chiếu bảng với vùng câu hỏi/lời giải. Tách ô, hàng, cột và ảnh nguồn.
4. Che glyph/cạnh của bảng và ảnh trước khi đề xuất vùng công thức. Một glyph
   không được vừa thuộc bảng vừa thuộc công thức trong cùng phần/trang.
5. Đọc hình học có giới hạn: baseline, chỉ số trên/dưới, phân số lồng nhau,
   dấu ngoặc ghép đủ mảnh, cận tích phân và gạch trên có chứng cứ. Hệ nhiều
   dòng hoặc cấu trúc mơ hồ giữ ảnh; không nối phẳng các phương trình.
6. Với vùng chưa đọc chắc: PP-FormulaNet M và S local, kiểm tra cú pháp KaTeX,
   ký hiệu số, dấu và cấu trúc nguồn. Hai model đồng ý vẫn chỉ là bản nháp.
7. Qwen3-VL local đọc độc lập **một vùng ảnh mỗi câu thuộc bộ đánh giá**.
   Kết quả là kiểm tra chẩn đoán có phạm vi, không duyệt toàn bộ câu/lời giải.
8. Xuất JSONL, JSON dễ đọc, giao diện đối chiếu, ảnh và báo cáo so sánh glyph.

Ô bảng chưa đọc chắc dùng ảnh từng ô; ô gộp giữ ảnh cả bảng. Dòng có ký tự
ghép bị lặp trong PDF được gắn cờ và giữ ảnh thay vì làm mất cả câu. Chuỗi
`raw_text_lossy` chỉ để truy vết, không dùng làm nội dung chuẩn để chấm.

Contract máy đọc nằm tại
`tools/pdf_metadata/pdfmeta/paired/transcription_v2/record.schema.json`.
Contract bắt buộc giữ trạng thái bản nháp, kiểm tra tọa độ/hash/định danh glyph;
schema hợp lệ không chứng minh công thức đúng về toán học.

## Chạy lại bộ mẫu cố định

Từ thư mục repo trên ổ E, dùng Python của môi trường PDF hiện có:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'tools\pdf_metadata'
$env:PYTHONUTF8 = '1'
$py = '.tmp\pdf-pipeline-runtime\.venv\Scripts\python.exe'
& $py -m pdfmeta.paired.transcription_v2.batch `
  --input .tmp\pdf-jobs\4ebd40c425c242baa4faf416\corpus\cau-hoi-co-loi-giai.metadata.jsonl `
  --plan .tmp\toan12-local-corpus\plan.json `
  --v1 .tmp\pdf-jobs\4ebd40c425c242baa4faf416\transcription-100-20261103 `
  --output .tmp\pdf-jobs\4ebd40c425c242baa4faf416\transcription-v2-100-20261103 `
  --runtime .tmp\pdf-pipeline-runtime --katex frontend\node_modules\katex\dist `
  --baseline .tmp\pdf-transcription-v2-20261103\v1-integrity-baseline.json
```

Đây là lệnh thử nghiệm 100 câu đã khóa, không phải lệnh nhập PDF bất kỳ.
Pipeline nhập PDF hiện có vẫn phải phân đoạn và ghép đề/lời giải trước.
Cache OCR chỉ tái sử dụng khi SHA ảnh, model, trọng số, package và adapter
trùng khớp; cache cũ được đọc có kiểm tra hash, không ghi đè.

## Qwen đọc ảnh

Chỉ chạy sau tầng OCR để tránh cùng tranh CPU. Không cần tải model mới.

```powershell
& tools\pdf_metadata\transcription_vision_runtime.ps1 -Action start `
  -Runtime .tmp\pdf-pipeline-runtime `
  -State .tmp\pdf-transcription-v2-20261103\qwen-runtime
# Chờ /health báo ok, rồi chạy:
& $py -m pdfmeta.paired.transcription_v2.vision `
  --output .tmp\pdf-jobs\4ebd40c425c242baa4faf416\transcription-v2-100-20261103 `
  --runtime .tmp\pdf-transcription-v2-20261103\qwen-runtime
& tools\pdf_metadata\transcription_vision_runtime.ps1 -Action stop `
  -Runtime .tmp\pdf-pipeline-runtime `
  -State .tmp\pdf-transcription-v2-20261103\qwen-runtime
```

Server chỉ nghe loopback, chạy CPU 6 luồng, ưu tiên thấp; không gọi Gemini
hay dịch vụ cloud. Có ledger token local, hash ảnh đầu vào và phạm vi mỗi lần đọc.

## Giới hạn và điều kiện mở rộng

- Mẫu cố định 100 câu của 12 PDF, mỗi chương 25 câu; không phải mẫu ngẫu
  nhiên đủ để công bố độ chính xác của toàn bộ kho.
- PDF ngoài mẫu có 47 trang, chọn trước 12 trang để kiểm tra layout/đọc trang.
  Tối đa 60 suy luận mỗi model; hết ngân sách giữ ảnh. PDF này chưa có cặp
  đề/lời giải được chấp nhận, vì vậy không tạo lời giải hoặc kết quả chấm giả.
- So sánh v1/v2 theo định danh glyph: tách riêng vùng được chuyển thành bảng,
  vùng giữ ảnh và vùng còn thiếu. Giảm số vùng công thức không tự chứng minh
  rằng LaTeX chính xác hơn.
- Chưa cho toàn bộ dữ liệu vào core chấm. Cần đo lỗi trên nội dung chuẩn,
  giải quyết vùng thiếu/khác nhau, rồi mới tách step và kiểm tra chấm thực tế.

## Kết quả chạy ngày 2026-11-04

| Phạm vi | Kết quả quan sát |
| --- | --- |
| Bộ cố định | 100/100 câu, 25 câu mỗi chương, cùng ID với v1 |
| Công thức | 1.657 vùng; 1.088 vùng hiển thị LaTeX nháp, 569 vùng giữ ảnh |
| Bảng | 34 bảng, 508 ô; 456 ô native nháp, 52 ô dùng ảnh |
| Qwen đọc ảnh | 40/40 vùng đã gửi, mỗi câu đánh giá một vùng |
| Kết quả Qwen | 3 cách đọc trùng, 8 khác, 15 không chắc, 14 phản hồi không dùng được |
| Phản hồi Qwen không dùng được | 11 chạm giới hạn đầu ra 384 token; 3 không đạt kiểm tra cấu trúc nội dung |
| PDF ngoài mẫu | 12/47 trang đã chọn trước, 405 vùng công thức, 3 bảng, 96 lượt OCR |
| Kiểm tra tài sản | 2.107 ảnh của bộ 100 + 434 ảnh ngoài mẫu khớp hash, không thiếu ảnh |
| Schema | 112/112 record hợp lệ về cấu trúc |
| Giữ nguyên v1 | 4.068 file kiểm tra, không thay đổi nội dung |
| Kiểm thử | 397 test qua; giao diện desktop/mobile, lọc chương, 40 câu đánh giá, tab và tải JSON đã kiểm tra |

Tỷ lệ Qwen trùng không phải độ chính xác: vùng khó được ưu tiên và chưa có
gold transcription độc lập cho cả mẫu. Không nâng trạng thái học thuật của
bất kỳ câu nào. Mọi câu vẫn `PENDING`, không xuất điểm chấm thật.

So sánh theo glyph cho thấy 119 vùng v1 từng giữ ảnh nay có LaTeX nháp phủ đủ
glyph, 37 vùng được phân loại lại thành bảng. 137 vùng không còn là ROI công
thức nhưng nằm trong ảnh hình nguồn; 6 vùng còn lại cần kiểm tra ranh giới,
vẫn có ảnh toàn đoạn. Những số này phản ánh thay đổi đường xử lý, không phải
số câu được xác nhận đúng.

Lượt xuất cuối mất 346,85 giây, RSS lớn nhất của cây tiến trình khoảng
2,09 GB (hệ thập phân), có tái sử dụng 1.110 cache OCR. Đây là lượt có cache,
không phải benchmark khởi động lạnh. Qwen chạy CPU local, không gọi API cloud;
server model đã được dừng sau khi hoàn tất.

Chưa đưa v2 thành mặc định hoặc chạy toàn kho để chấm. Ưu tiên tiếp theo:
giải quyết ranh giới ROI, nội dung toán nằm trong ảnh và phản hồi vision bị
cắt/không chắc; sau đó kiểm tra lại nội dung trước khi tách bước chấm.
