> Consolidated checkout: use [LOCAL_SETUP.md](../../LOCAL_SETUP.md) for current setup. Absolute worktree paths/QA sessions below are historical; private fixtures are optional and not distributed.

# Quyết định OCR V2 Experimental — 04/11/2026

## Cập nhật remediation cùng ngày

Lab mặc định hiện dùng `constructScopeCandidates()` độc lập với box/label: geometry anchors, fragment/limit completion và learned alternatives, kèm routing chưa xác nhận. **Layout-M cũ** vẫn chọn được để tái hiện lỗi. Không thay production Page OCR.

File người dùng cung cấp `D:/Downloads/ocr-v2-package.json` có source14 nét và snapshot71 nét trong archives. Đã tái hiện lỗi cũ14→TEXT12+UNKNOWN2/0 inference và71→MATH71/0 inference vì overlap gate. Browser thực đã chạy geometry/hybrid tự tạo MATH14 và raw `x^{2}+3x-4=0`. Đây là một phép tái hiện có transcript do người dùng xác nhận, không phải accuracy tổng quát. Trang hỗn hợp tách prose khỏi toán, còn cần review Sigma và quan hệ ngoặc; xem báo cáo/ma trận đầy đủ ở `.tmp/tri-ocr-v2-remediation/`.

Các bảng dưới là kết quả **prototype detector-only trước remediation**, được giữ làm baseline lịch sử. Chúng không mô tả routing Hybrid hiện tại. Kết luận chưa bật tự động hóa production, HTR manual, V3 blocked và thiếu GT đa người viết vẫn giữ nguyên.

## Trạng thái bàn giao

| Phần | Trạng thái | Bằng chứng / giới hạn |
|---|---|---|
| MathCanvas live → scope → CoMER → review/export | **WORKING_UI** | Next.js thật, component MathCanvas dùng chung; browser pointer replay sinh ink mới, chạy model thật, xuất package; không gửi bước chấm. |
| PP-DocLayout-M CPU | **VERIFIED_ON_REAL_INK** ở mức chạy inference và quan sát output | Weights official đã load, kiểm checksum; chạy trên4 capture MathCanvas thật. Điều này không đồng nghĩa nhãn/scope đúng. |
| Scope đầy đủ → CoMER | **VERIFIED_ON_REAL_INK** ở4 DEV captures | Manual scope giữ đúng13/22/25/10 stroke IDs; output thô được lưu. Integral vẫn đọc cận3 theo model; không tự sửa thành2. |
| Bảo toàn nét / correction / hierarchy / stale | **VERIFIED_SOFTWARE** | Unit tests và actual browser: không mất/nhân đôi ownership, TEXT nhập tay giữ dấu, correction giữ khi OCR lại, child edit vô hiệu parent, revision mới vô hiệu approval. |
| Layout-M làm bộ tự động chọn/định tuyến scope production | **CHƯA ĐỦ BẰNG CHỨNG; KHÔNG BẬT PRODUCTION** | Sai loại trên nhiều DEV captures; còn gộp hai biểu thức trong layout dựng. |
| PP-DocLayoutV3 | **BLOCKED_UNSUPPORTED_RUNTIME** | Weights đã cache, nhưng PaddleX3.3.13 không đăng ký `PP-DocLayoutV3`; đã thử load thật và lưu lỗi. Không có benchmark chất lượng V3. |
| Vietnamese HTR | **BLOCKED / MANUAL_FALLBACK** | OCeanpaRk gated; checkpoint public còn lại khoảng1.88GB, cần Torch/Transformers và kiểm chứng nét dòng/dấu riêng. Không tự tải thêm runtime/model nặng để báo có HTR. TEXT/MIXED/UNKNOWN không vào CoMER. |
| Accuracy / CER / WER / confusion / native multi-line generalization | **NOT_MEASURED** | Chưa có HUMAN_VERIFIED GT độc lập;4 mẫu đã dùng debug. Không lấy số test PASS hay box recall trên bốn trang một biểu thức làm accuracy. |
| Handoff evaluator | **BLOCKED_BY_CONTRACT** | IR1.1 giữ nguyên. `PREVIEW_ONLY`, `steps=[]`, `submitPayload=null`, `readyToSubmit=false`, kể cả sau duyệt. |

## Kết quả quyết định của Layout-M

| Capture thật | Raw labels | Scope đang có ownership | Tự chạy CoMER? |
|---|---|---|---|
| Quadratic13 | `header_image` | đủ13 nét | Không, UNKNOWN; người dùng chọn MATH/manual |
| Derivative22 | `doc_title` | đủ22 nét | Không, TEXT; giữ unresolved/manual |
| Sigma25 | `formula` | đủ25 nét | Có, output pre-repair/selected được lưu |
| Integral cũ10 | `image`, `text` | một scope10 nét, một candidate không có ownership | Không; nhãn và overlap được giữ để review |

**CONFIRMED:** model có thể tạo một box bao đủ nét nhưng gán sai loại. Không sửa thầm `header_image` thành MATH để làm demo trông tốt hơn. Raw score là score detector, không phải xác suất chép đúng.

Ở hai bố cục kiểm tra **SYNTHETIC_LAYOUT** dựng từ hai source thật độc lập: hai dòng gần nhau tạo scope35 nét chứa cả hai biểu thức; hai cột tạo hai scope13/22 nét nhưng gán TEXT. Đây là stress test có biến đổi tọa độ được ghi lại, không phải native multi-line hay nhãn human-verified. Nó đủ để bác bỏ quyết định bật tự động rộng rãi, chưa đủ để tính accuracy.

**HYPOTHESIS:** domain gap từ tài liệu in và nhãn layout tài liệu sang MathCanvas góp phần vào các nhãn sai. Chưa tách tác động renderer/scale khỏi domain/model trên tập có GT. Không chọn thuật toán OCR mới, không fine-tune, không thêm heuristic để bốn mẫu PASS.

## Giữ gì và bước tiếp theo

Giữ prototype sau flag để thu dữ liệu và sửa scope có người hỗ trợ. Giữ baseline V1/V2 đúng membership hiện hành; không đổi Page OCR/Math View/CoMER production. Scope giao biên hoặc trùng candidates cần người dùng đối chiếu trước khi gọi CoMER; orphan vẫn hiện UNKNOWN. Mỗi thao tác có ngân sách inference hữu hạn.

Bước quyết định tiếp theo là thu15–30 mẫu mới có nhãn độc lập, gồm nhiều dòng, hai cột, TEXT/MIXED và mũ/cận, tách DEV/HOLDOUT. Chạy adapter tương thích V3 trong môi trường riêng nếu muốn đối chứng; không nâng runtime đang chạy ổn chỉ để che lỗi của M. Chỉ cân nhắc tự động hóa production sau khi đo false split/merge và routing trên các mẫu đó. Người dùng đã có thể thử, sửa/review/export ngay bằng [hướng dẫn chạy](EXPERIMENTAL_E2E_README.md).

Source/model/run manifests và output gốc nằm tại `.tmp/tri-ocr-v2-e2e/`; xem `RESULTS.md`, `comparison.csv`, `detections.json`, `scope_mapping.json`, `ocr_raw.json`, `layout-stress-results.json`, `live-verification.json`, `production-gates.json`. Không có commit/push/merge hoặc thay đổi DB/schema/evaluator trong lượt này.
