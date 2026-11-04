# Đo luồng PDF → sơ đồ tư duy trên dữ liệu hiện có

Ngày đo: 01/11/2026. Mã nguồn tại commit `ff0db46a1a041d0679fed4e6d139c83c5ff8d566`.

## Phạm vi và cách đo

- Đọc bảng `theory_documents` trong transaction PostgreSQL `READ ONLY`, sau đó rollback. Không ghi database, không sửa PDF hoặc sơ đồ đã phát hành.
- Database hiện có một tài liệu trong phạm vi truy vấn: `982fd340-38e4-447a-a799-a617d69d3df1`, tiêu đề lưu là “dạo hàm”, 64 trang, revision 19, trạng thái `PUBLISHED`, nhãn `ai_model=gemini`.
- Đọc lại PDF thật bằng hàm production; kiểm tra sơ đồ hiện có; dựng lại đầu vào AI bằng chính hàm production rồi dừng trước lời gọi provider. Không tạo phản hồi AI giả, không gọi Gemini, không phát sinh phí API mới.
- Đo input AI phản ánh thuật toán hiện tại trên văn bản đang lưu, không phải log chứng minh nội dung request Gemini từng chạy trong quá khứ.
- Kết quả chi tiết: [measurement.json](measurement.json). Phiếu đối chiếu còn trống để giáo viên đánh giá: [teacher_review.csv](teacher_review.csv).

## Kết quả đo

| Hạng mục | Kết quả | Ý nghĩa và giới hạn |
|---|---:|---|
| Hash PDF gốc | Khớp SHA-256 đã lưu | File dùng để đo đúng nguồn đang lưu |
| Text đọc lại so với text đã lưu | Khớp toàn bộ | Xác nhận tái lập extraction; không chứng minh ký hiệu toán đúng |
| Văn bản gốc đọc được | 96.544 ký tự; không có trang trắng text | Text có thể tồn tại nhưng bị lỗi font |
| Trang bị bộ kiểm tra font cảnh báo | 63/64 | Có dấu hiệu cần kiểm tra, không có nghĩa 63 trang đều sai |
| Ký tự thuộc vùng Unicode riêng | 9.320 | Đếm ký tự PUA; chưa ánh xạ được chắc chắn sang ký hiệu toán |
| Trang được chọn vào phần nội dung prompt | 64/64 = 100,0% | Bao phủ 100% số trang (trước: 35/64 = 54,69%) |
| Văn bản phần nội dung được chọn | 62.911/76.125 ký tự sau làm sạch = 82,64% | Phân bổ ngân sách đều, không bỏ trang (trước: 53,37%) |
| Số node của sơ đồ hiện có | 113 | 1 ROOT, 6 SECTION, 66 CONCEPT, 5 FORMULA, 33 EXAMPLE, 2 NOTE |
| Schema/cấu trúc/cổng xuất bản | Không phát hiện lỗi qua validator hiện tại | Đã bổ sung lineage `block_id`, `bounding_box`, `origin` |
| Mã dạng bài phát hiện trong nguồn | 33 | Inventory tự động dựa vào tiêu đề `Dạng X.Y`, không phải bộ nhãn học thuật độc lập |
| Mã dạng bài có trên sơ đồ | 33/33 = 100% | Không thiếu/thừa mã được inventory phát hiện; chưa kiểm tra đủ kiến thức bên trong |
| Trích dẫn node tồn tại đúng trang | 113/113 = 100% | Đã loại bỏ hoàn toàn cơ chế lấy `lines[0]` làm quote giả |
| Bản ghi bước hướng dẫn | 242 | Đã loại bỏ `CURRICULUM_DATA` bịa đặt phương pháp giải tích |
| Bản ghi bước có trích dẫn riêng | 0/242 = 0% | Chưa có evidence ở mức từng bước; không được hiểu là tất cả bước đều sai |
| Trường LaTeX render được bằng KaTeX | 254/254 = 100% | Kiểm tra cú pháp, không kiểm tra công thức đúng; các trường có thể trùng biểu thức |
| Sổ tay từ nguồn | 39 mục, 257 vùng nội dung | 33 METHOD, 96 STEP, 79 EXAMPLE, 16 THEORY, 18 NOTE, 15 CONTINUATION |
| Mẫu render vùng ảnh | 3/3 tạo PNG hợp lệ | Đo mẫu đầu/giữa/cuối, chưa duyệt chính xác ranh giới cắt của 257 vùng |
| Bản nháp cục bộ | 83 node, hai lần cho cùng nội dung | Tái lập xác định trên tài liệu này |

