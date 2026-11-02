# Một PDF đầu vào, workflow tự xử lý metadata

Luồng hoàn chỉnh hiện tại và cách lấy file cuối được mô tả trong `pdf-complete-pipeline-2026-11-02.md`: entry nhận PDF nay chạy text→LaTeX, Qwen review và xuất `final.html` / `final.json`. Các đường dẫn metadata câu bên dưới vẫn là đầu ra trích xuất gốc, được giữ nguyên để truy vết.

Ngày 02/11/2026. Mục tiêu đã triển khai: đưa một đường dẫn PDF, không phải tự chọn số trang, số câu, thư mục pilot hay chạy lần lượt nhiều lệnh. Đây là workflow trích xuất bản nháp có nguồn, không phải cam kết mọi PDF đều đọc đúng hoặc đủ điều kiện chấm.

Cập nhật: `process_pdf` nay tự chạy Qwen local sau trích xuất, rồi mở `qwen-review.html`. Xem `pdf-metadata-qwen-auto-review-2026-11-02.md` cho ba luồng machine-cleared, machine-flagged và deferred. Thêm `-SkipQwen` nếu chỉ cần bản trích xuất; `-ReviewLimit 3` để thử ngắn, mặc định 0 là mọi câu. Số đo 171 tests và thời gian trích xuất dưới đây thuộc lớp trích xuất; bộ kiểm sau tích hợp Qwen là 179 tests, thời gian model review được ghi riêng.

## Cách dùng

Trong Windows Explorer, kéo PDF thả vào:

`E:\HocTap\Hackathon-SGU2026\Coach_Learning\tools\pdf_metadata\process_pdf.cmd`

File chạy nhận một PDF, gọi PowerShell/Python và mở trang kết quả khi hoàn tất. Nếu chạy trực tiếp không có tham số, nhập đường dẫn PDF khi được hỏi. Entry PowerShell đã được chạy thực tế; thao tác kéo thả/mở cửa sổ mặc định chưa được kiểm trực tiếp bằng UI automation.

Hoặc chỉ một lệnh, từ thư mục repo:

```powershell
.\tools\pdf_metadata\process_pdf.ps1 'E:\tai-lieu\bat-ky.pdf'
```

Thêm `-Open` nếu muốn PowerShell tự mở HTML khi xong. Có thể dùng đường dẫn PDF ở ổ khác; môi trường, model, cache và output vẫn ở E. Script kiểm môi trường local, tự cài dependency còn thiếu vào `.venv` ở E; model được tải từ nguồn chính thức khi thực sự cần. Máy thử dùng Python 3.13. Một máy chưa có Python cần cài Python một lần; không phải cấu hình lại theo từng PDF.

Không cần API key. Workflow này không khởi động Qwen, không gọi Gemini và không tự chuyển cloud khi OCR thất bại. Các lệnh `gemini-*` cũ vẫn là tính năng thử riêng, không thuộc đường chạy này.

## Workflow tự làm gì

1. Kiểm file và tính SHA-256. Tạo job riêng, chụp một bản PDF đầu vào để giữ nguồn ổn định; không sửa PDF gốc.
2. Tách ký tự, font, đường vẽ, ảnh và vị trí bằng pdfplumber. Ưu tiên cache raw khớp hash/parser/library; không lấy sửa tay hoặc ghi chú biên tập làm dữ liệu OCR.
3. Phân loại trang. Trang có chữ native dùng dữ liệu native; trang ảnh hoặc gần như chỉ có header chuyển sang OCR text local. Với PDF scan hỗn hợp, lựa chọn diễn ra từng trang.
4. Nhận câu/đáp án/lời giải theo marker tiếng Việt và các biến thể ASCII/English thông dụng. Số câu có thể lặp giữa các chương: khóa chính là question ID gồm hash nguồn và thứ tự xuất hiện.
5. Tự chọn trang có dấu hiệu công thức, dùng detector và FormulaNet local. Cache theo ảnh, weights, package và adapter; chỉ chạy phần còn thiếu hoặc không còn hợp lệ.
6. Tạo đề xuất bước, ứng viên công thức native/phân số, audit toán trong phạm vi hỗ trợ. Không dùng fixture 20 câu, đáp án sửa tay hay số câu của pilot làm luật chung.
7. Tự tìm vùng bảng theo question ID, đọc bảng dấu/biến thiên được hỗ trợ; vùng chưa đọc chắc được ghi kèm ảnh, bbox, lý do và hàng chờ.
8. Xuất metadata JSONL, bản pretty, nội dung từng trang, hàng chờ kiểm tra và HTML. PDF không có marker câu hỏi vẫn có metadata từng trang thay vì bị coi là đã tách đúng câu.

