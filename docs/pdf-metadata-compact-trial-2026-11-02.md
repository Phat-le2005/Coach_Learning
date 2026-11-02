# Thử pipeline metadata local trên PDF đạo hàm

Ngày 02/11/2026. Kết luận: **chưa đủ điều kiện chạy toàn bộ kho để tạo dữ liệu chấm tự động**. Native/OCR và tách câu có thể dùng làm bản nháp có nguồn, nhưng kiểm tra toán và review Qwen chưa đạt độ tin cậy cần thiết.

**Đính chính sau đối chiếu crop 240 DPI:** nhận xét ban đầu về hai dấu âm ở bảng câu 161 là sai. Nét dọc rất mảnh của dấu cộng bị khó nhìn ở ảnh xem trước 120 DPI. Crop rõ hơn cho thấy bảng là `+ 0 −`, phù hợp với công thức đạo hàm. Không dùng câu này như một ca lỗi nguồn. Các số đo Qwen phía dưới vẫn là số đo của lượt thử trước.

## Phạm vi thực tế

PDF được người dùng chỉ định:

`E:\HocTap\Hackathon-SGU2026\Coach_Learning\data\tu-luan-va-trac-nghiem-ung-dung-dao-ham-de-khao-sat-va-ve-do-thi-ham-so-toan-12-knttvcs9.pdf`

- 57 trang, 120 câu, số thứ tự 151–270; SHA-256 `5db1fc66ab0a42553e882981d1b22935967295b9a73cd2c96840e6ee5dd76927`.
- Tái sử dụng native/OCR đã trích xuất từ đúng PDF này; lượt thử hiện tại không chạy lại toàn bộ Paddle OCR. Hash PDF, trang và candidate generation được kiểm tra.
- Kiểm tra cấu trúc nguồn và toán có giới hạn trên cả 120 câu. Tạo lại đề xuất bước từ extraction, **không dùng sửa công thức hoặc ghi chú biên tập đã biết**.
- Qwen review **8 câu được chọn chủ đích**: 151, 152, 154, 158, 213, 260, 157, 161. Sáu câu hồi quy và hai câu ngoài bộ biên tập 20 câu cũ. Không coi đây là mẫu ngẫu nhiên hay độ chính xác trên cả PDF.
- Cả hai lượt Qwen chỉ nhận chữ/OCR, công thức ứng viên và đáp án in trong nguồn. Không gửi ảnh hoặc các ghi chú lỗi đã biết vào inference. Người kiểm tra đối chiếu các ảnh nguồn riêng sau khi có phản hồi.
- Câu 260 có bước dài bị rút ngắn theo ngân sách 350 ký tự; package ghi `input_truncated=true`. Vì vậy kết quả câu này phản ánh cả hạn chế đầu vào lẫn model, không phải phép đo khả năng đọc toàn lời giải của Qwen. Phần đối chiếu ảnh bên dưới đọc đủ nguồn. Input bị rút ngắn luôn cần review, kể cả khi model không báo lỗi.
- Chưa chạy inference trên kho 13 PDF / 3.478 trang.

## Luồng mới đã triển khai

PDF hash → native/OCR có sẵn → tách bước không dùng sửa tay → nhóm các cách đọc công thức → parser số học/LaTeX có giới hạn → SymPy kiểm đồng nhất đạo hàm → Qwen trả danh sách vấn đề/tách-gộp ngắn → cổng schema và số bước → hàng chờ review.

`safe_math.py` dùng tokenizer/parser riêng, không đưa chuỗi nguồn vào `eval` hoặc `sympify`. Hỗ trợ một phần số thập phân, số mũ, phân thức, hàm lượng giác có ngoặc; kiểm đạo hàm hiện chỉ nhận hàm hữu tỉ/đa thức bậc giới hạn. Lưu mẫu số trước khi rút gọn. Không suy bảng dấu, miền xác định đầy đủ, dấu tham số, đáp án hoặc điểm số từ một kết quả đồng nhất đại số.

Khi các OCR khác nhau, có thể kiểm từng giả thuyết nhưng không tự chọn một bản là đúng. Ví dụ công thức Latin `v` và Greek `ν` được giữ khác nhau; việc một bản PASS không xóa cờ xung đột. Cảnh báo không phải bằng chứng câu đó sai; nhiều trường hợp nằm ngoài phạm vi parser.

## Kết quả trên cả PDF

| Hạng mục | Kết quả |
|---|---:|
| Câu có metadata để kiểm tra | 120 |
| Nhóm công thức OCR trong các bước | 187 |
| Nhóm đủ điều kiện chọn ứng viên theo parser | 23 |
| Câu có kiểm tra đồng nhất đạo hàm được hỗ trợ | 3/120 |
| Phép kiểm tra đạo hàm PASS | 3 |
| Phép kiểm tra NOT_ASSESSED | 16 |
| Câu không có phép kiểm toán được hỗ trợ | 117 |
| Câu chứa công thức chưa hỗ trợ hoặc mơ hồ | 88 |
| Câu có nhiều cách đọc công thức chưa thống nhất | 15 |
| Câu còn bảng biến thiên dạng ảnh, chưa có hàng/cột có nghĩa | 12 |
| Câu chứa chuỗi đẳng thức OCR không nhất quán | 5 |
| Câu được duyệt học thuật / sẵn sàng chấm / xuất bản tự động | 0 / 0 / 0 |

