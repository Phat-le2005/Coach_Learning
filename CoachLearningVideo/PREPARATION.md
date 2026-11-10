# Chuẩn bị quay dựng — Coach Learning

Ngày: 2026-11-09. Trạng thái: đã chuẩn bị và kiểm tra công cụ; chưa quay ứng dụng hoặc dựng video demo chính thức. Các clip/ảnh/audio đã tạo trong lượt này chỉ là mẫu kỹ thuật riêng, không chứa tài khoản hoặc dữ liệu sản phẩm.

## Khung 180 giây điều chỉnh

Ba luồng cần thể hiện bằng thao tác có đầu vào/kết quả:
1. Mục tiêu và quỹ thời gian → kế hoạch/ưu tiên → chọn đúng nhánh tri thức và tài liệu.
2. Khám phá công thức → viết lời giải → OCR → xác nhận bản chép → nộp → phản hồi theo bước.
3. Học liệu đã duyệt → giao bài → giáo viên xem bài nộp và phần cần quan tâm. Đoạn cuối giải thích vai trò giáo viên phía sau hành trình học sinh.

| Thời gian | Cảnh | Điểm phải thấy |
|---|---|---|
| 00:00–00:08 | Vấn đề | Biết sai ở đâu và học gì tiếp; không intro logo dài. |
| 00:08–00:33 | Mục tiêu → kế hoạch → bản đồ | Một mục tiêu cụ thể và quỹ thời gian → kế hoạch có nội dung → chọn dạng bài có dữ liệu năng lực. Không chỉ quay cảnh xoay cây 3D. |
| 00:33–00:49 | Tra cứu lý thuyết | Chọn nhánh liên quan, một công thức/ví dụ và nguồn bài học. |
| 00:49–01:15 | Math View | Vẽ/chọn công thức đơn giản → nhận diện và xác nhận → hình 3D → thay tham số và xoay để thấy kết quả. Chỉ một ví dụ chủ đạo; tiếp tuyến 2D là cảnh dự phòng hoặc thay thế một phần nếu đã nghiệm thu và đủ nhịp. Không gọi mặt 3D là đồ thị 2D của cùng một phương trình khi phương trình đã đổi. |
| 01:15–02:05 | Viết và xác nhận OCR | Nét viết thật qua canvas; 5–8 giây ghép hai browser mô phỏng thiết bị; OCR thật; đối chiếu nét gốc, sửa bản chép và xác nhận lưu bước. |
| 02:05–02:28 | Nộp và phản hồi | Cận cảnh một bước cần xem lại và lời giải thích thực tế. Không dựng nội dung trả lời; giữ đúng trạng thái điểm/duyệt. |
| 02:28–02:54 | Giáo viên khép vòng | Kho học liệu từ PDF đã được xử lý/duyệt → giao bài → mở bài nộp đúng học sinh và báo cáo liên quan. Tái sử dụng cùng lớp/bài/người học xuyên suốt. |
| 02:54–03:00 | Kết | Học có định hướng, làm bài có phản hồi, giáo viên theo dõi. |

Không đưa phụ huynh, admin, tuyển sinh hoặc thi thử vào bản ba phút này. Không quay OCR Lab. Không biến những chu trình mới có backend hoặc frontend chưa nối đủ thành tính năng đã demo hoàn chỉnh.

Thời lượng là mục tiêu dựng. Sau nghiệm thu dữ liệu/cảnh thật, thuyết minh miền Nam sẽ được viết lại và cân theo audio thực tế; không kéo giọng đọc quá nhanh để ép khung.

## Bộ công cụ đã cài

- Skill chính thức tại C:/Users/ADMIN/.codex/skills/: remotion-best-practices, remotion-create, remotion-render, remotion-captions, remotion-docs, remotion-markup; version 4.0.541. Đã đọc hướng dẫn phù hợp. Skill mới sẽ được catalog nhận từ lượt tiếp theo.
- Node project riêng: C:/CoachLearningVideo/toolchain. Remotion/CLI/renderer/bundler/media/captions/fonts/transitions cùng version 4.0.541; Playwright 1.64.1; React 19.3.0. Có package-lock.
- Chrome Headless Shell dành riêng cho Remotion đã tải bằng ensureBrowser(), mở/đóng thành công. Browser quay sử dụng Microsoft Edge hiện có, tách khỏi browser render.
- Python riêng: C:/CoachLearningVideo/.venv. Có google-genai, httpx, python-dotenv, Pillow, numpy, soundfile; pip check PASS. Snapshot package tại C:/CoachLearningVideo/requirements-lock.txt.
- FFmpeg/ffprobe 7.1.1 hiện có tại C:/ffmpeg/bin.
- Font Be Vietnam Pro Regular/SemiBold/Bold cùng OFL.txt đã chuẩn bị tại C:/CoachLearningVideo/assets/fonts.
- Không cài OBS, dịch vụ cloud editor hoặc mô hình speech recognition lớn: pipeline hiện có đủ cho nguồn giọng đọc được sinh theo từng đoạn và phụ đề theo câu. Nếu sau này cần word alignment chính xác hơn, bổ sung công cụ sau khi đo audio thực tế.

