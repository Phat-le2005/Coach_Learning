# EduMS frontend

Next.js 16 App Router frontend của EduMS, dùng visual system **EduMS Verdant / Learning Forest**. Runtime hiện kết nối FastAPI thật qua lớp BFF của Next.js; Student Home không đọc preview fixture hoặc synthetic student.

## Cấu hình local

```bash
cd frontend
npm ci
copy .env.example .env.local
```

Cập nhật `.env.local`:

```text
API_BASE_URL=http://127.0.0.1:8000
AUTH_SESSION_SECRET=<chuỗi ngẫu nhiên tối thiểu 32 ký tự>
SESSION_COOKIE_SECURE=false
AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS=604800
SELF_STUDY_PUBLISHED_SUBJECT_CODES=MATH_G12
```

> **Lưu ý bảo mật:** `AUTH_SESSION_SECRET` bắt buộc phải có độ dài tối thiểu 32 ký tự. Hệ thống từ chối khởi tạo phiên nếu secret ngắn hơn 32 ký tự hoặc để trống.
>
> Tạo secret ngẫu nhiên nhanh:
> - **PowerShell (Windows):** `-join ((65..90) + (97..122) + (48..57) | Get-Random -Count 48 | % {[char]$_})`
> - **Bash / macOS / Linux:** `openssl rand -hex 32`
> - **Node.js:** `node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"`

`API_BASE_URL` chỉ chứa origin. Client dùng đúng canonical root paths của FastAPI và không tự thêm `/api/v1`. Trong production, dùng HTTPS và bỏ `SESSION_COOKIE_SECURE=false` hoặc đặt thành `true`.

Khởi động FastAPI trước, sau đó chạy:

```bash
npm run dev
```

Mở `http://localhost:3000/login`. Token chỉ tồn tại trong HttpOnly cookie do Next Route Handlers quản lý; frontend không lưu token trong `localStorage`.

## Authentication boundary

- Browser gọi `/auth/login`, `/auth/refresh`, `/auth/me`, `/auth/logout` trên Next.js BFF.
- BFF chuyển tiếp ba endpoint canonical đầu tiên tới FastAPI và validate response runtime.
- Access/refresh token dùng HttpOnly cookie; session metadata có chữ ký HMAC; mutation dùng SameSite cookie, kiểm tra Origin và CSRF double-submit token.
- `src/proxy.ts` làm optimistic route guard. Mỗi server page vẫn kiểm tra session/role, còn authorization dữ liệu cuối cùng thuộc FastAPI.
- Backend contract hiện chưa có logout/revoke endpoint; logout frontend xóa cookie cục bộ, không tuyên bố thu hồi server session.
- `/student` đọc `GET /students/me/learning-state`. Trường backend chưa cung cấp hiển thị unavailable/empty state, không được lấp bằng số giả.

## Independent self-study boundary

- Student Home và Knowledge Forest hợp nhất phạm vi hoạt động thật từ `GET /students/me/learning-state` với hierarchy của `GET /students/me/mastery`.
- `SELF_STUDY_PUBLISHED_SUBJECT_CODES` là publication allowlist phía server. Mastery chỉ cung cấp read model curriculum; bản thân response mastery không phải bằng chứng rằng mọi subject đã được phát hành. Hiện môi trường phát triển cho phép `MATH_G12`.
- Subject có activity, assignment, goal hoặc lớp học thật vẫn được giữ nguyên dù không nằm trong allowlist tự học. Subject chỉ để khám phá phải vừa nằm trong allowlist vừa có hierarchy chapter → topic → problem type thật.
- Lựa chọn subject trước activity chỉ nằm trong URL điều hướng hiện tại. API v1 chưa có contract lưu đăng ký môn tự học độc lập; frontend không dùng `localStorage`, AcademicGoal giả hoặc lớp học giả để thay thế. Khi một practice session thật được tạo, Learning State sẽ nhận subject đó từ activity.
- Practice Workspace và bước kiểm tra câu hỏi `APPROVED` theo ProblemType thuộc FE-REAL-04. Knowledge Forest hiện chỉ chuẩn bị đúng subject/problem type và không tạo session rỗng.

## Design system

- Token màu, spacing, radius, shadow và breakpoint: `src/styles/tokens.css`.
- Global reset/canvas/accessibility: `src/app/globals.css`.
- Motion constants: `src/lib/motion.ts`.
- Motion dùng `motion/react` và phải tôn trọng `prefers-reduced-motion` thông qua `MotionProvider` cùng CSS fallback.
- UI control icons dùng `lucide-react`; nature decoration dùng CSS/SVG nội bộ.
- Feature styles dùng CSS Modules; không thêm framework UI hoặc utility CSS toàn cục.

## Commands

```bash
npm install
npm run dev
npm test
npm run typecheck
npm run build
npm run check
```

## Validation

Chạy validation từ một dependency tree tái lập bằng lockfile:

```bash
npm ci
npm test
npm run typecheck
npm run build
```

`npm run typecheck` chạy `next typegen` trước `tsc --noEmit`, vì vậy typecheck không phụ thuộc vào `.next/` từ một lần chạy development trước đó. `next-env.d.ts` và `.next/` đều do Next.js sinh và không được theo dõi trong Git.

Đọc `AGENTS.md` và tài liệu tương ứng trong `node_modules/next/dist/docs/` trước khi thay đổi convention của Next.js 16.
### Tài khoản thử nghiệm (Development)

| Vai trò | Email đăng nhập | Trang đích |
| :--- | :--- | :--- |
| 🎓 Học sinh (Student) | `student01.demo@example.com` | Student Home (`/student`) & Khu Rừng Tri Thức (`/student/knowledge`) |
| 👨‍🏫 Giáo viên (Teacher) | `teacher.math01.demo@example.com` | Teacher Dashboard (`/teacher`) |
| 👨‍👩‍👧 Phụ huynh (Parent) | `parent01.demo@example.com` | Parent Dashboard (`/parent`) |
| 🛡️ Quản trị viên (Admin) | `admin.demo@example.com` | Admin Dashboard (`/admin`) |

> Mật khẩu tài khoản demo được cấu hình trong môi trường phát triển (xem `backend/.env.example`), không commit thông tin mật khẩu thực tế vào kho mã nguồn.
9O4DgZI4uhZ5nf1yLHy1y3zyhdCRgUjp