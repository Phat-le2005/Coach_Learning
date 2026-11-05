# Lớp học 3D trong trang giáo viên

Mở `/teacher` bằng tài khoản giáo viên: tab **Lớp học & Học sinh** và cảnh 3D mở mặc định ở đầu nội dung.
Các thẻ chọn/tạo lớp và danh sách quản lý nằm phía dưới cảnh. Link trực tiếp tới tab khác vẫn được giữ nguyên.
Chế độ **Lớp học 3D** là mặc định của tab này; **Danh sách** hiển thị cùng danh sách học sinh.
Giao diện hiện dùng concept **Lớp Mình — Cozy Campus**; hồ sơ mở bên cạnh khi chọn học sinh,
và chuyển xuống dưới trên màn hình hẹp.
Tab lớp học mở rộng tới 1760px, phần cảnh cao tới 780px trên desktop;
banner tổng quan được ẩn ở tab này để nhường chỗ cho lớp 3D; các tab học liệu, lý thuyết, bài giao và năng lực vẫn giữ luồng API hiện có.

## Chức năng

- Mười bàn trong năm hàng, mỗi hàng hai bàn, có lối đi giữa. Camera perspective ở phía giáo viên nhìn xuống lớp; học sinh quay mặt về giáo viên và các hàng sau nhỏ dần theo khoảng cách.
- Chọn nhân vật hoặc nút tên/số bàn để xem hồ sơ, tiến độ bài tập, mastery và yêu cầu hỗ trợ.
- Các tư thế học bài, giơ tay, hoàn thành và ngoại tuyến được lấy từ trạng thái rõ ràng trong dữ liệu.
- Nút xem bài làm mở tab **Bài giao & Chấm bài**, lọc roster theo đúng ID học sinh. Nếu em không có trong roster bài đang chọn, hiển thị trạng thái trống; nút **Xem cả lớp** bỏ bộ lọc. Đổi lớp sẽ xóa bộ lọc học sinh cũ. Trong lớp minh họa, nút bài làm bị vô hiệu hóa vì không có bài thật.
- Tìm tên tiếng Việt có hoặc không dấu, tìm email; học sinh giữ nguyên số bàn khi tìm kiếm.
- Lớp đông hơn mười người được chia thành các nhóm bàn; các bàn chưa có người hiển thị trống.
- Màn hình hẹp có nút số bàn; trường hợp WebGL không hoạt động vẫn chọn được hồ sơ và chuyển sang danh sách.
- Nhân vật có tóc, đồng phục, cổ áo, cặp sách, kính và biểu cảm. Chọn nhân vật làm bạn ấy nhìn về giáo viên và chào nhẹ; giơ tay có bong bóng gọi hỗ trợ.
- Mascot Mầm là nhân vật mầm cây 3D trong lối đi, có thể chạm để chào. Toàn bộ hình khối và artwork Mầm được tạo trong dự án.
- Đổi màu cặp, chậu cây/ngôi sao và kính ngay trong hồ sơ. Lựa chọn được lưu tại trình duyệt theo lớp, không đồng bộ qua tài khoản hay thiết bị khác.
- Nút **Khoảnh khắc** tạo ảnh PNG 1080×1350 hoặc 1080×1920. Ảnh chụp cảnh WebGL loại bỏ nhãn tên, email và vòng chọn; mặc định ẩn tên lớp. Dữ liệu demo được ghi nhãn trên ảnh xuất.
- Có thể tải riêng sticker Mầm dạng PNG 512×512 nền trong suốt để dùng cùng ảnh lớp.
- Khi cả lớp hoàn thành bài tập, cảnh chúc mừng chạy khoảng hai giây. Nút xem thử chỉ thay đổi animation, không cập nhật điểm, mastery hay số bài hoàn thành.

## Khoảnh khắc và cá nhân hóa

`classroom-personalization.ts` kiểm tra dữ liệu localStorage theo danh sách học sinh được phép và các tùy chọn cố định.
Key lưu là `edums:cozy-campus:v1:<classroom-id>`; chỉ lưu ID và lựa chọn trang trí, không lưu tên/email hoặc điểm số.
Dữ liệu hỏng, version lạ hay khóa prototype đều được bỏ qua. Các tab cùng trình duyệt nhận thay đổi qua sự kiện storage.

`classroom-moment.ts` nhận ảnh cảnh và số liệu tổng hợp, tạo PNG trực tiếp ở client.
Ảnh nguồn được chụp ở kích thước cố định để chất lượng không phụ thuộc vào màn hình điện thoại.
Không tải ảnh hoặc gửi dữ liệu học sinh lên dịch vụ chia sẻ; người dùng tự tải ảnh xuống.
Khi không có WebGL, thẻ dùng ảnh lớp minh họa ẩn danh thay thế.

## Dữ liệu

