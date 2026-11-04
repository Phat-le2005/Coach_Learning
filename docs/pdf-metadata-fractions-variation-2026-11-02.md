# Tiếp tục pipeline: phân số native và bảng biến thiên

Ngày 02/11/2026. Phần cải tiến tiếp theo trong checkout `E:\HocTap\Hackathon-SGU2026\Coach_Learning`, sau 12 commit đã push ở `cdb9296`. Chưa push thêm trong lượt này. PDF gốc, OCR cũ, editorial state và output thử trước đều được giữ nguyên.

**Kết luận:** đã mở rộng thuật toán và chạy thử thật trên pilot, chưa hoàn thiện pipeline để tạo dữ liệu chấm từ kho lớn. Độ phủ toán vẫn thấp; các bảng ngoài mẫu điều chỉnh còn nhiều trường hợp chưa hỗ trợ.

## Công thức: phục hồi theo nguồn hình học

Module `fraction_layout.py` lấy glyph và đường phân số từ metadata PDF, xây cây tử/mẫu có giới hạn độ sâu, rồi dựng LaTeX. Mỗi nút giữ bbox đường phân số và danh sách glyph của tử/mẫu. Ký tự không rõ quyền sở hữu hoặc nhiều baseline còn dư làm ứng viên bị từ chối; không tự bỏ chúng để tạo công thức dễ parse.

- Có kiểm tra riêng cho phân số lồng nhau, số mũ hai chữ số và mẫu số bị loại trước rút gọn. Hỗ trợ lồng được kiểm bằng ca tổng hợp; không coi đó là bằng chứng đã đọc đúng mọi phân thức nhiều tầng trong PDF này.
- Dấu `⇒`, `⇔`, dấu chấm phẩy và phần điều kiện trong baseline cắt cả các mảnh tử/mẫu tương ứng. Nếu không cắt, hai phương trình trên cùng dòng có thể bị ghép thành một tích; các ca hồi quy ngăn lỗi này.
- Với chuỗi như `R(x)=p(x)x=50x/(0,01x²+1)`, không diễn giải `p(x)` thành `p*x`. Giữ toàn chuỗi làm bằng chứng, dùng riêng đẳng thức đầu-cuối khi cần, ghi rõ `FINAL_EQUALITY_ENDPOINT_ONLY`. Phép kiểm đạo hàm không xác nhận phép thế trung gian.
- Lấy thêm các định nghĩa hàm native trong đề, giữ chúng ở `source_definitions`, không thêm thành bước lời giải. Khi lời giải đã thay biến hoặc thế một quan hệ mới, ưu tiên công thức biến đổi mới nhất. Một đường thẳng xuất hiện sau trong đề không được tự thay thế hàm số cần khảo sát chỉ vì cùng ký hiệu `y`.
- Điều kiện gốc và mẫu số được giữ riêng. PASS vẫn chỉ là đồng nhất đại số theo một cách đọc; không xác nhận điều kiện, đáp án hay việc dùng biểu thức đó làm rubric.

## Bảng: đọc cấu trúc trước, kiểm toán sau

Module `variation_table.py` nhận dạng hàng, cột, khung ngoài, vùng gạch chéo và các thành phần trong ảnh. Hỗ trợ có giới hạn:

- Bảng hai hàng chỉ có hàm và mũi tên, hoặc ba hàng có thêm đạo hàm.
- Mũi tên tăng/giảm từ nét ảnh: yêu cầu thân chéo và đầu mũi tên ở phía phải; nối khe raster tối đa một pixel, có ghi phương pháp tiền xử lý. Đường chéo đơn thuần không được coi là mũi tên.
- Mốc số hữu hạn và vô cực; giá trị hàm tại mốc hữu hạn. Vùng gạch chéo được giữ đúng vị trí, chưa tự diễn giải thành bất phương trình.
- Bỏ đường viền ngoài khỏi thành phần ký tự, phân biệt đường viền với đường chia hàng/cột bên trong.
- Với biểu thức hữu tỉ không tham số, kiểm dấu trên khoảng sau khi loại khả năng có nghiệm hoặc cực chưa ghi trong khoảng. Khoảng vô hạn dùng nghiệm thực của đa thức và điểm thử hữu hạn hợp lệ, không kiểm một vài điểm rồi suy toàn khoảng.
- Có thể kiểm bằng đạo hàm đã đọc trong lời giải hoặc đạo hàm tự tính từ hàm trong đề. Hai nguồn này có nhãn khác nhau; đạo hàm tự tính không được mô tả là bản chép đạo hàm nguồn.
- Kiểm giá trị hàm trong bảng với biểu thức ứng viên. Ví dụ bảng ghi `P(12)=72`; nếu ghi `73`, bộ kiểm báo không khớp và giữ nguyên `73` để review.