Các hàng cảnh báo có thể cùng thuộc một câu; không cộng chúng thành tổng số câu lỗi. Ba phép PASS là kiểm công thức ứng viên, không phải ba lời giải đã được duyệt.

## Hai lượt Qwen thực tế

Cùng Qwen3-VL-2B-Instruct Q8_0, llama.cpp CPU 3 threads, một slot, model đã load. Không tải thêm model, không gọi API cloud.

| Hạng mục | Lượt 1 | Lượt 2 sau sửa adapter |
|---|---:|---:|
| Câu được gửi inference | 8 | 8 |
| Thời gian vòng review | 191,837 giây | 87,178 giây |
| Local tokens theo server | 9.423 | 9.100 |
| Phản hồi qua cổng định dạng và số bước | 3 | 2 |
| Phản hồi bị chặn | 5 | 6 |
| Cloud API calls | 0 | 0 |

Lượt 1: schema portable vốn dùng cho cloud đã bỏ giới hạn độ dài chuỗi. Năm phản hồi có JSON đầy đủ nhưng nội dung vượt giới hạn hợp đồng nên bị chặn; không phải lỗi cắt token.

Lượt 2: adapter local giữ JSON Schema đầy đủ, gồm độ dài và số phần tử. Lỗi độ dài được xử lý, nhưng sáu phản hồi đề xuất SPLIT nhiều bước cùng lúc hoặc MERGE chỉ một bước. Cổng deterministic từ chối chúng, không tự sửa rồi coi là hợp lệ. Câu 154 có trạng thái `NO_ISSUE_FOUND` nhưng vẫn đề xuất thay đổi nên tiếp tục bị gắn cờ. Câu 158 qua cổng định dạng nhưng bỏ sót lỗi nguồn. Đúng JSON không chứng minh đúng toán.

Lượt 2 chạy trên server đã được làm nóng bởi lượt 1 và có thể dùng KV prompt cache. Không suy thời gian toàn kho từ số đo này, không đồng nhất với cache kết quả của pipeline. Thử lại đúng 8 job qua cache ứng dụng: **0 inference calls**, 0,057 giây sau preflight. Kết quả lỗi cũng được lưu để tránh tự lặp inference.

## Nội dung đối chiếu với ảnh PDF

Đây là kiểm tra có mục tiêu bằng ảnh nguồn, không phải bộ đáp án vàng do giáo viên duyệt.

| Câu | Điều thấy trong ảnh nguồn | Kết quả Qwen và giới hạn |
|---|---|---|
| 151 | Đạo hàm `1,5x−0,075x²` và nghiệm `0,20` phù hợp với hàm đã in. Bảng dấu vẫn chưa được cấu trúc hóa. | Nhận xét rằng phép giải nghiệm sai nhưng không chỉ ra sai ở đâu; không đủ căn cứ để dùng sửa lời giải. |
| 152 | Công thức đạo hàm năng lượng đúng theo phép đồng nhất; vẫn cần xét dấu `c` để suy tính giảm. | Nêu nghi ngờ đạo hàm thiếu căn cứ và không giải quyết rõ vấn đề dấu tham số. |
| 154 | Khoảng tăng `(0;12)` không chứa đầu mút 0. | Phản hồi coi việc đầu mút 0 không thuộc miền là vấn đề của khoảng mở; đề xuất tách/gộp thiếu ích lợi. |
| 158 | Dòng nguồn in `P=C−R` nhưng phần sau tính `R−C=−0,01x²+30x−1000`. | Trả `NO_ISSUE_FOUND`, bỏ sót mâu thuẫn. |
| 213 | Lời giải chia cho `m`, viết điều kiện `m≠0` rồi kết luận `m=0`. Cần xét riêng `m=0`: hàm thành `−x²+2`, có cực trị. | Có nhắc vấn đề điều kiện `m≠0` nhưng không giải quyết nhánh `m=0`; kèm nhận xét không có bảng chưa đúng trọng tâm. |
| 260 | Đề hỏi **hoành độ** hai cực trị cùng dấu; lời giải xét `y₁y₂>0`, là **tung độ**. Với đúng câu chữ đề: `m<2` và `m>−2`, ba số nguyên là `−1,0,1`; đáp án in 6 giải điều kiện khác. | Không phát hiện sự khác nhau hoành độ/tung độ, lại yêu cầu bảng dữ liệu không cần thiết. |
| 157 | Bài logistic có đạo hàm dài và bảng; OCR còn khó đọc. | Nhận xét đạo hàm có lỗi rất chung, không cung cấp chứng cứ để sửa. |
| 161 | Crop nguồn 240 DPI cho thấy bảng `+ 0 −`, khớp dấu của đạo hàm trên hai khoảng. Ảnh xem trước 120 DPI làm nét dọc của dấu cộng khó nhìn. | Nhận xét chung của Qwen về lỗi đạo hàm không có chứng cứ đủ để sửa. Rút lại ghi chú ban đầu cho rằng bảng nguồn có hai dấu âm. |

