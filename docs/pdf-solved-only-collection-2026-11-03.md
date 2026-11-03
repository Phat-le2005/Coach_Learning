# Tập riêng chỉ gồm câu có lời giải

Đã tạo một PDF độc lập và metadata chỉ chứa các lần xuất hiện có cả đề và lời giải từ tài liệu xác suất. Không đưa phần câu chưa ghép được lời giải hoặc các mục lý thuyết đã tách vào tập này. ID nguồn và số câu gốc vẫn giữ, thêm số thứ tự tập 001–253. Đây là 253 lần xuất hiện được chọn; chưa khẳng định đã loại mọi bài toán trùng nội dung.

## Kết quả hiện tại

- **253 mục**, **151 trang**, **5.298.491 byte**; PDF có 253 bookmark.
- **255 lần xuất hiện chưa ghép được lời giải** bị loại khỏi cả PDF, HTML và danh sách metadata chính của tập riêng.
- Bổ sung nhận dạng nhãn `Giải` đứng riêng tìm thêm 2 cặp so với kết quả 251 trước đó.
- Đã tách 12 chuyển mục khỏi lời giải trước, gồm 7 cảnh báo cũ và 5 chuyển mục thêm. Giữ nguyên nội dung bị tách trong hàng ngữ cảnh và `boundary-audit.json`; không xóa nguồn.
- Các vùng giữ lại được crop tới khoảng trắng sau dòng cuối thay vì sát đầu tiêu đề đậm tiếp theo. Các trang chuyển mục đã được xem trực tiếp trên ảnh nguồn.
- Không lỗi cấu trúc do validator phát hiện. Tất cả record còn `academic_review=PENDING`, `grading_support=NOT_ASSESSED`, `publishable=false`.

Nguồn gốc vẫn nguyên SHA-256 `3298956d1d00de01e9ada735d3ca87c69599beca07169ff4d86e7f86d469dec1`.

## Các file

Trong `E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-jobs\3298956d1d00de01e9ada735\collections\solved-only-20261103`:

- `Xac_suat_cac_cau_co_loi_giai.pdf`: file tổng hợp để đọc, chỉ gồm các mục có lời giải.
- `cau-hoi-co-loi-giai.metadata.json` / `.jsonl`: đúng 253 mục, không có record chưa ghép. Mỗi mục có `collection_number`, `collection_pdf_pages`, `collection_placements` ngoài ID, text hỗ trợ và source spans gốc.
- `cau-hoi-co-loi-giai.html`: bản xem offline hoặc qua dashboard, cũng chỉ chứa 253 mục.
- `pdf-collection.json`: hash PDF, số trang, số mục và đường dẫn metadata đã gắn với PDF.
- `assets/`: các crop nguồn và crop kết hợp. PDF/HTML tự chứa ảnh; metadata dùng các crop/hash để truy vết.

Trang HTML: http://127.0.0.1:8789/artifacts/3298956d1d00de01e9ada735/collections/solved-only-20261103/cau-hoi-co-loi-giai.html

## Cách dựng lại

Chạy `convert_pairs.ps1` trước để có job trích xuất hiện hành. Sau đó:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'tools\pdf_metadata'
& .tmp\pdf-pipeline-runtime\.venv\Scripts\python.exe -B -m pdfmeta.paired solved-collection `
  --job '.tmp\pdf-jobs\3298956d1d00de01e9ada735' `
  --output '.tmp\pdf-jobs\3298956d1d00de01e9ada735\collections\solved-only-20261103'
```

`collection_pdf.py` là renderer độc lập dùng ReportLab/Pillow và font Arial hệ thống. Lượt này sử dụng runtime PDF đã có sẵn của Codex, không tải thêm package vào máy. Renderer nhận `--metadata`, `--output`, `--font-dir`; đọc `questions.metadata.json` của tập riêng rồi tạo PDF và metadata có ánh xạ trang mới.

PDF dùng các vùng ảnh nguồn liền mạch để tránh cắt ngang sơ đồ tại nhãn Lời giải, không giữ lớp text ẩn của những câu bị loại. Không OCR lại PDF tổng hợp để tạo metadata; metadata lấy từ cùng các ID/vùng đã chọn và thêm tọa độ trên PDF mới. Nhờ đó tránh thêm một vòng mất ký hiệu. Text/LaTeX và đáp án chuẩn vẫn cần hậu kiểm riêng.

## Kiểm tra và giới hạn

**326 tests qua**, gồm tách ngữ cảnh mà không mất block, không nhận câu văn thường làm tiêu đề, nhãn Giải, lọc vật lý record/ảnh, dấu phủ định và gạch điều kiện, giới hạn kết quả số. Đã kiểm toàn bộ 347 vị trí ảnh trên 151 trang: trong lề, không chồng nhau, không có trang chỉ chứa tiêu đề. ID/bookmark/metadata có đủ 253 mục và 0 record chưa ghép.

Đã render 13 trang đại diện của PDF cuối, xem contact sheet và ảnh đầy đủ ở đầu tài liệu/câu qua trang. Ảnh nguồn có một số lỗi vốn có, chẳng hạn hình mạch điện chồng chữ trong câu 5; bản tổng hợp giữ nguyên bằng chứng, chưa phục dựng nội dung bị che. Các kết quả này chưa là đánh giá nội dung toán học trên toàn bộ 253 mục.

Theo yêu cầu chuyển sang làm tập riêng, lượt này ưu tiên hoàn tất PDF và metadata. Các helper `quality.py` / `probability.py` là nhánh thử nghiệm cho đọc công thức có giới hạn; **chưa chạy OCR hay hoàn tất audit 20 câu** và không có tuyên bố cải thiện độ đúng LaTeX. Không gọi model/API, không import database, không push Git. Kiểm chứng nằm tại `.tmp/pdf-paired-quality-20261103`.