Đo thời gian một lượt trên máy hiện tại: đọc text PDF khoảng 5,3-5,6 giây; lập chỉ mục sổ tay 0,5-0,7 giây; render ba thẻ khoảng 0,06–0,11 giây/thẻ. Đây là số đo đơn lẻ, chưa phải latency trung bình/P95 và chưa bao gồm Gemini/network.

Các trang bị bỏ sót trong prompt: **0 trang** (Toàn bộ 64/64 trang đều được cung cấp cho prompt).

## Kiểm thử thực sự đã chạy

```powershell
cd D:\CoachLearning\backend
.\.venv\Scripts\python.exe -m pytest tests/theory_maps -q
```

Kết quả: **37 passed, 1 warning in 22.93s**. Warning là deprecation của Starlette/AnyIO. Cả 4 test mới về bao phủ 100% trang, phân loại trạng thái trang, lineage sơ đồ, và chống bịa đặt dữ liệu đều đạt chuẩn.

Đã chạy audit offline bằng:

```powershell
cd D:\CoachLearning\backend
.\.venv\Scripts\python.exe ..\.tmp\theory-measurement-20261101\audit.py
```

Script audit và snapshot trung gian nằm trong `.tmp/theory-measurement-20261101/`; kết quả JSON không chứa key API hoặc mật khẩu. Lần chạy hoàn tất cuối cùng không có lỗi thực thi.

## Chưa có cơ sở tính phần trăm chính xác học thuật

Chưa đo được precision/recall nội dung độc lập, độ đúng công thức và điều kiện áp dụng, tỷ lệ nội dung bổ sung không có căn cứ, độ đúng ranh giới crop toàn bộ PDF, thời gian giáo viên sửa, hoặc nhãn chồng lấn trên trình duyệt. Chưa chạy benchmark OCR chữ viết tay/chấm từng bước trong đợt đo này.

`reviewed=true` ở 113 node là trạng thái dữ liệu, không phải bằng chứng một hội đồng đã đánh giá độc lập. Không dùng confidence AI, số test PASS hay độ bao phủ mã dạng bài để thay thế độ chính xác kiến thức.

## Đối chiếu tiếp theo

1. Giáo viên đánh dấu phiếu `teacher_review.csv` cho 113 node: nội dung đúng, nhánh cha đúng, công thức đúng và nguồn có hỗ trợ nội dung. Để trống khi chưa đánh giá; không tự điền nhãn giả.
2. Bổ sung danh sách kiến thức bắt buộc từ PDF, gồm định nghĩa, định lý, điều kiện, công thức, ví dụ và phương pháp. Phiếu các node hiện có chỉ đủ tính precision; muốn tính recall phải có inventory kiến thức nguồn độc lập để tìm cả mục bị bỏ sót.
3. So sánh kết quả sau cải tiến trên cùng tài liệu, sau đó dùng PDF khác chưa tham gia tinh chỉnh. Một PDF chưa đủ để khái quát độ chính xác cả chương trình.

Ưu tiên kỹ thuật từ số đo hiện có: xử lý font/toán trước khi tóm tắt; đọc theo từng mục thay vì bỏ trang; bắt buộc lineage cho từng bước; tách nội dung trích từ PDF với nội dung bổ sung.
