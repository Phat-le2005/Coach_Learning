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
```

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