Mặc định **Lớp đang quản lý** nhận danh sách từ `teacherApi.students(classId)` qua BFF có xác thực.
`classroom-adapter.ts` chỉ chuyển ID, họ tên, email, trạng thái ghi danh và bỏ học sinh synthetic.
Roster API hiện chưa có mastery, số bài hoàn thành, hiện diện trực tiếp hoặc yêu cầu hỗ trợ từng em;
những trường này được giữ `null`/`unknown` và hiển thị **Chưa có dữ liệu**.
Không dùng thống kê tổng hợp của cả lớp hay điểm của một bài để suy ra mastery từng học sinh.
Ảnh xuất khi chưa có dữ liệu cũng ghi rõ chưa có tiến độ, không hiển thị tỷ lệ 0% hoặc ăn mừng hoàn thành.

Nút **Minh họa 10 bạn** là chế độ người dùng chủ động chọn, dùng fixture riêng trong
`frontend/src/features/teacher/classroom-demo.ts`. Lớp mẫu có mười học sinh, chín người online và hai yêu cầu hỗ trợ.
Giao diện và ảnh xuất đều ghi nhãn minh họa. Lỗi API, lớp rỗng hoặc chưa chọn lớp không tự động thay bằng dữ liệu mẫu.
Lớp rỗng hoặc chưa có lớp vẫn hiện phòng 3D với mười bàn trống và Mầm, kèm lời nhắc chọn/tạo lớp; không tạo học sinh giả trong roster thật.

`status: ACTIVE` chỉ biểu diễn ghi danh. Không suy ra online, giơ tay hoặc hoạt động học từ
mastery thấp, nội dung yếu hay thời gian hoạt động gần nhất.

Các trường của `classroom-types.ts` hỗ trợ mở rộng khi backend có bằng chứng tương ứng:

- `presence`: `online`, `offline`, `unknown`; bỏ trống được hiển thị là chưa có trạng thái online.
- `activity`: `studying`, `completed`, `idle`.
- `helpRequest`: ID yêu cầu và nội dung học sinh gửi. Bỏ trống nghĩa là chưa có yêu cầu.

Không thêm endpoint WebSocket, heartbeat hay ghi nhận hỗ trợ vào backend trong thay đổi giao diện này. Chỉ tư thế và yêu cầu rõ ràng trong dữ liệu mới kích hoạt animation học bài/giơ tay/hoàn thành; dữ liệu chưa biết giữ tư thế ngồi trung tính.

## Tải và vòng đời cảnh

`Classroom3DScene` được tải bằng `next/dynamic` ở client khi mở chế độ 3D.
Three.js dùng dependency hiện có, không tải thư viện hoặc model từ CDN.
Phòng, bàn và ghế được gộp geometry theo material. Avatar dùng chung geometry/material khi có thể.
Giới hạn pixel ratio 1.5 và nhịp animation 30 khung/giây là giới hạn cấu hình, chưa phải kết quả benchmark.
Cảnh dừng vẽ khi ngoài vùng nhìn hoặc tab trình duyệt bị ẩn, tôn trọng `prefers-reduced-motion`,
và có nút tạm dừng. Renderer, geometry, material, texture, listener và observer được giải phóng khi đóng cảnh.

## Kiểm tra

Từ thư mục `frontend`:

```powershell
npm test
npm run typecheck
npm run build
$env:CLASSROOM_E2E_PRODUCTION = "1"
npx playwright test --config playwright.classroom.config.ts
```

Lệnh trên kiểm tra bản production vừa build, qua server riêng ở `127.0.0.1:3105`.
Bỏ biến `CLASSROOM_E2E_PRODUCTION` để dùng Next dev khi cần debug; chế độ dev có thể chậm hoặc treo chờ tải tài nguyên trong kiểm thử reload/download.
Suite dùng khóa phiên ngẫu nhiên
chỉ dành cho kiểm thử, giả lập phản hồi API ở browser, không đăng nhập hoặc thay đổi cơ sở dữ liệu của ứng dụng. Trên Windows dùng Edge đã cài; các hệ điều hành khác dùng Chromium của Playwright (`npx playwright install chromium`).
Kiểm tra lớp thật và lớp mẫu riêng, dữ liệu chưa biết, loại synthetic, đổi lớp, lỗi API, chọn nhân vật, mở bài đúng học sinh, bài trống, tìm kiếm, chuyển chế độ nhiều lần,
màn hình 390/320px, giảm chuyển động và mất WebGL context.
Ảnh và báo cáo nằm trong `.tmp/teacher-classroom/` và không được commit.

Ngày 05/11/2026: sau khi ghép vào dashboard API mới nhất, 525 kiểm thử frontend và 12 ca trình duyệt đã qua; production build thành công.
Các ca bị ảnh hưởng bởi việc đưa 3D lên đầu trang đã được chạy lại trên bản build cuối cùng.
Suite browser kiểm tra lưu/khôi phục đồ trang trí, chọn nhân vật, ảnh PNG ở hai kích thước,
sticker Mầm 512×512 có alpha, Mầm, ăn mừng ngắn và thẻ ảnh khi mất WebGL.
Dữ liệu API trong suite browser là giả lập; không phải đánh giá hiệu quả học tập hay benchmark FPS trên thiết bị thật.
