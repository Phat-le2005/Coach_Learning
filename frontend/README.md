# EduMS frontend

Next.js App Router frontend cho EduMS. Phase hiện tại thiết lập **EduMS Verdant** (`Nature × Future × Learning`) và visual experience của Student Home tại `/student`.

## UI preview

Preview data chỉ dùng để duyệt thiết kế. Sao chép `.env.example` thành `.env.local` và bật:

```text
NEXT_PUBLIC_UI_PREVIEW_MODE=true
```

Khi flag là `false`, Student Home hiển thị disconnected state có chủ đích và không hiển thị số liệu giả. Chưa có auth hoặc Student Learning State API integration trong phase này.

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

Đọc `AGENTS.md` và tài liệu tương ứng trong `node_modules/next/dist/docs/` trước khi thay đổi convention của Next.js 16.
