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

## Gemini OCR và chấm bài viết tay

Trong `backend/.env`, đặt `AI_PROVIDER=gemini`, `MATH_OCR_PROVIDER=gemini` và
`AI_API_KEY` (hoặc `GEMINI_API_KEY`). OCR và chấm bài dùng cùng key phía máy chủ;
không điền key vào frontend hoặc biến `NEXT_PUBLIC_*`. Khởi động lại backend sau
khi đổi cấu hình.

Luồng làm bài: **Trích xuất trang (OCR)** → sửa bản chép, đối chiếu với nét gốc →
chọn loại bước, tích xác nhận nội dung/thứ tự → **Xác nhận & lưu bước** →
**Nộp bài & kiểm tra**. Trên điện thoại, chuyển giữa **Bản chép** và **Nét gốc**
để đối chiếu; nút lưu luôn ở cuối cửa sổ.
Gemini tự đề xuất các bước logic, tiêu đề và loại bước ngay trong lần OCR:
đạo hàm, giải phương trình (giữ cả các nghiệm), bảng xét dấu/biến thiên và kết luận
nếu học sinh có viết. Cả bảng giữ trong một bước. Bên trái hiển thị từng bước với
nét gốc tương ứng; sửa nội dung/loại hoặc đổi thứ tự khi cần, rồi chọn
**Xác nhận & lưu N bước** để lưu riêng theo thứ tự. Chỉ sau khi nộp, bộ chấm mới
đánh giá các bước đã lưu theo dữ liệu đề/đáp án/rubric.
Gemini chỉ chép lại nội dung nhìn thấy, giữ nguyên phép tính của học sinh.
Khi nộp, ứng dụng giữ nội dung đã sửa và xác nhận, không chạy OCR để ghi đè bước.
Nếu Gemini OCR lỗi, bản chép vẫn sửa được thủ công; giao diện hiển thị lỗi.

Chấm bài lấy đề, đáp án/lời giải đã duyệt và rubric hiện có của đúng câu hỏi;
bài giao dùng bản nội dung đã chốt khi giao. Thiếu dữ liệu tham chiếu hoặc rubric
thì không tự tạo điểm chính thức. Độ tin cậy OCR không phải điểm bài làm.

Kết quả chấm Gemini dùng nhóm lưu trữ `AI_HEURISTIC` hiện có trong database;
`GEMINI_REFERENCE` và trích dẫn đáp án được giữ trong `evidence_quote`/metadata.
Không ghi tên provider thành một giá trị mới ngoài ràng buộc `evaluator_type`.

Kiểm tra luồng giao diện bằng dữ liệu mẫu, không truy cập database:

```powershell
cd frontend
npx.cmd playwright test --config playwright.gemini-review.config.ts
```

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

## PDF bài tập trong kho học liệu giáo viên

Ảnh trong đề bài dùng chung danh sách `visuals` ở các trang xem học liệu, duyệt OCR,
làm bài học sinh, xem lại và chấm bài giáo viên. Backend tự đọc lại metadata ảnh từ
bản nhập OCR cũ; không cần nhập lại học liệu hoặc sửa snapshot bài đã giao. Khởi động
lại backend và tải lại trang sau khi cập nhật cả backend/frontend. API ảnh sử dụng
cookie đăng nhập qua frontend, không cần mở công khai thư mục ảnh. Ảnh đáp án/lời
giải chỉ gửi cho học sinh khi trạng thái bài đã nộp cho phép xem lời giải.

Khi chạy trên máy khác, cần dùng cùng backend/database/storage hoặc tải và duyệt lại
học liệu trên máy đó. Dữ liệu học liệu ở `backend/var/teacher_materials/` và nguồn OCR
mặc định ở `.tmp/teacher-pdf-imports/` là dữ liệu riêng, không được đưa vào Git.

