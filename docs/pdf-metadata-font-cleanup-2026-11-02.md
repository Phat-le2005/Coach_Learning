# Sửa mã font trong file metadata biên soạn

Ngày 02/11/2026. Phạm vi: file xuất 20 bài, không sửa PDF, đầu ra OCR hay lịch sử review.

## Nguyên nhân

File v1 nhúng nguyên `reference_solution.step_candidates[*].text_raw` từ PDF. Trong dữ liệu này có 927 ký tự private-use từ font toán, không có ký tự thay thế U+FFFD. Ví dụ U+F03D của SymbolMT là dấu bằng và U+F0A2 là dấu prime. Vì những mã này không có cách hiển thị thống nhất bằng font văn bản thông thường, người xem thấy ô vuông/dấu hỏi dù dấu tiếng Việt vẫn là UTF-8 đúng.

Đó là lỗi ở ranh giới xuất: chứng cứ raw chưa được tách khỏi bản biên soạn. Mở JSONL với mỗi bài một dòng cũng làm nội dung khó đọc, nhưng không phải nguyên nhân tạo ra ký tự font riêng.

## Đã sửa

- Export chuyển sang `assessment-authoring/v2`; không nhúng `text_raw` của step vào bản biên soạn.
- Đổi ký tự theo font ghi trên glyph. Bảng Adobe Symbol được tái sử dụng từ codec pypdf hiện có, giữ thông báo bản quyền Unicode. Không áp cùng bảng cho MT-Extra hoặc font chưa xác định.
- Chuẩn hóa 920 glyph Symbol; 7 glyph thuộc font khác được ghi bằng nhãn U+... cần kiểm tra, không tự đoán thành dấu prime/tập số.
- Những mảnh ngoặc lớn có ký tự Unicode tương ứng được giữ thành mảnh ngoặc, kèm cảnh báo cần ảnh nguồn; không suy thành cấu trúc phương trình.
- Bước giải có `text_candidate` để đối chiếu, `latex_candidates` tách riêng và `raw_reference` để truy lại nguyên bản. Các ứng viên LaTeX vẫn chưa được duyệt.
- Bản JSONL chính và JSON trình bày lại không còn private-use/U+FFFD. Export từ chối nếu ký tự như vậy còn lọt vào trường do người biên soạn nhập.
- Không tự bật điểm/chấm: `math_expression`, checker, rubric vẫn chưa được gán; `publishable=false`.

## File để sử dụng

Trong `.tmp/pdf-metadata-pilot-v1/exports`:

| File | Mục đích |
| --- | --- |
| `pilot20.authoring.jsonl` | Dữ liệu v2 cho công đoạn xử lý tiếp |
| `pilot20.authoring.pretty.json` | Cùng dữ liệu, xuống dòng/thụt lề để đọc |
| `pilot20.readable.md` | Báo cáo câu hỏi, đáp án và các đoạn/LaTeX ứng viên |
| `pilot20.raw-evidence.jsonl` | Chứng cứ raw nguyên gốc; không dùng để chấm |

Trang review có liên kết **JSON dễ đọc**. Mở lại file hoặc tải lại trang nếu đang xem bản v1 đã nạp trước đó.

## Giới hạn còn lại

Đổi mã font không khôi phục phân số, số mũ, chỉ số hay bố cục bảng đã mất trong native extraction. `text_candidate` được ghi rõ `NORMALIZED_NATIVE_TEXT_LOSSY`. Dùng ảnh nguồn và LaTeX ứng viên để biên soạn/duyệt tiếp; không coi việc hết ô vuông là bằng chứng công thức toán đã đúng.

42 kiểm thử qua, gồm mapping theo font, không nhầm MT-Extra thành Symbol, ngoặc assembly, giữ nguyên raw evidence, và kiểm tra export v2 không chứa mã font lỗi.
