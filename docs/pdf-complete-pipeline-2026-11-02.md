# Nhập một PDF, nhận bản xuất cuối có LaTeX và Qwen review

## Thao tác sử dụng

Kéo PDF vào `tools/pdf_metadata/process_pdf.cmd`, hoặc chạy từ thư mục repository:

```powershell
.\tools\pdf_metadata\process_pdf.ps1 'E:\tai-lieu.pdf'
```

Đường dẫn PDF là thông tin bắt buộc duy nhất. Mặc định xử lý mọi câu tìm được. Môi trường, cache, weights và đầu ra ở E; không gọi cloud API. Python 3.13 cần có để tạo môi trường lần đầu; model/package còn thiếu được tải một lần. PDF có mật khẩu cần bản mở khóa hợp lệ.

Luồng thực hiện:

1. Nhận dạng tài liệu bằng SHA-256, giữ snapshot và kiểm dữ liệu gốc không thay đổi.
2. Tự chọn đọc native hoặc OCR cho từng trang; tạo ảnh, glyph/bbox và metadata nguồn.
3. Tách câu, đáp án nguồn và bước giải ứng viên; đọc công thức/bảng trong phạm vi hỗ trợ.
4. Chuẩn hóa text/công thức sang LaTeX, ưu tiên code cho trường hợp rõ.
5. Qwen local đề xuất LaTeX cho các mảnh khó, rồi rà soát metadata. Các vai trò dùng prompt/schema và cache riêng.
6. Code kiểm source ID, nội dung số/biến, phép toán, mẫu số/miền và các tham chiếu. Model không được cấp quyền tự sửa nguồn, chấm điểm hay bật xuất bản.
7. Xuất một file cuối có đủ dữ liệu nguồn, công thức ứng viên, trạng thái và phản hồi Qwen; mở trang xem offline.

Tắt máy/ngắt lệnh thì chạy lại cùng PDF. Các job model đã hoàn tất dùng lại cache; raw response chưa hợp lệ vẫn được giữ. Thử lại các job lỗi bằng `review_pdf.ps1 -RetryFailed` thay vì lặp vô hạn. OCR và Qwen chạy nối tiếp; Qwen dùng 3 CPU threads, BelowNormal priority, GPU layers 0. Server do wrapper khởi tạo sẽ tự dừng khi xong; server có sẵn được giữ lại.

## File cuối và phiên bản

Mỗi PDF có thư mục `.tmp/pdf-jobs/<24-ký-tự-hash>/`. Không cần tự đặt tên job.

```text
final.html                         Mở trang xem bản xuất mới nhất
final.json                         Đường dẫn file cuối + báo cáo
result.json                        Giữ cả đường dẫn trích xuất và đường dẫn cuối
pipeline-status.json               Bước hiện tại/trạng thái dừng
final/versions/<hash>/
  questions.final.jsonl            File cuối cho xử lý tiếp
  questions.final.pretty.json      Cùng nội dung, dễ đọc
  schema.json                      Hợp đồng pdf-final/v1
  report.json
  review.html
latex/versions/<hash>/
  formulas.jsonl
  unresolved.jsonl
  model-states.json
  jobs/<hash>/                     Input, raw response, trạng thái Qwen LaTeX
reviews/qwen/<hash>/               Qwen review và raw response riêng
```

File cuối dùng `pdf-final/v1`: mỗi dòng chứa `source_metadata` nguyên bản, `latex_normalization`, `machine_review`, trạng thái máy và ID câu. `source_metadata_file` chỉ ra phiên bản trích xuất được sử dụng. Các record luôn `academic_review=PENDING`, `grading_support=NOT_ASSESSED`, `publishable=false`. Đây là bản xuất biên soạn có truy vết, không phải schema import production grading đã duyệt.

Trang xem có ảnh đề, text nguồn, LaTeX render bằng KaTeX offline, nhận xét Qwen, tìm kiếm và lọc trạng thái. Assets được dùng lại từ KaTeX đã cài trong frontend, kèm license và font; nếu frontend chưa cài thì vẫn xem được mã LaTeX và metadata. Không tải CDN khi mở trang.

## Quy tắc text → LaTeX

- `y=x²-3x+2` chuyển thành `y=x^{2}-3\cdot x+2` bằng code.
- `y=x/x` giữ `\frac{x}{x}` và mẫu số, không rút gọn thành 1 làm mất điều kiện `x≠0`.
- `y=x2` được giữ mơ hồ; không tự kết luận số 2 là số mũ.
- `y=1/2x`, ký tự chưa giải mã, điều kiện hoặc chuỗi đẳng thức không nhất quán không được tự chuẩn hóa thành cách đọc chắc chắn.
- Công thức từ glyph/native/OCR và công thức lấy từ text là các ứng viên có nguồn riêng. Không lấy số lượng ứng viên làm số công thức độc lập hoặc độ chính xác.
- Qwen chỉ nhận tối đa ba mảnh công thức có mã `f1`, `f2`, `f3` do code cấp và trả tối đa hai LaTeX ứng viên. Model không viết lại đoạn văn, tự gán bbox hay tự chép source ID.
- Bản đề xuất chỉ được nhận là thay đổi cách biểu diễn nếu text gốc parse được độc lập, biểu thức tương đương, số không bị thay đổi và mẫu số không bị mất. Trường hợp khác giữ `MODEL_PROPOSAL_NEEDS_SOURCE`; model báo tự tin không thay thế bằng chứng.

