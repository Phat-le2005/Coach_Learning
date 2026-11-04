# Đối chiếu 40 công thức với PDF nguồn

## Kết quả và phạm vi

Đã đọc trực tiếp ảnh công thức và các trang nguồn liên quan, chép nhãn tham chiếu rồi đánh giá trên **40 vùng công thức** thuộc hai PDF. Đây là mẫu chẩn đoán có chủ đích, không phải mẫu ngẫu nhiên và không phải độ chính xác của toàn pipeline chấm.

| Nhóm | Số mẫu | Trước: đúng / sai / giữ lại | Sau: đúng / sai / giữ lại |
|---|---:|---|---|
| Mẫu dùng điều chỉnh trong PDF 57 trang | 24 | 14 / 7 / 3 | 16 / 0 / 8 |
| Mẫu giữ riêng trong cùng PDF | 8 | 5 / 0 / 3 | 5 / 0 / 3 |
| PDF khác, chưa dùng điều chỉnh | 8 | Không có baseline tương đương | 5 / 0 / 3 |
| Tổng sau sửa | 40 | Không so tổng với baseline 32 mẫu | **26 / 0 / 14** |

`Đúng` đánh giá phần biểu thức được chỉ định, định danh hàm/dấu đạo hàm và các cấu trúc bắt buộc so với bản chép từ ảnh. `Giữ lại` là chưa có đầu ra hợp lệ thuộc phạm vi hỗ trợ. Mẫu đúng không đồng nghĩa lời giải hoặc đáp án nguồn đúng toán. Điều kiện được ghi riêng trong nhãn; không coi việc nhận phần thân biểu thức là đã xác minh miền/điều kiện.

Trong 7 bản đọc sai nhưng vẫn mang nhãn NORMALIZED trước đó: **2 được phục hồi đúng**, **5 bị chuyển sang giữ lại**. Không báo chúng thành 7 lỗi đã đọc đúng. Mẫu còn nhỏ, thiên về các loại lỗi đang quan tâm và không đo độ bỏ sót các công thức chưa từng được phát hiện.

## Những lỗi đã sửa

1. **Thiếu hạng tử khi gặp chữ ngay sau công thức.** Regex tìm văn xuôi trước đây nuốt cả đoạn `+1000(nghìn...)`. Giới hạn regex vào chữ và cắt dấu mở đơn vị giúp giữ đúng `C(x)=0,01x²+20x+1000`.
2. **Dấu căn là vector, không có trong text PDF.** Bộ phục hồi nhận mái căn và chân căn từ các đoạn thẳng, chỉ bọc đúng các glyph nằm dưới mái. Trường hợp `y=√(x²−2x)` được giữ căn; chỉ có một đường ngang mà thiếu chân căn thì giữ lại thay vì tự đoán căn.
3. **Mất dấu giá trị tuyệt đối, gạch trên hoặc chỉ số dưới.** Trước đây `y=|x²+5x+6|`, `y=f(|x|)` hoặc `f(x)=(x₀−x)x²` có thể thành biểu thức khác vẫn parse được. Nay kiểm các nét/glyph nguồn rồi chặn bản đọc thiếu cấu trúc. Chưa coi các trường hợp bị chặn là đã đọc đúng.
4. **Đơn vị bị hiểu như phép nhân.** Dạng `t=0(s)` không tự biến thành tích đại số với biến `s`; giữ lại để tách đơn vị bằng một hợp đồng riêng.
5. **Model không được bỏ qua cảnh báo nguồn.** Cổng xuất file cuối giữ chặn một mảnh đã có SOURCE_LAYOUT_UNRESOLVED dù Qwen định dạng lại nó thành một chuỗi parse được.

Các sửa đổi nằm trong `native_math.py`, `source_layout/`, `latex_stage/` và cổng xuất `document_pipeline/`. Không có hằng số câu 158/174 hoặc ánh xạ theo tên PDF trong code xử lý. Các số câu và nhãn chỉ thuộc fixture kiểm thử/audit.

