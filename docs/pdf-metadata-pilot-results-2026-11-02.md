# Kết quả pilot PDF metadata - 02/11/2026

Đã triển khai và chạy thử offline trên PDF mẫu 57 trang. Đây là dữ liệu staging có nguồn đối chiếu; chưa phát hành vào ngân hàng câu hỏi hay bật chấm. Chưa xử lý Toan12.zip hoặc kho 3.478 trang.

## 1. Đã có gì chạy thật

Pipeline Python độc lập tại `tools/pdf_metadata`, không cài thêm model vào backend đang chạy:

```text
PDF bất biến
 -> chữ/glyph/tọa độ/font/màu/vector native + ảnh trang
 -> ghép câu, đề, đáp án, lời giải xuyên trang
 -> crop nguồn riêng cho đề/đáp án/lời giải
 -> PP-DocLayoutV3 phát hiện vùng công thức
 -> PP-FormulaNet_plus-S đọc crop 240 DPI
 -> so với chữ/glyph gốc, đánh dấu bất đồng
 -> PP-FormulaNet_plus-M đọc lại vùng bị cảnh báo
 -> JSONL ứng viên + kiểm tra nguồn/schema + trang review
```

PaddleOCR-VL-1.6 được chạy riêng trên trang 1 làm đối chứng toàn trang. Không dùng đầu ra model để ghi đè dữ liệu native hoặc tự duyệt một công thức.

## 2. Kết quả cấu trúc

| Kiểm tra | Kết quả |
| --- | --- |
| Trang nguồn | 57 |
| Câu ứng viên | 120, số 151-270 |
| Đáp án nguồn được liên kết | 120 |
| Lời giải nguồn được liên kết | 120 |
| Câu có vùng nguồn qua nhiều trang | 43 |
| Nhóm đoạn lời giải/bước ứng viên | 367, chưa là rubric đã duyệt |
| Lỗi schema, bbox, tham chiếu block, chồng crop đề với đáp án/lời giải | 0 trên output đã kiểm tra |
| Ca hồi quy có đối chiếu nguồn | 8/8 qua |
| Unit tests | 16 qua |
| Bài được phát hành/chấm tự động | 0 |

Đếm đủ câu/đáp án không chứng minh toàn bộ chữ và công thức đúng. 57/120/151-270 chỉ nằm trong fixture của nguồn này; parser không viết cứng các giá trị đó.

Các lỗi cấu trúc đã sửa bằng quy tắc chung và có test:

- Hai dòng “Đáp án” không có dấu hai chấm ở Câu 183-184.
- Tử số nằm cao hơn dòng “Câu 184” bị text extraction xếp sang câu trước. Giữ mảnh toán có bbox chồng lên dòng tiêu đề cho câu mới.
- Phần lời giải/bảng tiếp tục ở đầu trang kế tiếp, kể cả trước dòng chữ đầu tiên, được giữ trong vùng nguồn.
- Trang cuối không có tiêu đề câu mới vẫn nối vào Câu 270.
- Chặn dùng cùng thư mục output cho hai PDF khác hash để tránh lấy ảnh/cache cũ.

## 3. Kết quả model và tài nguyên

Máy thử có RTX 3050 Ti Laptop 4 GB; các lượt này chạy **CPU, 3 threads**, không benchmark GPU/Kaggle.

| Lượt thử | Phạm vi và kết quả | Thời gian đo |
| --- | --- | --- |
| PaddleOCR-VL-1.6, pipeline toàn trang | Trang 1, 24 block | 385,104 giây inference; 92,141 giây khởi tạo gồm tải model |
| Native + PP-DocLayoutV3 + FormulaNet S | Cả 57 trang; 190 crop công thức được detector tìm thấy | 329,095 giây toàn lượt; 12,094 giây khởi tạo; p50/trang 5,234 giây, p95 theo nearest-rank 8,574 giây |
| FormulaNet M, control | 4 vùng được đối chiếu trực tiếp với ảnh nguồn | Từng vùng khoảng 1-2 giây; log giữ số đo cụ thể |
| FormulaNet M, fallback | 42 vùng công thức bị cảnh báo từ lượt trước | 89,283 giây xử lý, không gồm khởi tạo model |

Hai dòng đầu có phạm vi tác vụ khác nhau: full-page VLM đọc cả chữ và công thức; hybrid lấy chữ native và chỉ OCR các vùng công thức detector tìm được. Không dùng các số này để kết luận chất lượng tương đương hoặc tốc độ tổng quát của hai model.

Lượt hybrid gắn được bằng chứng OCR cho 91/120 câu; hai vùng không gán chắc chắn được vào một câu đã vào hàng chờ. Không phát hiện vùng công thức trên một trang không có nghĩa trang đó không có công thức.

PaddleOCR-VL có RSS đỉnh được lấy mẫu khoảng 4.415 MB. Hybrid có RSS sau trang cao nhất khoảng 1.026 MB; đây không phải phép đo peak RAM. Tổng bốn file trọng số được tải là 2.921.972.508 byte, ngoài dung lượng môi trường/package/cache. Tất cả nằm trên ổ E tại `.tmp/pdf-pipeline-runtime`; SHA-256 giữ trong `model-manifest.json`.

