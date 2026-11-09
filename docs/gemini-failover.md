# Gemini failover cho demo

`GeminiFailoverManager` dùng chung trong một tiến trình backend cho AI Gateway
(Tutor, gợi ý, review), OCR nét bút và OCR ảnh/PDF bài làm của học sinh. Pipeline
PDF giáo viên dùng Qwen local giữ nguyên. Frontend và quy tắc chấm/evidence không đổi.

## Chọn lựa và phục hồi

Thử model ưu tiên trên các key/project hợp lệ trước khi xét model kế tiếp. Mỗi
cặp key/model chỉ được gọi một lần trong request. Không sleep/backoff sau lỗi
upstream; trần 18 attempts và deadline tổng có thể dừng sớm hơn.

| Lỗi | Phạm vi tạm bỏ qua | Cách tiếp tục |
|---|---|---|
| 401 / API_KEY_INVALID (kể cả HTTP 400) | Key trên mọi model | Key hợp lệ tiếp theo |
| 403 quyền model / 404 model | Cặp key/model | Key khác cùng model trước |
| 429 quota theo model | Project/model | Project khác cùng model trước |
| 429 billing/spend toàn project | Toàn project | Project được phép khác |
| Timeout, mạng, 5xx, JSON sai/cụt | Project/model | Lựa chọn khác ngay |
| Request sai, nội dung bị chặn, tài khoản bị hạn chế | Dừng request | Trả lỗi có kiểm soát, không xoay key |

`Retry-After` và Google `RetryInfo.retryDelay` được ưu tiên. Mặc định cooldown
lỗi tạm thời 15s, quota 60s, daily quota 1 giờ nếu không có chỉ dẫn phục hồi,
key/quyền model 600s. Sau cooldown chỉ một request thăm dò lựa chọn đó; nếu thành
công sẽ quay lại thứ tự ưu tiên. Request đồng thời chờ probe đang chạy trong
deadline, thay vì báo hết lựa chọn khi vẫn đang phục hồi. Thành công đến muộn của request cũ không xóa
cooldown mới do request đồng thời tạo ra. Tối đa 4 request đang xử lý/project/model;
chờ slot vẫn nằm trong deadline, không hạ model chỉ vì hết slot cục bộ.

Nhóm project phải khai báo đúng: không thể suy project đáng tin cậy từ chuỗi key.
`GEMINI_KEY_POOL` là JSON chứa alias `id`, alias `project`, và tham chiếu `env`
(`GEMINI_KEY_*`). Hai key cùng project phải cùng alias project. Key lặp được loại
bỏ; một secret bị gán vào hai project sẽ bị từ chối. Pool explicit ghi đè cấu hình
legacy. Nếu dùng `AI_API_KEYS` thì danh sách này ghi đè các key legacy khác;
nếu không, ghép các biến `AI_API_KEY`, `GEMINI_API_KEY`, `GEMINI_API_KEYS`, loại trùng.
Key không có nhóm được gom vào `unknown`: gặp quota sẽ bỏ qua cả nhóm, không
thử key/model tiếp một cách mù quáng. Xem mẫu trong `backend/.env.example`.

## Thời gian và chất lượng

| Luồng | Mỗi attempt mặc định | Deadline tổng mặc định |
|---|---:|---:|
| Tutor / Hint | 6s | 30s (`AI_TIMEOUT_SECONDS`) |
| OCR nét bút | 8s | 24s |
| OCR ảnh/PDF bài làm | 8s | 24s (không vượt trần cũ 60s) |
| Review lời giải | 25s | 90s (`AI_STEP_REVIEW_TIMEOUT_SECONDS`) |
| Gateway khác | 8s | 30s hoặc timeout caller |

Mỗi attempt nhận `min(timeout_attempt, thời_gian_còn_lại)`. Gateway không retry
thêm ở ngoài manager cho Gemini. SDK OCR chỉ gửi một lần/attempt; dùng async để
deadline bao cả thời gian chờ mạng. Adapter vẫn giữ giao diện sync và chạy trên
worker thread FastAPI như trước. Adapter cấp transport HTTPX trực tiếp cho SDK
để lỗi mạng và retry không thay đổi theo transport SDK tự chọn. Các con số là cấu hình khởi đầu, **chưa phải
latency Gemini đã đo**. Giảm timeout có thể loại nhầm một generation hợp lệ nhưng chậm.

