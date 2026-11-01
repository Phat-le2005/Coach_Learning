# Thử chấm từng bước và tải bài viết giấy

Chỉ dùng bài mẫu `SAMPLE_TEST` trong development/test. Lệnh dưới đây bổ sung đáp án
tham chiếu cho đúng bản ghi mẫu đã có; không tạo câu hỏi học thuật mới và không
chạy trên production.

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.seed_step_review_demo
```

Đăng nhập tài khoản học sinh có quyền Toán 12, mở **Bài làm của tôi** rồi chọn
**Thử chấm từng bước**. Giải bài khảo sát hàm số bậc ba thành các bước:
đạo hàm, xét dấu/đồng biến nghịch biến, cực trị, nhận xét đồ thị. Xác nhận các
bước, bấm **Nộp bài giải** để nhận kết quả. Nếu câu hỏi có đáp án, rubric đã duyệt
và mọi bước nằm trong phạm vi quy tắc toán học đã kiểm chứng, backend chấm và
ghi điểm chính thức mà không gọi Gemini. Nếu thiếu rubric hoặc có bước chưa
thể kiểm chứng, backend gọi Gemini một lần cho toàn bài để nhận góp ý tạm thời.
Nếu thiếu đáp án, Gemini chỉ gợi ý điều cần kiểm tra, không kết luận đúng sai.
Cần `AI_PROVIDER=gemini` và `AI_API_KEY` trong `backend/.env` cho hai trường hợp
cần AI. Góp ý AI không ghi điểm hoặc cập nhật mastery. Lệnh seed mẫu ở trên chỉ
bổ sung đáp án, không tạo rubric đã duyệt nên bài mẫu dùng nhánh góp ý AI.

Trong trang làm bài, bấm **Tải bài giấy** để nộp tối đa 10 ảnh PNG/JPEG hoặc PDF,
mỗi tệp tối đa 10 MB. Tệp được lưu riêng theo lượt giải trong
`backend/var/math_paper/` (có thể đổi bằng `MATH_PAPER_STORAGE_DIR`). Chọn tệp
đã tải, bấm **Trích xuất OCR từ bài chụp**. Backend gửi riêng tệp đó tới Gemini
để gợi ý từng dòng/công thức hoặc bảng; không gửi đáp án tham chiếu trong yêu cầu
OCR. Học sinh đối chiếu với ảnh gốc, sửa và xác nhận từng bước theo thứ tự.
Với gợi ý công thức, bản xem trước LaTeX cập nhật khi sửa và bàn phím toán giúp
thay ký hiệu tại vị trí con trỏ; chỉ công thức hiển thị hợp lệ mới được lưu.
Các bước không đọc rõ vẫn có thể nhập thủ công. Chỉ bước được xác nhận mới được
lưu và đưa vào nhận xét sau khi nộp; ảnh/PDF hay văn bản OCR thô không tự trở
thành điểm số. Nếu không có bước xác nhận thì nút nộp vẫn bị khóa. Tệp vẫn xem
được sau khi nộp, nhưng không thể thay/xóa.
