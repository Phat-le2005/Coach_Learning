# Qwen local cho pipeline review PDF

Ngày 02/11/2026. Chuyển phần review mặc định sang local theo yêu cầu người dùng. API Gemini không tự chạy dự phòng khi local bị lỗi. Khóa Gemini cũ được giữ trong `.env` và không chuyển tới server local. Các chức năng AI khác của ứng dụng backend không thuộc thay đổi này.

**Thử nghiệm mới hơn:** xem [review metadata ngắn + SymPy trên 120 câu](pdf-metadata-compact-trial-2026-11-02.md). Luồng này không gửi ảnh vào Qwen, không đưa ghi chú biên tập đã biết vào inference và chưa đạt điều kiện chạy toàn kho để làm dữ liệu chấm. Các số đo vision bên dưới là thử nghiệm trước, giữ lại để so sánh.

## Cấu hình đã chọn và lý do

- Máy thử: i5-12450H, khoảng 48 GB RAM; tại lúc kiểm tra còn 27,5 GiB RAM trống. RTX 3050 Ti Laptop có 4 GB VRAM nhưng đã dùng khoảng 2,5 GB cho các tiến trình hiện có.
- Model: `ggml-org/Qwen3-VL-2B-Instruct-GGUF`, file Q8_0 và projector Q8_0. Dùng bản hỗ trợ ảnh vì metadata có thể đã sai OCR; model chỉ nhận chữ không đối chiếu được ảnh gốc.
- Revision Hugging Face: `ea6a11058182570be6436b9a2e4ee7f7b49f908d`.
- Model SHA-256: `b7802e29f71a9e5b5e3f83f613df898a2204342dcea71a231ea501d481813c39`.
- Projector SHA-256: `69066c8f279ec85ff48ab4059f6ebba0d2932ca57667f2bbdac7d9805bca9e7b`.
- Runtime: Windows CPU x64 llama.cpp `b12032`; ZIP SHA-256 `5296f5d18bb7d422c7c26f4bb9bc796d9d4f41e1312a8c296cff475bdc60d0d4`.
- Tổng tải khoảng 2,3 GB, toàn bộ trên E; không cài model vào ổ C hoặc cài Ollama toàn hệ thống. Chỉ dùng binary đã đối chiếu hash từ release chính thức.
- CPU 3 threads, batch threads 3, priority BelowNormal, một slot, context 16.384, GPU layers 0. Không thay đổi hay dừng ứng dụng khác đang dùng GPU. Mỗi ảnh dùng 1.024 vision tokens để giữ khả năng đọc/grounding; đây là tham số tính toán local.

## Luồng thực thi

Native/Paddle OCR hiện có → nhóm câu và bước local → ảnh đề/đáp án/lời giải gốc + metadata → Qwen local → kiểm schema/nguồn/điều kiện → checkpoint và bản review riêng.

Qwen dùng HTTP nội bộ ở `127.0.0.1:8790`, không phải API dịch vụ bên ngoài. Client chỉ cho phép địa chỉ loopback, không dùng proxy từ môi trường và không đi theo redirect. Server có token riêng trong file runtime bị Git ignore; token này không phải khóa Gemini và không có phí dịch vụ. Bản viewer chứa dữ liệu nguồn/kết quả, không chứa các khóa.

`PDF_REVIEW_PROVIDER=local` trong `.env`; wrapper Windows cũng mặc định `-Provider local`. Chỉ `gemini-*` hoặc `-Provider gemini` mới chọn Google. Không có cơ chế tự chuyển cloud khi Qwen chậm, model chưa bật, JSON sai hoặc thiếu bộ nhớ.

Cache của lượt local chứa provider và hash weights. Kết quả khác model/weights không bị coi là cùng một lượt. Toàn bộ cổng source, context-owner, schema, chữ/điều kiện bổ sung và trạng thái chưa duyệt tiếp tục áp dụng. Model chạy local vẫn có thể sai hoặc bỏ sót; không được tự bật rubric, điểm, mastery hay publication.

## Cách chạy

```powershell
.\tools\pdf_metadata\run.ps1 -Action local-setup
.\tools\pdf_metadata\run.ps1 -Action local-start
.\tools\pdf_metadata\run.ps1 -Action local-preflight
.\tools\pdf_metadata\run.ps1 -Action local-review -Questions '152' -Limit 1 -MaxCalls 1 -MaxOutputTokens 4096
```

Đầu ra câu mẫu: `.tmp/pdf-metadata-pilot-v1/local-review/questions.reviewed.jsonl`, bản pretty, report, usage, raw response/checkpoint. Khi server biên soạn cũ còn hoạt động, viewer ở `http://localhost:8787/local-review/review.html`.