## Kết quả kiểm tra công cụ

Evidence nằm tại C:/CoachLearningVideo/toolchain/qa/.

| Kiểm tra | Kết quả |
|---|---|
| Canvas pointer | PASS: 4 nét, 48 điểm di chuyển |
| Thiết bị phụ mô phỏng | PASS: mobile context độc lập, thao tác tap |
| Font tiếng Việt | PASS; đã xem ảnh trực tiếp |
| WebGL2 | Available; chưa phải benchmark FPS với cảnh 3D của sản phẩm |
| Browser capture | PASS: video 1920×1080 |
| Remotion | PASS: bundle và render still 1920×1080, cấu hình 30 FPS |
| MP4 encode | PASS: H.264, 1920×1080, 30/1 FPS, yuv420p |
| Audio/video mux | PASS: H.264 + AAC |
| Phụ đề | PASS: parse/serialize SRT tiếng Việt và burn vào clip thử |
| Tăng tốc | PASS: clip thử ~1.43 giây thành ~0.73 giây với setpts 0.5 |
| Gemini TTS | PASS HTTP 200: mẫu kỹ thuật 5.09 giây, PCM 24 kHz; có WAV và MP3 |

Giọng mẫu: Aoede, gemini-2.5-flash-preview-tts, yêu cầu giọng nữ miền Nam. Chưa xác nhận chất lượng phương ngữ bằng nghe; accentValidated=false trong report. Mẫu không phải thuyết minh chính thức. Có thể tiếp tục thử giọng/prompt ở giai đoạn sản xuất; nếu cần FPT Lan Nhi/Linh San thì cần key FPT riêng. Không khẳng định giọng đạt yêu cầu chỉ vì API trả 200.

## Cách dùng công cụ khi sản xuất

- Quay theo scene và đánh dấu các hành động, request, kết quả. Browser recording đặt rõ cả viewport và recordVideo.size ở Full HD.
- Replay nét qua pointer/mouse vào canvas thật; pairing, OCR và chấm đi qua app/backend thật. Các fixture test chỉ làm tài liệu kỹ thuật.
- Thu đầy đủ thời gian chờ. Khi dựng, tăng tốc đúng đoạn và ghi tỷ lệ thực tế, hoặc cắt với nhãn 'Đã rút ngắn thời gian xử lý'. Audio thuyết minh giữ tốc độ bình thường. Trở về 1× trước kết quả và giữ đủ nhịp đọc.
- Dựng trên timeline theo audio và marker, không theo sleep cố định. Giữ nội dung bài làm và phản hồi nguyên nghĩa.
- Chỉ dùng tài khoản/lớp/bài demo riêng. Không quay key, log quản trị, thông tin người học thật. Credential đọc từ file local hiện có và không được copy vào project video, package hoặc report.
- Bản chính xuất MP4 H.264/AAC, 1920×1080, 30 FPS, yuv420p, faststart. Raw footage, source, voice và captions giữ riêng phục vụ sửa.

## Nguồn công cụ chính thức đã khảo sát

- https://www.remotion.dev/docs/ai/skills
- https://www.remotion.dev/docs/renderer/ensure-browser
- https://www.remotion.dev/docs/renderer/open-browser
- https://playwright.dev/docs/videos
- https://ai.google.dev/gemini-api/docs/speech-generation
- https://docs.fpt.ai/docs/vi/speech/api/text-to-speech/

## File kiểm tra có thể chạy lại

Trong C:/CoachLearningVideo/toolchain:
- node capture-preflight.cjs
- node render-preflight.cjs

Python:
- C:/CoachLearningVideo/.venv/Scripts/python.exe C:/CoachLearningVideo/tts-preflight.py (gọi dịch vụ TTS, có thể tính usage)
- C:/CoachLearningVideo/.venv/Scripts/python.exe C:/CoachLearningVideo/media-preflight.py

Các script này kiểm tra công cụ trên mẫu kỹ thuật, không tự quay sản phẩm. Bộ công cụ sẵn sàng để chuyển sang chuẩn bị dữ liệu/cảnh và quay; vẫn cần nghiệm thu luồng demo trong ứng dụng và chọn giọng phù hợp trước khi làm bản chính. Không thay package/lock/source ứng dụng trong lượt chuẩn bị này và không push Git.