Tại `/teacher?tab=materials`, cùng nút tải tài liệu nhận **PDF, ảnh PNG/JPG/JPEG**
để tạo bản nháp OCR; TXT vẫn đi theo luồng văn bản hiện có. Máy chủ gọi trực tiếp
`tools/pdf_metadata/ocr_pdf_direct.ps1` (layout + OCR + kiểm tra chất lượng hiện có),
chạy nền và giữ checkpoint. Giáo viên mở bản nháp, đối chiếu PDF/ảnh vùng nguồn,
sửa nội dung/đáp án/lời giải, tích duyệt từng câu và chọn **Lưu … câu vào kho**.
Các câu chưa duyệt được giữ trong bản nháp, không trở thành câu hỏi trong kho.
TXT vẫn dùng luồng tải tài liệu văn bản hiện có.

Ảnh gốc được giữ để đối chiếu, kiểm tra định dạng thực và hướng EXIF; ảnh được
bọc thành PDF một trang với pixel nén không mất dữ liệu rồi đi qua cùng pipeline.
Giới hạn upload 25 MB, ảnh tối đa 25 triệu pixel; PNG có nền trong suốt được đọc
trên nền trắng. Ảnh chưa có nhãn Câu/Bài được đưa thành một ứng viên cần giáo viên
kiểm tra ranh giới và tách đáp án/lời giải bằng phần chỉnh sửa. Không tự sinh đáp án.

Mỗi thẻ tài liệu có nút **Xóa** và hộp xác nhận tên tài liệu. Xóa gỡ tài liệu khỏi
kho, chặn tải/xem/sửa và giao mới. Bài đã giao, bài làm, bản snapshot và ảnh nguồn
mà bản chỉnh sửa khác đang sử dụng được giữ nguyên. Cơ chế này dùng trạng thái
`ARCHIVED`, không xóa vật lý các hàng/tệp vẫn cần cho lịch sử bài tập. API DELETE
kiểm tra quyền giáo viên trong lớp và gọi lại nhiều lần vẫn trả 204.

Mỗi câu có nút **Chỉnh sửa câu hỏi** để sửa đề bài, đáp án và lời giải, kèm bản
xem trước công thức. Gõ chữ trực tiếp; bấm vào công thức đang có hoặc chọn
**Chèn công thức** để mở trình soạn trực quan. Bảng có tìm kiếm tiếng Việt,
các nhóm phân số/căn/lũy thừa, đạo hàm/tích phân, hàm/lượng giác, quan hệ/tập hợp,
hình học/xác suất, chữ Hy Lạp và chữ/số. Chọn mẫu, điền các ô trống bằng bàn phím
hoặc các nút số/chữ rồi chèn; LaTeX được tạo tự động. Phần mã chỉ nằm trong mục
tùy chọn cho người muốn dùng. MathLive được ghim phiên bản trong `package.json`,
font được đóng gói cùng frontend; trình soạn không cần CDN hoặc dịch vụ AI.
Kiểm thử danh mục ký hiệu và bảo toàn nội dung: `cd frontend; npm.cmd run test:teacher-math`.
Nội dung đã sửa phải được tích duyệt lại. Chọn một trong bốn
mức **Nhận biết / Thông hiểu / Vận dụng / Vận dụng cao** cho mỗi câu được giữ lại;
bản nháp có thể để **Chưa phân loại**, nhưng khi lưu vào kho phải chọn đủ mức.
Mức giáo viên chọn được lưu cùng bản nháp, tệp đã duyệt và metadata câu hỏi;
được quy đổi sang thang difficulty hiện có lần lượt 0.25 / 0.5 / 0.75 / 1.0.
Không tự gán độ khó khi OCR không cung cấp mức hợp lệ.

Tài liệu đã lưu có đường **Xem nguồn / Chỉnh sửa** → **Chỉnh sửa & phân loại
câu hỏi**. Hệ thống tạo bản nháp chỉnh sửa từ nội dung đã duyệt, dùng lại OCR và
ảnh nguồn; khi lưu sẽ tạo tài liệu mới, giữ nguyên tài liệu cũ và bài đã giao.
Mở lại cùng một tài liệu sẽ tiếp tục bản nháp chỉnh sửa đang có.

