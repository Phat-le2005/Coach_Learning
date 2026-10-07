# EduMS frontend

Next.js App Router frontend cho EduMS. Phase hiện tại thiết lập **EduMS Verdant** (`Nature × Future × Learning`) và visual experience của Student Home tại `/student`.

## UI preview

Preview data chỉ dùng để duyệt thiết kế. Từ thư mục repository, cài dependency và vào frontend:

```bash
cd frontend
npm install
```

Sao chép `.env.example` thành `.env.local` và bật:

```text
NEXT_PUBLIC_UI_PREVIEW_MODE=true
```

Khi flag là `false`, Student Home hiển thị disconnected state có chủ đích và không hiển thị số liệu giả. Chưa có auth hoặc Student Learning State API integration trong phase này.

Khởi động development server:

```bash
npm run dev
```

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
npm run typecheck
npm run build
npm run check
```

## Validation

Chạy validation từ một dependency tree tái lập bằng lockfile:

```bash
npm ci
npm run typecheck
npm run build
```

`npm run typecheck` chạy `next typegen` trước `tsc --noEmit`, vì vậy typecheck không phụ thuộc vào `.next/` từ một lần chạy development trước đó. `next-env.d.ts` và `.next/` đều do Next.js sinh và không được theo dõi trong Git.

Đọc `AGENTS.md` và tài liệu tương ứng trong `node_modules/next/dist/docs/` trước khi thay đổi convention của Next.js 16.
