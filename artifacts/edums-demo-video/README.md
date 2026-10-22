# EduMS — Video demo 6 phút

Video kết hợp ảnh chụp có xác thực từ frontend EduMS đang chạy thật với các cảnh minh họa cho chức năng đang phát triển. Tất cả cảnh dùng chung ngôn ngữ hình ảnh Verdant / Learning Forest.

## Video bàn giao

- `output/EduMS_Demo_3phut30_V2.mp4`: **bản rút gọn đề xuất**, H.264/AAC, 1920×1080, thời lượng metadata `03:30.04`.
- `output/EduMS_Demo_3phut30_V2_vi.srt`: phụ đề tiếng Việt rời, gồm 24 đoạn và đã đồng bộ với bản rút gọn.
- `output/EduMS_Demo_3phut30_V2_vi_chitiet.srt`: **phụ đề tiếng Việt chi tiết đề xuất**, gồm 37 đoạn giải thích thao tác, xử lý hệ thống và ranh giới AI/prototype.
- Bản rút gọn tăng tốc đồng bộ hình và âm thanh `1.7147619×` từ bản V2 sáu phút; không cắt bỏ luồng chức năng.
- SHA-256 bản 3 phút 30: `B015B4B6DAD0509CF61A4401DD9DA7E6AD7C176EEC6BFF33D2E140D5452773E3`.
- `output/EduMS_Demo_6_phut_V2.mp4`: **bản trình chiếu chính**, H.264/AAC, 1920×1080, 10 fps.
- `output/EduMS_Demo_6_phut_V2.webm`: bản ghi gốc V2, VP8/Opus.
- Thời lượng V2 đã kiểm tra: `360.1` giây.
- SHA-256 V2 MP4: `4877F543C9AAA240CBF34B53EF0CACBEB412D85740E8AB58C14975E802A04542`.
- SHA-256 V2 WebM: `739AFC3C4BE827905B0D973E3A01A65019976DDBCAB618BEE53A16B43F38E020`.
- `EduMS_Demo_6_phut.mp4` và `.webm` là bản V1 được giữ để đối chiếu.

Video có nhạc nền ambient tự tạo và phụ đề tiếng Việt nằm trong khung hình. Video không có giọng đọc.

## Timeline

| Thời gian | Nội dung | Trạng thái |
|---|---|---|
| 00:00–00:18 | Mở đầu EduMS | Giới thiệu |
| 00:18–00:42 | Đăng nhập và session thật | Live demo |
| 00:42–01:08 | Student Home | Live demo |
| 01:08–01:34 | Knowledge Forest / Galaxy | Live demo |
| 01:34–02:04 | Practice Workspace | Product vision |
| 02:04–02:38 | Công thức và trình xem hình học 3D | Product vision |
| 02:38–03:04 | Chấm lời giải theo từng bước | Prototype |
| 03:04–03:34 | Giáo viên theo dõi phiên làm bài | Product vision |
| 03:34–04:08 | Dashboard tiến độ lớp và heatmap | Product vision |
| 04:08–04:46 | PDF lý thuyết → sơ đồ tư duy | Product vision |
| 04:46–05:10 | Mastery, Digital Twin và repair | Backend foundation |
| 05:10–05:30 | Ôn tập thích ứng và thi thử | Product vision |
| 05:30–05:48 | Student–Teacher–Parent–Admin | Tổng quan |
| 05:48–06:00 | Màn kết | Tổng kết |

## Nhãn trung thực trong video

- `LIVE DEMO`: ảnh chụp trực tiếp từ frontend local với tài khoản hợp lệ.
- `PROTOTYPE`: luồng đã có một phần nền tảng nhưng giao diện minh họa chưa phải production.
- `BACKEND FOUNDATION`: năng lực domain/backend được biểu diễn trực quan.
- `PRODUCT VISION`: giao diện mô phỏng cho chức năng chưa hoàn thiện.

Video không tuyên bố handwriting OCR, tự động chấm tự luận, tạo sơ đồ tư duy, thi thử, Parent Portal, Admin dashboard hoặc Admission Assistant đã hoàn thiện production.

## Nguồn hình ảnh

- `captures/login.png`
- `captures/student-home.png`
- `captures/knowledge-galaxy.png`

## Cách dựng

`renderer.html` vẽ timeline lên canvas 1920×1080 và ghi canvas cùng audio bằng MediaRecorder. `render-video.mjs` điều khiển Chrome headless, lấy blob theo từng chunk và ghi ra `output/`. Bản WebM được chuyển mã bằng FFmpeg đi kèm `imageio-ffmpeg`:

```powershell
python -m http.server 8765 --directory artifacts/edums-demo-video
node artifacts/edums-demo-video/render-video.mjs
```

Chrome dùng để render cần tắt background throttling hoặc chạy renderer trong cửa sổ foreground. `validate-video.mjs` kiểm tra metadata, độ phân giải và SHA-256.
