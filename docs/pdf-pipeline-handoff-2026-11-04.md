# Bàn giao pipeline PDF — 04/11/2026

## Mục tiêu đã chốt với người dùng

Ưu tiên hoàn thiện pipeline PDF trước. PDF vào → tách đề/đáp án/lời giải →
metadata có ảnh nguồn → kiểm chất lượng → đưa các phần còn nghi vấn cho
Gemini đối chiếu. Chỉ đưa dữ liệu phù hợp vào core sau khi kiểm lại.

Không tiếp tục mở rộng giao diện đồ thị, Cây tri thức hoặc core chấm trong
đợt bàn giao này. Nhánh thử nghiệm Luyện từ PDF và dữ liệu DB local đã được
tạo ở máy làm việc nhưng **không nằm trong đợt push này**. Không coi đây là
tính năng đã có trên checkout mới. PDF workflow trong commit không ghi DB.

## Đọc và chạy từ đâu

| Nhu cầu | Điểm vào |
| --- | --- |
| Một PDF → bộ metadata phân nhóm | `tools/pdf_metadata/build_dataset.ps1` |
| Mô tả luồng dễ sử dụng | `docs/pdf-usable-pipeline.md` |
| Khởi tạo môi trường/model local hiện có | `tools/pdf_metadata/process_pdf.ps1`, `local_model.ps1` |
| Chạy transcription nhiều câu, có checkpoint | `tools/pdf_metadata/transcribe_corpus.ps1 -Version v2` |
| Chạy toàn bộ danh sách thay vì quota đều chương | `transcribe_corpus.ps1 -Version v2 -All` |
| Cách chạy lớn/timeout/RAM/cache | `docs/pdf-scale-runner-2026-11-04.md` |
| Kết quả chạy lạnh 200 câu | `docs/pdf-scale-trial-200-2026-11-04.md` |
| Tổng thể các nhánh cũ, CLI và cấu hình | `tools/pdf_metadata/README.md` |

Trên Windows, checkout và runtime đặt trên ổ E theo cấu hình của người dùng.
Python 3.13; Node và KaTeX từ frontend. Không dùng base Python để trộn model.

```powershell
cd E:\<thu-muc-checkout>\Coach_Learning
cd frontend
npm.cmd ci
cd ..
# Chuẩn bị môi trường PDF theo process_pdf.ps1 / README khi máy chưa có.
# process_pdf.ps1 là luồng cũ và tự chạy xử lý, không phải chỉ cài dependency.
.\tools\pdf_metadata\build_dataset.ps1 `
  -Pdf 'E:\<du-lieu>\source.pdf' -Profile native -Open
