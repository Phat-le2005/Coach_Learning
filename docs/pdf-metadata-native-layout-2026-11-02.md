# Phục hồi công thức native và cấu trúc bảng dấu

Kết quả dưới đây là lượt thử baseline trước. Xem [phân số và bảng biến thiên](pdf-metadata-fractions-variation-2026-11-02.md) cho cải tiến tiếp theo, phạm vi 11 bảng và các trường hợp chưa hỗ trợ.

Tiếp tục sau đợt push đúng 12 commit lên `origin/main`, từ `7c83355` đến `cdb9296`. Đợt push gồm 70 file nguồn/test/tài liệu, khoảng 0,5 MB; không chứa PDF/ZIP, model, `.env` hoặc kết quả local. Phần cải tiến mô tả dưới đây được làm tiếp trong checkout ở E, chưa nằm trong 12 commit đó.

## Những gì đã chạy

PDF thử vẫn là bản 57 trang, 120 câu, hash `5db1fc66ab0a42553e882981d1b22935967295b9a73cd2c96840e6ee5dd76927`. Dùng extraction native/OCR có sẵn từ đúng bản này, không sửa raw PDF hoặc các bản đọc OCR cũ.

1. Đọc vị trí và cỡ chữ của từng glyph. Số nhỏ nằm cao hơn baseline mới được đề xuất là số mũ; không đổi mọi `x2` thành `x²`. Lưu chỉ số glyph, bbox, cỡ chữ và baseline làm bằng chứng.
2. Chỉ nhận công thức trên một baseline. Bỏ qua phân thức xếp tầng, ký tự dưới, font chưa rõ hoặc đường phân số sát bên; không tự bỏ phần phân thức để lấy một biểu thức dễ parse hơn.
3. Kiểm đồng nhất đạo hàm cho các cách đọc được hỗ trợ. Bản OCR mất dấu prime trong cùng một nhóm công thức không được dùng như hàm gốc của bản đọc còn prime.
4. Nhận thêm tiêu đề “Có bảng xét dấu”, “Ta có bảng biến thiên”. Thuật toán tách bước lên `layout-reasoning/v2`; schema vẫn đọc được v1. Các bản đề xuất cũ được giữ nguyên, bản mới được tính trong output thử riêng.
5. Render vùng bảng từ PDF ở 240 DPI. Chỉ nhận dạng bảng raster hai hàng có một đường phân hàng và một đường phân cột. OCR đọc nhãn và mốc số; dấu cộng/trừ được kiểm trực tiếp từ nét ảnh, ở nhiều ngưỡng đậm nhạt. Không dùng đạo hàm để điền dấu mà ảnh không cho thấy.
6. Với biểu thức hữu tỉ không có tham số, kiểm mốc/interval bằng đại số, kiểm không có nghiệm hoặc cực trong khoảng trước khi kết luận dấu. Giữ cả mẫu số trước rút gọn để không quên điểm loại trừ.

Không có nhánh theo số câu hay giá trị đáp án trong thuật toán. Số câu trong lệnh chạy chỉ là bộ chọn mẫu có giới hạn.

## Số đo trên pilot

| Hạng mục | Trước | Sau cải tiến |
|---|---:|---:|
| Câu được audit | 120 | 120 |
| Câu có phép kiểm đạo hàm được hỗ trợ | 3 | 6 |
| Nhóm công thức đủ điều kiện chọn ứng viên theo parser | 23 | 76 |
| Công thức ứng viên mới từ glyph PDF | 0 | 85 |
| Bước đề xuất | 371 | 372 |

Sau cải tiến có 11 phép đồng nhất PASS trên 6 câu (151, 152, 154, 176, 221, 225) và 47 phép NOT_ASSESSED. Nhiều phép dùng các bản đọc khác nhau của cùng công thức nên không đồng nhất số phép với số câu. **Không có câu nào tự được duyệt học thuật hoặc sẵn sàng chấm.**

Tăng độ phủ parser không phải tăng độ chính xác đã được đo. Vẫn còn 114/120 câu chưa có phép kiểm đạo hàm được hỗ trợ, 87 câu chứa nhóm công thức chưa hỗ trợ/mơ hồ và 14 bước có bảng cần cấu trúc hóa. Cờ audit toàn file giữ nguyên ngay cả khi một bảng mẫu đã được cấu trúc ở sidecar riêng.

Ví dụ câu 154: glyph số 2 có cỡ khoảng 6,94 pt, cao hơn baseline 12 pt. Phục hồi `P=12I−0,5I^{2}`, đối chiếu `P'=12−I` cho PASS. Đây là kiểm công thức ứng viên, không phải xác nhận toàn bài.

## Ba bảng được thử riêng

