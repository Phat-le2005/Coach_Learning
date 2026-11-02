# Trang theo dõi PDF local

Mở `http://127.0.0.1:8789/`. Cổng 8790 dành cho Qwen; nếu cổng dashboard bận, launcher chọn cổng khác và in URL thực tế. Trang riêng với FE/BE, không cần chạy Next.js để xem tiến trình.

## Sử dụng

Kéo PDF vào `tools/pdf_metadata/process_pdf.cmd`. Dashboard tự mở khi bắt đầu và tự cập nhật mỗi 2 giây. Hoặc chạy tại thư mục repository:

```powershell
.\tools\pdf_metadata\process_pdf.ps1 'E:\tai-lieu.pdf' -Open
# Thử giới hạn Qwen trên 3 câu; đây không phải duyệt đủ tài liệu.
.\tools\pdf_metadata\process_pdf.ps1 'E:\tai-lieu.pdf' -ReviewLimit 3 -Open
```

Khi chạy xong, bấm **Mở kết quả** hoặc **Tải file cuối JSONL**. Chạy lại cùng PDF để dùng checkpoint. `-NoProgress` tắt dashboard, `-ProgressPort 8800` chọn cổng khác. Không mở thêm tab kết quả sau khi đã mở dashboard.

Có thể mở riêng dashboard khi chưa chạy tài liệu:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'tools\pdf_metadata'
& .tmp\pdf-pipeline-runtime\.venv\Scripts\python.exe -B -m pdfmeta.progress ensure --root .tmp/pdf-jobs --runtime .tmp/pdf-pipeline-runtime
```

## Số liệu có ý nghĩa gì?

- Tám công đoạn: đọc trang, tách câu, nhận dạng công thức, kiểm tra bước giải được hỗ trợ, đọc bảng, chuẩn hóa LaTeX, Qwen rà soát và xuất file.
- Thanh tổng thể đếm công đoạn; không ước tính thời gian còn lại. Từng bước chỉ hiện bộ đếm khi có tổng số thật.
- Lượt Qwen giới hạn ghi số câu trong phạm vi và số câu còn chưa chạy. Hoàn tất lượt xử lý không phải xác nhận đáp án đúng hoặc dữ liệu sẵn sàng chấm.
- Tài liệu cũ lấy trạng thái từ báo cáo đã lưu, không tạo thời gian bắt đầu hoặc nhật ký giả. Kết quả lượt trước vẫn mở được khi chạy lại nhưng tách khỏi chất lượng của lượt đang chạy.
- RAM là RSS cộng của worker và Qwen do pipeline quản lý; CPU được chuẩn hóa theo toàn máy. Không cộng trình duyệt, FE/BE hoặc dashboard. Mẫu CPU đầu tiên có thể chưa có giá trị.
- Trạng thái/nhật ký nằm tại `<job>/progress.json` và `progress-events.jsonl`. Pipeline giữ lock và quyền quyết định của mình; dashboard chỉ đọc.

## Tài nguyên và phạm vi

HTML/CSS/JavaScript thuần, không CDN, không framework mới. Server chỉ nghe `127.0.0.1`, không có API upload/chạy model/sửa dữ liệu. Chỉ phục vụ file kết quả trong thư mục job, không phục vụ PDF gốc hoặc `.env`. Tài nguyên, log, cache và kết quả giữ trên E.

Qwen chỉ nạp trong lượt xử lý; wrapper dừng server mà chính nó đã khởi động. Dashboard có thể tiếp tục chạy để xem kết quả. Thông tin server ở `.tmp/pdf-pipeline-runtime/progress-server.json`; không dùng lệnh dừng toàn bộ Python.

## Kiểm tra

Đã kiểm thử API, trạng thái theo giai đoạn, lượt Qwen giới hạn, cache, tiến trình bị ngắt và giới hạn đường dẫn. Giao diện được kiểm tra trực tiếp bằng Edge headless ở desktop và màn hình 390 px, gồm tìm tài liệu, bộ lọc, menu di động, hộp hướng dẫn, liên kết kết quả và KaTeX. Chạy thử pipeline trên PDF 57 trang/120 câu với Qwen giới hạn 3 câu; không chạy bộ 3.478 trang.
