# Pipeline PDF → metadata → Gemini review

Ngày 02/11/2026. Mã xử lý nằm trong `tools/pdf_metadata`; môi trường và đầu ra trên ổ E. PDF/ZIP gốc, dữ liệu OCR cũ và lịch sử biên soạn được giữ nguyên. Chưa chạy suy luận trên toàn bộ 3.478 trang.

Cập nhật theo yêu cầu sau đó: provider mặc định đã chuyển sang **Qwen local**. Các lệnh trong tài liệu này dùng `-Provider gemini` để gọi Google một cách tường minh. Xem `pdf-metadata-local-qwen-2026-11-02.md` cho luồng local; các kết quả Gemini cũ vẫn được giữ riêng.

## Hai luồng dùng chung hợp đồng và checkpoint

**Luồng review câu đã có:** native/Paddle extraction → ghép câu → bước local → đóng gói ảnh đề/đáp án/lời giải → Gemini đề xuất bước/cảnh báo → kiểm tra source/schema → bản review riêng.

**Luồng PDF mới:** inventory → cửa sổ trang có context → render ảnh + native text → Gemini trích xuất/rà soát → kiểm tra quyền sở hữu trang/nguồn/schema → staging và hàng chờ lỗi. Luồng này phục vụ PDF scan, lý thuyết, trắc nghiệm/đúng–sai và bố cục hỗn hợp, nhưng chất lượng phải được đánh giá trên từng nguồn. Nó không phụ thuộc fixture 20 câu của pilot và không tự kế thừa trạng thái đã duyệt của fixture.

Ảnh được gửi kèm vì JSON cuối có thể đã mất dấu, phân số hoặc cả nội dung. Câu qua trang giữ nhiều evidence IDs. Mỗi điều kiện có nguồn và basis riêng: `VISIBLE_SOURCE` hoặc `PROPOSED_ADDITION`. Bản chép nguồn và đề xuất sửa là hai trường riêng. Chỉ dẫn nằm trong tài liệu được coi là dữ liệu, không có quyền điều khiển job.

## Thử nghiệm thật

- Đã kiểm tra quyền API bằng khóa trong `.env`, không in/lưu khóa vào report. Model chốt cho thử nghiệm: `gemini-3.6-flash`.
- Review 7 câu 151, 152, 153, 154, 158, 213, 260 của pilot: 7 hoàn tất; 2 `AI_REVIEWED`, 5 `AI_FLAGGED`. Bộ này cố ý chứa các câu có ghi chú lỗi nguồn, không phải mẫu ngẫu nhiên hay bài benchmark độc lập.
- Lượt 7 câu sử dụng 43.347 input tokens và 12.211 output tokens, tổng 55.558 tokens theo usage trả về; mất khoảng 72 giây, gồm một lần retry HTTP. Không coi đây là chi phí hóa đơn; quota/tier và các lượt lỗi trước khác nhau.
- Câu 152 trả 7 bước; giả thiết về dấu `c` được giữ là bổ sung cần duyệt. Câu 158 giữ lỗi `C-R` của nguồn và đề xuất `R-C` riêng. Câu 260 giữ nguồn hỏi hoành độ nhưng lời giải xét tung độ, không âm thầm đổi đáp án nguồn.
- Đã lập plan đủ 13 PDF / 3.478 trang / 1.743 cửa sổ. Mặc định hai trang owner, một trang context mỗi phía. Plan không gọi API suy luận.
- Đã chạy mẫu ba cửa sổ: tài liệu đạo hàm trang owner 9–10, tài liệu thống kê ảnh-only trang owner 3–4, tài liệu xác suất trang owner 3–4. Có 6 owner pages và 12 trang ảnh tính cả context. Đây là kiểm thử mẫu đa bố cục, không phải chứng nhận toàn kho.
- Các kết quả corpus và cờ nguồn cụ thể được lưu trong `report.json`/staging; nhiều câu trên trang mẫu không có lời giải tham chiếu hoặc đáp án rõ. Pipeline ghi cờ thiếu dữ liệu thay vì tạo lời giải rồi coi là nguồn.
- Bản corpus cuối giữ 28 units: 26 câu hỏi và 2 mục kiến thức; 27 units mang cờ cần kiểm tra, 1 unit qua các cổng local và được AI rà soát. Có 6 units bắt đầu ở trang context được loại khỏi staging, giữ nguyên trong raw response và `normalization_audit` để tránh lặp. Lượt tạo response dùng 25.365 input và 11.715 output tokens, tổng 37.080; bước lọc/revalidate sau đó dùng 0 API calls. Không suy ra 27/28 là tỷ lệ OCR sai: phần lớn cờ là trang nguồn không có lời giải/đáp án hoặc có lựa chọn cần kiểm tra lộ đáp án.
- Chạy lại 7 câu và ba cửa sổ đã hoàn tất: 7 và 3 cache hits, **0 generation calls**. Tests cũng xác nhận lần chạy kế tiếp bỏ qua job hoàn tất và tiếp tục job chưa chạy.
- Mọi bản xuất giữ `academic_review=PENDING`, `grading_support=NOT_ASSESSED`, `publishable=false`. Chưa có câu nào được dùng để chấm chính thức từ pipeline này.

