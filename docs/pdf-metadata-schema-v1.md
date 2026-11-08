# Cấu trúc metadata PDF cố định

Hợp đồng đầu ra chính thức là
[`question-metadata.v1.schema.json`](../tools/pdf_metadata/schemas/question-metadata.v1.schema.json).
File `content.method.pretty.json` là mảng các bản ghi có cùng cấu trúc, dù đầu vào
là Toan12, tài liệu thống kê, xác suất hay một tài liệu khác. Nội dung và giá trị
nhãn có thể khác nhau giữa tài liệu; tên trường và kiểu dữ liệu được giữ cố định.
`content.draft.pretty.json` là đầu vào OCR trung gian, không phải bản metadata cuối.

Hai phiên bản độc lập:

- `schema_version`: `pdf-question-metadata/v1.0.0` ở từng bản ghi.
- `method.schema_version`: `question-method/v1.0.0` cho cấu trúc nhãn.
- `method.pipeline_version`: phiên bản thuật toán tạo nhãn, có thể thay đổi mà
  không làm thay đổi cấu trúc. Ví dụ `question-method-candidates/v2` là phiên bản
  thuật toán cũ, không phải schema đầu ra mới.

Mọi khóa được khai báo trong schema đều bắt buộc có mặt. Nhãn chưa xác định là
`null`; danh sách không có phần tử là `[]`. Không đổi giữa chuỗi, object và mảng
theo từng lần chạy. Trường riêng của nguồn chưa có trong hợp đồng được giữ trong
`extensions`, không thêm khóa tùy ý vào cấu trúc chính. Thay đổi cấu trúc chính
phải tạo phiên bản schema mới và bước chuyển đổi rõ ràng.

## Các trường chính

| Trường | Kiểu cố định | Ý nghĩa |
| --- | --- | --- |
| `question_id` | string | ID bản ghi được giữ nguyên |
| `collection_number` | integer | Thứ tự bản ghi trong bộ xuất |
| `source_number` | integer hoặc null | Số câu trong nguồn, nếu có |
| `source` | object | Danh tính và hệ tọa độ của PDF |
| `question`, `solution`, `answer` | object | Nội dung Markdown và dấu vết nguồn |
| `topic_context` | object | Ngữ cảnh tiêu đề từ bước trích xuất |
| `method` | object | Chương, bài, dạng và căn cứ gán nhãn |
| `extensions` | object | Dữ liệu mở rộng riêng của nguồn |

`method.chapter`, `method.lesson`, `method.exercise_type` đều có cùng kiểu
`label | null`. Một label luôn có đủ các khóa dưới đây:

```json
{
  "code": "BAYES_POSTERIOR",
  "name": "Công thức Bayes",
  "canonical_code": null,
  "parent_code": null,
  "source_number": null,
  "source_label": null,
  "origin": "inferred",
  "basis": null,
  "evidence": [],
  "extensions": {}
}
```

`origin` cho biết nhãn đến từ nguồn (`source`), suy luận (`inferred`) hoặc chưa
xác định được từ kết quả cũ (`unknown`). Giá trị `null` ở `canonical_code` không
đồng nghĩa nhãn sai; nguồn có thể dùng một cây chương/bài/dạng riêng.

`method` luôn có đủ các khóa:

```text
schema_version, pipeline_version, record_kind,
chapter, lesson, exercise_type, label_path,
status, classification_method, review_required,
source_header_evidence, document_labels,
candidates, inference_candidates, exercise_type_candidates, flags, extensions
```

`document_labels` luôn có `chapter`, `lesson`, `exercise_type`, `extensions`.
Ba trường nhãn giữ cấu trúc in sẵn trong tài liệu; các ứng viên suy luận vẫn nằm
trong `candidates`/`inference_candidates`. `exercise_type_candidates` là mảng
label, kể cả khi chỉ có một ứng viên. Căn cứ `evidence` luôn là mảng; mỗi phần tử
có đủ `basis`, `field`, `page_number`, `bbox`, `block_ids`, `text`,
`normalized_match`, `source_reference`, `extensions`.

`record_kind` phân biệt `EXERCISE`, `SOURCE_HEADING_NOT_EXERCISE`, `UNKNOWN`.
Bản ghi tiêu đề bị OCR ghép thành câu được giữ để đối chiếu và có thể lọc bằng
trường này. Cấu trúc cố định không bảo đảm nhãn suy luận đã đúng về học thuật;
`review_required` và các cờ chất lượng vẫn được giữ nguyên.

Schema cũng cố định các khóa của phần nội dung, fragment, block, source span và
visual asset. Các payload gốc `choices`, `tables`, `source_errors`, `quality_audit`
được giữ nguyên nội dung bên trong; v1 không định nghĩa lại định dạng nội bộ của
chúng. Đây là dữ liệu trích xuất nguồn, không phải nhãn chương/bài/dạng.

## Xuất và kiểm tra

`pdfmeta.method_labels` chuẩn hóa kết quả rồi kiểm tra JSON Schema **trước khi
ghi đầu ra**. File sai cấu trúc làm lệnh dừng với `METADATA_SCHEMA_INVALID`.
`methods.pretty.json` và `methods.jsonl` dùng cùng object `method` như bản đầy đủ.
`schema-validation.json` ghi số bản ghi và kết quả kiểm tra.

Chuẩn hóa một kết quả cũ sang schema v1 mà không chạy lại OCR hoặc phân loại:

```powershell
$env:PYTHONPATH = 'tools/pdf_metadata'
$env:PYTHONUTF8 = '1'
& 'C:\CoachLearningPdf\pdf-pipeline-runtime\.venv\Scripts\python.exe' -B `
  -m pdfmeta.metadata_contract `
  --input 'C:\CoachLearningPdf\my-job\content.method.pretty.json' `
  --output '.tmp\my-job-schema-v1\content.method.pretty.json'
```

Đầu vào và đầu ra phải khác đường dẫn. Lệnh kiểm tra nội dung nguồn, ID và mã/tên
nhãn chính không đổi; xuất thêm `content.method.pretty.schema-report.json`.
Các trường tùy chọn cũ được bổ sung mặc định hoặc chuyển vào `extensions`;
Markdown không được sửa. File gốc được đối chiếu hash để bảo đảm không bị ghi đè.
