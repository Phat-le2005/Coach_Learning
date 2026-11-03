# Thử nghiệm chuẩn hóa nội dung 100 bản ghi Toán 12

Đợt này đánh giá lớp đọc nội dung trước khi mở rộng toàn corpus hoặc tách bước
cho core chấm. Chạy hoàn toàn local, không gọi API cloud, không tải model mới,
không ghi đè corpus nguồn và không thay đổi trạng thái duyệt học thuật.

## Mẫu và đầu ra

- 100 bản ghi nguồn: 25 mỗi chương, lấy luân phiên từ cả 12 PDF có câu kèm lời giải.
- 40 bản ghi đánh giá được cố định trước inference: 10 mỗi chương, phủ 12 PDF.
- Đây là mẫu chẩn đoán cân bằng, không phải ước lượng accuracy theo phân bố corpus.
- Có 99 bản nháp qua luồng trích nội dung và 1 bản ghi chỉ giữ ảnh vì model trả
  đầu ra không hợp lệ. Câu lỗi vẫn nằm trong bộ đánh giá; không loại để làm đẹp số.

Thư mục đầu ra:

`.tmp/pdf-jobs/4ebd40c425c242baa4faf416/transcription-100-20261103/`

File dễ đọc là `content.draft.pretty.json` hoặc `content.draft.jsonl`: đề bài,
lựa chọn, lời giải, đáp án riêng, nguồn, ảnh và cảnh báo. Không có text thô lỗi
font trong phần này. Tiền tố trang trí của nhãn câu được bỏ ở bản đọc; nhãn thô
và text gốc vẫn giữ trong `metadata.transcribed.draft.jsonl` và `records/`.

Giữ thư mục `assets/` cùng dữ liệu vì Markdown tham chiếu ảnh bằng đường dẫn
tương đối. `review.html` có ảnh nguồn cạnh bản đọc, tab công thức/JSON, lọc chương,
bộ đánh giá và bản tải nội dung. Mỗi câu giữ ID/hash PDF, trang, bbox, hash ảnh,
cách đọc native và ứng viên model để truy nguyên.

## Luồng xử lý

1. Cố định mẫu/seed và kiểm hash corpus/PDF gốc.
2. Mở lại trang gốc bằng pdfplumber có tên font và tọa độ glyph thật.
3. Tìm phương trình, tích phân, biểu thức inline và phân số số học theo glyph/vector.
4. Dùng native ở bố cục đơn giản không mơ hồ. Các vùng phức tạp đọc bằng
   PP-FormulaNet_plus-M và S local, so ký hiệu, số/dấu và cấu trúc nguồn.
5. Kiểm cú pháp bằng KaTeX local. Vùng chưa đủ kiểm tra giữ ảnh, không tự đoán
   hoặc sửa phương án nhiễu.
6. Ghép bản nháp Markdown, lựa chọn A–D và lời giải theo nguồn. Nhóm lựa chọn
   lặp được giữ inline thay vì gộp thành một bộ đáp án.
7. Qwen3-VL-2B local rà soát metadata của 40 bản ghi. Luồng này không cung cấp
   ảnh cho Qwen, không có quyền tự duyệt hay chấm điểm.
8. Xuất các file nội dung/kỹ thuật, kiểm schema, hash ảnh, tham chiếu và các
   đẳng thức số được hỗ trợ trong lời giải.

## Kết quả thực chạy

| Kiểm tra | Kết quả |
|---|---:|
| Bản ghi được giữ trong đầu ra | 100/100 |
| Vùng được đề xuất là công thức | 1.752 |
| Vùng hiển thị LaTeX sau kiểm tra kỹ thuật | 1.044 |
| Vùng dùng ảnh thay vì LaTeX chưa đủ kiểm tra | 708 |
| Ứng viên primary qua cú pháp / không qua | 1.704 / 48 |
| Vùng hai model đọc khác nhau | 631 |
| Vùng có khác biệt tập chữ số so với glyph nguồn | 234 |
| Qwen hoàn tất phản hồi hợp lệ | 40/40 |
| Qwen chưa đủ đầu vào để kết luận / có vấn đề | 38 / 2 |
| Đẳng thức số: qua / cần đối chiếu lại | 4 / 4 |
| Ảnh tham chiếu đã kiểm hash | 2.013 |
| Lỗi schema / lỗi hash ảnh | 0 / 0 |