Runtime PDF được thiết lập riêng theo [hướng dẫn công cụ](tools/pdf_metadata/README.md).
Ứng dụng không tải model hoặc cài dependency khi người dùng tải PDF. Cấu hình trong
`backend/.env`, rồi khởi động lại backend:

```ini
# Dùng đường dẫn runtime thực tế đã thiết lập trên máy của bạn.
TEACHER_PDF_RUNTIME_DIR=C:/CoachLearningPdf/pdf-pipeline-runtime
TEACHER_PDF_DEVICE=CPU
TEACHER_PDF_PORT=8790
```

Mặc định runtime là `.tmp/pdf-pipeline-runtime` tại root repo; thư mục bản nháp,
PDF nguồn, checkpoint và log là `.tmp/teacher-pdf-imports`. Có thể đổi bằng
`TEACHER_PDF_IMPORT_DIR` với đường dẫn tuyệt đối. Đây là luồng Windows/PowerShell
và runtime local hiện có của công cụ; thiếu runtime trả lỗi cấu hình rõ ràng.
Chọn `GPU` khi runtime CUDA đã được thiết lập, không tự cài CUDA từ luồng upload.

Khi Qwen đã chạy, công cụ tái sử dụng đúng PID, cổng và profile đã ghi nhận.
Nếu quyền của worker web không cho đọc đường dẫn tiến trình qua CIM, công cụ
đối chiếu trạng thái runtime và xác thực model qua khóa API local trước khi dùng
lại. Không nhận một tiến trình chỉ vì cổng đang mở, và không dừng model được nối
qua cơ chế này. Lỗi kết nối/profile được hiển thị riêng trong bản nháp OCR.

Bản đã duyệt được lưu thành **một tệp `.reviewed.json`**, gồm các câu đã chọn,
nội dung giáo viên sửa, đáp án/lời giải, thông tin nguồn và ảnh minh họa nhúng;
đồng thời lưu các câu này vào `teacher_material_items` để xem và giao cho lớp.
Nút **Tải bản đã duyệt** tải tệp này. PDF gốc được giữ riêng để đối chiếu,
không phải bản đã lọc. Trạng thái đã duyệt do giáo viên xác nhận, không đồng nghĩa
OCR tự đánh giá tính đúng sai hoặc tự bật chấm đáp án khách quan.

Bản nháp thuộc giáo viên tải lên và lớp được phân quyền. Lưu nháp giữ cả quyết định
và phần sửa để mở lại sau. Tác vụ OCR dùng khóa file để tuần tự hóa model; sau khi
backend khởi động lại, bấm **Tiếp tục xử lý** hoặc **Thử lại OCR** để dùng checkpoint.
Khi triển khai, giữ thư mục bản nháp và kho tệp trên ổ đĩa bền vững dùng chung cho
các worker; phiên bản này không có hàng đợi tác vụ phân tán. Không xóa thư mục bản
nháp nếu tài liệu đã duyệt còn tham chiếu ảnh nguồn.

Kiểm tra độc lập, không dùng database học sinh:

```powershell
cd backend
.venv/Scripts/python.exe -m pytest tests/teacher_materials -q
cd ../frontend
npm.cmd run typecheck
npm.cmd run test:compile
node --test .test-build-run/tests/teacher-api.test.js .test-build-run/tests/theory-api.test.js
npx.cmd playwright test --config playwright.pdf-review.config.ts
```

Kiểm thử trình duyệt dùng Next server riêng trên port 3106, phiên giáo viên test
tạm thời và phản hồi API cố định; kiểm thử backend dùng SQLite riêng. Không dùng
mô hình giả để xử lý upload thật. Chưa đo lại độ chính xác OCR toàn bộ sách bằng
luồng tích hợp này.

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