Chữ OCR scan có thể mất dấu. Một nhãn ngắn như “Li gii” có thể được gợi ý là “Lời giải” bằng so khớp cả dòng; điều này chỉ xảy ra với nhãn có giới hạn độ dài/khoảng cách, không áp dụng vào công thức hay đoạn văn. Giữ nguyên chữ OCR, thêm `OCR_SECTION_MARKER_INFERRED`. Khi phát hiện đáp án mà mất nhãn lời giải, phần sau đáp án được tách khỏi đề và ranh giới suy đoán có cờ riêng. Tests kiểm không đưa lời giải trở lại phần đề trong các ca này.

Đây vẫn là preview biên soạn. Không đưa file `student-preview.jsonl` hoặc trường `student_view` vào API học sinh khi chưa qua kiểm tra nội dung/ranh giới nguồn.

## Tái dùng và chạy tiếp

- Cùng bytes PDF, dù đổi tên hoặc di chuyển, dùng cùng job theo SHA-256.
- PDF khác bytes có job khác; không trộn hai tài liệu vào cùng pilot.
- Cùng phiên bản workflow dùng lại năm checkpoint: định tuyến trang, tách câu, công thức, bước/audit, bảng.
- Mỗi checkpoint kiểm hash artifact. File bị sửa/mất sẽ được tính lại; không coi trạng thái COMPLETE cũ là đủ.
- Raw OCR có checkpoint theo trang/ô. Nếu bị ngắt giữa chừng, chạy lại đúng lệnh để tiếp tục những phần chưa xong.
- Lock chỉ được tự thu hồi khi PID/creation time cho thấy tiến trình local cũ không còn sống. Không bỏ lock của tiến trình đang chạy.
- Thay code/schema sinh thư mục phiên bản mới, giữ kết quả cũ. OCR thô còn hợp lệ được dùng lại; phần diễn giải được kiểm lại.
- Chỉ có một job cho cùng PDF chạy tại một thời điểm. Nên xử lý lần lượt trên laptop; các adapter đặt CPU 3 threads, không dùng GPU.

Các mô hình text mới dùng `PP-OCRv5_mobile_det` và `latin_PP-OCRv5_mobile_rec`. PaddleOCR công bố bộ nhận dạng Latin có hỗ trợ tiếng Việt; đây không phải bảo đảm nó đọc đúng mọi dấu tiếng Việt trong PDF. [Tài liệu chính thức](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html).

## Mốc biểu thức không còn bị ép thành số hữu tỉ

`math_value.py` lưu riêng:

```json
{
  "source_expression": "\\ln 5",
  "canonical_expression": "log(5)",
  "kind": "CONSTANT_EXPRESSION",
  "symbols": [],
  "approximate_value": 1.6094379124341,
  "status": "PARSED_CANDIDATE_NOT_SOURCE_VERIFIED"
}
```

Hỗ trợ có giới hạn số, phân số, căn/hàm đã khai báo trong parser, vô cực và biểu thức ký hiệu như `m+1`. Biểu thức ký hiệu giữ danh sách symbol, không bịa giá trị gần đúng. So thứ tự và kiểm dấu dùng kết quả đại số có thể chứng minh; không suy bằng một số float khi thiếu giả thiết. Phép kiểm không được hỗ trợ giữ NOT_ASSESSED.

OCR sai `ln` thành chữ khác vẫn là lỗi đọc; schema rộng hơn không tự sửa được ảnh mờ hoặc nhãn sai. Các ràng buộc parser về độ dài, độ sâu, số token và phạm vi phép toán tiếp tục áp dụng; không dùng eval để parse nguồn.

## Đầu ra ở đâu

Thư viện chung:

`E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-jobs\review.html`

Mỗi tài liệu:

```text
.tmp/pdf-jobs/<24 ký tự hash>/
  input.pdf                 Bản chụp nguồn, không sửa
  review.html               Mở phiên bản mới nhất
  result.json               Đường dẫn chính xác các artifact
  latest.json               Phiên bản mới nhất và report
  status.json               Đang chạy, hoàn tất, thất bại hoặc bị ngắt
  native/                   Native extraction và ảnh trang
  ocr/                      Raw checkpoint local, dùng qua các phiên bản
  versions/<fingerprint>/
    report.json
    review.html
    state.json              Checkpoint các stage
    routes.json
    review-queue.json
    metadata/
      questions.jsonl       File metadata câu cho xử lý tiếp
      questions.pretty.json
      pages.jsonl           Vẫn có khi chưa nhận ra cấu trúc câu
      student-preview.jsonl Preview biên soạn, chưa được duyệt
```

`pdf-content/v1` có JSON Schema, trace nguồn, câu, đáp án in trong tài liệu, bước ứng viên, audit và bảng. Các record luôn `academic_review=PENDING`, `grading_support=NOT_ASSESSED`, `publishable=false`. Đáp án nguồn không được tự biến thành đáp án chấm đã xác minh.

## Bằng chứng chạy thật

- PDF người dùng 57 trang: workflow tự nhận 120 câu, 11 vùng bảng. Không truyền số trang hoặc số câu. Cache phù hợp được tự phát hiện; các trang chưa có cache hợp lệ đã chạy lại OCR.
- Lượt đầu của workflow tự động dùng 335,698 giây, 160 lượt gọi adapter local và 28 cache hits. Counter adapter không đồng nhất với số forward của các model con; không phải token dịch vụ cloud.
- Bản chạy hiện tại có 3 bảng ứng viên có cấu trúc, 8 bảng cần kiểm tra và 7 câu có phép kiểm đạo hàm được hỗ trợ. Không đồng nhất với thử nghiệm thủ công trước đó có thêm nguồn OCR/control; luồng tự động không nhập các chỉnh sửa biên tập hoặc control dành riêng pilot.
- Chạy lại cùng phiên bản trên 57 trang: 5 stage cache hits, **0 suy luận mới**, 2,417 giây. Đây là số đo cache, không phải tốc độ OCR toàn tài liệu.
- PDF scan tiếng Việt mới do công cụ tạo để kiểm đường chạy: 1 trang ảnh, tự chọn OCR và nhận 2 câu (901, 902). Lần đầu 28,430 giây, gồm tải hai model text còn thiếu về E. Chữ tiếng Việt bị mất một số dấu; đã phát hiện và xử lý ranh giới phần giải, không coi bản chép này đúng học thuật.
- PDF native mới, marker English và số câu lặp: nhận 2 câu với ID riêng, giữ đáp án/lời giải riêng. Lần đầu 15,697 giây với 5 lượt gọi adapter local.
- Hai PDF mới là fixture kiểm tích hợp, không phải benchmark độc lập về chất lượng OCR trên tài liệu thực tế. Unit tests có các adapter giả để kiểm orchestration; ba lượt chạy kể trên dùng adapter local thật.

171 tests qua: typed expression, checkpoint/tamper/resume, lock, nhận PDF mới/đổi tên, số câu trùng, giữ metadata trang khi không thấy marker, ranh giới OCR không đẩy lời giải vào đề, cùng các bộ kiểm trước. Entry PowerShell parse không lỗi. Chưa kiểm trực tiếp UI kéo thả trong Explorer.

Không gọi API cloud, không chạy kho 3.478 trang, không nhập database production. Mọi dữ liệu tải mới/cache/output ở E. Nguồn cũ giữ nguyên.

## Giới hạn sử dụng

Workflow tự chạy trên file khác mà không cần sửa cấu hình theo tên tài liệu. Điều này không bảo đảm parser nhận đúng mọi bố cục: đề nhiều cột, cấu trúc đáp án cuối tài liệu, bảng vector/nối trang hoặc scan mờ vẫn cần mở rộng parser/đối chiếu. PDF khóa mật khẩu cần bản đã mở khóa hợp lệ. Tài liệu chưa nhận được câu vẫn xuất page metadata và báo rõ, không đánh dấu đủ để chấm.

Chưa tự bật tiêu chí điểm, rubric hoặc đánh giá học sinh. Trước khi chạy đại trà làm nguồn chấm, cần đo chất lượng trên bộ PDF độc lập và duyệt các dạng checker được hỗ trợ.