`GEMINI_MODEL_PRIORITY` cho phép cấu hình thứ tự 9 ứng viên của thiết kế. Để
trống sẽ giữ model chính riêng của từng caller và fallback cũ. Đây là danh sách
ứng viên, không phải khẳng định cả 9 ID có quyền truy cập trên tài khoản hiện tại.
Gemini 3 không nhận các tham số sampling cũ trong request builder này; Gemini 2
giữ temperature khi caller cung cấp. JSON/schema và nội dung OCR được kiểm tra
trước khi trả kết quả. Output không hợp lệ không biến thành một điểm chấm giả.

Review chỉ dùng model hiện hành, hoặc các model trong `GEMINI_GRADING_MODELS`
được người vận hành chấp nhận sau đánh giá chất lượng. Có key dự phòng cùng model
vẫn failover được. Không tự cho Lite chấm thay. Phải đưa model review được chấp
nhận vào cả priority và grading allowlist khi cấu hình danh sách mới.

## Preflight trước demo

Từ thư mục `backend`, lệnh sau **không gọi mạng**:

```powershell
.venv/Scripts/python.exe -m app.ai.gemini_preflight
```

Nó báo alias/project/model và `UNVERIFIED`. Không dùng kết quả offline làm bằng
chứng model khả dụng. Không có probe tự động lúc khởi động hoặc trong healthcheck.

Chỉ sau khi được cho phép gọi Gemini thật, người vận hành mới chạy:

```powershell
.venv/Scripts/python.exe -m app.ai.gemini_preflight --live --probe --output ../.tmp/gemini/capabilities.json
```

`--live` riêng kiểm tra metadata và `generateContent`; chưa đủ điều kiện JSON/OCR.
`--probe` gửi mẫu JSON số học nhỏ, ảnh PNG đỏ và PDF một trang; có thể dùng quota.
Manifest ràng buộc fingerprint của key, chứa quyền truy cập/capability từng model,
hết hạn sau 6 giờ. OCR ảnh cần vision; OCR PDF cần pdf; mọi luồng cần JSON.
Model thiếu capability phù hợp sẽ bị bỏ qua. Smoke test không chứng minh chất
lượng nhận diện tiếng Việt hoặc chất lượng chấm toán; vẫn cần duyệt bộ mẫu thật.

Sau preflight, đặt `GEMINI_CAPABILITIES_FILE` và
`GEMINI_REQUIRE_VERIFIED_MODELS=true` để chỉ dùng lựa chọn đã xác minh. Manifest
được đọc lại khi file đổi, không cần restart. Manifest hết hạn/không khớp key ở
chế độ strict sẽ trả lỗi có kiểm soát. Chế độ mặc định false giữ tương thích
cấu hình hiện tại, chưa có bằng chứng quyền truy cập/capability thực tế; **không
coi đó là trạng thái đã đạt điều kiện demo**. Chuẩn bị/xác minh pool trước demo;
failover không yêu cầu sửa `.env` hoặc restart khi key/model trong pool bị lỗi.
Thay pool/budget trong `.env` vẫn cần restart backend để nạp Settings mới.

Trạng thái cooldown và slot chỉ dùng bộ nhớ một process, phù hợp demo một worker.
Nhiều worker không chia sẻ trạng thái; không dùng cơ chế này để tăng quota.

## Log và kiểm thử

`gemini_failover` ghi request ID, task, model, alias key/project, loại lỗi/status;
`gemini_call_success` ghi model thực tế, số attempts và tổng `latency_ms`.
`gemini_call_failed` ghi nguyên nhân hết lựa chọn/deadline/trần attempts và thời gian.
Gateway lưu model thực tế và token đầu vào/đầu ra nếu upstream cung cấp. Không ghi
secret, body lỗi upstream, ảnh hay bài viết học sinh. Không bật debug HTTP chứa
headers trong demo. Log Gateway dùng model được yêu cầu; log manager và usage
thể hiện model thực tế sau failover.

Test sử dụng transport giả và SDK giả. Fixture backend chặn request Google API
thật nếu không dùng `httpx.MockTransport`. Bao phủ chuyển key/model, quota nhóm,
deadline, concurrency, half-open, phục hồi, schema lỗi, safety, usage, manifest,
compatibility ảnh/PDF, và cấu hình một key cũ. Kết quả mô phỏng không thay thế
preflight trên tài khoản thật.