`NORMALIZED` có nghĩa chuyển biểu diễn trong phạm vi grammar đã kiểm, không có nghĩa đã xác nhận khớp ảnh hoặc đúng học thuật. Chuỗi LaTeX render được vẫn có thể là bản đọc sai ảnh. Qwen trong hai vai trò mới đều đọc text/công thức ứng viên, không đọc lại ảnh PDF.

## Chạy thử và giới hạn

```powershell
# Thử giới hạn cả Qwen LaTeX và Qwen review trên ba câu đầu.
.\tools\pdf_metadata\process_pdf.ps1 'E:\tai-lieu.pdf' -ReviewLimit 3

# Không load Qwen; vẫn xuất file cuối, giữ trạng thái review DEFERRED.
.\tools\pdf_metadata\process_pdf.ps1 'E:\tai-lieu.pdf' -SkipQwen

# Chạy tiếp hai bước mới từ metadata đã có, không OCR lại.
.\tools\pdf_metadata\review_pdf.ps1 -Job '.tmp\pdf-jobs\<hash>'
```

207 tests qua, gồm nguồn/miền không bị đổi, cấm đoán số mũ từ `x2`, mẫu số mơ hồ, model tự đổi số/rút gọn, fragment ID sai/trùng, chia vai trò model, cache cả hai bước, PDF hash sai, xuất bản cuối khi chỉ chạy rules và tài liệu không có marker câu được giữ PAGE_METADATA_ONLY thay vì báo hoàn tất nhầm. Unit tests có mock provider; không đại diện độ đúng OCR học thuật.

Lớp rules đã chạy trên metadata thật 120 câu từ PDF 57 trang: 910 ứng viên, 319 chuyển được biểu diễn; còn 579 không hỗ trợ/mơ hồ và 12 thuộc nhóm có các cách đọc xung đột. Đây là đếm ứng viên có trùng lặp theo nguồn, không phải tỷ lệ chính xác. Toàn bộ 319 LaTeX NORMALIZED qua KaTeX renderer với strict errors; kiểm đó không xác nhận nội dung toán.

Đã chạy trang viewer bằng Edge headless, thấy 120 thẻ câu, render công thức, tìm câu 152 ra đúng một thẻ, không có lỗi JavaScript và đã xem ảnh screenshot. Chưa kiểm thao tác kéo thả trực tiếp trong Explorer. Các số đo runtime Qwen thật, cache và đường dẫn mới nhất nằm trong `final.json`, `latex.json`, `qwen-review.json` và ledger local.

Lượt tích hợp Qwen thật giới hạn ba câu 151–153: 3 lượt text-to-LaTeX mất 19,137 giây, đều có JSON hoàn chỉnh; có thêm 4 đề xuất được giữ `MODEL_PROPOSAL_NEEDS_SOURCE`, không tự nhận các số mũ suy đoán là đúng. Tổng 914 ứng viên, số NORMALIZED vẫn là 319. Sau đó 3 lượt Qwen review mất 90,556 giây; cả ba câu MACHINE_FLAGGED, 117 câu DEFERRED vì giới hạn thử. Cả hai bước mất 110,160 giây, không tính setup/khởi động server. Chạy lại cùng cấu hình có 3+3 cache hits, 0 inference mới; hai bước và đóng gói mất 1,019 giây, không tính startup. Chưa chạy Qwen trên đủ 120 câu.

PDF native mới tạo độc lập, khác hash và chưa có cache: entry PowerShell tự trích 1 trang, 2 câu (701,702), 4 lượt gọi adapter OCR local, 33,594 giây; sau đó `-SkipQwen` vẫn xuất file cuối với 15 ứng viên/9 NORMALIZED, giữ review DEFERRED đúng yêu cầu. Đây là smoke test đường nhận PDF mới, không phải benchmark layout/OCR độc lập. Server Qwen đã dừng trước khi OCR fixture mới để tránh load đồng thời.

Luồng tự chạy theo file khác, nhưng bố cục nhiều cột, scan mờ, mất font/ký tự, bảng nối trang và nội dung toán ngoài grammar có thể vẫn chưa nhận đúng. Câu có vấn đề tự tách trạng thái, không chặn cả PDF và không được tự coi là đáp án chấm đúng. Chưa chạy toàn kho 3.478 trang hoặc đo chất lượng trên một benchmark PDF độc lập.
