# MathCanvas: kết nối thiết bị viết

Tính năng nằm trong **MathWorkspace chính**: `/student/attempts/<attemptId>`.
Chọn **Kết nối thiết bị viết**, đăng nhập cùng tài khoản STUDENT trên điện thoại/iPad,
rồi mở link/QR. Link chỉ chứa attempt, trang và chế độ hiển thị; không cấp quyền đọc bài.
Không có thay đổi schema database, OCR, CAS, Evaluator hay định dạng InkStroke.

## Khởi động và dùng qua LAN

Dùng feature branch `feat/mathcanvas-live-device-sync`. Cài theo README của dự án,
với PostgreSQL và cấu hình xác thực hiện có. Ví dụ PowerShell, từ repository:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
# backend/.env: cấu hình database và JWT_SECRET_KEY theo .env.example.
# Không seed/reset database đang có bài làm.
$env:FRONTEND_URL = 'http://192.168.1.20:3000'
# Nếu cũng dùng localhost trên laptop, cho phép thêm origin đó một cách tường minh.
$env:LIVE_INK_ORIGINS = 'http://localhost:3000'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --ws-max-size 300000
```

Terminal thứ hai:

```powershell
cd frontend
npm ci
# frontend/.env.local: AUTH_SESSION_SECRET ngẫu nhiên >=32 ký tự, cấu hình auth hiện có.
$env:API_BASE_URL = 'http://127.0.0.1:8000'
$env:MATH_INK_WS_ORIGIN = 'ws://192.168.1.20:8000'
$env:NEXT_PUBLIC_APP_URL = 'http://192.168.1.20:3000'
$env:SESSION_COOKIE_SECURE = 'false' # Chỉ cho HTTP phát triển nội bộ.
npm run dev -- --hostname 0.0.0.0
```

Thay `192.168.1.20` bằng IP LAN thật của laptop (`ipconfig`). Mở cùng địa chỉ
`http://192.168.1.20:3000` trên cả hai máy, đăng nhập và mở bài đang chỉnh sửa.
Frontend và backend phải cùng truy cập được từ điện thoại; localhost trên điện thoại
không trỏ về laptop. Nếu firewall chặn, chỉ cho phép các cổng cần thiết trên mạng
Private tin cậy theo chính sách máy. Không tự mở firewall hoặc public tunnel.
`NEXT_PUBLIC_APP_URL` cũng cấu hình Origin BFF và allowedDevOrigins của Next; đặt
trước khi khởi động/build. Không cho phép Origin lạ chỉ dựa vào Host do client gửi.

Trong hộp kết nối có QR, link sao chép, danh sách thiết bị **trên trang hiện tại**,
trạng thái và số thao tác chưa có ACK. QR localhost được thay bằng hướng dẫn nhập
địa chỉ LAN. Nhấn **Ngắt kết nối thiết bị này** chỉ ngắt thiết bị hiện tại sau khi
đã lưu hết. Để dừng toàn bộ, ngắt trên từng thiết bị/đóng trang; logout làm mất quyền
khi heartbeat kiểm tra lại session. Không có link chia sẻ ẩn danh.

Chế độ **viết cảm ứng** dùng chính MathCanvas, Pointer Events/pointer capture,
tọa độ [0,1], DPR và tỷ lệ A4; không gửi ảnh màn hình. Toolbar có bút, tẩy, undo/redo,
zoom và chuyển trang. Một pointer ghi nét tại một thời điểm; pointer phụ không kết
thúc nét đang viết. Pointer cancel giữ phần nét đã thu nhận như một stroke hoàn tất.
Không chuyển trang hoặc đổi transport khi đang giữ bút. Chọn **Về MathWorkspace**
để trở lại bố cục đầy đủ, vẫn giữ cùng trang và transport.

## Kiến trúc và protocol

```text
MathCanvas → nét nháp cục bộ → WS BEGIN/POINTS/END → nét nháp trên thiết bị khác
           → pointerup → IndexedDB operation outbox → BFF POST operations
               → MathInk transaction + operation journal → DB commit
               → HTTP ACK / WS STROKE_COMMITTED → canonical page + revision
```

Các endpoint backend dưới `/api/v2/math-solutions/attempts/{attemptId}/ink`:

| Endpoint | Mục đích |
|---|---|
| `POST /live-ticket` | JWT/session + STUDENT + ownership/editable → ticket 30 giây, dùng một lần, gắn origin/attempt/page |
| `WS /live` | Origin allowlist; frame đầu `{type:"AUTH", ticket, label}` trong 5 giây; không đưa token lên URL |
| `POST /pages/{pageIndex}/operations` | `{client_action_id, expected_document_revision, add: InkStroke[], remove: InkStroke[]}` |
| `GET /pages/{pageIndex}` | Canonical snapshot cho resync/conflict |

