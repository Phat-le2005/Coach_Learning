# MathMate — bộ quay và dựng video Hackathon

Lưu trữ ngày 10/11/2026 từ `C:\CoachLearningVideo`. Coach Learning và MathMate là cùng dự án. Đây là công cụ sản xuất video riêng, không phải dependency của frontend/backend ứng dụng.

- `production/src/`: composition Remotion và timeline.
- `production/public/`: footage đã biên tập, audio, font và phụ đề phục vụ render.
- `production/out/`: video đã xuất và các cảnh giới thiệu/giáo viên để cắt ghép.
- `production/scene00*`, `production/revision/`: các lần chỉnh cảnh giáo viên và mở đầu.
- `rehearsal/`: kịch bản, bản thuyết minh và script chuẩn bị.
- `toolchain/`: package manifest/lock và công cụ kiểm tra quay dựng.
- `assets/`: font cùng giấy phép.
- `ARCHIVE_MANIFEST.json`: danh sách file, SHA-256, các file đã loại và script đã bỏ mật khẩu cố định.

## Chuẩn bị để chỉnh lại video

Cần Node.js, Python và FFmpeg/ffprobe. Thư mục `.venv`, `node_modules`, cache trình duyệt và file môi trường không được lưu trong Git.

```powershell
cd CoachLearningVideo/toolchain
npm ci
cd ../production
npm install
npm run studio
```

Python packages tham khảo tại `requirements-lock.txt`; tạo virtualenv mới nếu dùng các script Python. Việc dựng từ footage có sẵn không yêu cầu key AI. Một số script quay/TTS lịch sử vẫn tham chiếu đường dẫn `C:/CoachLearningVideo`, checkout cũ, FFmpeg tại `C:/ffmpeg/bin`, API và ID dữ liệu ở máy quay; phải điều chỉnh các đường dẫn này trước khi chạy ở máy khác. Các ghi chú READINESS/PREPARATION là trạng thái lịch sử, không phải kết quả kiểm tra checkout mới.

## Dữ liệu riêng tư

Bản lưu trữ không bao gồm `.env`, phiên đăng nhập/token, context riêng tư, log, bản quay thô và bản frontend sao chép để quay. Năm script trước đây có mật khẩu cố định đã chuyển sang đọc `VIDEO_DEMO_PASSWORD` từ môi trường tiến trình. Các script quay cần người vận hành chuẩn bị lại tài khoản/ngữ cảnh demo theo schema mà script sử dụng; dữ liệu đó phải nằm trong `.tmp/` bị Git bỏ qua. Không dùng tài khoản thật của học sinh.

Bản gốc `C:\CoachLearningVideo` vẫn giữ nguyên ở máy phát triển. Việc lưu trữ này không chạy lại capture, TTS, migration, seed hoặc render video.