```

`build_dataset.ps1` cần môi trường tại
`.tmp/pdf-pipeline-runtime/.venv/Scripts/python.exe`. Dependencies mô tả ở
`requirements-native.txt` và `requirements-paddle.txt`. Profile `native`
không gọi model OCR hay API cloud, nhưng runner dùng cùng môi trường PDF đã
chuẩn bị; không hứa đây là bộ cài hoàn toàn không phụ thuộc Paddle/model.
Profile `ocr` gọi OCR local. Không tự fallback sang Gemini khi local lỗi.

Sau chạy, con trỏ `.tmp/pdf-jobs/<sha256-24>/dataset-final.json` chỉ tới
output version hiện tại. Chạy lại đúng lệnh và input sẽ tái dùng checkpoint.
Khi code/cấu hình thay đổi, identity có thể đổi: dùng namespace mới; không
copy checkpoint cũ để giả vờ là lần chạy mới đã hoàn thành.

## Các module chính

1. `pdfmeta.dataset_workflow`: điều phối một PDF, hash, ghép cặp, chạy v2,
   kiểm lại nguồn, xuất metadata và ảnh trang chưa ghép được.
2. `paired.fast_native`, `paired.corpus`: trích nội dung native và ghép đề với
   lời giải trong bố cục hỗ trợ; vùng không ghép được giữ ở hàng chờ.
3. `paired.transcription_v2`: dùng glyph/vector và OCR có giới hạn; nguồn
   chưa chắc dùng ảnh. `geometry.py` giữ trị tuyệt đối; `choice_layout.py`
   ghép nhãn A–D với phân số qua tọa độ nguồn.
4. `source_recheck.py`: đọc lại PDF gốc, kiểm cấu trúc/ký hiệu, kiểm KaTeX.
   Cú pháp hợp lệ không đồng nghĩa toán đúng; không tự sửa ý của sách.
5. `curation.py`: phân loại cả câu, giữ ảnh, đọc đáp án cuối có chứng cứ.
6. `progress/`: dashboard local và artifact server; `curation_view.html`:
   xem từng câu/nhóm bằng ảnh gốc và metadata.

Runner v2 giới hạn chunk, page cache, RSS, disk floor và timeout của cây
tiến trình do chính runner tạo. Có checksum checkpoint, streaming export,
chạy tiếp và mã thoát khác 0 khi chưa hoàn tất. `-PlanOnly` không inference.

## Định nghĩa output và giới hạn phải giữ

| File | Dùng cho |
| --- | --- |
| `metadata.final.jsonl` | Toàn bộ câu đã ghép, có phân nhóm |
| `core_candidates.jsonl` | Có thể đối chiếu đáp án cuối theo khóa in trong nguồn |
| `image_reference.jsonl` | Xem từ ảnh; chưa có khóa đáp án máy đọc chắc |
| `held_items.jsonl` | Lỗi toàn vẹn/nguồn, phải tạm giữ |
| `held_source_occurrences.jsonl`, `held_pages.jsonl` | Vùng/trang chưa chuyển được thành câu; không bịa bản ghi câu hỏi |
| `summary.json`, `validation.json`, `index.html` | Thống kê, kiểm kỹ thuật, xem kết quả |

`core_candidates` không có nghĩa đề và lời giải đã sạch toàn bộ LaTeX hay
được phê duyệt học thuật. Giữ `academic_review=PENDING`, `publishable=false`,
`production_grade=false`, `assessment_ready=false`, `step_grading_ready=false`.
`compare_source_answer()` chỉ đối chiếu khóa nguồn, trả `score=null`.

Quan trọng: không chỉ review nhóm `image_reference`. Nhiều câu có đáp án cuối
đọc được nhưng text/công thức lời giải còn lỗi. Phải xét `text_review_reasons`,
`math_expressions`, `presentation_mode` và ảnh gốc theo từng trường.

## Bằng chứng chạy tại máy làm việc (không phải gold benchmark)

### Pilot một PDF

Tên PDF: `tu-luan-va-trac-nghiem-ung-dung-dao-ham-de-khao-sat-va-ve-do-thi-ham-so-toan-12-knttvcs9.pdf`.
Thực tế 57 trang. SHA256:
`5db1fc66ab0a42553e882981d1b22935967295b9a73cd2c96840e6ee5dd76927`.

- 120 câu; 111 ứng viên đáp án số theo nguồn; 9 câu ảnh tham khảo; 0 held.
- 111 ứng viên đều còn dùng ảnh gốc làm bản trình bày chuẩn, không phải 111
  câu đã sạch LaTeX hoặc được duyệt lập luận.
- Kiểm 2.338 ảnh tham chiếu trong export; 398 ảnh vùng nguồn đầy đủ ở lần QA.
- Native lần đầu khoảng 205 giây; chạy lại khoảng 52 giây, 120 checkpoint
  được dùng lại, 0 record transcription mới. Không gọi cloud API.
- Ví dụ câu cá hồi: đáp án nguồn 15, nhập 15 khớp, 14 không khớp. Đây là so
  sánh đáp án nguồn, không phải chứng minh lời giải nguồn đúng.

Output tại máy gốc:
`.tmp/pdf-jobs/5db1fc66ab0a42553e882981/usable-dataset/fd1a99d3098bb681/final`.
Không có thư mục này trong Git; người nhận cần PDF riêng và chạy lại. Code
identity sau bàn giao có thể tạo đường dẫn khác; đọc `dataset-final.json`.

### 200 câu mới, không đọc cache OCR

12 PDF, 4 chương; 200 ID mới ngoài mẫu 100 câu trước. Tổng thời gian worker
khoảng 49 phút, peak RSS khoảng 3,78 GB (thập phân), output khoảng 56 MB.
1.124/3.587 vùng công thức giữ ảnh; 197 câu có cờ review. Các chunk hoàn tất
không đồng nghĩa 200 lời giải chính xác. Tái phân loại sau source recheck có
43 ứng viên đáp án cuối (33 A–D, 10 số), 157 ảnh tham khảo. Bộ này khác pilot
57 trang; không cộng số lượng mà chưa kiểm trùng nội dung.

Kho có inventory khoảng 3.478 trang và 3.695 occurrence. Chỉ là kiểm kê/plan,
không tuyên bố tất cả đã transcription v2 hoặc đủ điều kiện chấm.

## Công việc tiếp theo: Gemini review có chọn lọc

**Chưa triển khai đường nối từ curated/v2 output mới sang Gemini. Chưa gọi
Gemini cho bộ curated mới trong lần bàn giao này.** Không ghi chức năng đề
xuất dưới đây thành tính năng đã có.

Các thành phần có thể tái sử dụng:

- `gemini_client.py`: REST client, preflight model, giới hạn calls/tokens,
  usage ledger; không log khóa.
- `gemini_jobs.py`: job identity/cache/lock, checkpoint, xử lý trạng thái
  chưa biết sau lỗi mạng và retry có kiểm soát.
- `gemini_review.py`, `gemini_contracts.py`: review một câu với ảnh crop gốc,
  schema và nguồn bằng evidence ID. Hiện đọc schema pilot cũ
  (`questions.enriched.candidates.jsonl`), không đọc trực tiếp curated v2.
- `local_client.py`: chọn provider local/Gemini tường minh.
- `paired/transcription_v2/vision.py`: Qwen chẩn đoán **một vùng/câu**, không
  phải duyệt đầy đủ đề và toàn bộ lời giải.

### Phạm vi triển khai đề xuất

1. Tạo adapter `curated-question/v1` → package review. Giữ ID, source hash,
   record hash, ảnh đầy đủ đề/đáp án/lời giải và các vùng bị cảnh báo.
2. Tạo queue theo lỗi: LaTeX/cấu trúc, thiếu text, đáp án mâu thuẫn, ghép cặp,
   bảng/hình. Lỗi thiếu file hoặc sai hash phải sửa nguồn trước, không gửi
   model để nó bịa phần thiếu.
3. Gửi một câu/job, ảnh cần thiết và cảnh báo liên quan; chỉ thêm trang lân
   cận khi cần ngữ cảnh. Không gửi cả kho PDF vào một request.
4. Gemini trả patch có `field_path`, `before`, `after`, `evidence_ids`,
   loại lỗi và mức không chắc. Evidence ID phải lấy từ input; không cho
   model tự tạo bbox, xác nhận học thuật hay đánh dấu sẵn sàng chấm.
5. Code kiểm schema, ID/hash, trường cho phép sửa, KaTeX, dấu/số/điều kiện
   nguồn và phép toán nằm trong grammar hỗ trợ. Kiểm cú pháp và việc hai
   model đồng ý không được coi là chứng minh toán học.
6. Xuất version/overlay mới, giữ bản gốc và diff; không ghi đè JSONL đầu vào.
   Không đủ nguồn hoặc còn mâu thuẫn tiếp tục dùng ảnh/tạm giữ.
7. Có budget rõ cho max calls, tổng token, output token, timeout/retry; cache
   identity gồm hash ảnh, nội dung, model, prompt và schema/adapter version.
8. Thử khoảng 30 câu thuộc nhiều loại lỗi trước; đo token, thời gian, số câu
   đề xuất sửa, số bản sửa qua kiểm, lỗi còn lại. Chỉ mở rộng khi có bằng
   chứng so với ảnh nguồn. Mẫu model báo PASS không tự thành gold test.

Model lấy qua preflight tài khoản. Đề xuất Gemini Flash khả dụng trước;
không tự thay model khi model được cấu hình không tồn tại. `.env.example`
là mẫu, `.env` thật bị Git ignore. Thao tác `-Provider gemini` / CLI Gemini
là gửi ảnh/nội dung chọn lọc sang Google và có thể tiêu token; local không
tự fallback sang cloud. Không in khóa hoặc commit usage có dữ liệu riêng.

## Kiểm thử và bàn giao Git

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'tools\pdf_metadata'
$env:PYTHONUTF8 = '1'
& '.tmp\pdf-pipeline-runtime\.venv\Scripts\python.exe' -B -m pytest `
  tools/pdf_metadata/tests -q `
  --basetemp=.tmp/pytest-pdf-handoff -p no:cacheprovider
```

Snapshot bàn giao đã chạy lại toàn bộ suite PDF: **427 passed trong 31,37
giây**, với source từ worktree chuẩn bị push và môi trường Python/KaTeX
local hiện có; các entry point PowerShell parse thành công. Đây là kiểm thử code/fixture, không
phải độ chính xác học thuật của toàn kho. Bài thực tế, thời gian và bộ test
phải báo riêng. Chi tiết kiểm tra commit xem lịch sử Git của đợt bàn giao.

Không push PDF gốc, ZIP, `.env`, API key, model weights, `.tmp`, checkpoint,
database, screenshots, logs hoặc output metadata lớn. Fixture hồi quy nhỏ
ở `tests/fixtures` là dữ liệu kiểm thử cho lỗi vector trị tuyệt đối và các
ô đáp án phân số; không chứa PDF hoặc bộ dataset đầy đủ.
