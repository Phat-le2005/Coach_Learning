# Thử tách bước lời giải — 02/11/2026

## Vấn đề và thay đổi

Ở Câu 152, bộ trích xuất cũ chia lời giải thành ba nhóm: mô hình vận tốc/thời gian/năng lượng, đạo hàm/tìm nghiệm, bảng biến thiên/kết luận. Một tử số còn bị xếp sang nhóm trước do thứ tự dòng PDF. Đây là nhóm trích đoạn, chưa phải bước suy luận.

Stage `pdfmeta.step_segmentation` tạo đề xuất riêng từ native blocks và OCR đã lưu. Không chạy lại model, không gọi API suy luận, không sửa PDF/JSON trích xuất gốc, không sửa lịch sử duyệt, không ghi database. Tất cả file vẫn ở ổ E. Không thay thế `pilot20.authoring.jsonl`: bộ bước mới có schema và file riêng để kiểm thử trước khi đổi hợp đồng downstream.

## Cách xử lý

1. Lấy đúng block của vùng lời giải, đổi font bằng bằng chứng glyph/font.
2. Gắn tử/mẫu ngắn vào dòng cơ sở theo giao nhau vị trí, thay vì chỉ đọc từ trên xuống. Trường hợp gắn theo khoảng cách mà không có giao nhau được cảnh báo.
3. Dùng dấu chuyển ý để đề xuất ranh giới; tách hai ý đạo hàm/tìm nghiệm khi có dấu `;` hoặc `.` rõ ràng ở ngoài ngoặc. Không tách dấu `;` trong khoảng hoặc nhận hệ số `0,003` thành phương trình bằng 0.
4. Tách tương ứng công thức OCR, giữ cả các bản nhận dạng khác nhau và nguồn model. Xếp bản M trước để đối chiếu, không coi bản M tự động đúng.
5. Giữ vùng bảng bằng ảnh, kể cả phần không có chữ ở đầu trang tiếp theo. Tách kết luận khỏi bảng; không tự diễn giải dấu trong bảng.
6. Kiểm tra từng đoạn ký tự chuẩn hóa được giữ đúng một lần, thứ tự bước liên tục, vùng ảnh nằm trong lời giải của câu. Hai bước tách trên cùng dòng có thể dùng chung ảnh, có nhãn rõ.

Mỗi bước có loại ứng viên, tiêu đề, chữ nguồn còn mất bố cục toán, công thức OCR ứng viên, điều kiện thấy trong nguồn, source spans, text slices, vùng ảnh và liên kết thứ tự với bước trước. Liên kết này chưa phải quan hệ phụ thuộc logic đã chứng minh. `math_expression`, `checker`, `rubric_weight` vẫn null. Dạng `MODEL_SETUP` không tự mở rộng tập loại rubric của core hiện tại.

## Kết quả thử trên pilot

- Nguồn: PDF 57 trang, SHA-256 `5db1fc66ab0a42553e882981d1b22935967295b9a73cd2c96840e6ee5dd76927`.
- Chạy toàn bộ 120 câu đã trích xuất: 367 nhóm cũ → 371 bước đề xuất. Đây là số lượng, không phải chứng cứ chất lượng tăng.
- Kiểm tra cấu trúc nguồn PASS cho 120 câu; không mất/lặp ký tự chuẩn hóa trong các block có sẵn. Kiểm tra này không phát hiện nội dung mà native extraction đã bỏ sót.
- Có 95 câu mang ít nhất một cờ kỹ thuật/phân loại cần kiểm tra; 44 bước chưa phân loại và 46 bước dài cần xem xét tách thêm. Tất cả 120 câu vẫn chưa được duyệt học thuật cho các bước mới.
- Câu 152: bảy bước gồm vận tốc, thời gian, hàm năng lượng, đạo hàm, nghiệm, bảng biến thiên qua hai trang, kết luận.
- Câu 151: ba nhóm → năm bước; Câu 154: ba nhóm → năm bước. Các kết quả này là kiểm tra mẫu, không phải đánh giá đủ mọi dạng bài.
- Số lần chạy model trong stage mới: 0. Thời gian xử lý cấu trúc khoảng 0,6 giây trên lần chạy thử; không bao gồm OCR/extraction đã thực hiện trước hoặc thời gian đọc ảnh của người duyệt.
- Điều kiện về dấu `c` của Câu 152 vẫn là ghi chú cần xác minh; pipeline không âm thầm thêm `c>0` như dữ kiện nguồn.
- Academic approved / grading ready / publishable: 0 / 0 / 0.
- Kiểm thử: 53 tests qua; SHA-256 của 62 file đầu vào đã chụp trước khi chạy (PDF, native pages, candidates, lịch sử review) giữ nguyên. Đã kiểm tra trực tiếp trình duyệt: mở đúng Câu 152 từ trang biên soạn, bảy bước, công thức hiển thị và ảnh bảng ở trang 2.

## Chạy và kiểm tra

```powershell
.\tools\pdf_metadata\run.ps1 -Action steps
.\tools\pdf_metadata\run.ps1 -Action test
```

Mở `http://localhost:8787/steps.html?question=152`. Dùng nút Bước 1–7 để chuyển đến từng ý; ảnh ở bên phải giữ đối chiếu nguồn, các bản OCR khác có thể mở rộng. Trang biên soạn cũ có nút `Xem các bước giải` theo câu đang chọn. Bản này chỉ đọc; nội dung biên soạn và sửa công thức tiếp tục lưu ở trang review cũ. Sau khi sửa, chạy lại `steps` để đồng bộ ứng viên.

Đầu ra: `.tmp/pdf-metadata-pilot-v1/steps/questions.steps.jsonl`, bản pretty JSON và report cùng thư mục. Schema: `tools/pdf_metadata/schemas/solution-step-proposals.v1.schema.json`.

Tests bao phủ phân số rời dòng, bảng qua trang, tách nội dòng, hệ số thập phân, dấu chấm phẩy trong khoảng, câu văn xuống dòng, bất đồng OCR, mất/lặp chữ, block thuộc câu khác, vùng crop vượt biên và cấm tự bật checker. Tests cấu trúc không thay thế kiểm tra ảnh/học thuật.

## Việc còn lại trước khi chạy kho lớn / đưa vào core

Các chuỗi suy luận dài, bất phương trình, hệ phương trình, nhiều cách giải và bố cục mới chưa được tách ngữ nghĩa đầy đủ. Cần bộ chuẩn do người duyệt đánh dấu ranh giới và loại bước trên nhiều PDF, rồi đo precision/recall ranh giới và lỗi ghép nguồn. Có thể thử thêm model local ở nhánh đề xuất cho các vùng bị gắn cờ, nhưng đầu ra vẫn phải qua cùng cổng source/schema/review. Chưa có bước tự sinh rubric hoặc tự xét tương đương toán học cho mọi dạng bài.
