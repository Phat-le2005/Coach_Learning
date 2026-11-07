> Consolidated checkout: use [LOCAL_SETUP.md](../../LOCAL_SETUP.md) for current setup. Absolute worktree paths/QA sessions below are historical; private fixtures are optional and not distributed.

# OCR V2 — dataset, annotation và evaluation local

Mở **http://localhost:3014/ocr-v2-lab/evaluation** và đăng nhập QA tại origin này. Route chỉ chạy development khi bật flag; production luôn 404. Toàn bộ nét/nhãn/kết quả nằm trên máy (IndexedDB và file export), không gửi Evaluator hoặc cloud OCR.

## Khởi động Windows / PowerShell

Worktree thực: `D:\SGU\DuAn\Coach_Learning_OCR_SLICE34`, nhánh `feat/tri-ocr-core-transcription-slice`. Giữ nguyên thay đổi local; không cần chuyển nhánh/reset.

```powershell
cd D:\SGU\DuAn\Coach_Learning_OCR_SLICE34
# Chỉ cần nếu chưa setup detector; Python 3.12, venv/cache riêng ngoài Git:
powershell -ExecutionPolicy Bypass -File tools/ocr-v2-lab/setup.ps1
# Backend QA hiện có phải chạy; không dùng production. Nếu cần:
cd frontend
npm run test:compile
cd ..
node tools/ocr-v2-lab/qa-backend.cjs start
node tools/ocr-v2-lab/manage.cjs start
# Tải một lần excerpt chính thức ~1.6 MB; không tải full corpus:
& .tmp\tri-ocr-v2-runtime\venv\Scripts\python.exe tools/ocr-v2-lab/prepare_evaluation.py
```

Manager giữ lại service đang chạy, kiểm tra cổng và in URL thực nếu 3014 bận. Backend helper chỉ chấp nhận cấu hình test/QA đã được chuẩn bị, không tạo database/account. Nếu backend đang chạy sẵn, không cần gọi helper. Docker PostgreSQL QA cần healthy trước khi đăng nhập. Credential QA lấy từ cấu hình private hiện có; không đưa vào export hoặc tài liệu.

Các lần sau có thể chuẩn bị dữ liệu offline:

```powershell
& .tmp\tri-ocr-v2-runtime\venv\Scripts\python.exe tools/ocr-v2-lab/prepare_evaluation.py --offline
```

Internet chỉ cần khi setup dependencies/weights/excerpt. Inference detector chạy CPU local, CoMER chạy ONNX/WASM trong browser. Không có API Gemini/GPT.

## Luồng sử dụng không cần sửa JSON

1. **Nguồn có nhãn:** bấm **Nạp nguồn MathWriting + captures local**. Có 300 biểu thức người thật có nhãn từ metadata nguồn và 7 capture native chưa có GT. Dataset overview phân biệt nguồn, tập, trạng thái nhãn.
2. **Trang vừa viết:** vào `/ocr-v2-lab`, viết MathCanvas, dùng nút chuyển sang annotation. Tab mới mở với snapshot vector và DRAFT trống; canvas gốc vẫn giữ. Hoặc import `ocr-v2-package.json`/capture vector qua input file. Ảnh screenshot không thay được nét vector. Bundle chỉ lấy source đang active, không tự lấy archived predictions làm GT.
3. Chọn **Khoanh nét GT**, khoanh một đơn vị; có thể click từng nét để thêm/bớt và zoom. Chọn MATH/TEXT/UNKNOWN rồi tạo đơn vị. Nhập nguyên văn đã viết, kể cả sai toán học. MATH nhập LaTeX có preview; TEXT nhập tiếng Việt.
4. Chọn unit để sửa type/transcript/membership. Chọn các unit để gộp; muốn tách, chọn một tập nét và tạo unit mới (ownership được chuyển rõ ràng). Dùng nút đổi thứ tự. Tạo STRUCTURE từ các children đã chọn và nét khung nếu có; không cần nhập LaTeX giả cho container. Quan hệ SYSTEM phải do người xác nhận.
5. Nhập mã người gán nhãn; tick đã đối chiếu nét gốc; xác nhận từng unit (children trước parent), rồi xác nhận GT toàn trang. Phần chưa rõ giữ UNKNOWN. Model proposals chỉ hỗ trợ khoanh, không phải Oracle hoặc GT tự động.
6. IndexedDB tự lưu, có undo/redo. **Xuất dataset + annotation + kết quả** để có backup bền vững; có thể reimport. Nếu cùng capture nhưng annotation khác, bản nhập được giữ thành một `[import version]` riêng, không bỏ qua hay ghi đè bản cũ. Tab cũ bị chặn nếu một tab khác đã lưu bản mới, tránh ghi đè âm thầm. Tải lại tab cũ trước khi tiếp tục. Dữ liệu chỉ trong browser có thể mất nếu xóa site data.
7. Chọn case hoặc đưa các case đang lọc vào batch. Tick Geometry/Layout/Hybrid/Oracle và ablations nếu cần; đặt max cases, inference budget. Có thể tắt CoMER để chỉ đo scope. Bấm **Chạy benchmark**, xem overlay và chi tiết lỗi. Chạy benchmark không sửa annotation.
8. Xuất kết quả JSON + CSV + Markdown, GT và overlay SVG/PNG. Các file chứa nét viết tay; kiểm tra trước khi chia sẻ. Không chứa cookie/token/.env.

