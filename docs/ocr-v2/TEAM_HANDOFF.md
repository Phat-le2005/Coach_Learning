# OCR V2 trong MathWorkspace

> Cập nhật budget sau tích hợp: giới hạn lưu trang hiện là **512 KiB raw / 320 KiB compressed / 768 KiB request**. Giữ nguyên 400 nét/15.000 điểm và kiểm tra giải nén. Capture71 từng bị chặn ở mức256KiB đã được lưu/tải nguyên vẹn qua API QA (HTTP200, 71 nét/4.114 điểm); mô tả giới hạn256KiB bên dưới là kết quả lịch sử trước cập nhật này.

Nhánh `feat/ocr-v2-core-integration` lấy nền từ main `f73b93618a151814558e294be8b7aa7c708d784d`. **Trích xuất trang dùng OCR V2 mặc định**, không cần research flag. Không thêm canvas khác, không có route Lab/evaluation/dataset/Oracle trên nhánh này.

## Luồng đang chạy

MathCanvas hiện có → kiểm tra batch recovery → lưu/đợi ink đúng revision → snapshot bất biến → Geometry V2 hoặc Hybrid → stroke scopes có ownership → MATH chạy CoMER ONNX/WASM trong browser → IR 1.1 → học sinh đối chiếu/sửa/xác nhận nội dung và thứ tự.

Detector chỉ là bằng chứng. Chưa cấu hình, lỗi, timeout hoặc không có box: dùng **Geometry V2**, không dùng segmentation V1/V2 cũ làm fallback. Engine/mode và tình trạng detector hiển thị trong modal. Nhãn TEXT/UNKNOWN không bị ép qua CoMER; người dùng có thể chọn lại loại hoặc nhập tay. Output CoMER là bản chép, không xác định đúng/sai toán học.

Nút **Trích xuất trang** hiện có là entrypoint mới. Math View/lasso, paper/PDF flow, drawing/erasing, undo/redo, điều hướng trang, ink sync, attempt APIs, idempotency và journal recovery giữ đường xử lý hiện có. `page-ocr.ts` còn cho compatibility/tests và các thao tác legacy; nó không chọn scopes cho entrypoint mới.

## Cài và chạy độc lập

Node >=20.9, backend/PostgreSQL và tài khoản local theo README của dự án. Ví dụ clone mới:

```powershell
git clone --branch feat/ocr-v2-core-integration https://github.com/Phat-le2005/Coach_Learning.git Coach_Learning_OCR
cd Coach_Learning_OCR/frontend
npm ci
Copy-Item .env.example .env.local
# Điền API_BASE_URL, AUTH_SESSION_SECRET ngẫu nhiên >=32 ký tự và cấu hình cookie theo example.
# OCR_LAYOUT_SERVICE_URL / OCR_LAYOUT_SERVICE_TOKEN để trống cho Geometry.
npm run dev
```

Chỉ copy `.env.example` trong clone mới chưa có cấu hình. Backend cần cấu hình `.env`/venv riêng theo README hiện có; không dùng database/tài khoản production cho QA. Không cần Python layout service để dùng Geometry + CoMER. Không cần bất kỳ file research `.tmp`, đường dẫn máy tác giả, MathWriting hoặc credential nghiên cứu nào.

Mở `http://localhost:3000`, đăng nhập, vào bài giải tại `/student/attempts/<attempt-id>`. Viết trên giấy A4 hiện có rồi bấm **Trích xuất trang**. CoMER/vocab/ORT được phục vụ từ `frontend/public/ocr/` đã có trên main; setup không tải model vào request. Giữ các file LICENSE đi kèm assets. Inference không gọi Gemini/GPT/cloud OCR.

## Review và lưu bước

1. Chọn từng đơn vị trong danh sách phân cấp, so ink với raw CoMER, sửa transcript và chọn MATH/TEXT/UNKNOWN nếu cần. Công thức có preview KaTeX; HTR tiếng Việt chưa có nên TEXT nhập nguyên văn.
2. Xác nhận nội dung/cấu trúc từng đơn vị; container cần children và quan hệ đã xác định. Container không cần LaTeX giả. Dùng lên/xuống rồi xác nhận thứ tự đọc.
3. Trong **Điều chỉnh phạm vi / cấu trúc**, chọn nhiều đơn vị để gộp hoặc khoanh nét để tách/gán lại. Tạo/tháo cấu trúc giữ nguyên children và nguồn nét. Thực hiện thay đổi phạm vi trước khi lưu bước; sau khi lưu, bindings được khóa để tránh lệch với server.
4. Muốn lưu một bước đơn giản: chọn một **atomic root MATH/TEXT đã xác nhận**, tick quyết định nó là một bước riêng và tự chọn StepKind. Bấm **Tiếp tục lưu bước đã chọn**, kiểm tra màn hình lưu rồi **Lưu ngay bước này**. Bộ lưu dùng journal/idempotency cũ, kể cả khi chỉ có một bước.
5. Bước được nối cuối danh sách server. Các đơn vị chưa chọn vẫn giữ trong bản chép. STRUCTURE, children trong container và UNKNOWN không được tự chuyển sang legacy API. Nếu relation thực sự là independent, có thể tháo container tường minh trước khi chọn các bước; không tự hạ cấu trúc để gửi.