Browser gọi BFF cùng origin, HttpOnly cookies và CSRF; bearer chỉ nằm ở server.
WS stream dùng full-prefix stroke có `seq` tăng dần, tối đa 20 lần/giây khi kéo bút;
frame cũ/trùng bị bỏ. Nhận `STROKE_END` **chưa có nghĩa đã lưu**. Relay không nhận
lệnh ghi database qua WS. `PRESENCE`, `PAGE_AVAILABLE`, `PAGE_SNAPSHOT` và
`STROKE_COMMITTED` là sự kiện server. Có heartbeat/resync mỗi 5 giây, reconnect
backoff 1–10 giây và cấp lại ticket. Session/editable được kiểm tra lại khi bắt đầu
nét và heartbeat; socket được cấp lại quyền sau tối đa 15 phút.

Ghi durable dùng khóa attempt/document như PUT cũ. Revision conflict dẫn đến tải
canonical rồi gửi lại **cùng intent và action ID**, không gửi một snapshot thay thế.
Hash idempotency không chứa revision để cùng intent có thể rebase. ACK replay trả
canonical hiện tại; cùng action ID với intent khác bị từ chối. Stroke ID hiện hữu
không được sửa nội dung bằng thao tác append. Remove kèm nét đã thấy: nếu cùng ID
bị sửa qua PUT cũ thì conflict, không xóa âm thầm.

Clear chỉ xóa các IDs đã hoàn tất đang thấy lúc bấm; nét thiết bị khác đang viết
hoặc thêm sau đó được giữ.
Undo/redo đảo **thao tác cục bộ**, không phục hồi snapshot toàn trang, không undo
cả trang của thiết bị khác. History giới hạn 30 và reset khi đổi trang/reload/đổi
transport; đây là chính sách riêng của live mode. Erase/clear và undo đều cần ACK.

Trước khi bật live, chờ PUT đang chạy và lưu/đối soát bản nháp legacy. Khi live bật,
MathWorkspace ngừng hẳn PUT autosave cho trang đang viết; canonical snapshots đi
vào cùng page memory dùng bởi OCR. OCR vẫn đòi snapshot/source revision nhất quán;
không chạy OCR trên sự kiện nét nháp. Không có lời gọi grading/submit tự động.

Outbox IndexedDB giữ nguyên action ID qua reconnect/reload, xóa sau ACK. Snapshot
mới không xóa pending intent; client replay intent lên canonical để hiển thị.
Legacy dirty draft khác server vẫn chặn kích hoạt và cho phép sao lưu, không được
áp lên một revision mới một cách mù quáng. Không đánh dấu SAVED trước ACK; nét
nháp từ thiết bị khác cũng được ghi rõ là chưa lưu. Nếu IndexedDB lỗi, bản nháp
trong memory còn giữ và hiện lỗi; cần xuất bản nháp, không đóng trang.

Outbox quá **24 giờ** không tự replay vì journal idempotency có retention 7 ngày.
Cần xuất bản nháp/đối soát trong tình huống này; không có automatic merge lịch sử
vô hạn. Chuyển trang/ngắt kết nối bị chặn khi còn thao tác chưa xác nhận.

## Bảo vệ và triển khai

- Giữ giới hạn MathInk: 30 trang, 400 stroke/trang, 3000 điểm/stroke, 15000 điểm/trang,
  codec 512 KiB raw/320 KiB compressed; HTTP ink body 768 KiB. Không cắt bớt nét để
  vượt budget. Lỗi budget giữ pending và hiện lỗi, không báo đã lưu.
- WS frame tối đa 300000 byte (cấu hình uvicorn + validation), 35 message/giây/socket;
  durable writes 20/giây/actor, tối đa 8 socket/trang và ticket có quota.
- HTTPS production bắt buộc cấu hình `MATH_INK_WS_ORIGIN=wss://<backend-public-origin>`;
  backend phải phục vụ WSS qua reverse proxy/TLS. Bật secure cookies, cấu hình đúng
  `FRONTEND_URL`/`LIVE_INK_ORIGINS`. Không có wildcard Origin.
- Nếu chung domain, reverse proxy phải chuyển **WS upgrade** cho đường
  `/api/v2/math-solutions/attempts/<uuid>/ink/live` tới backend, không tới Next BFF.
  Có thể dùng backend domain riêng; browser không cần bearer cookie của domain đó.
- Relay/tickets/presence **in-memory, chỉ hỗ trợ một backend worker/instance**.
  Không cấu hình nhiều worker/replica cho live trước khi có shared broker/tickets.
  DB locking vẫn bảo vệ ghi nhưng không tạo được fanout đa worker.
