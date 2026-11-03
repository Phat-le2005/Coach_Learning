# Một file đề–lời giải và metadata có nguồn

## Quyết định

Chuyển file xác suất đã chọn thành **một HTML tự chứa ảnh và dữ liệu**. Mỗi mục hiển thị đề ở trên, lời giải nguyên bản ở dưới. Text native là phần hỗ trợ tìm kiếm, chưa được coi là bản chép toán chính xác. Phân số, gạch phủ định, bảng/hình được giữ trong ảnh nguồn, không phải dựng lại từ text đã mất bố cục.

Metadata được đọc từ payload của chính HTML đó rồi xuất JSON/JSONL. Không gọi OCR lần nữa trên file đã chuyển, không ép một lời giải thành rubric hoặc các bước chấm trước khi xác định được nội dung đúng. Đây là một nhánh nhẹ cho PDF native có nhãn câu và lời giải; luồng OCR/model đầy đủ vẫn riêng biệt.

## Kết quả file xác suất

Nguồn: `chuyen-de-xac-suat-co-dieu-kien-tu-co-ban-den-nang-cao.pdf`, SHA-256 `3298956d1d00de01e9ada735d3ca87c69599beca07169ff4d86e7f86d469dec1`.

- Đã đọc đủ **167 trang**, không cần inference. Native extraction lượt đầu 198,852 giây, RSS cao nhất lấy mẫu khoảng 790 MB; chạy ở BelowNormal. Đây không phải benchmark trên toàn bộ kho.
- Tìm được **508 lần xuất hiện của câu**, không gọi đây là 508 bài khác nhau. Có phần đề riêng lặp lại ở phần có lời giải, và số câu bắt đầu lại giữa các mục.
- **251 ứng viên có cả đề và lời giải** được xuất vào JSONL chính. **257 lần xuất hiện chưa có lời giải được ghép** giữ riêng; không suy ra tất cả là thiếu lời giải thật trong PDF.
- **7 ứng viên có cảnh báo ranh giới**, vì lời giải có thể chứa mở đầu mục tiếp theo. Cảnh báo nằm trong từng record và hàng chờ; chưa tự cắt nội dung hoặc coi chúng là cặp đã xác minh.
- Tìm được nhãn đáp án riêng ở 63 lần xuất hiện trong toàn bộ 508. Với các câu còn lại, `answer.text_raw` là null, kết luận vẫn giữ trong lời giải. Không tự suy ra đáp án chuẩn bằng cách lấy số cuối cùng.
- 111 lần xuất hiện có vùng nguồn qua nhiều trang. Đã kiểm trực tiếp ví dụ câu 2 nối lời giải từ trang PDF 8 sang 9; đây là kiểm mẫu, chưa là độ chính xác ghép toàn bộ 251 cặp.
- 941 ảnh crop được giữ trong HTML; kích thước file khoảng **7,54 MB**. Chỉ dựng DOM/ảnh của câu đang xem để tránh tải đồng thời hàng trăm ảnh.
- Không có lỗi cấu trúc do validator phát hiện. Điều này không xác nhận toàn bộ nội dung toán hoặc tất cả ranh giới đều đúng. Mọi record vẫn PENDING / NOT_ASSESSED / publishable=false.

## File nào để dùng

Thư mục job: `E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-jobs\3298956d1d00de01e9ada735`.

Đọc **`paired.json`** để lấy đường dẫn phiên bản hiện hành, không gắn cứng hash thư mục:

| File | Vai trò |
| --- | --- |
| `questions-and-solutions.html` | File chuyển đổi chính; mở offline được, chứa ảnh và payload metadata |
| `questions.metadata.json` | 251 cặp ở `questions`, 257 trường hợp chưa ghép ở `unpaired_questions`, cùng ảnh/hash và metadata tài liệu |
| `questions.metadata.jsonl` | Mỗi dòng một cặp đề–lời giải ứng viên để xử lý tiếp |
| `questions.unpaired.jsonl` | Các lần xuất hiện chưa đủ cặp, giữ riêng để kiểm tra |
| `assets/` | Ảnh crop tham chiếu bởi metadata; export lại từ HTML sẽ tái tạo các file này |
| `metadata.schema.json` | Hợp đồng cấu trúc cho JSON tài liệu |
| `pairing-review-queue.json`, `report.json` | Cảnh báo, số lượng và bằng chứng xử lý |

