# Giao diện Gia sư AI và AI Core

Hai lối vào nằm trên thanh điều hướng học sinh. Dùng phiên đăng nhập học sinh hiện tại; không cần nhập token qua Swagger.

## Gia sư AI

Mở `/student`, bấm **Gia sư AI**, nhập câu hỏi hoặc chọn một câu mẫu rồi bấm **Gửi câu hỏi**. Câu hỏi tối đa 2.000 ký tự. Có trạng thái chờ, thông báo lỗi và đường dẫn đăng nhập lại nếu phiên đã hết hạn.

Mỗi câu hỏi được xử lý riêng, không lưu lịch sử hội thoại. Hãy kèm đề bài và bước đang vướng trong câu hỏi mới. Phản hồi là hướng dẫn học tập, không phải điểm chính thức và không tự cập nhật mastery.

Trình duyệt gửi JSON tới `POST /api/student/tutor`. Route frontend xác minh session, vai trò STUDENT, origin và CSRF; chỉ chuyển `message` cùng `stream=false` tới `POST /ai/tutor` bằng access token trong cookie HttpOnly. Không đưa bearer token hoặc service key vào JavaScript phía trình duyệt. Khi gặp 401, giao diện dùng cơ chế refresh phiên hiện có rồi thử lại một lần.

Backend và provider AI cần được cấu hình theo hướng dẫn hiện hành. Giao diện sử dụng Tutor API hiện có; thay đổi này không bổ sung LangChain workflow, streaming hoặc embeddings. Khi provider không khả dụng, Tutor backend có thể trả thông báo dự phòng; HTTP 200 tự nó không chứng minh chất lượng câu trả lời hay model đã chạy thành công.

## AI Core

Mở `/student/ai-core` hoặc bấm **AI Core** trên thanh điều hướng. Trang đọc dữ liệu của học sinh đang đăng nhập qua các API đã có:

| Khối | Nguồn | Nội dung |
|---|---|---|
| Attempt Tracker | Danh sách MathWorkspace attempts | Sáu bài gần đây, trạng thái, số bước nếu có và phiên bản |
| Knowledge Graph | `/students/me/digital-twin` | Số khái niệm, quan hệ tiên quyết và ánh xạ dạng bài; tối đa sáu quan hệ được hiển thị |
| Mastery V1 | `/students/me/mastery` | Tối đa 12 mục, ưu tiên mục có bằng chứng, gồm mastery, confidence và số lượt |
| Recommendation | `/students/me/learning-state` | Tối đa tám mục tiêu theo đúng thứ tự backend, mã lý do, điểm ưu tiên, độ khó và lịch hôm nay |

Trang không gọi LLM, chấm bài, tạo lượt làm, tính lại kế hoạch hoặc ghi database. Nó là ảnh chụp trạng thái hiện có, không phải bản ghi từng bước thực thi của một request.

Để so sánh trước/sau:

1. Bấm **Ghi mốc so sánh**.
2. Bấm **Mở bài làm để test**, thực hiện bài ở tab khác và hoàn tất luồng nộp/đánh giá.
3. Quay lại, bấm **Làm mới dữ liệu**. Chỉ kết quả đủ điều kiện mới có thể thay đổi mastery.

Mốc chỉ ở bộ nhớ trang. Nút làm mới dữ liệu giữ mốc; tải lại toàn bộ trình duyệt hoặc chuyển trang có thể mất mốc. Chênh lệch hiển thị bằng điểm phần trăm và chỉ tính khi cả hai mốc đều có bằng chứng.

Các mục chưa có bằng chứng hiển thị **Chưa đo**, không biến thành năng lực 0%. Khi một nguồn không đọc được, phần tương ứng để trống kèm thông báo, không thay bằng dữ liệu mẫu. Hồ sơ mô phỏng được gắn nhãn theo cờ từ API. Phần chiếu đồ thị kiểm tra student ID và không chuyển các trường hồ sơ riêng như ngày sinh sang component giao diện.

Engine hiện tại là `DeterministicMasteryCalculationStrategy` tại `backend/app/mastery/strategy.py`: quy tắc Mastery V1 tất định, **chưa triển khai BKT**. Trang không thay đổi công thức mastery, grading hoặc bộ đề xuất.

## Kiểm thử

Từ `frontend`:

```powershell
npm run typecheck
npm run test:tutor
npm run test:ai-core
npm test
```

Hai bộ test chuyên biệt kiểm tra biên đầu vào Tutor, chỉ chuyển trường được phép, phản hồi rỗng, phân biệt thiếu bằng chứng với điểm 0, kiểm tra danh tính khi chiếu đồ thị, loại trường hồ sơ riêng và phép so sánh trước/sau. Các ca mới cũng được đưa vào `npm test` để chạy trong CI.

Kiểm tra trên trình duyệt: mở/đóng hộp thoại bằng bàn phím, chọn câu mẫu, gửi câu hỏi, xác nhận phản hồi và lỗi/phiên hết hạn; mở trang AI Core, ghi mốc rồi làm mới và xác nhận mốc còn giữ. Kiểm tra thêm màn hình nhỏ để bảo đảm nút điều hướng và bảng có thể truy cập được.

Test kỹ thuật với dữ liệu giả lập không thay cho đánh giá độ đúng toán học của AI thật. Không đưa ảnh chụp riêng tư, token, log hội thoại, kết quả cá nhân hoặc cấu hình `.env` vào commit.
