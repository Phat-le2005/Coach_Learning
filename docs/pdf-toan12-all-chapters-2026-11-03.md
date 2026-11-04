# Toán 12: tổng hợp câu hỏi có lời giải trên toàn bộ ZIP

Nguồn: `data/Toan12.zip`, SHA-256
`4ebd40c425c242baa4faf4160f112e9696942294433269cec11584d969951e25`.
Đã xử lý đủ 13 PDF, 3.478 trang; không chỉ tài liệu xác suất của lượt thử trước.
Tất cả nguồn gốc, cache OCR và đầu ra vẫn nằm trên E. Không gọi API suy luận.

| Nhóm kiến thức | PDF nguồn | Trang nguồn | Mục đề–lời giải được chọn |
| --- | ---: | ---: | ---: |
| Ứng dụng đạo hàm và đồ thị | 4 | 1.535 | 1.448 |
| Nguyên hàm, tích phân và ứng dụng | 4 | 1.381 | 1.691 |
| Thống kê số liệu ghép nhóm | 3 | 350 | 274 |
| Xác suất có điều kiện | 2 | 212 | 282 |
| Tổng | 13 | 3.478 | 3.695 |

Số mục là **lượt xuất hiện trong nguồn**, chưa khử trùng nội dung giữa các sách.
Generation: `8f49ef4f9bbadb63b849b2ab`. ID theo số in và thứ tự xuất hiện cần
được dùng cùng generation; thay đổi bộ nhận dạng có thể đổi thứ tự này.

## Đầu ra

Thư mục:
`E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-jobs\4ebd40c425c242baa4faf416\corpus`.

- `Toan12_Cau_hoi_co_loi_giai.pdf`: một quyển chung, chia bốn chương, có mục lục
  bấm được và bookmark từng mục. Ảnh nguồn giữ công thức/biểu đồ in trong sách; PDF dùng JPEG chất lượng 94, còn metadata và bộ xem giữ PNG nguồn.
- `cau-hoi-co-loi-giai.metadata.jsonl`: metadata cuối, có ánh xạ trang và bbox
  trên PDF tổng hợp; `source` của từng mục vẫn là PDF gốc, không phải ZIP.
- `cau-hoi-co-loi-giai.metadata.json`: bản JSON có danh mục nguồn, chương, ảnh,
  hash và toàn bộ mục. `questions.metadata.*` là bản trước bước dàn trang PDF.
- `index.html`: xem theo chương, tìm trong đầu đề, phân trang và tải ảnh khi mở câu.
- `review-queue.jsonl`: 4.831 lượt chưa được đưa vào bộ có lời giải. Một lượt có
  thể có nhiều lý do; không được cộng số lần xuất hiện từng lý do để suy ra số câu.
- `page-review-queue.jsonl`: 1.285 trang chưa có vùng đề–lời giải được chọn. Bao
  gồm cả bìa, lý thuyết và trang chỉ có đề; đây không phải 1.285 trang bị lỗi OCR.

Một PDF 47 trang chỉ tìm được phần đề trong phạm vi nhận dạng hiện tại nên không
đóng góp cặp vào bản tổng hợp; nguồn và các mục chưa ghép vẫn có trong báo cáo.
Không tự tạo lời giải để lấp chỗ thiếu.

## Luồng xử lý

1. Kiểm kê/hash mọi PDF trong ZIP; không sửa hoặc di chuyển dữ liệu raw.
2. Đọc text và tọa độ bằng PDFium, lưu ảnh trang riêng, kiểm tra hash khi chạy tiếp.
3. Trang thiếu text dùng OCR local. Đã có 60 trang OCR trong cache, gồm đủ 46 trang
   ảnh ở tài liệu thống kê. Lượt ghép cuối dùng lại cache nên số gọi OCR mới là 0.
4. Nhận dạng đầu câu `Câu`, `Bài`, `Ví dụ`, cả nhãn có ký hiệu trang trí `»`/PUA;
   ghép theo thứ tự vật lý, qua trang và cột. Không nối hai câu chỉ vì cùng số in.
5. Chỉ chọn mục có đề và nội dung lời giải. Loại 134 mục có nhãn “Lời giải” nhưng
   chỉ là dòng chấm cho học sinh viết. Cắt phần mở đầu bài/dạng tiếp theo ra khỏi
   lời giải trước, giữ quyết định và các block bị tách trong audit.
6. Gộp đủ mọi nguồn, xuất ảnh, JSON/JSONL, bộ xem và PDF. Lỗi một nguồn chặn xuất
   chung; không âm thầm bỏ nguồn đó. Vùng cột không chắc chắn vào hàng đợi.

## Chạy lại hoặc dùng PDF khác

Entry: `tools/pdf_metadata/collect_solved.ps1`; xem hướng dẫn trong
`tools/pdf_metadata/README.md`. Dùng lại `-Work` để chạy tiếp từ checkpoint.
Nếu đã có `profile.json`, bỏ `-InputPath` để không giải nén lại.
PDF chưa xác định được chương phải truyền `-Chapter`; hiện có bốn nhóm nêu trên.
Đổi nguồn phải dùng thư mục work khác.

`controller.json` ở `.tmp/pdf-solved-corpus-20261103` ghi tiến trình; log và báo cáo
từng nguồn nằm trong `documents/<source_sha256[:24]>/`. Worker xử lý tuần tự,
ưu tiên BelowNormal; OCR CPU ba luồng. Không khởi chạy song song 13 model.

## Phạm vi chất lượng

341 kiểm thử đã qua, gồm ca đầu câu có trang trí, phân cột, giữ tọa độ nguồn,
loại ô lời giải trống, tách lý thuyết, kiểm tra cache và workflow chạy tiếp.
Kiểm tra PDF và giao diện được lưu riêng trong thư mục QA của lần chạy này.

Đây là **bộ dữ liệu có nguồn ở trạng thái nháp**, chưa phải kết quả chấm tự động.
Text hỗ trợ có thể sai ký hiệu; ảnh nguồn là bằng chứng đối chiếu. Tám mục có phần đề, đáp án hoặc lời giải phụ thuộc OCR được giữ ở hàng đợi để đối chiếu ranh giới; không tính vào 3.695 mục xuất cuối. Chưa đo độ bao
phủ đầy đủ mọi câu, chưa xác minh tính đúng của toán và chưa có rubric/checker
cho từng bước. `academic_review=PENDING`, `grading_support=NOT_ASSESSED`,
`publishable=false` được giữ nguyên. Bước tiếp theo cho core là chuẩn hóa lời giải
thành các bước và kiểm tra biểu thức, điều kiện, đáp án trên từng loại bài.