Không lấy bản chép CoMER vừa hiển thị làm nhãn độc lập. Nếu đã xem gợi ý, nhãn người dùng được ghi `assisted`. Lịch sử benchmark đi cùng provenance cả trong GT-only export/reimport; các capture diagnostic có sẵn được đánh dấu đã có model evidence, không phải native holdout chưa từng xem. Các xác nhận do browser automation đều mang `SOFTWARE_SIMULATED`, không phải người thật xác nhận.

## Sinh trang tự động

Mở phần **Sinh batch từ nét người thật có nhãn** sau khi nạp nguồn. Chọn seed, số trang (16 smoke, 100–300 pilot), DEV/HOLDOUT, số biểu thức, family, khoảng cách, xoay nhỏ và độ dày. Không cần tạo từng case.

Families: SINGLE, ROWS, NEARBY, COLUMNS, INDENTED, SCALE_VARIATION, ALIGNED, SYSTEM_DEFINED và CYCLE. ALIGNED chỉ căn lề trái bbox, **chưa căn đúng dấu bằng** vì nguồn chưa có symbol-level GT. Sigma/fraction/integral được giữ nguyên từ source expression, không vẽ lại glyph. SYSTEM_DEFINED là quan hệ do generator định nghĩa tường minh, không tự tạo nét ngoặc.

Output có `SYNTHETIC_COMPOSED_REAL_INK`, source IDs, nhãn, affine/inverse, stroke maps và GT membership đúng theo phép ghép. Đây không phải trang native do người viết trọn trang. Chỉ nguồn whole-expression human có nhãn nguồn hợp lệ được đưa vào pool. Biến thể cùng nguồn không được vượt DEV/HOLDOUT. Nếu chọn writer split khi thiếu writer ID, hệ thống báo lỗi; không bịa writer IDs.

## Cách đọc benchmark

- Matching dùng maximum-total-stroke-IoU Hungarian, không so theo index. Coverage toàn trang khác exact membership từng unit. Xem missing/extra IDs, split/merge và duplicate/orphan riêng.
- Recognition-only score chỉ tính khi tập nét khớp GT hoàn toàn. Oracle có scope chuẩn nhưng model vẫn có thể sai. TEXT/UNKNOWN không bị ép vào CoMER.
- Raw trước repair, repaired và selected đều giữ riêng. So sánh LaTeX theo lexical tokens, NFC, giữ braces/commands, không CAS. Strict exact có thể fail chỉ vì `\limits`; diagnostics phân biệt trường hợp này, không âm thầm nâng điểm.
- Cache dùng tensor/mask/model/config/code hashes. Cache hit không được tính là inference mới. Thời gian gốc của model khác thời gian cache lookup hiện tại.
- NATIVE/EXTERNAL/COMPOSED, DEV/HOLDOUT, nguồn GT và software workflow được tách cohort. `NOT_MEASURED` khác 0. Không có một accuracy chung cho tất cả.
- `geometryMs` bao gồm constructor; `reconciliationMs` là thời gian lồng bên trong, chưa đo tách riêng. Không cộng hai trường. Detector dùng chung giữa arms; không cộng arm totals thành batch wall time.

## Nguồn, license và giới hạn