| Câu | Kết quả |
|---|---|
| 151 | Bảng biến thiên nhiều hàng, vùng gạch chéo và mũi tên: giữ `NEEDS_LAYOUT_REVIEW`; không gửi cả bảng vào recognizer công thức trong luồng mới. |
| 154 | Có mốc không phải số hữu hạn và cách đọc OCR không đủ rõ: giữ `NEEDS_LAYOUT_REVIEW`, không tự thay bằng mốc mong đợi từ đáp án. |
| 161 | Tách được mốc `0,10,20`, dấu `+` trên `(0,10)`, dấu `−` trên `(10,20)`, và giá trị `0` tại `10`. |

Hai bản OCR của công thức đạo hàm câu 161 cùng cho kết quả đại số khớp hai khoảng và mốc. Scope là `CONDITIONAL_ON_TRANSCRIPTION_NOT_SOURCE_OR_ANSWER_APPROVAL`: chưa chứng minh công thức đó chính là đạo hàm của hàm đề bài và chưa xác nhận đáp án cuối.

**Đính chính:** ảnh xem trước 120 DPI làm nét dọc rất mảnh của dấu cộng ở câu 161 khó nhìn. Ghi chú cũ “bảng có hai dấu âm” đã được rút lại trong báo cáo thử compact. Crop 240 DPI và kiểm nét cho thấy bảng `+ 0 −`. Không dùng nhận xét cũ làm nhãn lỗi nguồn hay làm dữ liệu huấn luyện.

Thử nghiệm chẩn đoán gửi nguyên bảng 151 vào FormulaNet-M trước đó mất khoảng 103 giây và tạo chuỗi LaTeX array lặp, không dùng được. Raw probe được giữ riêng trong `table-probe`, không được nhận thành bảng. Luồng mới kiểm bố cục trước, chỉ OCR các ô nhỏ khi hình dạng được hỗ trợ.

## Cách chạy và output

```powershell
cd E:\HocTap\Hackathon-SGU2026\Coach_Learning
.\tools\pdf_metadata\run.ps1 -Action layout-refine -Questions '151,154,161' -Limit 3
```

Không cần khởi động Qwen. Dùng FormulaNet-M đã có trên E, CPU 3 threads, một model; không có API cloud hoặc download model mới. Suy luận kết thúc thì process Python thoát, giải phóng bộ nhớ model. Cache ô có hash ảnh, weights, phiên bản package và adapter. Cùng vùng ảnh có thể đọc lại cache; provenance trang/câu vẫn được ghi theo PDF hiện tại.

Đầu ra:

`E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-metadata-pilot-v1\layout-trial-v1\`

- `review.html`: bảng có cấu trúc cạnh ảnh nguồn rõ hơn, công thức từ glyph và bằng chứng số mũ.
- `layout-report.json`: phạm vi, package/weights, số lượt OCR và các hạn chế.
- `tables.jsonl` / `tables.pretty.json`: bảng ứng viên, bbox, mốc, dấu, kiểm tra đại số hoặc lý do chưa hỗ trợ.
- `questions.math-audit.jsonl` / bản pretty: audit mới của 120 câu.
- `cell-ocr/`: raw OCR từng crop, cache và thời gian; không đưa vào Git.

Viewer đang có tại [bản cải tiến](http://127.0.0.1:8787/layout-trial-v1/review.html). Kiểm HTTP/ảnh và unit tests tách biệt với việc nhìn giao diện browser; chưa có xác nhận trực tiếp toàn UI.

Snapshot đầu/cuối mỗi lượt kiểm 121 file nguồn, không có file thay đổi. Bộ kiểm tham chiếu 62 file pilot gốc cũng được giữ nguyên. Không ghi vào database production và không chạy kho 3.478 trang.

Lượt với cache mới theo phiên bản package dùng 7 lượt OCR ô nhỏ, 25,394 giây cho toàn bước audit/render/nhận dạng. Đây là số đo trên ba câu được chọn, không suy tốc độ cả kho. Bộ công cụ PDF hiện có 119 tests qua; các ca mới kiểm số mũ thật/giả, phân số bị cắt, nét cộng mảnh, miền bị loại trước rút gọn, khoảng có nghiệm chưa tách và việc giữ nguyên dấu nguồn khi công thức không khớp.

## Giới hạn tiếp theo

Chưa hỗ trợ cấu trúc hóa toàn bộ bảng nhiều hàng, mũi tên, mốc vô cực, miền tham số hoặc phân thức native nhiều tầng. Không tự bỏ qua các phần này để tăng tỷ lệ PASS. Cần mở rộng bộ kiểm theo cấu trúc, giữ ảnh nguồn đủ rõ và đánh giá riêng câu chưa dùng điều chỉnh thuật toán trước khi chạy batch nhiều PDF.
