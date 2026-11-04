# Khôi phục công thức trong corpus Toán 12

Ảnh người dùng chỉ ra mục 1461, Câu 33, trang gốc 16 của tài liệu nguyên hàm Lê
Bá Bảo. `question.text_lossy` chứa glyph Symbol riêng và thứ tự chữ đã bị trải
phẳng. Thụt lề JSON không sửa được số mũ, phân số hay quan hệ vị trí. Dữ liệu
PDFium nhanh hiện không có tên font thật để ánh xạ đáng tin cậy.

## Thay đổi

- Viewer đưa ảnh nguồn lên trước khi phát hiện text mất mã ký hiệu; text lỗi nằm
  trong mục thu gọn. JSON gốc và trạng thái duyệt giữ nguyên.
- Thêm `pdfmeta.paired.math_recovery`: đọc lại trang gốc có kiểm hash, giữ tên
  font và tọa độ glyph, tách vùng công thức theo các neo hàm/phương trình/tích
  phân, đọc ảnh vùng bằng PP-FormulaNet_plus-M local.
- Số mũ đơn giản có cách đọc native độc lập. Phân số nhiều dòng hoặc cấu trúc
  chưa hỗ trợ giữ ứng viên OCR và lý do từ chối native để đối chiếu.
- Kết quả nằm ở thư mục riêng. Không tự ghi đè metadata, tách bước lời giải,
  chọn đáp án, tạo rubric hoặc nâng trạng thái đủ dùng cho core chấm.
- Không sửa ba module đã đóng băng trong đợt source audit trước.

## Kết quả mẫu

Lần chạy tự tìm vùng của mục 1461 thu được 6 công thức: hàm trong đề, bốn lựa
chọn và chuỗi tích phân trong lời giải. Bốn vùng khớp ký hiệu native/OCR, hai vùng
cần đối chiếu ảnh do phân số có ngoặc ghép và dòng tích phân. Đã xem ảnh nguồn
và kết quả render cạnh nhau: cả sáu vùng khớp các ký hiệu in trong nguồn; giữ
nguyên cả các phương án nhiễu. Đây là đối chiếu một mẫu, không phải độ chính xác
đo trên toàn bộ corpus.

Đầu ra thử nghiệm tại:

`.tmp/pdf-jobs/4ebd40c425c242baa4faf416/latex-recovery-20261103/`

Metadata chuẩn vẫn có SHA-256:
`8612e76d88b64467ca52601c4bc08fe2d88439fee684f9004e78aecb81149657`.

QA và ảnh desktop/mobile nằm tại `.tmp/pdf-corpus-latex-trial-20261103/`.
Viewer dùng KaTeX đóng gói tại máy, không gọi CDN. Model CPU ba luồng,
BelowNormal; không gọi API và không tải model mới.

## Giới hạn và bước mở rộng

Đây là stage ứng viên theo vùng, chưa xuất toàn văn đề/lời giải sạch. Neo hiện
có chưa bao phủ mọi biểu thức độc lập, bảng, hình hoặc PDF scan. Trước khi dùng
cho cả bộ, cần đánh giá trên mẫu chia theo tài liệu và loại cấu trúc: số mũ/chỉ
số, phân số lồng, căn, tích phân có cận, hệ phương trình và bảng. Thêm luồng
layout/OCR cho vùng không có glyph và tiêu chí phát hiện thiếu vùng. Chỉ đưa bản
đọc đã qua các kiểm tra phù hợp sang stage tách bước; ảnh và text gốc vẫn giữ để
truy nguyên. Render thành công hoặc model đồng ý không đồng nghĩa nội dung toán
đúng hoặc đủ điều kiện chấm.