## Lỗi đã quan sát và cách xử lý

1. Lượt đầu dùng Flash 3.8 bị timeout; trạng thái remote và usage không chắc chắn. Không tự chạy lại job đó.
2. Lược đồ JSON hợp lệ theo JSON Schema đầy đủ nhưng provider trả 400. Đã dùng subset tương thích cho request (có type rõ cho enum); phía local vẫn kiểm schema chặt, không bỏ kiểm tra.
3. Lượt review sớm của Câu 152 tự thêm `c>0` và các biến đổi đạo hàm rồi gắn nhãn nội dung nhìn thấy. Đã yêu cầu basis cho từng điều kiện, tách rõ nội dung bổ sung, giữ ghi chú nguồn chưa giải quyết và thêm cổng phát hiện bất đẳng thức đơn giản không thấy trong native text. Đây là tín hiệu cần review, không phải bộ chứng minh toán học. Các response cũ được giữ trong jobs; bản active dùng hợp đồng mới.
4. AI đồng ý với chính nó hoặc trả `CONSISTENT` không làm nội dung thành đã duyệt. Không dùng confidence để tự cấp quyền chấm. Kiểm source/schema không chứng minh công thức đúng hay không bỏ sót câu.
5. Cửa sổ giới hạn có thể cắt câu dài, xuất thiếu hoặc vượt output token limit. Các trường incomplete/continuation và trạng thái MAX_TOKENS chặn nhận âm thầm. Các job này cần retry có kiểm soát/cửa sổ nhỏ hơn hoặc kiểm tra nguồn; chưa có suy luận tự động không giới hạn.
6. Model có thể xuất thêm unit bắt đầu ở trang context. Cổng local tách các unit đó khỏi bản xuất và lưu audit, không sửa số trang để làm chúng có vẻ hợp lệ. `-Revalidate` xử lý lại raw response đã có bằng cổng mới, không gọi API; `-RetryFailed` là thao tác khác, có thể gửi request mới.

## Chạy tiếp

Từ root repository:

```powershell
# Chỉ kiểm kê toàn bộ, không inference.
.\tools\pdf_metadata\run.ps1 -Action corpus-plan -Provider gemini

# Lấy tiếp tối đa 10 job mới; cache không bị tính thành job mới.
.\tools\pdf_metadata\run.ps1 -Action corpus-run -Provider gemini -Limit 10 -MaxCalls 12 -MaxTotalTokens 200000

# Thử nhiều tài liệu theo vòng thay vì chỉ PDF đầu tiên.
.\tools\pdf_metadata\run.ps1 -Action corpus-run -Provider gemini -SamplePerDocument -Limit 13 -MaxCalls 15 -MaxTotalTokens 250000

# Dữ liệu mới: một PDF, ZIP hoặc thư mục PDF, đầu ra tách riêng trên E.
.\tools\pdf_metadata\run.ps1 -Action pipeline -Provider gemini -InputPath 'E:\materials\another.zip' -Output 'E:\pdf-output\another' -Limit 3 -MaxCalls 5

# Xem nguồn và bản AI đề xuất, chỉ đọc.
.\tools\pdf_metadata\run.ps1 -Action corpus-review -Provider gemini
```