- Chưa chứng nhận Safari iOS/Apple Pencil hay điện thoại vật lý; browser acceptance
  dùng hai Chrome contexts, mobile viewport và pointer replay, không phải chữ viết tay
  mới. Không tuyên bố hỗ trợ Internet nếu chưa triển khai hostname/TLS/network phù hợp.

## Kiểm thử có thể chạy lại

Backend thông thường (SQLite schema cách ly):

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/math_solutions/test_live_ink.py tests/math_solutions/test_ink_service.py tests/math_solutions/test_ink_body_limit.py -q
```

Để chạy thêm race test PostgreSQL, đặt `EDUMS_TEST_DATABASE_URL` tới database QA riêng.
Fixture tạo schema ngẫu nhiên, chỉ dọn schema của chính nó. Không dùng DB production.

Browser acceptance có harness thật, database QA riêng, không mock WS/auth/persistence:

1. Tạo PostgreSQL/pgvector database riêng có tên kết thúc `_qa`, loopback. Cài dependencies
   từ lockfile trong venv của feature worktree. Không dùng dữ liệu/bảng đang có của dự án.
2. Terminal backend:

```powershell
$env:LIVE_QA_DATABASE_URL = 'postgresql+psycopg://<qa-user>:<qa-password>@127.0.0.1:5544/edums_live_qa'
$env:LIVE_QA_ARTIFACT_DIR = '<repo>\.tmp\tri-mathcanvas-live-sync'
.\.venv\Scripts\python.exe -m tests.math_solutions.live_sync_harness
```

Harness tạo schema mới và tài khoản QA, giữ dữ liệu để điều tra, lắng nghe `127.0.0.1:8050`.
`qa-session.json` chỉ dùng local, không commit. Tắt bằng Ctrl+C, không tự xóa database.
Để chạy QA qua IP LAN: đặt `LIVE_QA_FRONTEND_ORIGIN=http://<IP>:3050`,
`LIVE_QA_BIND_HOST=0.0.0.0`, frontend bind `0.0.0.0`, public frontend/WS origins tương ứng.
Đây vẫn là test qua địa chỉ LAN trên browser laptop; không thay cho test điện thoại vật lý.

3. Frontend dev: `API_BASE_URL=http://127.0.0.1:8050`, cấu hình secret auth mới, HTTP
   cookie cho QA, rồi `npm run dev -- --port 3050 --hostname 127.0.0.1`.
4. Terminal frontend khác:

```powershell
$env:E2E_BASE_URL = 'http://127.0.0.1:3050'
$env:LIVE_QA_SESSION_FILE = '<repo>\.tmp\tri-mathcanvas-live-sync\qa-session.json'
$env:LIVE_QA_ARTIFACT_DIR = '<repo>\.tmp\tri-mathcanvas-live-sync'
$env:PW_HEADLESS = '1'
npx playwright test e2e/live-ink.spec.ts --reporter=list
```

Harness mới cho mỗi lượt acceptance (mỗi lần khởi động tạo schema/attempt mới).
Spec kiểm tra stream trước pointerup, hai chiều, concurrent append, offline outbox,
reconnect, reload, erase/clear/undo/redo, page navigation, QR UI và không gọi steps/submit.
Trace/video tắt để không ghi auth cookies/tickets. PNG và JSON acceptance không chứa token.

Frontend targeted checks:

```powershell
npm run test:compile
node --test .test-build-run/tests/live-ink.test.js .test-build-run/tests/math-ink-geometry.test.js .test-build-run/tests/draft-recovery.test.js .test-build-run/tests/math-ocr-sync.test.js .test-build-run/tests/math-workspace-path.test.js
npm run typecheck
npm run build
```

## Xử lý sự cố

`LIVE_ORIGIN_DENIED`: thêm đúng origin frontend vào allowlist backend, không nới wildcard.
`LIVE_WSS_REQUIRED`: cấu hình địa chỉ WSS công khai cho HTTPS/production và restart frontend.
`reconnecting/offline`: kiểm tra điện thoại tới được cổng backend WS; để nguyên trang/outbox.
`INK_REVISION_CONFLICT`: tự resync/rebase có giới hạn; nếu tiếp tục tranh chấp, giữ pending
và thử lại. `INK_STROKE_CONFLICT`/budget/nháp >24 giờ: xuất bản nháp rồi đối soát; không
xóa IndexedDB để làm mất cảnh báo. Các draft nháp mờ của thiết bị đã rời phòng tự hết hạn;
chỉ canonical stroke sau ACK được xem là đã lưu.