Trang ổn định: http://127.0.0.1:8789/artifacts/3298956d1d00de01e9ada735/paired/review.html

Đáp án/lời giải là dữ liệu biên soạn, không đưa nguyên file này vào luồng đề của học sinh.

## Chạy lại và dùng PDF khác

Từ thư mục repo trên E:

```powershell
.\tools\pdf_metadata\convert_pairs.ps1 `
  '.tmp\pdf-layout-survey-20261103\selected\chuyen-de-xac-suat-co-dieu-kien-tu-co-ban-den-nang-cao.pdf' -Open

# Cùng lệnh cho PDF native có nhãn câu/lời giải khác:
.\tools\pdf_metadata\convert_pairs.ps1 'E:\tai-lieu\file-khac.pdf' -Open
```

Lệnh dùng môi trường Python đã có, không cài thêm model. File gốc và các kết quả trước không bị sửa. Job chọn theo SHA; page cache được dùng lại. Hash phiên bản gồm nguồn, code và nội dung cache/ảnh, không dùng thời gian chạy làm phiên bản.

Nếu chỉ còn HTML đã chuyển, vẫn xuất lại metadata và ảnh được:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'tools\pdf_metadata'
& .tmp\pdf-pipeline-runtime\.venv\Scripts\python.exe -B -m pdfmeta.paired metadata `
  --html 'E:\du-lieu\questions-and-solutions.html' --output 'E:\du-lieu\metadata'
```

Đầu vào HTML có schema/ID/ảnh được kiểm tra trước khi xuất; đường dẫn ảnh không được thoát ra ngoài output. Hash payload/ảnh kiểm tính nhất quán, chưa xác nhận toán học hoặc chứng thực tác giả.

PDF scan không có text trả `OCR_REQUIRED`, không giả thành trang trắng đã làm xong. Nhánh này chưa tự OCR PDF scan hoặc nhận mọi nhãn ví dụ/bố cục nhiều cột. Dùng luồng xử lý PDF đầy đủ và kiểm bố cục riêng cho các trường hợp đó.

## Sửa lỗi và kiểm tra

Đã sửa bộ ghép chung: `Trả lời: 6,67` ở bên trong **Lời giải** được giữ là nhãn đáp án, không chuyển parser về vùng học sinh trả lời và bỏ phần chứng minh phía sau. Ô `Trả lời: …` ở trước Lời giải vẫn được tách khỏi đề. Các phần nguồn không chắc được giữ với cảnh báo.

**314 tests qua**, gồm 12 tests cho nhánh chuyển đổi và lỗi nhãn đáp án: qua trang, số câu lặp, thiếu lời giải, trang ảnh, dữ liệu HTML giả/sai, đường dẫn ảnh, export từ HTML sang thư mục mới và chạy lại giữ phiên bản.

Đã kiểm Edge desktop, 390 px và mở file offline: 251 mục ở bộ lọc mặc định, 257 ở bộ lọc chưa ghép, tìm kiếm hoạt động, ảnh qua trang còn đủ, phần giải sau nhãn Trả lời được giữ, không lỗi JS/HTTP, không tràn ngang ở viewport đã thử. File offline không phát sinh request HTTP. Đã xem trực tiếp ảnh chụp desktop, mobile và câu nối hai trang. Native text vẫn mất dấu phủ định ở một số chỗ; ảnh nguồn giữ được dấu, không gắn nhãn text là chuẩn LaTeX.

Thư mục kiểm chứng: `.tmp/pdf-paired-conversion-20261103`. Chưa gọi Qwen/Gemini, chưa import database hoặc push Git trong lượt này.

## Hướng đi tiếp

Dùng 251 cặp này làm đầu vào trích xuất nội dung có cấu trúc. Trước tiên xử lý 7 cảnh báo ranh giới, rồi chọn mẫu có phân số, gạch phủ định và lời giải qua trang để đo độ đúng text/LaTeX. Sau khi có bản nội dung khớp nguồn mới thêm phân loại dạng bài, điều kiện, kết quả và đề xuất bước. Các ứng viên chỉ có ảnh/text chưa trở thành rubric chấm máy.