## Giữ riêng mẫu kiểm tra

Sau khi sửa theo 24 mẫu phát triển và qua 217 tests, hash ba module xử lý biểu thức được lưu vào `frozen-candidate.json`. Sau đó mới xem và gán nhãn 8 mẫu giữ riêng của pilot và 8 mẫu tài liệu khác. Không chỉnh các module đó theo kết quả giữ riêng. Công cụ audit kiểm lại hash và dùng metadata baseline cố định, không đọc nhầm `latest.json` sau khi pipeline đã được cập nhật.

Cổng bổ sung ở bộ xuất file cuối chống Qwen vượt cảnh báo được kiểm bằng invariant riêng; nó không đổi đường đánh giá các biểu thức giữ riêng. Bộ test cuối có **221 ca qua**: các fixture glyph/vector nguồn, căn, hạng tử cuối, trị tuyệt đối, chỉ số dưới, gạch trên, không nhầm số mũ của mẫu phân số thành chỉ số dưới, model không thể bỏ qua nguồn, và phân loại kết quả audit.

## Hai tài liệu nguồn

- Pilot: PDF 57 trang người dùng cung cấp, SHA-256 `5db1fc66ab0a42553e882981d1b22935967295b9a73cd2c96840e6ee5dd76927`.
- Tài liệu khác: `bai-tap-ung-dung-dao-ham-de-khao-sat-va-ve-do-thi-ham-so-toan-12-chuong-trinh-moi.pdf`, 47 trang, trích ra từ ZIP gốc mà không sửa ZIP; SHA-256 `12ca911c6a275d90a6ba4767e79caa4d4df80fd4727852df6e24629136fd4463`.

Tài liệu thứ hai chỉ chạy trích native toàn 47 trang và đánh giá 8 vùng công thức đã chỉ định. **Chưa chạy OCR/Qwen toàn tài liệu này**, chưa đo tự động phát hiện mọi công thức hoặc tách đủ mọi câu của nó. Vì cùng chủ đề đạo hàm, kết quả chưa đại diện các môn/chương khác hay scan mờ.

## Xem và tái chạy

Thư mục audit ở E:

`E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\formula-source-audit-20261102\`

- `review.html`: ảnh nguồn, bản chép tham chiếu và trước/sau từng công thức.
- `audit-report.json`, `audit-results.json`: số đo và quyết định từng mẫu.
- `gold-all.json`, `pilot-sample.json`, `external-sample.json`: nhãn và định nghĩa vùng mẫu.
- `frozen-candidate.json`: hash module đã chốt trước khi xem mẫu giữ riêng.
- `external-source.pdf`, `external-native/`: nguồn độc lập đã trích từ ZIP và cache native.

Nhãn không chứa ảnh/PDF được lưu thêm ở `tests/fixtures/formula-source-labels-v1.json`; một số vùng glyph/vector phục vụ regression ở `tests/fixtures/source-layout-v1.json`.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'tools\pdf_metadata'
.\.tmp\pdf-pipeline-runtime\.venv\Scripts\python.exe -B -m pdfmeta.source_audit `
  --sample-dir '.tmp\formula-source-audit-20261102' `
  --pilot-job '.tmp\pdf-jobs\5db1fc66ab0a42553e882981' `
  --baseline-file '.tmp\pdf-jobs\5db1fc66ab0a42553e882981\final\versions\41a91d3ca0e6b5b4\questions.final.pretty.json'
```

Pipeline đã được chạy lại trên 120 câu với phiên bản sửa: 0 inference OCR mới nhờ 94 cache hits. Qwen chỉ thử ba câu, không phải cả 120. Các kết quả vẫn là bản nháp có nguồn, `academic_review=PENDING`, `grading_support=NOT_ASSESSED`, `publishable=false`. Chưa đủ bằng chứng để coi toàn kho 3.478 trang là dữ liệu chấm sạch.
