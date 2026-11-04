# Chạy corpus PDF theo từng đợt có giới hạn

Tầng đọc nội dung v2 có thể chọn mẫu mới hoặc chạy lại một selection đã khóa,
không cần tạo kết quả v1 trước. Đây vẫn là bản nháp nội dung, chưa tự xác minh
toán học và chưa đưa dữ liệu vào core chấm. Lệnh nhập PDF thô và ghép cặp đề
lời giải vẫn là giai đoạn trước lệnh transcription này.

## Lệnh thống nhất

Tại repo `E:\HocTap\Hackathon-SGU2026\Coach_Learning`:

```powershell
$run = @{
    Version = 'v2'
    Metadata = '.tmp\pdf-jobs\4ebd40c425c242baa4faf416\corpus\cau-hoi-co-loi-giai.metadata.jsonl'
    Plan = '.tmp\toan12-local-corpus\plan.json'
    Output = 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-jobs\4ebd40c425c242baa4faf416\transcription-v2-scale-200-cold-20261104'
    Count = 200
    ExcludeSelection = '.tmp\pdf-jobs\4ebd40c425c242baa4faf416\transcription-v2-100-20261103\selection.json'
    CacheMode = 'cold'
    Workers = 2
    ChunkSize = 10
    MaxPageCache = 8
    ChunkTimeout = 1800
    RunTimeout = 14400
    MemoryLimitMB = 8192
    SkipQwen = $true
}
# Chỉ kiểm tra và khóa kế hoạch, chưa khởi tạo model:
& tools\pdf_metadata\transcribe_corpus.ps1 @run -PlanOnly
# Thử dừng có chủ đích sau một nhóm câu, exit code 3:
& tools\pdf_metadata\transcribe_corpus.ps1 @run -StopAfterChunks 1
# Chạy tiếp những câu chưa xong:
& tools\pdf_metadata\transcribe_corpus.ps1 @run
```

`Version` mặc định vẫn là `v1` để tương thích lệnh cũ. Chọn `v2` một cách
tường minh. Tham số count của chế độ chọn mẫu cân bằng phải là bội số của 4.
Có thể dùng `-Selection <selection.json>` để chạy một danh sách được khóa sẵn.
Để lập kế hoạch cho toàn bộ corpus không ép cân bằng chương, dùng `-All`.
Kết hợp `-All -PlanOnly -SkipQwen` chỉ khóa danh sách, chưa chạy OCR.
Chế độ này giữ số câu thật của từng chương và hỗ trợ chương khác; `Count`
không áp dụng khi đã dùng `All` hoặc `Selection`. Có thể dùng
`ExcludeSelection` với `All` để chỉ lập kế hoạch cho các ID chưa thử.
Không chọn mẫu dựa trên model có đọc được hay không. Các gợi ý bố cục đến từ
text và các trang của span nguồn, không phải nhãn layout đã được xác minh.

`cold` không đọc hoặc nhập cache OCR, kể cả cache vừa được ghi trong cùng
lượt. Model đã có sẵn trên ổ E; đây không phải phép đo tải model từ mạng.
Checkpoint của câu hoàn thành vẫn được dùng khi resume, đó là chủ đích của
thử nghiệm phục hồi. `local` cho phép cache trong thư mục chunk. CLI Python
còn hỗ trợ `import-v1` với `--v1` và `--baseline` tường minh, kiểm hash cache
cũ trước khi dùng, không ghi đè cache cũ.

## Giới hạn thực thi và bảo toàn câu

Danh sách được chia thành nhóm câu hoàn chỉnh, mặc định 10 câu. Tất cả span
của đề, đáp án và lời giải đi cùng câu, kể cả nằm ở trang khác. Nhóm được
sắp theo PDF và trang để tăng tính liên tục. Mỗi nhóm dùng một tiến trình
ngắn hạn; mặc định tối đa hai nhóm chạy song song, mỗi model CPU ba luồng.
Khi tiến trình kết thúc, bộ nhớ model và PDF được hệ điều hành thu hồi.

Mỗi worker chỉ giữ tối đa 8 trang đã phân tích glyph/vector theo LRU. Khi
loại một trang, nó cũng giải phóng cache nặng của pdfplumber. PDF vẫn giữ
đối tượng định danh trang và cấu trúc tài liệu cần thiết, vì vậy không coi
giới hạn 8 trang là giới hạn tuyệt đối RAM của mọi PDF.

Supervisor theo dõi mỗi 0,5 giây. Khi quá thời gian nhóm, thời gian lượt,
RAM cây tiến trình hoặc ngưỡng trống ổ đĩa, chỉ cây tiến trình do lượt chạy
sở hữu bị dừng. RAM là RSS quan sát, không phải quota cứng của hệ điều hành.
Có thể xảy ra tăng bộ nhớ giữa hai lần lấy mẫu. Mặc định timeout nhóm
1.800 giây, timeout lượt 14.400 giây, RAM 8.192 MiB, trống ổ đĩa tối thiểu
2.048 MiB. Có thể chỉnh giới hạn; không tăng worker chỉ vì còn nhiều RAM.

## Hàng đợi nhập PDF thô

`process_corpus.ps1` tiếp tục xử lý nguyên PDF để tránh cắt mất lời giải ở
ranh giới trang. `MaxPages` là ngân sách mềm của cả lượt, không phải kích
thước chunk. Nếu tài liệu đầu tiên lớn hơn ngân sách, `OversizePolicy=run`
chạy nguyên tài liệu một lần và ghi số trang vượt ngân sách. Có thể chọn
`-OversizePolicy defer` để hoãn, với lý do `DOCUMENT_EXCEEDS_PAGE_BUDGET`.
Những tài liệu còn lại không vừa ngân sách nhận lý do hoãn rõ ràng.
Timeout theo PDF vẫn áp dụng. Thay đổi này không biến nhập PDF thô thành
luồng v2 hay tự chia trang tùy tiện; chunk theo câu thuộc giai đoạn sau ghép cặp.

