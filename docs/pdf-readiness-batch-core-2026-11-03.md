# PDF: đối chiếu ảnh, hàng đợi và gói nối core

## Lệnh sử dụng

Kéo một PDF vào `tools/pdf_metadata/process_pdf.cmd`. Sau trích xuất, LaTeX và Qwen metadata, lệnh tự đối chiếu ảnh công thức và xuất gói core. Mặc định hậu kiểm tối đa **12 vùng**; `-VisualLimit 0` mới kiểm mọi vùng tìm được. Chỉ vùng có bbox công thức được sử dụng, không giả vờ một đoạn văn là công thức đã định vị chính xác.

```powershell
.\tools\pdf_metadata\process_pdf.ps1 'E:\tai-lieu.pdf' -ReviewLimit 3 -VisualLimit 8 -Open
```

Kéo thư mục PDF hoặc ZIP vào `process_corpus.cmd` để chạy hàng đợi. Mặc định mỗi lượt tối đa 100 trang, Qwen tối đa 3 câu/PDF, hậu kiểm 8 vùng/PDF, timeout 3.600 giây/PDF. PDF vượt ngân sách trang còn PENDING; không cắt rồi nhận là đã xử lý cả tài liệu. Dùng MaxPages 0 để bỏ giới hạn trang.

```powershell
.\tools\pdf_metadata\process_corpus.ps1 'E:\thu-muc-pdf' -MaxPages 100 -ReviewLimit 3 -VisualLimit 8 -Open
# Thu thập cả kho thành bản nháp, không gọi Qwen:
.\tools\pdf_metadata\process_corpus.ps1 '.\data\Toan12.zip' -MaxPages 0 -SkipQwen -VisualLimit 8 -Open
```

Hàng đợi chạy một PDF tại một thời điểm, priority BelowNormal trên Windows. PDF cùng byte được gộp theo SHA-256. Chạy lại dùng checkpoint nếu báo cáo còn đúng hash. Lỗi được giữ lại, không lặp vô hạn; `-RetryFailed` chạy lại tài liệu thất bại. Việc thử lại phản hồi model lỗi là thao tác riêng: `review_pdf.ps1 -RetryFailed` hoặc `verify_images.ps1 -RetryFailed`.

PDF/ZIP gốc không sửa. ZIP được đọc vào cache trên E, không dùng đường dẫn thành viên để giải nén ra ngoài cache; kiểm CRC trước khi dùng lại. Timeout dừng cây tiến trình của worker do chính hàng đợi tạo, không dừng toàn bộ Python/Qwen trên máy.

## Đối chiếu ảnh

`pdfmeta.readiness.visual` đọc file cuối, nhóm bbox, ưu tiên cảnh báo cấu trúc và các vùng mơ hồ. Mỗi lượt có giới hạn từ 4 vùng trở lên bổ sung một vùng NORMALIZED làm mẫu kiểm nếu có. Crop PDF ở 240 DPI với lề nhỏ, lưu ảnh/hash/model/raw response riêng. Cache bao gồm ảnh, weights, phiên bản package và adapter; thay model/ảnh/adapter không dùng nhầm phản hồi cũ.

Mặc định dùng PP-FormulaNet_plus-M local đã có. Qwen nhận ảnh là lựa chọn riêng, không phải review metadata cũ:

```powershell
.\tools\pdf_metadata\verify_images.ps1 -Job '.tmp\pdf-jobs\<hash>' -Engine ocr -Limit 8
.\tools\pdf_metadata\verify_images.ps1 -Job '.tmp\pdf-jobs\<hash>' -Engine qwen -Limit 2
```

Wrapper Qwen tự khởi động, chờ sẵn sàng và dừng server do nó tạo. Server có sẵn được giữ lại. Không chạy OCR và Qwen nặng đồng thời trong một entry PDF. Toàn bộ model, cache và log ở E, không có cloud fallback.

Các trạng thái gồm AGREEMENT_NEEDS_SOURCE_REVIEW, IMAGE_TEXT_CONFLICT, SOURCE_STRUCTURE_BLOCKED, UNSUPPORTED_COMPARISON, IMAGE_MODEL_UNCERTAIN và IMAGE_OCR_FAILED. Hai bản đọc đồng ý không tự thành source_verified. Không tự ghi đè LaTeX hoặc bỏ các cảnh báo nguồn. Biểu thức chưa parse được vẫn giữ ảnh và bản đề xuất, không tự nhận là sai toán.

## Gói nối core và kiểm thử một bước

Mỗi job có `core-package.json` trỏ đến `core/versions/<hash>/questions.core-candidates.jsonl` và JSON Schema. Mỗi bước giữ ID, nội dung/ảnh nguồn, bộ kiểm có thể áp dụng, lý do bị chặn, thứ tự và trọng số còn null. Thứ tự bước không được coi là quan hệ chứng minh.

Adapter thật có ở `pdfmeta.readiness.core.check(job, request)` hoặc CLI:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'tools\pdf_metadata'
& .tmp\pdf-pipeline-runtime\.venv\Scripts\python.exe -B -m pdfmeta.readiness check `
  --job '.tmp\pdf-jobs\<hash>' --request 'E:\request.json'
```

