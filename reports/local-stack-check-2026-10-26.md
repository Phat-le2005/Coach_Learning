# Kiểm tra stack local và dữ liệu team — 26/10/2026

Máy chạy được luồng học sinh frontend → backend → PostgreSQL với dữ liệu trong
`D:\Học\hackathon\edums_dump.sql`. Đã kiểm tra bằng HTTP và trình duyệt Edge ẩn.
Chưa xác nhận mọi chức năng của sản phẩm hoạt động đầy đủ: còn thiếu migration
0049 trong mã nguồn, API key Gemini và cấu hình OCR phía backend.

## Môi trường đã kiểm tra

| Thành phần | Kết quả |
| --- | --- |
| Python của project | 3.12.15 tại `.conda/python.exe` |
| Node.js của project | 22.23.4 tại `.conda/node.exe` |
| PostgreSQL | 16.15, chạy local `127.0.0.1:5432` |
| Extension vector | 0.8.6, đã cài |
| Dependency Python | `pip check` đạt khi dùng `PYTHONNOUSERSITE=1` |
| Frontend | Next.js 16.3.8; production build đạt |
| Test frontend hiện có | 181 đạt, 0 lỗi |

Python mặc định ngoài project là Python 3.10. Nên dùng launcher của project
hoặc `.conda/python.exe`, tránh vô tình dùng môi trường toàn cục. Kết quả kiểm
tra dependency ban đầu bị ảnh hưởng bởi user-site; môi trường riêng không có
hai xung đột được báo trong lần kiểm tra đó.

## Database thử nghiệm và cách khôi phục

- Database gốc `edums` được giữ nguyên. Trước kiểm tra có 19 tài khoản, 14
  khái niệm, chưa có câu hỏi; migration 0048.
- Database mới: **`edums_team_check_20261026`**. Cùng server, port và thông tin
  kết nối local hiện có; không thay `backend/.env`.
- Khôi phục đủ 137 bảng từ dump: ban đầu 19 tài khoản, 559 câu hỏi, 99 khái niệm,
  24 lượt giải toán. Sau kiểm tra có thêm tài khoản và hoạt động thử nghiệm.
- Dump gốc được xuất từ PostgreSQL 17.11. Thử nhập trong một transaction vào
  database mới, PostgreSQL 16 từ chối `SET transaction_timeout = 0;`. Transaction
  được rollback. Tạo bản sao chỉ bỏ dòng này rồi khôi phục thành công.
- Bản gốc tại `D:\Học\hackathon\edums_dump.sql` giữ nguyên; đã so sánh byte.
- Bản tương thích: `.local/stack-check/edums_dump.pg16.sql`.
- Log khôi phục: `.local/stack-check/restore-original.log` và `restore-pg16.log`.
- Đường dẫn psql sử dụng junction ASCII của helper local để tránh lỗi đường dẫn
  có dấu trên PostgreSQL Windows.
- Đối chiếu các bảng ORM: không thiếu cột mà mã nguồn hiện tại khai báo. Database
  có thêm bảng `math_paper_attachments` chưa có model/migration tương ứng trong
  checkout hiện tại. Đối chiếu cột không thay thế kiểm thử toàn bộ nghiệp vụ.

## Các luồng đã đạt

1. Backend khởi động; `/health` và `/openapi.json` trả 200.
2. Đăng ký một học sinh thử nghiệm riêng; đăng nhập và đọc thông tin tài khoản.
3. Tạo phiên luyện tập, đọc learning state/mastery, lấy câu hỏi đã duyệt.
4. Gửi câu trả lời; backend chấm đúng và lưu `question_attempts` trong PostgreSQL.
5. Đăng nhập qua frontend BFF với CSRF/cookie; `/auth/me` trả đúng người dùng.
6. Trang học sinh và cây kiến thức tải được dữ liệu thật. Trình duyệt hiển thị
   chương trình Toán 12, các chương và trạng thái học tập.
7. Trình duyệt bấm **Bắt đầu làm bài**, tạo lượt giải mới từ câu hỏi đã duyệt và
   mở không gian viết toán. Đã đối chiếu lượt giải được lưu trong database.