Các số cảnh báo có thể chồng lấp, không cộng thành tổng lỗi. Hai model khác nhau
hoặc thay tập chữ số không tự chứng minh công thức sai: có thể là thay cách viết,
thiếu vùng, thay bố cục hoặc lỗi nhận dạng. Tương tự, render được và model đồng ý
không chứng minh đọc đúng ảnh hay lời giải đúng toán.

Qwen có 2 phản hồi đầu tiên tự mâu thuẫn verdict/issues; validator từ chối. Đã
retry với hướng dẫn nhất quán schema, giữ bản thất bại trong lịch sử; sau đó cả
40 phản hồi hợp lệ. 38 phản hồi `INSUFFICIENT_INPUT` phản ánh giới hạn của bản
metadata còn có ảnh thay công thức và việc không đưa ảnh vào Qwen, không có nghĩa
là 38 PDF nguồn không có lời giải.

Mục 3365 bị lỗi `INVALID_FORMULA_MODEL_OUTPUT`. Vùng đưa vào FormulaNet là một
cột bảng gồm nhiều hàng, chưa được phân loại đúng thành bảng. Bản ghi được giữ
với `SOURCE_IMAGE_ONLY_EXTRACTION_FAILED`, `math_transcription_completed=false`
và ảnh gốc. Không tính đây là một câu đã khôi phục LaTeX thành công. Số inference
của lần lỗi không được khẳng định là đã thống kê đầy đủ.

## Vận hành và kiểm chứng

- Hai worker OCR, ba luồng CPU mỗi worker, BelowNormal; giữ model trong bộ nhớ.
- Thời gian đợt trích: khoảng 41,2 phút. Peak cây tiến trình trích khoảng 3,37 GiB;
  Qwen chạy riêng, peak khoảng 6,84 GiB. Máy còn nhiều RAM; inference CPU là phần nặng.
- Windows có lần khóa file `report.json` khi đọc/đổi tên. Workers vẫn hoàn tất;
  monitor đã khôi phục xuất đủ dữ liệu. Đã sửa ghi file bằng temporary riêng cho
  mỗi writer và retry khóa đọc ngắn; kiểm thử khóa/concurrent writers đều qua.
- Đã thử resume một bản ghi thật: dùng lại checkpoint, không inference, bytes không đổi.
- Đã thử lại rescue: không inference và không đổi bản ghi ảnh đã giữ.
- Bộ test PDF có 380 test qua; kiểm tra tập trung sau chỉnh trình bày cũng qua.
- Browser QA: 100 bản ghi, 4 chương, 40 bản đánh giá, render 1.044 LaTeX hiển thị,
  tải JSON nội dung, thấy rõ câu chỉ giữ ảnh, không tràn ngang ở mobile.
- Corpus gốc và ba module đã đóng băng trước đây giữ nguyên hash. Extractor của
  đợt 100 bản ghi giữ nguyên sau khi cố định mẫu; thay đổi sau chạy chỉ ở audit,
  trình bày, retry advisory và cơ chế giữ ảnh khi lỗi.
- Model Qwen do đợt này khởi động đã được dừng sau khi hoàn tất. Viewer 8789 vẫn hoạt động.

QA chi tiết nằm tại `.tmp/pdf-transcript-dev-20261103/`. Báo cáo sử dụng tiếp:
`quality-summary.json`, `evaluation-40.json`, `reference-checks.jsonl`,
`schema-errors.json`, `asset-errors.json`, `selection.json` và `reviews/`.

## Kết luận sử dụng

Chưa đủ điều kiện đưa bản nháp vào core chấm hoặc chạy toàn corpus với giả định
nội dung đã sạch. Mọi bản ghi vẫn `PENDING`, `NOT_ASSESSED`, `publishable=false`.
Chưa đo complete formula recall, accuracy với toàn bộ gold transcription hay độ
đúng toán của toàn lời giải.

Ưu tiên tiếp theo là tách bảng/hình khỏi công thức trước FormulaNet, cải thiện
vùng công thức nhiều dòng và ký hiệu trên/dưới, rồi dùng ảnh nguồn cho lượt review
những vùng còn nghi vấn. Cũng cần kiểm tra việc dính nội dung lý thuyết tiếp theo
vào lời giải (ví dụ mục 3190). Chỉ sau khi lớp nội dung ổn mới tách step cho core.