Request chỉ được cấp `step_id`, `candidate_latex`, và tùy chọn `declared_excluded` (danh sách điểm bị loại). Không nhận expected answer/checker từ request. Adapter đọc bộ kiểm theo ID từ package đã kiểm hash và từ chối package cũ khi file cuối đổi.

Phạm vi hiện tại là đồng nhất biểu thức hữu tỉ một biến, bậc tối đa 8, với kiểm miền loại nghiệm mẫu số. Ví dụ y=x/x và y=1 không được coi tương đương miền nếu thiếu x≠0. Hàm lượng giác, nhiều biến, chuỗi điều kiện chưa cấu trúc hoặc trường hợp không hỗ trợ trả NOT_ASSESSED. Parser có giới hạn độ dài/token/số mũ, không eval text.

Phản hồi chỉ là CANDIDATE_MATCH, CANDIDATE_MISMATCH hoặc NOT_ASSESSED, luôn `score=null`, `production_grade=false`. Tất cả record còn academic_review=PENDING, grading_support=NOT_ASSESSED, publishable=false. Đây là adapter kiểm thử nối core; chưa import vào database hoặc bật chấm điểm chính thức.

## Kết quả đã chạy

- Pilot 57 trang/120 câu/372 bước: tạo được **32 bộ kiểm thử nghiệm**, toàn bộ 372 bước còn bị chặn khỏi chấm chính thức. Đã gọi adapter thật với biểu thức khớp và lệch +1, trả CANDIDATE_MATCH/CANDIDATE_MISMATCH và không sinh điểm.
- Hậu kiểm OCR 8/342 vùng đã định vị: 1 vùng đồng thuận cần kiểm nguồn, 7 vùng chưa so sánh được bằng grammar hiện tại. 458 ứng viên chưa định vị chính xác được đếm riêng, không biến mất khỏi báo cáo. OCR đọc lại được gạch trên và chỉ số dưới ở hai crop đã xem trực tiếp; chưa tự đưa các bản đọc này vào đáp án chấm. Lượt đầu 30,157 giây; lượt dùng lại 8 cache hits, 0 inference, 1,423 giây.
- Qwen vision thử riêng 2 vùng: 2 phản hồi hoàn chỉnh, 126,742 giây, cả hai chưa so sánh được trong grammar hiện tại. Không coi kết quả này là cải thiện độ chính xác. Qwen đã được dừng sau khi thử.
- Hàng đợi thử **5 mẫu/9 trang từ 4 PDF gốc**: xác suất, tích phân, thống kê, mục lục native và một bản raster được tạo từ trang mục lục. Bản raster là stress test tổng hợp, không phải PDF scan độc lập. Các cửa sổ có thể cắt câu cuối, nên số đo chỉ kiểm dấu mốc câu.
- Đã xem ảnh cả hai trang của ba cửa sổ bài tập rồi ghi nhãn dấu mốc: lần lượt tìm đủ 12/12, 12/12 và 8/8; hai mẫu mục lục có 0 câu. Không suy rộng thành nhận dạng toàn nội dung chính xác 100%. Lỗi nhận Bài 1/Bài 2 trong mục lục thành câu đã sửa bằng nhận diện heading + cấu trúc danh mục; giữ trang đó ở metadata/orphan với lý do rõ ràng.
- Các mẫu ngoài đạo hàm chưa có lời giải hoặc ngoài grammar vẫn giữ DRAFT_PARTIAL, 0 bước chấm; pipeline không tự tạo lời giải cho chúng.
- Audit 40 vùng công thức trước đây chạy lại, ba module đóng băng còn đúng hash: 26 đúng biểu thức được chỉ định, 14 giữ lại; đây vẫn là mẫu chẩn đoán, chưa là benchmark toàn kho.

Dashboard `http://127.0.0.1:8789/` có hàng đợi, tài nguyên worker hậu kiểm, ảnh đối chiếu và số bộ kiểm thử nghiệm. Liên kết đánh giá đa tài liệu xuất hiện sau chạy evaluate. Báo cáo cũ bị đánh dấu STALE_RESULT nếu một lượt mới thay đổi các artifact nó tham chiếu.

```powershell
& .tmp\pdf-pipeline-runtime\.venv\Scripts\python.exe -B -m pdfmeta.readiness evaluate `
  --queue '.tmp\pdf-queues\<queue-id>\queue.json' --manifest '.tmp\pdf-readiness-20261103\manifest.json'
```

Chưa chạy toàn bộ 3.478 trang. Có thể thu thập cả kho dưới dạng bản nháp bằng hàng đợi; bằng chứng hiện tại chưa cho phép gọi kho đó là dữ liệu chấm sạch.

## Kiểm tra cuối

257 tests qua, gồm các giới hạn source/domain, cache ảnh đổi weights, lỗi ảnh và retry, package core bị sửa/cũ, request tự cấp expected answer, ZIP traversal/cache CRC, hàng đợi tuần tự/ngân sách/resume, loại mục lục và API báo cáo. Đã thử lại hàng đợi thật: 5 tài liệu vẫn COMPLETED, pages_attempted=0, không mở worker xử lý lại; thời gian từng tài liệu được giữ. Dashboard được kiểm bằng Edge ở desktop và 390 px, cùng liên kết ảnh/đánh giá. Ba PDF/ZIP đầu vào, 62 artifact cũ và ba module công thức đã đóng băng không đổi hash. Các file thuộc phần việc khác không đổi.