`Region != ContentUnit != GradingStep`. Projection tổng quát của IR vẫn PREVIEW_ONLY, `steps=[]`, `submitPayload=null`, `readyToSubmit=false`. `declareStepBoundary()` chỉ tạo intent sau quyết định người dùng, không phải adapter tự động 1:1. Không có bước tự submit/Evaluator/CAS. Lỗi toán học học sinh viết được giữ nguyên.

## Bản chép, provenance và recovery

`CoreReview` (`ocr-core-review/1`) gồm IR (`schemaVersion=1.1`), source snapshot/revision/page/attempt, scopes/stroke IDs, Geometry/Hybrid và detector status, relation proposals, evidence raw/selected/token IDs/timing, explicit boundary/action IDs và ledger bước đã lưu. Raw trước repair và selected output được giữ riêng. Beam score không được diễn giải thành calibrated confidence.

Bản chép/correction lưu trong IndexedDB `edums-ocr-transcription-v1`, theo attempt + SHA-256 của snapshot/revision; export JSON để sao lưu/chuyển tiếp. Backend giữ ink và các bước legacy được chọn tường minh; **chưa có API lưu toàn bộ Approved IR lên server**. Đổi browser/xóa site data sẽ mất bản chép local nếu chưa export. LocalVersion là concurrency metadata, không phải approval của evaluator.

Refresh rồi mở lại Trích xuất trang khôi phục đúng snapshot; không tự chạy lại model lên nội dung đã sửa. Retry model giữ correction thủ công và lưu raw evidence mới. Ink/revision thay đổi khóa duyệt/lưu snapshot cũ; source được kiểm tra lại trên server trước khi bắt đầu lưu và trước từng ADD_STEP. Hai tab không âm thầm ghi đè bản sửa: tab stale phải export rồi reload.

Journal batch hiện có vẫn là nguồn recovery cho mutations. Khi có pending/corrupt journal, OCR mới bị khóa đến khi phục hồi/xử lý an toàn. Không sửa schema journal hoặc backend contracts. Step API hiện chưa kiểm tra ink revision trong cùng transaction ADD_STEP; frontend kiểm tra ngay trước request nhưng chưa có cross-domain atomic revision contract. Không tuyên bố đã loại bỏ mọi race với chỉnh sửa từ xa.

## Layout-M tùy chọn

Service tách riêng tại `tools/ocr-layout-service/`, không import app backend/database. Dùng Python3.12, CPU, dependencies pin riêng:

```powershell
# Tại root repo; chỉ chạy setup khi muốn dùng Hybrid:
powershell -ExecutionPolicy Bypass -File tools/ocr-layout-service/setup.ps1 -Python python
$env:OCR_LAYOUT_SERVICE_TOKEN=(Get-Content -Raw .tmp/ocr-layout/service-token.txt).Trim()
& .tmp/ocr-layout/venv/Scripts/python.exe tools/ocr-layout-service/service.py --port 8016
```

Ở terminal frontend, đặt trong `.env.local`:

```dotenv
OCR_LAYOUT_SERVICE_URL=http://127.0.0.1:8016
OCR_LAYOUT_SERVICE_TOKEN=<token local đã tạo; không commit>
```

Restart frontend sau khi đổi env. URL chỉ được cấu hình server và chỉ nhận HTTP loopback. Token không đi vào `NEXT_PUBLIC_*`. API `/api/ocr/layout` yêu cầu signed session và same origin, giới hạn ảnh/request; không nhận URL/path từ client. Khi đã đăng nhập, GET endpoint này kiểm tra trạng thái service; trực tiếp `/health` cần bearer token từ terminal riêng.

Setup tải chính thức `PaddlePaddle/PP-DocLayout-M`, revision `7dbfcce3154a55776dc71ca026a4a2a8388dad8d`, license Apache-2.0; cache/manifests/SHA ở `.tmp/ocr-layout/models/`, ngoài Git. Worker chặn network ngoài loopback trong inference; weights chỉ tải ở setup. Không yêu cầu V3 hoặc Vietnamese HTR. Thiếu weights được báo MODEL_MISSING, không tạo box giả.