## Checkpoint và đầu ra

`run-identity.json` khóa hash metadata, plan, PDF nguồn, selection, code,
package, trọng số và KaTeX. Khi đầu vào hoặc code thay đổi, dùng namespace
output mới; không trộn record từ hai cấu hình. Lock phát hiện chủ còn sống
để không cho hai lượt cùng ghi vào một output.

Mỗi record chỉ được công nhận hoàn thành khi đã qua schema và có sidecar
trong `checkpoints/`. Sidecar ghi hash JSON và từng ảnh. Resume kiểm tra cả
record lẫn ảnh; record hoặc ảnh bị sửa cần được xử lý lại. Một phản hồi OCR
không đọc chắc có thể vẫn là record nháp hoàn thành nếu ảnh nguồn được giữ
và lý do được ghi; nó chưa trở thành đáp án đúng.

| File hoặc thư mục | Mục đích |
| --- | --- |
| `selection.json` | Danh sách câu và chính sách chọn mẫu cố định |
| `records/` và `checkpoints/` | Bản nháp từng câu cùng chứng cứ hoàn thành |
| `runtime.json` | Tiến độ nhỏ, số câu, RAM, thời gian và trạng thái cuối |
| `chunks/<invocation>/<chunk>/worker.log` | Log riêng của tiến trình nhóm |
| `chunks/.../supervision.json` | Exit code, thời gian, timeout và kết quả nhóm |
| `batch-state.json` | Lịch sử các lần chạy và resume |
| `benchmark.json` | Đo tài nguyên lượt gần nhất, dung lượng đầu ra và thời gian lũy kế |
| `catalog.json` và `review.html` | Danh mục nhẹ để xem câu và ảnh nguồn |
| `metadata.transcribed.draft.jsonl` | Bản nháp kỹ thuật đầy đủ, gồm dấu vết công thức |
| `content.draft.jsonl` | Nội dung để tiếp tục biên soạn |
| `*.pretty.json` | Bản dễ đọc, xuất tuần tự ở cuối lượt |

Trong khi chạy chỉ cập nhật file tiến độ và danh mục nhỏ. Bốn file tổng hợp
được stream từ từng record vào file tạm rồi đổi tên ở cuối lượt, kể cả khi
dừng có chủ đích. Không ghi lại toàn bộ JSON sau mỗi câu. Bộ nhớ xuất tổng
hợp giữ một record lớn tại một thời điểm, cộng metadata danh mục và bộ đếm.
Không có cơ chế tự xóa dữ liệu gốc, kết quả thử cũ hoặc câu khó.

## Trạng thái và cách hiểu phép đo

| Trạng thái | Exit code | Ý nghĩa |
| --- | --- | --- |
| `PLANNED` | 0 | Khóa kế hoạch, chưa chạy OCR |
| `COMPLETE_DRAFT` | 0 | Mọi câu chọn đã có checkpoint hợp lệ |
| `PAUSED_DRAFT` | 3 | Dừng ở ranh giới nhóm theo yêu cầu |
| `INCOMPLETE_DRAFT` | 1 | Thiếu câu, worker lỗi hoặc vượt ngân sách |
| `SOURCE_INTEGRITY_FAILED` | 1 | Nguồn thay đổi trong khi chạy |

Phép đo OCR cold tắt Qwen bằng `-SkipQwen` để biết riêng chi phí tầng đọc
nội dung. Nếu bật Qwen, luồng v2 dùng runtime vision 8792 sau OCR và vẫn chỉ
đọc một vùng cho mỗi câu thuộc tập chẩn đoán, không duyệt cả lời giải. Chi
phí và chất lượng vision phải được báo riêng, không gộp vào số OCR cold.

Các bộ đếm CPU và I/O là quan sát theo cây tiến trình, có thể bỏ lỡ công việc
ngắn giữa hai mẫu. RSS không đồng nghĩa bộ nhớ vật lý độc quyền. Thời gian
hoạt động lũy kế cộng các invocation, không cộng thời gian người dùng để
pipeline tạm dừng. Dung lượng bao gồm ảnh, record, cache và file xuất; đây
là chi phí lưu trữ thực tế của cấu hình được chạy, không ngoại suy tuyến
tính sang mọi PDF.

## Điều kiện mở rộng tiếp

Đợt 200 câu mới phải phủ bốn chương, nhiều PDF và các nhóm gợi ý bảng/hình,
câu nhiều trang. Kiểm chứng không trùng ID với 100 câu cũ; đây không phải
khẳng định đề toán không trùng nội dung giữa các PDF. Kiểm schema, hash ảnh,
phạm vi được xử lý, danh sách lỗi và số inference/cache. Sau pause/resume,
các record đã xong phải giữ nguyên hash và không suy luận lại.

Chỉ quyết định mở rộng sau khi biết thời gian cold, peak RAM, dung lượng,
lỗi nhóm/câu, tình trạng giữ ảnh và nội dung còn thiếu. Tách ba nhóm dữ liệu
ở cấp câu cho bước sau: ứng viên core, tham khảo ảnh và tạm loại khỏi bộ dùng.
`academic_review=PENDING`, `grading_support=NOT_ASSESSED`, `publishable=false`
vẫn được giữ. Chạy đủ, qua schema và hash không xác lập độ chính xác toán học.
