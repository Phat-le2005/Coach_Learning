# Consolidated Coach Learning checkout

Ứng dụng, Live Sync, OCR core, Research Lab và tooling nằm trong cùng repository.
Hướng dẫn hiện hành: [LOCAL_SETUP.md](../LOCAL_SETUP.md). Phát triển bằng feature
branch trong checkout này, không cần tạo các thư mục dự án song song.

## Những gì được giữ

| Nguồn trước đây | Quyết định |
|---|---|
| Coach_Learning / main | Giữ main mới nhất, gồm công việc teacher/classroom, theory/PDF và training của team. |
| LIVE_SYNC | Tích hợp feature cùng bản sửa touch toolbar, observed strokes, QR approval, guard chống PUT snapshot cũ và OCR/review trên LAN. |
| OCR_SLICE34 | Đưa source Lab/evaluation, HTR/Uni adapters, diagnostics, model setup và tests vào Git; gates development được giữ. |
| OCR_INTEGRATION | Core đã lên main được giữ; đồng bộ reconciler đã sửa trong Lab thành một implementation dùng chung. Storage budget hiện tại được giữ. |
| OCR_CORE33 / OCR_QA32 / CORE_CLEAN_VERIFY | Giữ lịch sử và bản bảo toàn; giữ các module QA/replay cần thiết trong repo, không merge chồng những cây cũ lên main mới. |
| Hai thư mục backup | Bảo toàn riêng ngoài checkout; không đưa database dump/private source archives lên GitHub. |
| Commit local bài mẫu chấm bước | Giữ seeder development có guard và các tests/error handling liên quan. Không chạy seed/reset trên database có sẵn. |

Historical PRs/branches30–34 không phải hướng dẫn merge lần lượt sau consolidation.
Source đã được chuyển có chọn lọc, giữ hành vi mới nhất của main. Gitlinks trỏ tới
build pgvector/worktree cũ được bỏ khỏi index; chúng không phải runtime dependencies.

## Core và dữ liệu riêng

MathWorkspace và Lab cùng gọi `ocr-v2-scope-candidates.ts`; signature geometry nhận
page/revision/strokes, không lấy source label/GT làm feature. Lab vẫn có adapter
render/projection/evaluation riêng, không tự biến thành production grading.
Các sửa đã có về fraction, satellites/fragment completion và bounded layout
reconciliation được dùng chung. Không thay weights/decoder/CAS/evaluator contracts.

Weights, private captures, annotations, API keys, DB và logs không lên GitHub.
Cache/model directories được chuyển về `.tmp/` của checkout duy nhất; bản bảo toàn
ngoài checkout có file inventory, manifests, ZIP đã đọc/hash-check và Git bundles.
Không xóa IndexedDB hay Docker/PostgreSQL volumes. Khi đổi origin, browser reviews
cũ vẫn thuộc origin cũ: export/import theo hướng dẫn, không giả vờ đó là dữ liệu Git.

Model downloader pin repository/revision/size/SHA và lưu manifest. HTR setup không
còn bắt buộc ba capture riêng; clean-clone catalogue trống là hợp lệ. Model weights
không có trong Git; [model catalogue](ocr-v2/MODELS.md) ghi rõ nguồn và license.
Uni CPU là tùy chọn mặc định khi setup; CUDA/hybrid không bắt buộc để chạy ứng dụng.

## Kiểm chứng

- Clone mới từ GitHub, không `.env`/`.tmp` nghiên cứu: `npm ci`, typecheck, production
  build đạt; backend venv mới từ requirements-lock: `pip check` và11 tests đạt,
  một PostgreSQL unit test được skip khi chưa cấu hình fixture tương ứng.
- Frontend chính533 tests; Lab63 tests; model setup portability dùng software-only
  fixture. Đây là kiểm thử phần mềm, không phải OCR accuracy.
- Browser trên source/venv của clone sạch: Lab viết/import → CoMER thật → annotation
  transfer; QR guest approval → stroke IDs → OCR thật → correction/retry/reload;
  Live Sync hai chiều/concurrent append/offline/reconnect/eraser/undo/redo/page switch.
  Browser pointer replay không được gọi là handwriting mới từ người thật.
- Local backend/frontend không phụ thuộc worktree cũ. Các session/database QA phục
  vụ kiểm thử được giữ ngoài Git, không thành credentials mặc định của ứng dụng.
- Npm audit phát hiện advisory inherited từ main; chỉ nâng next/@next16.3.8→16.4.5,
  sau đó audit0 vulnerabilities. Không dùng `npm audit fix --force`.
  [Image optimization advisory](https://github.com/advisories/GHSA-2464-fhr4-w9xw),
  [cache advisory](https://github.com/advisories/GHSA-673q-mjm6-r5xr).

CI backend/data còn baseline đã xác minh giống main: frozen v1 contract actual SHA
`4a8fc23cec6425405e94beb9726bfebf9ed23c56d13318a631487287e17937bd` khác snapshot
`01b558addf218c6d47a0e22d7ccd04f6d246170e8661b8d5c0fb844ea513e008`; hai tests
`test_student_mastery_tree_hides_inactive_legacy_branches` và
`test_reconciliation_cannot_mutate_production` cũng fail trên main nền.
Không tự re-freeze hợp đồng của team chỉ để đổi CI thành xanh. Lỗi này được báo riêng,
không đánh đồng với kết quả frontend, targeted backend hoặc browser acceptance.

Consolidation không đồng nghĩa TEXT/MIXED routing, recognition và mọi bài Toán12
đã hoàn chỉnh. Không có cam kết accuracy tổng quát hoặc tự chấm mọi bản viết tay.