Phiên bản đã chạy: Python 3.13.3, paddleocr 3.7.0, paddlex 3.7.2, paddlepaddle CPU 3.3.1. Môi trường thực tế có bản `requirements-installed.txt`; config và hash trọng số được giữ cùng kết quả.

## 4. Điều đã học từ lỗi thật

- Full-page VLM đọc `0,025` thành `0, 0.25` trong đề Câu 151, đồng thời có lỗi dấu tiếng Việt.
- Full-page VLM và FormulaNet S có chỗ đọc Latin `v` thành Greek `nu` ở Câu 152.
- FormulaNet S đọc đúng hệ số trong control crop nhưng mất dấu đạo hàm ở một vùng khác, và đổi điều kiện nghiêm ngặt `v>6` thành `nu>=6`.
- FormulaNet M giữ đúng nội dung toán của cả bốn control crop đã đối chiếu: hệ số, hai dòng đạo hàm G, và dòng đạo hàm E kèm miền `v>6`. Đây là kiểm tra phiên âm từ nguồn, không phải duyệt học thuật toàn bài.

Bộ phát hiện bất đồng ban đầu tạo 43 finding. Sau khi đọc lại 42 vùng công thức bằng M, 24 vùng không còn kích hoạt những quy tắc đó; 18 vùng vẫn kích hoạt ít nhất một quy tắc. **Không diễn giải thành 24 vùng đã được chứng minh đúng hoặc 18 vùng chắc chắn sai.** Các cảnh báo gồm cả trường hợp cần người đọc kiểm tra ngữ cảnh.

Kết quả và cảnh báo cũ được giữ trong bản enriched, nên tổng finding khi xem tất cả phiên bản sẽ cao hơn số vùng còn bất đồng ở lượt M. Trạng thái học thuật và khả năng chấm không được tự nâng lên sau fallback.

Cần duyệt cả nguồn: ở Câu 213, lời giải dùng phép chia theo m rồi kết luận m=0. Khi biên soạn rubric phải xét riêng trường hợp m=0, không sao chép chuỗi biến đổi ấy thành quy tắc chấm đã được kiểm chứng.

## 5. Cách xem và chạy lại

Trang review được phục vụ nội bộ tại `http://localhost:8787/review.html`; file tương ứng `.tmp/pdf-metadata-pilot-v1/review.html`. Mỗi câu có ảnh đề, đáp án, lời giải, liên kết toàn trang, chữ native, các phiên bản OCR và nhóm bước ứng viên.

Đã kiểm tra HTTP 200 và cú pháp JavaScript. Đã xem ảnh nguồn/crop của các ca trọng điểm; chưa kiểm tra tương tác trang HTML bằng browser automation.

Lệnh và giới hạn nằm ở `tools/pdf_metadata/README.md`. Các artifact chính:

- `questions.candidates.jsonl`, `questions.enriched.candidates.jsonl`.
- `report.json`, `enrichment-report.json`, `fixture-result.json`.
- `fast-hybrid/experiment.json`, `paddle-vl/experiment.json`, `formula-fallback/report.json`.
- `pages/`, `assets/`, `unassigned-blocks.jsonl` và hàng chờ OCR không gán được.

Server chỉ phục vụ authoring data trên loopback. Đáp án/lời giải trong artifact này không được dùng làm response bài tập cho học sinh. Muốn dừng server, tìm listener của port 8787, kiểm tra command line đúng `http.server` và thư mục pilot rồi dừng riêng tiến trình đó.

## 6. Quyết định sau pilot

Giữ hướng **native + layout + OCR công thức + fallback theo vùng** cho PDF digital. Bản M là ứng viên tốt hơn S trên các vùng khó vừa kiểm tra; cần tập nguồn chuẩn rộng hơn trước khi khẳng định mặc định cho mọi công thức. Full-page VLM dành cho trang scan/vùng không có native text và cần benchmark riêng.

Trước khi mở kho lớn: duyệt mẫu đại diện trên chính file này, bổ sung vùng chưa được detector nhận, kiểm tra công thức/bảng biến thiên và ghép bước theo ý nghĩa. Sau đó kiểm tra thêm PDF khác bố cục chưa dùng chỉnh quy tắc. Schema/version, adapter model và cache theo nguồn đã có nền tảng; assembler hiện chỉ được đánh giá trên dạng digital một cột của pilot.

Question/AnswerSpec/MathSpec/rubric phục vụ core là gói phát hành riêng. Bản hiện tại giữ ảnh nguồn và metadata để biên soạn; chưa import DB, chưa bật checker mới và chưa chạy dữ liệu lớn.

Nguồn kỹ thuật cho module công thức: [PaddleOCR Formula Recognition](https://www.paddleocr.ai/latest/en/version3.x/module_usage/formula_recognition.html). Các số đo trong báo cáo là kết quả cục bộ từ log/artifact, không lấy từ benchmark quảng bá.
