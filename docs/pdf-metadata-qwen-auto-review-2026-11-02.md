# Qwen local duyệt metadata tự động

Cập nhật luồng hiện tại: `review_pdf.ps1` nay chạy thêm text→LaTeX trước Qwen review và mở `final.html`. Xem `pdf-complete-pipeline-2026-11-02.md` cho file cuối `pdf-final/v1`, 207 tests và số đo tích hợp mới. Các số đo 179 tests bên dưới thuộc lượt triển khai bước review riêng trước đó.

## Cách chạy

Sau khi đưa PDF vào `tools/pdf_metadata/process_pdf.cmd` hoặc `process_pdf.ps1`, chương trình trích xuất trước rồi gọi Qwen local. Không cần chọn số câu hay duyệt từng câu để luồng tiếp tục. `-ReviewLimit 0` mặc định xử lý toàn bộ câu; `-ReviewLimit 3` để thử ngắn. `-SkipQwen` chỉ trích xuất.

Với PDF đã có metadata, không cần OCR lại:

```powershell
.\tools\pdf_metadata\review_pdf.ps1 -Job '.tmp\pdf-jobs\5db1fc66ab0a42553e882981'
```

`qwen-review.html` trong job là trang xem cố định. `qwen-review.json` chỉ tới phiên bản review hiện tại. Mỗi câu có checkpoint theo ID riêng, không phụ thuộc số câu in trên tài liệu. Đầu ra:

- `questions.qwen-reviewed.jsonl` và `.pretty.json`: kết quả mọi câu và đề xuất của model.
- `machine-cleared.jsonl`: chưa thấy vấn đề trong metadata và không vướng cổng kiểm local.
- `machine-flagged.jsonl`: có vấn đề từ model hoặc cờ OCR/toán chưa giải quyết; tự tách riêng, không chặn các câu khác.
- `deferred.jsonl`: chưa xử lý do giới hạn lượt thử, model lỗi/timeout hoặc thiếu bước.
- `jobs/<hash>/`: input, raw response và trạng thái; có thể kiểm lại vì sao một câu được phân loại.

Chạy lại dùng cache theo metadata, hash ảnh nguồn, model, prompt/schema và cấu hình output. Dùng `-RetryFailed` khi muốn chủ động thử lại các câu lỗi hoặc trạng thái in-flight chưa có kết quả. Không tự gọi lại vô hạn. Không gọi Gemini hoặc cloud fallback.

## Phạm vi duyệt

Qwen hiện chỉ đọc chữ/OCR và công thức ứng viên đã trích xuất, không đọc ảnh PDF trong lượt review này. Điều này giữ chi phí CPU thấp hơn đường vision từng thử; model không được phép báo đã đối chiếu ảnh. Các câu có glyph chưa giải được, công thức mâu thuẫn, bảng chưa đọc được hoặc input bị cắt vẫn bị code chặn dù model nói không thấy lỗi.

`MACHINE_CLEARED` là trạng thái rà soát nhất quán metadata, không phải bằng chứng toàn bài đúng toán. Các trường `academic_review=PENDING`, `grading_support=NOT_ASSESSED`, `publishable=false` của bản nguồn được giữ nguyên. Không áp dụng sửa đáp án, sửa công thức hoặc tách/gộp bước từ model một cách âm thầm. Nguồn raw, metadata và các phiên bản trước không bị ghi đè.

Qwen3-VL-2B Q8 đang có sẵn trên máy đã bỏ sót lỗi nội dung ở thử nghiệm cũ (`pdf-metadata-compact-trial-2026-11-02.md`). Vì vậy việc dùng model tự duyệt giúp phân luồng và giảm rà thủ công, chưa thay thế kiểm toán nguồn/chứng minh toán để bật core chấm.

## Tài nguyên và kiểm thử

OCR và Qwen chạy nối tiếp bằng hai process; OCR thoát trước khi load Qwen. Server local dùng 3 CPU threads, GPU layers 0, BelowNormal priority. Wrapper tự dừng server mà nó khởi tạo để trả RAM; server có sẵn được giữ lại. Không tải thêm model nếu runtime Qwen đã đầy đủ; môi trường, weights và output ở E.

179 tests qua sau tích hợp, gồm việc giữ nguyên metadata, chặn model tự bỏ qua lỗi OCR, input bị cắt, tham chiếu bước không tồn tại, merge bước không liên tiếp, ghi chú vượt giới hạn, server offline, source hash sai, số câu trùng và tiếp tục một lượt giới hạn bằng cache. Đây là test phần mềm có mock provider, không phải benchmark độ đúng nội dung. Runtime thật được ghi riêng trong `qwen-review.json` và `usage.jsonl`.

Lượt runtime đầu trên ba câu 151–153 dùng Qwen thật: 116,027 giây, hai phản hồi qua kiểm và một phản hồi chạm giới hạn output 512 tokens. Đã thu gọn hợp đồng còn tối đa hai vấn đề, ghi chú 100 ký tự và một đề xuất cấu trúc để giảm phản hồi bị cắt. Giữ riêng output của lượt cũ để đối chiếu. Đây là thử đường chạy, không phải đo độ đúng nội dung hay duyệt xong 120 câu.

Sau thu gọn hợp đồng: cả ba phản hồi qua schema/tham chiếu bước, 89,690 giây; cả ba câu ở `MACHINE_FLAGGED` do nguồn/model có cờ, 117 câu ở `DEFERRED` với lý do `REVIEW_LIMIT_REACHED`. Không có câu được duyệt học thuật. Chạy lại cùng ba câu có 3 cache hits, 0 inference mới, 0,359 giây cho phần review; số này không tính khởi động/kiểm checksum/dừng server. Lượt thật dùng khoảng 4,1 GB working set cho server Qwen, CPU threads=3. Server đã tự dừng sau cả lượt suy luận và lượt kiểm cache.

62 file raw/pilot và 39 file gốc ngoài phạm vi công cụ PDF giữ nguyên hash. Metadata trích xuất không thay đổi; các link file của viewer đã được kiểm tồn tại. Chưa kiểm trực tiếp browser UI hoặc kéo thả Explorer, chưa chạy cả 120 câu hay kho 3.478 trang trong lượt tích hợp này.