[MathWriting chính thức](https://github.com/google-research/google-research/tree/master/mathwriting): excerpt 500 InkML, chọn 300 whole human expressions; loại 100 symbols và 100 source-synthetic khỏi pool người thật. Dữ liệu **CC BY-NC-SA 4.0**, chỉ dùng phù hợp điều kiện phi thương mại; giữ attribution/share-alike. Nhãn có nguồn Wikipedia có thể kèm CC BY-SA. License code không thay thế license data. Archive SHA được pin trong preparation script; source/XML SHA và README giữ ngoài Git.

Internal split hiện 244 DEV / 56 HOLDOUT, không phải phép đánh giá official MathWriting. Không có published writer IDs; chưa chứng minh writer-disjointness. Generic InkML import giữ vector/channel order/metadata, nhưng nhãn file người dùng mặc định DRAFT; không tự tuyên bố authoritative.

CROHME: có adapter absolute InkML nhưng chưa tải release chính thức để benchmark. DTD/entities, delta trace encoding và file quá lớn bị từ chối. MathML/symbol metadata được giữ trong XML gốc, chưa diễn giải thành structural GT. Vietnamese HTR chưa có adapter đã kiểm chứng; TEXT manual, CER/WER NOT_MEASURED. V3 hiện BLOCKED_UNSUPPORTED_RUNTIME; không có kết quả giả thay thế.

## Lệnh tái lập và kiểm thử

```powershell
cd D:\SGU\DuAn\Coach_Learning_OCR_SLICE34\frontend
npm run test:ocr-evaluation
npm test
npm run typecheck
$env:NEXT_DIST_DIR='.next-ocr-v2-production'
npm run build
cd ..
& .tmp\tri-ocr-v2-runtime\venv\Scripts\python.exe tools/ocr-v2-lab/test_evaluation_import.py
& .tmp\tri-ocr-v2-runtime\venv\Scripts\python.exe tools/ocr-v2-lab/test_service.py
node tools/ocr-v2-lab/run_evaluation_pilot.cjs
node tools/ocr-v2-lab/verify_evaluation.cjs
node tools/ocr-v2-lab/verify_live.cjs
node tools/ocr-v2-lab/verify_gates.cjs
node tools/ocr-v2-lab/report_evaluation.cjs
```

Browser runner cần Chrome, backend QA và file credential QA private đã có; không provision account hay mock model. Nó dùng context riêng, không xóa annotation trong browser cá nhân. `verify_evaluation.cjs` chọn 4 nguồn DEV theo quy tắc ghi trước inference; kết quả không phải official dataset score. Artifacts local: `.tmp/tri-ocr-v2-evaluation/`, gồm nguồn/manifest, 100 trang pilot, 16 trang HOLDOUT chưa chạy, results, model hashes, CSV, 50 overlay, screenshots và 8 báo cáo theo yêu cầu. Không commit corpus/credential.

Kết quả hiện tại: WORKING_UI, VERIFIED_REAL_MODELS, có scope pilot và recognition smoke; **PARTIAL đối với native scientific accuracy** vì chưa có GT người thật xác nhận độc lập. Không suy ra chất lượng dùng thực tế từ số test PASS.

## Dừng / khắc phục

```powershell
node tools/ocr-v2-lab/manage.cjs stop
# Chỉ dừng backend riêng nếu đã bật bằng helper:
node tools/ocr-v2-lab/qa-backend.cjs stop
```

- 404: mở đúng managed dev URL; production luôn bị khóa.
- 401/login: đăng nhập QA tại đúng origin; không dùng production account.
- DATASET_NOT_PREPARED: chạy preparation một lần; lần sau dùng `--offline`.
- LOCAL_WORKSPACE_CHANGED_IN_ANOTHER_TAB: export phần đang xem nếu cần, reload để lấy bản đã lưu mới. Không tiếp tục ghi đè.
- Lỗi IndexedDB/quota: export ngay; autosave lỗi phải hiện rõ, không giả báo lưu thành công.
- Hết inference budget/cancel: phần chưa chạy hiện trạng thái riêng; tăng budget có kiểm soát rồi chạy lại. Cache hợp lệ được reuse.
- WASM threads warning: browser hiện fallback single-thread do chưa cross-origin isolated; inference vẫn chạy. Không bật COOP/COEP toàn app chỉ để giấu cảnh báo. Canvas readback warning là hiệu năng, không phải bằng chứng sai scope.
