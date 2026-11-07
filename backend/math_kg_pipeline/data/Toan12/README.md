# Kho PDF nguồn Toán 12 trên máy local

Tạo ngày 27/10/2026. Thư mục này dành cho PDF tải thủ công để đọc, đối chiếu và
chuẩn bị dữ liệu. Ứng dụng chưa được cấu hình tự quét hoặc import thư mục này.

## Cây thư mục

```text
math12/
├── README.md
├── sources.csv
├── inbox/
├── curriculum/
│   ├── 01_official_program/
│   ├── 02_amendments_and_guidance/
│   ├── 03_textbook_references/
│   │   ├── volume_1/
│   │   ├── volume_2/
│   │   └── special_topics/
│   ├── 04_software_practice/
│   ├── 05_experiential_activities/
│   └── 06_optional_topics/
│       ├── 12_1_discrete_random_variables/
│       ├── 12_2_optimization/
│       └── 12_3_financial_mathematics/
├── derivative_applications/
│   ├── theory_and_examples/
│   ├── exercises_and_exams/
│   └── answer_keys_and_solutions/
├── integrals/
│   ├── theory_and_examples/
│   ├── exercises_and_exams/
│   └── answer_keys_and_solutions/
├── grouped_statistics/
│   ├── theory_and_examples/
│   ├── exercises_and_exams/
│   └── answer_keys_and_solutions/
└── probability/
    ├── theory_and_examples/
    ├── exercises_and_exams/
    └── answer_keys_and_solutions/
```

## Chọn chỗ lưu PDF

| Thư mục | Tài liệu nên đặt vào |
| --- | --- |
| `inbox/` | PDF mới tải, chưa xác định nhóm; đề tổng hợp hoặc tài liệu có nhiều mảng. |
| `curriculum/01_official_program/` | Chương trình chính thức, bản đầy đủ hoặc phụ lục môn Toán. |
| `curriculum/02_amendments_and_guidance/` | Văn bản sửa đổi, đính chính, hướng dẫn triển khai để kiểm tra hiệu lực và phạm vi. |
| `curriculum/03_textbook_references/` | Sách giáo khoa/tài liệu đối chiếu theo tập 1, tập 2, chuyên đề; có thể chứa toàn bộ chương trình. |
| `curriculum/04_software_practice/` | Tài liệu thực hành với phần mềm toán học. |
| `curriculum/05_experiential_activities/` | Tài liệu hoạt động thực hành và trải nghiệm. |
| `curriculum/06_optional_topics/` | Chuyên đề biến ngẫu nhiên rời rạc, tối ưu, tài chính. |
| `derivative_applications/` | Hàm số, tính đơn điệu, cực trị, GTLN/GTNN, tiệm cận, khảo sát và đồ thị hàm số. |
| `integrals/` | Nguyên hàm, tích phân; xử lý ứng dụng diện tích/thể tích cần xác nhận phạm vi riêng. |
| `grouped_statistics/` | Khoảng biến thiên, khoảng tứ phân vị, phương sai, độ lệch chuẩn và diễn giải số liệu ghép nhóm. |
| `probability/` | Xác suất có điều kiện, toàn phần, Bayes, bảng 2x2 và sơ đồ cây. |

Trong bốn mảng công việc:

- `theory_and_examples/`: định nghĩa, định lý, tính chất, phương pháp và ví dụ.
- `exercises_and_exams/`: bài tập, đề kiểm tra/đề thi; có thể kèm đáp án trong cùng PDF.
- `answer_keys_and_solutions/`: PDF đáp án hoặc lời giải được cung cấp riêng.

Một PDF chứa cả lý thuyết, bài tập và lời giải chỉ cần lưu một bản theo mục đích
chính; ghi các nội dung/trang liên quan trong `sources.csv`. Không cần nhân bản
hoặc tách PDF gốc để khớp các thư mục. Giữ nguyên bản nguồn khi xử lý.

Curriculum được tổ chức đầy đủ để lưu tài liệu đối chiếu, kể cả tài liệu có phần
hình học. Điều này không mở rộng phạm vi triển khai: vectơ/hình học không gian/Oxyz
vẫn để nguyên. Chưa tạo luồng xử lý hoặc sửa dữ liệu curriculum trong backend.

## Ghi nguồn

Mỗi PDF thực tế thêm một dòng vào `sources.csv`:

- `source_id`: mã do bạn đặt để nhận biết tài liệu, ví dụ `M12_SRC_001`.
- `title`: tên đầy đủ của tài liệu.
- `source_url`: URL tải PDF trực tiếp, đã đối chiếu với file local nếu có kết quả xác minh.
- `source_page_url`: trang giới thiệu nguồn để đọc tên tài liệu, tác giả và thông tin đăng tải; tách riêng với link PDF.
- `downloaded_on`: ngày tải theo dạng YYYY-MM-DD.
- `relative_path`: đường dẫn tính từ thư mục math12 này, dùng dấu `/`.
- `sha256`: mã băm byte PDF nếu đã tính; chưa tính thì để trống.
- `notes`: tác giả, năm, các trang cần dùng, bộ sách hoặc nội dung chờ phân loại.

Nếu trường có dấu phẩy, bao giá trị bằng dấu nháy kép theo quy tắc CSV. Giữ file
dạng UTF-8 để không mất dấu tiếng Việt. Không điền thông tin xác minh hoặc hash giả.

Các trường CSV hiện được bọc bằng dấu nháy kép, kể cả URL. Giữ dấu nháy này khi
chỉnh sửa/căn cột: Ctrl + click trong VS Code có thể nhận cả dấu phẩy và cột kế tiếp
vào URL nếu URL không được tách rõ, khiến website chuyển đường dẫn sai về trang chủ.

Ngày 27/10/2026 đã kiểm tra HTTP trực tiếp 13 trang nguồn và 13 URL PDF liên kết;
SHA-256 của các PDF trên mạng khớp bản local. Chi tiết trong
`source_url_verification_2026-10-27.json`. Đây là kết quả tại thời điểm kiểm tra,
không bảo đảm website giữ nguyên URL hoặc nội dung về sau.

Tên PDF nên dễ nhận biết, chẳng hạn `tinh_don_dieu_tacgia_2026.pdf`. Thư mục
`.local/` đã được Git bỏ qua; dữ liệu ở đây chỉ nằm trên máy này, chưa tự chia sẻ
cho team. Cần lưu chung ở nơi nhóm thống nhất nếu các thành viên cùng sử dụng.

Kho này tách với `backend/var/teacher_materials/` và
`backend/var/question_acquisition/`, là nơi ứng dụng quản lý file upload/thu thập.
Chỉ đặt PDF vào đây chưa tạo document, block hay câu hỏi trong database.