8. Vẽ một nét bằng sự kiện chuột của trình duyệt, frontend tự lưu qua BFF/backend;
   PostgreSQL có document revision 1 và trang nét viết. Tải lại vẫn đọc được nét.
9. Refresh phiên và đăng xuất đạt; sau đăng xuất `/auth/me` trả 401.
10. Tài khoản học sinh truy cập `/teacher` được chuyển tới trang thiếu quyền.

Các trang trình duyệt đã kiểm tra không ghi nhận exception JavaScript hay phản
hồi HTTP 5xx trong lượt kiểm tra thành công. Có cảnh báo deprecation THREE.Clock
từ thư viện 3D. Chưa kiểm tra toàn bộ luồng giáo viên/phụ huynh/admin, mọi loại
bài, toàn bộ OCR, AI review, chấm lời giải nhiều bước hoặc triển khai production.

## Các điểm cần bổ sung

1. **Migration 0049:** dump lưu `0049_math_paper_attachments`, checkout chỉ có đến
   `0048_math_ink_retention_index`. `alembic current` trên database thử nghiệm báo
   `Can't locate revision identified by '0049_math_paper_attachments'`. Cần lấy
   migration và mã nguồn tương ứng từ team trước khi nâng cấp database tiếp.
   Không đổi giá trị trong `alembic_version` để che lỗi.
2. **AI Gemini:** `AI_PROVIDER=gemini` nhưng `AI_API_KEY` hiện chưa được điền.
   Chưa gọi hoặc xác nhận chức năng AI.
3. **OCR backend:** `MATH_OCR_PROVIDER=disabled`. Chưa xác nhận nhận diện công thức
   hoạt động; OCR chạy trong trình duyệt là luồng riêng và cũng chưa kiểm thử.
4. **Tệp đính kèm:** có metadata tệp trong dump, nhưng chưa xác nhận các tệp ngoài
   database đã được team cung cấp đầy đủ.

Cache `.next` cũ có file tự sinh `.next/dev/types/validator.ts` sai cú pháp. Đã
chuyển nguyên cache vào `.local/stack-check/frontend-next-before-check` và build
lại thành công; không sửa source TypeScript để bỏ qua kiểm tra.

## Mở ứng dụng và đăng nhập

Trong lần kiểm tra, backend chạy cổng 8000 với database thử nghiệm bằng biến
môi trường của tiến trình; frontend chạy chế độ development cổng 3000.

- Ứng dụng: <http://localhost:3000/login>
- Backend docs: <http://127.0.0.1:8000/docs>
- Tài khoản thử nghiệm: `local.check.20261026@example.com`.
- Mật khẩu nằm trong `.local/stack-check/test-account.json` (mở bằng editor).
  Đây là tài khoản mới, riêng cho kiểm tra. Không thay mật khẩu tài khoản team.

Nếu cần chạy lại sau khi tắt các server, mở PowerShell tại gốc project:

```powershell
# Khởi động PostgreSQL nếu đang tắt.
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONUTF8 = '1'
& .\.conda\python.exe scripts/local_setup.py start

# Terminal 1: backend dùng database team đã khôi phục.
powershell -NoProfile -ExecutionPolicy Bypass -File .local/stack-check/run-backend.ps1
```

Trong terminal thứ hai, cũng tại gốc project:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .local/stack-check/run-frontend.ps1
```

Dừng server đang chạy bằng Ctrl+C trước khi chạy lại để tránh trùng cổng. Launcher
backend riêng đặt `DATABASE_NAME=edums_team_check_20261026` cho tiến trình con;
chạy `backend/run_dev.ps1` trực tiếp vẫn đọc database `edums` trong cấu hình cũ.

## Bằng chứng local

- [Kết quả HTTP](../.local/stack-check/smoke-results.json).
- [Kết quả trình duyệt](../.local/stack-check/browser-results.json).
- [Ảnh trang học sinh](../.local/stack-check/browser-student.png).
- [Ảnh cây kiến thức](../.local/stack-check/browser-knowledge.png).
- [Ảnh không gian bài làm sau khi lưu nét](../.local/stack-check/browser-ink-persisted.png).

Các bản sao SQL, log, thông tin đăng nhập thử, cache và dữ liệu browser được lưu
trong `.local/stack-check`, vốn nằm ngoài Git theo `.gitignore` hiện tại.
