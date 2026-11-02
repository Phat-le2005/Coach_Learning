# Tiếp tục xử lý dữ liệu: review và bộ 20 bài

Ngày 02/11/2026. Đã triển khai trên pilot 57 trang, chạy tại ổ E. Không import database, không đổi core chấm, không xử lý bộ PDF lớn.

## Thay đổi đã thực hiện

- Chuẩn hóa dấu đạo hàm tương đương: `P'(x)`, `P^{'}(x)`, `P^{\prime}(x)`, `P^\prime(x)`. Giảm báo nhầm và so điều kiện biên theo cùng biến thay vì chỉ cùng số.
- Tính lại cảnh báo từ cache, không tải hay chạy lại model. Trong 42 vùng đọc lại bởi model M, số vùng kích hoạt cảnh báo giảm từ 18 xuống 13. Các số này là cảnh báo của quy tắc kiểm tra, không phải số lỗi đã được xác nhận.
- Trang review có công thức được render, ảnh crop theo vùng, sửa đề/đáp án/lời giải/công thức và lưu phiên bản trên ổ E. Thay đổi được lưu riêng, không sửa PDF hoặc đầu ra model.
- Nút lưu hỗ trợ nháp, cần kiểm tra và đã đối chiếu đề/đáp án với nguồn. Mọi bản vẫn `academic_review=PENDING`, `grading_support=NOT_ASSESSED`, `publishable=false`.
- Tạo 20 bài mẫu với đề biên soạn có LaTeX, đáp án số có kiểu, đặc tả toán bản nháp, ảnh nguồn và nhóm bước giải ứng viên. Đã đối chiếu ảnh đề và đáp án cho 20 mục; lời giải biên soạn và rubric chưa được duyệt học thuật.

## Lưu ở đâu

Output gốc: `E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-metadata-pilot-v1`.

| File | Vai trò |
| --- | --- |
| `exports/pilot20.authoring.jsonl` | Metadata biên soạn của 20 bài; mỗi dòng một bài |
| `exports/pilot20.student-preview.json` | Bản xem trước đề và ảnh đề; không chứa đáp án/spec/lời giải |
| `exports/pilot20.report.json` | Phiên bản export và trạng thái kiểm tra |
| `reviews/state.json` | Các bản sửa và lịch sử phiên bản, giữ nguyên qua reload/restart |
| `quality-recheck-v2.json` | Cảnh báo tính lại từ kết quả model đã cache |
| `curation.json` | Danh sách 20 bài và ghi chú nguồn để trang review sử dụng |

## Phát hiện cần xử lý trước khi chấm

Có 7 mục cần xem lại điều kiện, cách diễn đạt hoặc lời giải: 152, 153, 158, 168, 173, 213 và 260. Không coi đây là 7 đáp án chắc chắn sai.

Câu 260 là bất đồng rõ giữa đề và lời giải: đề hỏi **hoành độ** của hai cực trị cùng dấu; lời giải lại dùng tích **tung độ** và đáp án 6. Với câu chữ hiện tại, phương trình hoành độ cực trị là `x²-4x+m+2=0`; có hai nghiệm cùng dấu khi `-2<m<2`, ứng với 3 số nguyên. Bản biên soạn giữ đáp án nguồn 6 và lưu 3 thành ứng viên sửa kèm lý do, không âm thầm ghi đè đáp án.

Ở Câu 153 cần làm rõ làm tròn mốc thời gian; Câu 213 cần xét riêng m=0. Các nhận xét này chưa phải rubric chính thức. Ngân hàng câu hỏi cần thêm bước duyệt nội dung, ánh xạ taxonomy, kiểm tra khả năng checker và phát hành phiên bản.

## Cách dùng

1. Mở `http://localhost:8787/review.html`, mặc định lọc bộ 20 bài.
2. So ảnh nguồn với bản biên soạn, sửa công thức nếu cần; chọn vùng OCR để xem crop và các phương án nhận dạng.
3. Lưu bản nháp hoặc ghi nhận đã đối chiếu đề/đáp án. Tên/nhãn người biên soạn và revision được lưu trong lịch sử.
4. Bấm **Xuất bộ 20 bài** để tạo lại metadata từ các bản đã lưu. Bản đang gõ chưa lưu không được đưa vào export.

Hai tab cùng sửa một câu phải dùng đúng revision; bản cũ bị từ chối để tránh mất dữ liệu. Server review chỉ lắng nghe loopback và yêu cầu phiên trang hiện tại khi ghi. Đây là công cụ authoring nội bộ, không dùng làm server production.

## Kiểm chứng

37 bài kiểm thử qua, bao gồm lưu/restart, lịch sử, chống ghi đè giữa hai tab, không tự nâng quyền chấm, ràng buộc block nguồn, kiểm tra phiên trang khi ghi, số thập phân và tách student preview khỏi đáp án.

Đã kiểm tra trực tiếp bằng trình duyệt: render LaTeX, chọn bài, lưu đối chiếu, sửa công thức và tải lại vẫn giữ phiên bản. Bộ 20 bài và ghi chú Câu 260 hiển thị được; API export đã tạo đủ 20 mục theo schema. Ảnh xác minh nằm ở `curation-qa/review-editor-proof.jpg` trong output.

Bước tiếp theo là duyệt học thuật các ghi chú nguồn và biên soạn lời giải/rubric cho nhóm phù hợp; sau đó mới tích hợp staging/import và checker với Coach Learning.