```powershell
# Chuẩn bị kế hoạch cho kho lớn, chưa inference.
.\tools\pdf_metadata\run.ps1 -Action corpus-plan -Provider local -CorePages 1 -Overlap 1

# Chỉ chạy một cửa sổ mới để đo trước.
.\tools\pdf_metadata\run.ps1 -Action corpus-run -Provider local -Limit 1 -MaxCalls 1 -MaxOutputTokens 4096

# Trả lại RAM khi không dùng model.
.\tools\pdf_metadata\run.ps1 -Action local-stop
```

Kho local mặc định ở `.tmp/toan12-local-corpus/`, tách khỏi `.tmp/toan12-gemini-corpus/`. Với một trang owner và một trang context mỗi phía, plan có 3.478 cửa sổ. Đây là kế hoạch local, chưa phải số trang đã xử lý hay thời gian đã đạt.

## Kiểm tra và giới hạn

Đã xác nhận tải đủ và hash đúng, server load được cả model lẫn projector, `/v1/models` nhận đúng alias và preflight ghi `cloud_api_calls=0`. Tests bao phủ chặn host từ xa, credential trên URL, redirect, proxy môi trường, không gửi khóa cloud, danh tính weights, ảnh base64, structured output, timeout/truncation và các cổng pipeline có sẵn.

### Kết quả thực tế Câu 152

- Lượt multimodal đầu hoàn tất: 828,788 giây (khoảng 13 phút 49 giây), 7 bước, trạng thái `AI_FLAGGED`.
- Prompt 7.519 local tokens, output 1.999 local tokens; tổng 9.518. Cloud API calls: **0**. Đây là token tính toán trên máy, không phải usage dịch vụ Gemini.
- Engine ghi prompt processing 343,6 giây; generation 485,1 giây, khoảng 4,12 output tokens/giây. RAM peak working set của tiến trình server từ lúc load đến lúc đo: 4.345 MiB. Đây là một câu nhiều ảnh trên CPU 3 threads, không phải tốc độ bình quân toàn kho.
- Qwen trả 7 bước theo đề xuất local và giữ vấn đề dấu của `c`, nhưng verdict `CONSISTENT` không khớp warning của chính nó. Nó cũng gắn điều kiện `v>6` vào ảnh đề thay vì vùng lời giải có điều kiện. Cổng local ghi `CONDITION_EVIDENCE_MISMATCH_REVIEW_REQUIRED`; dữ liệu không được tự duyệt chỉ vì model trả JSON đúng.
- Lượt này có kèm các bước local và ghi chú nguồn đã biết trong đầu vào. Không coi nó là benchmark độc lập về khả năng phát hiện lỗi toán của Qwen.
- Đã chạy lại từ cache: 0 inference requests, khoảng 0,1 giây xử lý sau preflight. Khi đổi cổng kiểm tra, cached response được kiểm lại và lưu lịch sử thay đổi cờ; raw model response giữ nguyên.
- **85 tests qua**, 62 hash của dữ liệu pilot gốc không đổi. Viewer trả HTTP 200 ở `http://localhost:8787/local-review/review.html`; chưa có xác nhận giao diện bằng browser vì công cụ browser bị tắt.
- Sau benchmark đã dừng đúng PID server Qwen để trả lại RAM. Viewer và JSON vẫn đọc được; chạy `local-start` trước lượt inference mới.

Chi tiết số đo nằm trong `.tmp/pdf-metadata-pilot-v1/local-review/benchmark.json`; đầu ra sạch để đối chiếu ở `questions.reviewed.pretty.json`. Chưa chạy Qwen trên toàn bộ kho lớn.

Không suy thời gian toàn kho từ một câu. Vision trên CPU có thể chậm dù weights nhỏ, nhất là nhiều ảnh và context dài. Cửa sổ vượt context/output limit phải giữ ở hàng chờ hoặc chia nhỏ; không tự cắt rồi đánh dấu đã đúng. Qwen 2B chưa được chứng minh ngang chất lượng Gemini hoặc đủ chính xác để chấm tự động. Sau phép thử đầu, ưu tiên native text/OCR sẵn có và chỉ dùng review ảnh cho vùng có nghi vấn khi cần tối ưu thêm.

## Nguồn chính thức

- [GGUF do nhóm llama.cpp cung cấp](https://huggingface.co/ggml-org/Qwen3-VL-2B-Instruct-GGUF)
- [Hỗ trợ multimodal của llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
- [Runtime Windows đã ghim](https://github.com/ggml-org/llama.cpp/releases/tag/b12032)

Các file tải nằm trong runtime local và không đưa vào Git. Mã setup giữ URL, revision và digest để tái tạo; `.env.example` không chứa khóa thật.