Không đổi model hoặc schema giữa chừng rồi ghép thẳng hai bản xuất: generation/cache keys đã tách các biến thể. Không xóa checkpoint chỉ để chạy lại cho đến khi rõ job trước có hoàn tất từ xa không. `-MaxTotalTokens` là ngưỡng dừng giữa các request theo usage quan sát được, không phải giới hạn hóa đơn tuyệt đối; `-MaxCalls` giới hạn số lần thử generate thực tế trong mỗi lệnh. Một timeout có thể đã bị tính usage ở provider.

Các file cuối:

- Pilot: `.tmp/pdf-metadata-pilot-v1/gemini/questions.reviewed.jsonl` và bản pretty JSON.
- Kho: `.tmp/toan12-gemini-corpus/staging/content.jsonl`, bản pretty và `review-queue.json`.
- Kế hoạch/tiến độ: `plan.json`, `active-jobs.json`, `jobs/<hash>/state.json`, `report.json`, `runs/*.json`.
- Bằng chứng: ảnh trong `assets/` hoặc `pages/`, package và raw provider response theo job, usage ledger không chứa API key.

Staging là dữ liệu biên soạn riêng tư. Đáp án/lời giải và ảnh có thể lộ đáp án không được chuyển thẳng thành payload học sinh. Chưa có adapter ghi database, tạo rubric, gán điểm hoặc cập nhật mastery.

## Kiểm tra và giới hạn

Tests bao phủ timeout/401–403/429, retry/call limit, parse env literal, secret redaction, schema provider/local, tham chiếu sai nguồn, thứ tự bước, giả thiết bổ sung, output bị cắt, cache key/source image thay đổi, lock, cửa sổ owner không lặp, ZIP path traversal, nguyên trạng nguồn và resume không gọi lặp. CLI Windows giữ output/runtime trên E. Không tải thêm model trong phần Gemini.

Lần kiểm tra cuối: **74 tests qua**. SHA-256 của 62 file pilot đã chụp trước đó (PDF, native pages, candidates và lịch sử review) giữ nguyên. Đã xác nhận HTTP 200 cho viewer pilot ở cổng 8787 và corpus ở cổng 8788. Công cụ browser báo bị tắt trong Work settings ở lượt cuối nên chưa xác nhận giao diện bằng browser; đã xem ảnh nguồn của trang scan và đối chiếu mẫu JSON riêng.

Trang review có endpoint HTTP local riêng, không ghi dữ liệu, không có khóa trên trình duyệt. Nếu công cụ browser bị tắt, chỉ báo bằng chứng HTTP/source image; không coi đó là xác nhận đã kiểm giao diện bằng browser.

Trước khi chạy hết kho, mở rộng mẫu trên cả 13 PDF và kiểm chất lượng trích xuất câu, dấu toán, lựa chọn, bảng/hình, nối qua trang. Lập ngưỡng lỗi lọt qua review trên một tập đối chiếu nhỏ; chỉ duyệt tay những mẫu đánh giá và vùng AI bất đồng. Bộ câu thiếu lời giải cần luồng biên soạn lời giải riêng có nguồn/basis rõ, không giả là nội dung PDF.

## Tài liệu chính thức đã đối chiếu

- [Gemini PDF document understanding](https://ai.google.dev/gemini-api/docs/document-processing)
- [generateContent structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- [Model catalog](https://ai.google.dev/gemini-api/docs/models)
- [Pricing and usage](https://ai.google.dev/gemini-api/docs/pricing)

Model access và giá có thể thay đổi. Pipeline kiểm catalog bằng khóa thực tế trước mỗi lượt; tài liệu giá chỉ làm tham chiếu, không tính từ bảng giá cũ trong app backend.