Cold load có thể vượt timeout request 12s và fallback Geometry; sau khi model warm có thể trích xuất lại. Warm Hybrid đã chạy model thật; không có bằng chứng nó luôn tốt hơn Geometry. Dừng service bằng Ctrl+C ở terminal chạy nó; Geometry tiếp tục hoạt động.

## Kiểm thử

```powershell
cd frontend
npm ci
npm test
npm run typecheck
npm run build
cd ..
# Nếu cài service tùy chọn:
& .tmp/ocr-layout/venv/Scripts/python.exe tools/ocr-layout-service/test_service.py
```

Browser QA runner dùng ứng dụng chính, backend QA thật và model thật:

```powershell
# Thiết lập backend/local QA theo frontend/e2e/README.md, dùng database riêng.
# Env bắt buộc: APP_ENV=test, QA_E2E_DATABASE_NAME, DATABASE_NAME, QA_E2E_PASSWORD.
# Có thể dùng QA_E2E_ENV_FILE, QA_BACKEND_ENV_FILE và PYTHON_EXE thay vì paths mặc định.
$env:E2E_BASE_URL='http://localhost:3000'
node tools/ocr-core/verify-workspace.cjs
node tools/ocr-core/verify-cases.cjs
```

QA helper fail-closed trước mọi provisioning. Runner không chứa mật khẩu; chỉ tạo/ghi các fixture của QA student riêng. Capture ngoài Git có thể truyền bằng `OCR_TEST_CAPTURE` (workspace runner), `OCR_TEST_CAPTURE_DIR` (quadratic/derivative/sigma/old-native-integral `.capture.json`) và `OCR_TEST_MIXED_CAPTURE` (case runner). Không có captures thì runner dùng software pointer/geometry fixtures và ghi rõ nguồn, không báo native accuracy. `OCR_TEST_ARTIFACT_DIR` tách output workspace runner; `OCR_EXPECT_ENGINE=HYBRID` chỉ dùng khi đã cấu hình detector.

## Đã xác minh và giới hạn

Đã chạy MathWorkspace thật: pointer replay capture14, Geometry tự tạo scope, CoMER raw `x ^ { 2 } + 3 x - 4 = 0`, correction/retry/refresh, explicit CUSTOM boundary, journal lưu đúng một bước và reload không trùng, không tự submit. Các capture13/22/25/10 đi qua API ink QA và model thật; chưa có nhãn độc lập để tuyên bố accuracy. Failure tests gồm thiếu CoMER rồi retry thật, revision server đổi, pending batch/recovery, TEXT/UNKNOWN và cấu trúc tường minh; riêng xác nhận UI automation không phải human GT.

Capture71 hiện không lưu nguyên bản được qua API main: khoảng272KB JSON nguồn, vượt budget raw256KiB sẵn có tại `backend/app/math_ink/codec.py`. Nét không bị rút gọn/drop; request trả413 trước OCR. Đây là giới hạn nền được giữ nguyên, cần quyết định riêng về storage/compression để dùng những trang quá budget. Không tăng limit backend trong lần tích hợp này.

Sigma, tích phân, căn bậc ba, dấu ngoặc, ký hiệu tương đương và nhiều cấu trúc vẫn có thể sai scope/recognition. Geometry abstain nhiều vùng chưa có math evidence. Vietnamese HTR chưa có; KaTeX/graph-parser support khác transcription fidelity. Các thử nghiệm nhỏ không chứng minh chất lượng tổng quát hoặc production accuracy. Backend/Data CI đỏ có sẵn trên main; không được sửa trong OCR migration.

Troubleshooting: không sync được → giữ ink draft và sửa lỗi sync trước OCR; model thiếu → nhập tay/retry, kiểm tra Network `/ocr/`; journal pending → dùng recovery hiện có; `REVIEW_CHANGED_IN_ANOTHER_TAB` → export bản đang xem rồi reload; revision đổi → trích xuất lại; quota IndexedDB → export backup. Không xóa `.tmp`/cache/database để chữa lỗi tùy tiện.


Core scope reconciliation hi?n ???c d?ng chung cho MathWorkspace v? Lab, g?m c?c s?a fraction/fragment ?? ???c ki?m tra native. Lab adapters, model t?y ch?n v? annotation kh?ng t? thay ???ng ch?m b?i production. C?c gi?i h?n TEXT/MIXED v? h?p ??ng l?u b??c b?n tr?n v?n ?p d?ng.