FormulaNet-M đọc ô nhỏ vẫn có thể trả ký hiệu sai. Module `table_glyphs.py` dùng font đã có trên máy để so hình dạng trong tập chữ số/dấu/vô cực, hoặc một chữ Latin cho nhãn. Không tải font/model mới. Lưu hash file font, các lựa chọn thay thế, điểm khớp và khoảng cách điểm; **các điểm này chưa được hiệu chuẩn thành xác suất đúng**. Nếu OCR và font đều đọc được số nhưng khác nhau, pipeline giữ hàng chờ. Fallback có cờ `FONT_OR_OCR_FALLBACK_REQUIRES_SOURCE_REVIEW`.

Ví dụ câu 154: OCR đọc nhãn/giá trị sai; bộ đối chiếu nét đưa ra ứng viên `I`, `P` và `72`. Chúng có bằng chứng ảnh và hash font, vẫn cần đối chiếu nguồn, không tự được duyệt dù `P(12)=72` khớp đại số.

## Kết quả chạy trên PDF 57 trang

PDF hash vẫn là `5db1fc66ab0a42553e882981d1b22935967295b9a73cd2c96840e6ee5dd76927`. Tái sử dụng native/OCR đã trích xuất từ đúng PDF, không chạy lại toàn bộ OCR.

| Chỉ số audit 120 câu | Trước lượt này | Sau lượt này |
|---|---:|---:|
| Câu có phép kiểm đạo hàm được hỗ trợ | 6 | 8 |
| Nhóm công thức chọn được ứng viên theo parser | 76 | 78 |
| Ứng viên phân số native trong lời giải | 0 | 12 |
| Định nghĩa hàm native giữ riêng từ đề | 0 | 49 |

Có 17 phép đồng nhất PASS và 46 NOT_ASSESSED trong bản audit hiện tại. Nhiều phép kiểm là các cách đọc khác nhau của cùng công thức; không coi 17 phép là 17 câu. Tám câu có phép kiểm được hỗ trợ: 151, 152, 154, 156, 161, 176, 221, 225. Còn 112/120 câu chưa có phép kiểm đạo hàm được hỗ trợ. Chưa có câu được duyệt học thuật/chấm tự động/xuất bản.

Parser hiện từ chối hàm chưa khai báo như `f(x)` ở vế phải, thay vì hiểu sai thành tích `f*x`. Vì vậy số ứng viên chọn được thấp hơn bản thử trung gian (78 thay vì 82), nhưng không mất độ phủ tám câu đã kiểm. Không nới quy tắc chỉ để tăng số PASS.

Đã thử cả 11 vùng bảng raster mà bộ chọn vùng hiện tìm được trong PDF:

| Nhóm | Câu | Kết quả |
|---|---|---|
| Ba mẫu điều chỉnh ban đầu | 151, 154, 161 | 3 bảng ứng viên có cấu trúc |
| Mở rộng trong cùng PDF | 153, 159, 163 | Câu 163 có cấu trúc; 153 và 159 còn mơ hồ |
| Năm bảng chưa dùng điều chỉnh thuật toán trước lượt thử | 157, 167, 171, 187, 224 | Cả 5 giữ hàng chờ |
| Tổng | 11 vùng | **4 bảng có cấu trúc, 7 bảng cần xử lý thêm** |

Mẫu không ngẫu nhiên và cùng nằm trong một PDF. Không suy tỷ lệ đúng hoặc khả năng áp dụng mọi PDF từ kết quả này. Một số tiêu đề bảng trong audit chưa có vùng raster để bộ chọn hiện tại nhận; bảng dựng bằng vector/native glyph hoặc nối trang chưa thuộc phạm vi nhận dạng raster này.

