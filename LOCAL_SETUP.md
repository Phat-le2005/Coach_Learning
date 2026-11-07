# Coach Learning — một repository, một thư mục làm việc

Đây là hướng dẫn hiện hành cho clone mới. Các báo cáo OCR cũ có tên worktree, port,
SHA và tài khoản QA lịch sử; chúng không phải điều kiện chạy ứng dụng.

## Chạy ứng dụng chính từ clone sạch (Windows PowerShell)

Yêu cầu: Git, Node.js >=20.9, Python3.12, PostgreSQL và pgvector theo
[README](README.md#postgresql). Không cần Gemini, CodeGraph, GPU hoặc Python OCR
để dùng MathWorkspace Geometry+CoMER. Graphify là công cụ development tùy chọn.

```powershell
git clone https://github.com/Phat-le2005/Coach_Learning.git
cd Coach_Learning
```

Chỉ tại clone mới: tạo `backend/.env` từ `backend/.env.example`, điền database riêng,
`DATABASE_PASSWORD` và `JWT_SECRET_KEY` ngẫu nhiên. Tạo PostgreSQL database/user và
extension theo README; không copy database riêng tư từ máy tác giả, không reset DB.

```powershell
# Dùng đường dẫn Python3.12 thực tế trên máy bạn nếu python đang trỏ sang bản khác.
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-lock.txt
cd backend
.venv/Scripts/python.exe -m app.database.check
.venv/Scripts/python.exe -m alembic upgrade head
# Chỉ trên DB development mới: đặt SEED_DEMO_PASSWORD trong .env, rồi seed tường minh.
.venv/Scripts/python.exe -m app.seed
.venv/Scripts/python.exe -m app
```

Terminal thứ hai, từ root repo:

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local  # Chỉ khi chưa có .env.local; không ghi đè cấu hình cũ.
# Điền AUTH_SESSION_SECRET ngẫu nhiên >=32 ký tự và API_BASE_URL phù hợp.
# Tạo secret: node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"
cd ..
powershell -ExecutionPolicy Bypass -File tools/start-local.ps1
```

Mở `http://127.0.0.1:3000`, đăng nhập bằng tài khoản đã tạo/seed trong DB của bạn.
Không có tài khoản/mật khẩu tác giả được nhúng trong repository. Self-study publication
được khai báo trong `frontend/.env.local` bằng `SELF_STUDY_PUBLISHED_SUBJECT_CODES`.
CoMER ONNX int8, vocab, ORT/WASM và license đi kèm đã được track tại
`frontend/public/ocr/`; không tải model ngẫu nhiên khi bấm OCR.

Sau khi cập nhật một checkout đã có, chạy lại `npm ci` và cài lại
`backend/requirements-lock.txt` vào **venv của checkout hiện tại**. Live Sync cần
`websockets==15.0.1` trong lockfile; một venv cũ thiếu package này vẫn trả HTTP health
200 nhưng không nhận WebSocket. Không dựa vào venv của worktree đã bỏ.

## Live Sync / điện thoại

Chế độ LAN tự động (hai terminal PowerShell ở repo root; không sửa IP trong `.env`):

```powershell
# Terminal 1: dùng database/.env hiện tại, không seed/reset.
./tools/start-backend.ps1 -Lan -Port 8000 -FrontendPort 3000
# Terminal 2:
./tools/start-local.ps1 -Lan -Port 3000 -ApiUrl http://127.0.0.1:8000
```

Laptop mở `http://localhost:3000`, đăng nhập và chọn **Kết nối thiết bị viết**.
QR dùng IP LAN đang hoạt động; điện thoại cùng mạng quét rồi laptop cho phép.
Khi đổi Wi-Fi/IP, launcher tự phát hiện mỗi5 giây và refresh frontend để Next cập nhật
địa chỉ development hợp lệ; backend giữ nguyên. Mở lại hộp kết nối nếu trang được
reload và quét mã mới. Không cần sửa `NEXT_PUBLIC_APP_URL`, `MATH_INK_WS_ORIGIN`
hoặc `LIVE_INK_ORIGINS` trong chế độ này. Cả hai launcher phải bật `-Lan`,
`-FrontendPort` backend phải khớp `-Port` frontend. Có thể thêm `-Lab` ở frontend.

Chế độ tự động hiện dành cho local development IPv4 private (10/172.16–31/192.168),
không bật trong production. Windows dùng bảng interface OS để tránh DNS cache cũ.
Không tự thay firewall hay mở public tunnel. Router/hotspot cần cho phép hai thiết bị
truy cập nhau; cùng tên Wi-Fi không đảm bảo nếu mạng bật client isolation.
Mã/phiên cũ ràng buộc origin nên phải quét lại khi IP đổi. Nét đã được server ACK
vẫn giữ nguyên; bản nháp chưa ACK trên origin cũ không tự chuyển sang origin mới.
Giữ trang cũ và dữ liệu trình duyệt nếu còn nét chờ đồng bộ; không xóa storage.

[Hướng dẫn chi tiết](docs/mathcanvas-live-device-sync.md). Laptop và điện thoại phải
truy cập cùng một origin qua IP LAN hoặc domain HTTPS; localhost trên điện thoại
không trỏ về laptop. Backend allowlist đúng origin, frontend bind `0.0.0.0`, đặt
`NEXT_PUBLIC_APP_URL` và `MATH_INK_WS_ORIGIN` theo IP/domain mà cả hai thiết bị truy cập.
Không dùng `0.0.0.0` trong QR, không nhúng bearer token vào QR. QR hiện dùng approval
trên laptop và cookie HttpOnly chỉ có quyền viết; điện thoại không phải đăng nhập
tài khoản học sinh. Stroke operation ACK mới được coi là đã lưu. Relay hiện single-worker.

## OCR Research Lab trong cùng ứng dụng

```powershell
powershell -ExecutionPolicy Bypass -File tools/start-local.ps1 -Lab
```

Sau đăng nhập mở `/ocr-v2-lab` hoặc `/ocr-v2-lab/evaluation` trên cùng port3000.
Lab bị 404 trong production và khi không bật cờ, kể cả API. Không cần checkout khác.
MathWorkspace và Lab dùng cùng `ocr-v2-scope-candidates.ts`; Lab giữ bộ adapter/probe,
annotation và benchmark riêng. Viết trực tiếp hoặc import capture qua UI; thiếu model
optional được báo rõ, Geometry+CoMER vẫn dùng được. Lab không gửi bước đi chấm.

Các model local optional không đưa lên Git. Internet chỉ cần khi cài dependencies/
tải weights; inference gửi tới loopback, không gửi ảnh sang cloud AI. Mỗi môi trường
Python tách biệt, không nâng cấp Paddle của backend hoặc dùng Python toàn cục để infer.

| Model | Setup | Start/health/stop | Giới hạn |
|---|---|---|---|
| PP-DocLayout-M | `tools/local-models.ps1 -Component layout -Action setup -Python <python3.12>` | `-Component layout -Action start` chạy foreground port8031; Ctrl+C dừng; `-Action health` kiểm tra | Apache-2.0; Geometry fallback nếu thiếu. V3 chưa được xác nhận tương thích. |
| VietOCR handwritten | `tools/local-models.ps1 -Component htr -Action setup -Python <python3.12>` | `-Component htr -Action start`, `health`, `stop`; loopback8041 | CPU; không cần các crop private để setup/chạy scope mới. |
| Uni-MuMER Q4_K_M | `tools/local-models.ps1 -Component unimumer -Action setup -Python <python3.12> -Runtime cpu` | `-Component unimumer -Action start -Runtime cpu`, `health`, `stop` | CPU hoặc `-Runtime cuda` để tải runtime CUDA và chạy hybrid; không bắt buộc GPU. |

Các lệnh là PowerShell, chạy từ repo root. Trên Windows có thể thêm
`powershell -ExecutionPolicy Bypass -File` trước `tools/local-models.ps1`.
Layout start tạo token trong `.tmp/tri-ocr-v2-runtime/service-token.txt`; frontend launcher
`-Lab` đọc token khi start. Muốn app chính dùng cùng detector, cấu hình riêng
`OCR_LAYOUT_SERVICE_URL=http://127.0.0.1:8031` và `OCR_LAYOUT_SERVICE_TOKEN` trong
`.env.local`; token không đặt vào `NEXT_PUBLIC_*`. Restart frontend sau khi đổi env.

Danh tính/chính sách assets: [model catalogue](docs/ocr-v2/MODELS.md).
Không dùng `manage.cjs start` để dựng một frontend khác nếu đã dùng launcher chung.
Các script `verify_*.cjs`, `report*.cjs` cũ cần dữ liệu QA riêng và session manifests;
chúng là replay nghiên cứu, không phải lệnh setup mặc định cho clone mới.

## Dữ liệu nghiên cứu và bản sửa riêng

Capture native, annotations/ground truth, `.env`, database, cache, weights và evidence
của tác giả không được phát hành lên GitHub. Bản bảo toàn local có manifest/hash tại
vị trí ghi trong báo cáo consolidation trên máy tác giả. IndexedDB thuộc browser
origin: export annotation/review trước khi đổi IP/port/trình duyệt. Không xóa browser
storage hay database để chữa lỗi setup.

Clone mới vẫn viết/import/annotate/benchmark được. Ba HTR crops cũ chỉ xuất hiện nếu
bạn import archive private hợp lệ; catalogue trống không phải model lỗi. MathWriting
chỉ dùng cho nghiên cứu phi thương mại theo license nguồn; tùy chọn tải excerpt:

```powershell
python tools/ocr-v2-lab/prepare_evaluation.py
```

Script kiểm SHA, không tự đọc thư mục Downloads của tác giả. Nếu muốn thêm native
capture local vào index, đặt `OCR_NATIVE_CAPTURE` tới file của bạn. Screenshot không
thay vector ink, prediction không phải ground truth, synthetic layout không phải
native full-page accuracy. [Evaluation UI](docs/ocr-v2/EVALUATION_README.md).

## Kiểm tra và giới hạn đã biết

```powershell
cd frontend
npm test
npm run test:ocr-lab
npm run typecheck
npm run build
cd ..
python -m unittest discover -s tools/ocr-v2-lab -p test_portable_setup.py
backend/.venv/Scripts/python.exe -m pytest backend/tests/math_solutions/test_live_ink.py backend/tests/math_solutions/test_ink_pairing.py -q
```

PostgreSQL concurrency acceptance cần DB QA riêng theo tài liệu Live Sync; không
trỏ test vào DB học sinh. Một số CI backend/data có lỗi baseline ngoài consolidation;
không coi PASS frontend là PASS mọi backend/model/accuracy.

OCR chính vẫn còn giới hạn TEXT/MIXED routing, reading order và vocabulary của CoMER.
VietOCR/Uni trong Lab không đồng nghĩa app chính đã tự nhận dạng hoàn hảo toàn trang.
OCR giữ nguyên lời giải sai; review khác grading; không tự approve/submit. Phạm vi
Evaluator và rubric giữ nguyên. Đọc [TEAM_HANDOFF](docs/ocr-v2/TEAM_HANDOFF.md) để biết
hợp đồng lưu bước hiện tại; không ép STRUCTURE/UNKNOWN thành CUSTOM để bỏ mất dữ liệu.