Vì có lỗi đã biết bị bỏ sót và nhận xét không có căn cứ, không báo một tỷ lệ “đúng nội dung” từ tám phản hồi này. Không sửa đáp án nguồn hoặc rubric tự động.

## Đầu ra và cách xem

Lượt chính sau sửa adapter:

`E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-metadata-pilot-v1\metadata-trial-v2\`

- `review.html`: xem 120 câu, bước, cờ và tám phản hồi Qwen, kể cả raw response bị chặn; có ảnh nguồn để đối chiếu.
- `report.json`, `math-report.json`: phạm vi, số đo, trạng thái không sẵn sàng chạy kho lớn.
- `questions.math-audit.jsonl`, `questions.math-audit.pretty.json`: bản audit, không phải file đầu vào chấm đã duyệt.
- `qwen/jobs/*/`: package, raw response và state theo hash.
- `qwen/questions.compact-reviewed.pretty.json`: chỉ hai phản hồi qua cổng, vẫn chưa duyệt học thuật.
- `cache-check.json`: thử đọc lại kết quả không inference.
- Lượt 1 giữ riêng trong `metadata-trial-v1`; không ghi đè thử nghiệm đọc ảnh cũ ở `local-review`.

Viewer đã có ở [bản thử mới](http://127.0.0.1:8787/metadata-trial-v2/review.html), kiểm HTTP 200. Chưa xác nhận trực tiếp giao diện browser. Tất cả outputs và môi trường ở E. 121 file nguồn trong snapshot đầu/cuối lượt 2 không thay đổi; 62 hash đầu vào đã theo dõi từ trước cũng không thay đổi. Server Qwen đã dừng sau thử nghiệm để trả RAM; viewer vẫn đọc được.

Tái chạy có giới hạn từ thư mục repo:

```powershell
.\tools\pdf_metadata\run.ps1 -Action local-start
# Chờ local-preflight thành công rồi mới chạy inference.
.\tools\pdf_metadata\run.ps1 -Action local-preflight
.\tools\pdf_metadata\run.ps1 -Action pilot-trial -Limit 8 -MaxOutputTokens 768 `
  -TrialOutput 'E:\HocTap\Hackathon-SGU2026\Coach_Learning\.tmp\pdf-metadata-pilot-v1\metadata-trial-v2'
.\tools\pdf_metadata\run.ps1 -Action local-stop
```

Chỉ chạy audit không inference bằng `-Action pilot-trial -MathOnly` với output riêng. Action này cần native/enriched pilot có sẵn khớp PDF; không tự nhận mọi PDF khác là đã được trích xuất. Lượt khác PDF hoặc candidate generation khác phải tạo pilot mới trước.

107 tests của công cụ PDF đã qua sau thay đổi, bao gồm parser có giới hạn, các điểm loại trừ mẫu số, lỗi chain, cách đọc OCR mơ hồ, chặn ảnh/gold notes trong metadata inference, ràng buộc schema local, đề xuất bước không hợp lệ và chặn nhầm PDF/ghi đè vùng nguồn. Unit tests chứng minh hành vi phần mềm; không thay cho benchmark nội dung hay review giáo viên.

## Việc cần làm trước kho lớn

1. Tăng chất lượng lớp công thức trước: phục hồi số mũ/phân thức từ native glyph khi đủ bằng chứng, chỉ OCR lại các crop có xung đột. Chuẩn hóa một biểu thức có nguồn cho từng dòng; giữ các bản đọc chưa thống nhất ở hàng chờ.
2. Cấu trúc hóa bảng dấu/biến thiên thành mốc, khoảng, dấu, giá trị và miền; kiểm từng hàng với biểu thức đã xác minh. Câu 161 là ca hồi quy cho nét dấu cộng rất mảnh và độ phân giải ảnh.
3. Mở rộng kiểm toán có giới hạn theo loại bài: đạo hàm, nghiệm tới hạn, nhánh tham số bằng 0, đối chiếu điều kiện đề với kết luận. Câu 260 phải kiểm được đại lượng đang hỏi trước khi nhận đáp án.
4. Dùng model local để gắn cờ ngắn; chưa dùng model 2B này làm người duyệt cuối hoặc áp dụng đề xuất tách/gộp tự động. Tách việc báo lỗi nội dung khỏi việc sửa cấu trúc sẽ giảm gánh nặng hợp đồng.
5. Đánh giá bằng bộ câu đã đối chiếu nguồn, giữ riêng các câu chưa dùng chỉnh prompt. Sau khi cải thiện, thử một batch 50–100 trang thuộc nhiều PDF/layout ở chế độ bản nháp, đo độ phủ và lỗi còn sót rồi mới tăng quy mô.

Chưa cần chạy lại 3.478 trang để phát hiện các điểm nghẽn hiện có: chúng đã hiện rõ trong pilot này.