- Câu 151: mốc `0,20,+∞`, dấu `+ 0 −`, tăng rồi giảm, giữ vùng gạch chéo.
- Câu 154: mốc `0,12,+∞`, tăng rồi giảm, giá trị `P(12)=72`; ảnh không có hàng dấu nên UI không tự thêm hàng dấu.
- Câu 161: mốc `0,10,20`, dấu `+ 0 −`. Giữ đính chính trước đó: dấu bên trái là cộng với nét dọc mảnh, không phải dấu âm.
- Câu 163: mốc `0,2,3`, tăng rồi giảm, `f(2)=4`. Kiểm bằng đạo hàm tính từ định nghĩa hàm trong đề và kiểm giá trị tại mốc đều khớp có điều kiện theo bản đọc.

Các lỗi còn lại gồm mốc dạng `ln`, nhãn có gạch trên, chữ/số ở ảnh cũ rất nhỏ và cấu trúc nhiều cột. Pipeline không tự thay các mốc này bằng nghiệm tính từ lời giải.

## Output và tái chạy

Bản chính:

`E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-metadata-pilot-v1\layout-trial-v2\`

- `review.html`: công thức phân số, bảng ứng viên cạnh ảnh nguồn, cờ đọc chưa xác nhận.
- `questions.math-audit.jsonl` / bản pretty: audit toàn 120 câu.
- `tables.jsonl` / bản pretty: sáu bảng nhóm chính, gồm cả trường hợp bị chặn.
- `layout-report.json`, `review-queue.json`: số đo/phạm vi và hàng chờ đối chiếu.
- `cell-ocr/`: raw OCR/checkpoint từng ô, hash weights/package/adapter.

Năm bảng thử mở rộng giữ riêng tại `layout-trial-v2-holdout/`. Cả hai thư mục chỉ là output local, không phải dữ liệu đã nhập vào core chấm.

```powershell
cd E:\HocTap\Hackathon-SGU2026\Coach_Learning
.\tools\pdf_metadata\run.ps1 -Action layout-refine `
  -Questions '151,154,161,153,159,163' -Limit 6 `
  -TrialOutput 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-metadata-pilot-v1\layout-trial-v2'

.\tools\pdf_metadata\run.ps1 -Action layout-refine `
  -Questions '157,167,171,187,224' -Limit 5 `
  -TrialOutput 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-metadata-pilot-v1\layout-trial-v2-holdout'
```

Các lệnh chỉ dùng FormulaNet-M đã có, CPU 3 threads, không bật Qwen/Gemini và không download mới. Chạy lại dùng cache ô; thời gian cache không phải tốc độ OCR ban đầu. Sau lệnh, process Python thoát và giải phóng model. Thay PDF phải tạo pilot mới khớp hash trước; không tự coi extraction cũ là dữ liệu của file khác.

143 tests của bộ công cụ PDF qua, bao gồm phân số lồng, cắt mảnh theo mệnh đề, số mũ nhiều chữ số, hàm chưa khai báo không bị hiểu thành tích, không lấy đường chéo làm mũi tên, khung ngoài, vô cực, xung đột OCR/font, giá trị sai được giữ nguyên, UI không bịa hàng dấu cho bảng chỉ có mũi tên, và JSON Schema không cho ứng viên tự bật xuất bản. Tests kiểm hành vi phần mềm, không chứng minh độ chính xác học thuật của corpus.

Khi chạy tests đã tái hiện lỗi Windows reset kết nối nếu server từ chối POST rồi đóng socket còn body chưa đọc. Server review hiện đọc body có giới hạn trước khi trả lỗi; xác thực origin/token vẫn xảy ra trước parse JSON và lưu, request bị từ chối không tạo review. Đây là sửa lỗi trả phản hồi HTTP, không nới quyền lưu dữ liệu.

## Việc còn lại trước chạy kho lớn

Ưu tiên hàng chờ thực tế: mốc biểu thức (`ln`, căn/tham số), nhãn có gạch trên và bảng native/vector/nối trang. Sau đó đánh giá riêng trên 50–100 trang từ nhiều PDF và bộ câu được đối chiếu nguồn. Chỉ mở chạy nháp kho lớn khi có số đo độ phủ/lỗi còn sót phù hợp; chưa bật nhập core hoặc chấm tự động.
