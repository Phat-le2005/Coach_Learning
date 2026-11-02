# Survey: pipeline PDF Toán → metadata dùng lại được

Ngày khảo sát: 02/11/2026. Phạm vi: tài liệu/model card chính thức và thiết kế áp dụng cho Coach Learning. **Chưa chạy suy luận hay A/B các model được khảo sát.** Các lựa chọn bên dưới là shortlist thử nghiệm; không phải bảng xếp hạng đã đo trên PDF Toán tiếng Việt.

Cập nhật sau khảo sát: đã chạy pilot native, PaddleOCR-VL trang 1 và pipeline kết hợp trên 57 trang; xem `docs/pdf-metadata-pilot-results-2026-11-02.md`. Các mô tả “chưa chạy” bên dưới phản ánh thời điểm khảo sát ban đầu; trạng thái thực nghiệm mới nằm trong báo cáo kết quả và benchmark plan.

## 1. Kết luận đề xuất

Xây pipeline theo từng công đoạn với schema dữ liệu trung gian độc lập engine. Bắt đầu bằng native PDF extraction làm baseline, **PaddleOCR-VL-1.6 qua pipeline chính thức** là ứng viên đọc trang đầu tiên, **MinerU2.5-2509-1.2B** là đối chứng. Giữ Docling standard pipeline như phương án đối chứng về cấu trúc/provenance. Chọn parser mặc định sau khi đo trên tập có PDF chưa dùng để chỉnh cấu hình.

Qwen3-VL-4B-Instruct là ứng viên xử lý vùng khó/ghép ngữ nghĩa; việc phù hợp vai trò này là đề xuất kiến trúc, chưa phải khả năng đã được đánh giá cho bộ dữ liệu của nhóm. Chạy bổ sung trên vùng cần thiết sau khi đã đo, thay vì trả chi phí nhiều model cho mọi trang.

Tính kế thừa đến từ schema, adapter, cấu hình bố cục, tập kiểm tra hồi quy và phiên bản dữ liệu. Model đọc tốt PDF không tự cung cấp cấu trúc đề–đáp án–lời giải–reference step/rubric của Coach Learning.

## 2. Survey các lựa chọn

| Lựa chọn | Tài liệu chính thức xác nhận | Vai trò đề xuất và giới hạn cần đo |
| --- | --- | --- |
| PaddleOCR-VL-1.6, họ 0.9B | Model card có nhận dạng công thức/bảng/biểu đồ và tác vụ spotting; hướng dẫn phân biệt pipeline toàn trang với inference từng vùng qua Transformers. Model card ghi Apache-2.0. | Ứng viên A cho trang/vùng phức tạp. Tài liệu họ PaddleOCR-VL liệt kê tiếng Việt; chất lượng dấu và ký hiệu Toán vẫn phải đo riêng. |
| MinerU2.5-2509-1.2B | VLM 1.2B; layout toàn trang rồi nhận dạng crop độ phân giải gốc cho chữ/công thức/bảng. Card nhấn mạnh công thức Trung–Anh, gắn ngôn ngữ Chinese/English và AGPL-3.0. | Ứng viên B đối chứng công thức, thứ tự đọc, bbox. Tiếng Việt chưa được xác nhận bằng benchmark của nhóm. |
| Docling standard pipeline | Framework đa định dạng, có layout, reading order, bảng, công thức và DoclingDocument thống nhất; OCR chọn engine/ngôn ngữ riêng; formula enrichment là cấu hình riêng. | Đối chứng C về cấu trúc dữ liệu và khả năng tích hợp. Cần ghi rõ OCR/formula model và cấu hình, không chỉ ghi “Docling”. |
| PP-StructureV3 | PaddleOCR mô tả pipeline này có tọa độ chi tiết hơn họ PaddleOCR-VL, gồm dòng chữ và ô bảng. | Thử khi cần tọa độ chi tiết phục vụ source spans hoặc kiểm tra bảng; phải đo cả chất lượng các recognizer đi kèm. |
| Qwen3-VL-4B-Instruct | VLM tổng quát 4B; card mô tả OCR/hiểu cấu trúc tài liệu, Apache-2.0. | Ứng viên xử lý vùng khó và đề xuất ghép bài/step. JSON hợp lệ hay suy luận hợp lý chưa chứng minh đã đọc đúng nguồn. |
| Marker | Xuất Markdown/JSON/HTML, hỗ trợ bảng/công thức và hình. Có chế độ dùng LLM. Code Apache-2.0; trọng số dùng giấy phép riêng được mô tả tại repo. | Phương án tham khảo; smoke-test phiên bản và phụ thuộc inference hiện tại trước khi chọn cho notebook. |
| GLM-OCR | Card nêu 0.9B, pipeline hai chặng layout/recognition và MIT. Metadata liệt kê zh/en/fr/es/ru/de/ja/ko, không liệt kê vi. | Đối chứng phụ nếu còn ngân sách; chưa chọn làm mặc định cho tài liệu tiếng Việt. Việc không liệt kê vi không chứng minh model hoàn toàn không đọc được vi. |
| Granite-Docling-258M | Model nhỏ tích hợp Docling, có công thức và đọc theo vùng. Card ghi English, thử nghiệm thêm một số ngôn ngữ khác, Apache-2.0. | Có thể thử cho chi phí thấp; không đồng nhất phạm vi OCR của framework Docling với khả năng tiếng Việt của checkpoint này. |
| DeepSeek-OCR-2 | Repo chính thức có inference vLLM/Transformers, môi trường tham chiếu cụ thể và Apache-2.0. | Đối chứng phụ; mức phù hợp Toán Việt và môi trường Kaggle chưa được kiểm chứng ở đây. |
| VietOCR | Repo OCR tiếng Việt với mô hình nhận dạng và Apache-2.0. | Ứng viên đọc lại dòng chữ Việt đã crop khi cần. Không xem một recognizer chữ là bộ phân tích trang, bảng hay công thức đầy đủ. |

### Chi tiết phiên bản cần giữ

- Repo MinerU đang mô tả **4.1** với API Tasks có thay đổi lớn; checkpoint **MinerU2.5-2509-1.2B** là một tài sản riêng. Ghi cả phiên bản engine và revision checkpoint. Giấy phép repo hiện tại cũng không đồng nghĩa với giấy phép checkpoint cũ.
- Hướng dẫn Transformers của PaddleOCR-VL-1.6 chỉ hỗ trợ nhận dạng từng vùng/spotting; muốn layout toàn trang phải dùng pipeline tương ứng. Không benchmark prompt OCR từng ảnh rồi mô tả kết quả là đã chạy đầy đủ parser trang.
- Tài liệu quảng bá độ chính xác hoặc điểm OmniDocBench là bằng chứng tham khảo về tác vụ được đánh giá, không phải tỷ lệ đúng trên PDF Toán Việt. Không so trực tiếp điểm lấy từ phiên bản benchmark/cấu hình khác nhau.
- Khảo sát không cài package, tải trọng số, gọi API trả phí hoặc suy ra thời gian/VRAM thực tế trên Kaggle.

## 3. Pipeline chung đề xuất

```text
Nhận PDF và manifest nguồn
  -> kiểm tra từng trang/vùng
      -> lấy chữ/tọa độ/style/vector gốc khi dùng được
      -> layout + OCR/công thức cho trang ảnh hoặc vùng cần đọc bổ sung
  -> chuẩn hóa thành PageDocument / BlockDocument
  -> ghép đề, ý con, đáp án, lời giải qua nhiều trang
  -> tạo reference steps, MathSpec/AnswerSpec/rubric ứng viên
  -> kiểm tra schema, nguồn, liên kết và nội dung
  -> duyệt -> export có phiên bản -> adapter vào Coach Learning
```

### Công đoạn A — tiếp nhận và profile

Mã document gắn với hash PDF. Từng trang giữ kích thước, rotation, số trang PDF và số in trên trang nếu đọc được, text/image/vector, màu/font và cảnh báo trích xuất. Trang có nhiều ký tự không mặc định là công thức đúng. Trang không có chữ trích được không mặc định là trang trắng.

Baseline native PDF dùng pdfplumber/PyMuPDF hoặc thư viện tương đương; bộ đếm trang hiện có có thể dùng pypdf. Đây là các công cụ, không phải model OCR. Giữ nguyên PDF và ảnh nguồn để đối chiếu dấu gạch, số mũ, phân số, bảng và các đáp án có dấu hiệu tô màu.

### Công đoạn B — đọc bố cục và nội dung

Engine adapter nhận trang/crop và xuất block chữ, heading, formula, table, figure, caption, header/footer cùng reading order. Tọa độ từ các engine phải chuyển về hệ tọa độ trang gốc, lưu cả phép biến đổi resize/rotation/crop.

Không ép bảng biến thiên thành bảng ô thông thường: mũi tên, đường nét và quan hệ dấu có thể là cấu trúc chuyên biệt. Giữ crop/đường vẽ và trạng thái cần xử lý nếu chưa có bộ đọc đủ tốt. Biểu đồ cần giữ nguyên ảnh/nguồn khi chưa trích được số liệu được kiểm chứng.

### Công đoạn C — biểu diễn trung gian ổn định

PageDocument/BlockDocument tối thiểu có:

```text
schema_version
document_id, source_sha256, page_number
page_width, page_height, coordinate_origin, coordinate_unit
block_id, block_type, bbox, reading_order
text_raw, latex_candidate, table_candidate, asset_refs
style_runs / vector_refs khi có dữ liệu native
parser_id, parser_version, model_id, model_revision, config_hash
extraction_status, review_flags
```

Những phần model không trả được ghi thiếu một cách tường minh. Đầu ra backend đặc thù được giữ làm raw artifact, còn phần ghép bài dùng schema chung. Nâng model không buộc sửa core chấm.

### Công đoạn D — ghép thành bài và step metadata

- Tín hiệu kết hợp: vị trí, cỡ/màu/font, heading/mục, Câu/Bài/Ví dụ, Lời giải/Hướng dẫn/Đáp án, danh sách lựa chọn và caption.
- Một câu được phép có nhiều source spans, nhiều trang và ý con. Không dùng riêng số câu làm ID toàn cục; thêm document/section/occurrence.
- Giữ trạng thái đang ghép qua trang, bao gồm lời giải cuối trang; không tách cứng nội dung theo chunk ký tự.
- Quy tắc bố cục là profile cấu hình. LLM/VLM chỉ xử lý phần mơ hồ với các block/crop có ID nguồn, trả JSON theo schema. Trường thiếu để null và có lý do.
- Reference steps mô tả mục tiêu toán học có nguồn, khác với từng dòng PDF và khác bước học sinh viết. Rubric/chỉ dẫn kiểm chứng phải được biên soạn và kiểm tra riêng.

### Công đoạn E — kiểm tra và phát hành

Schema hợp lệ, biểu thức parse được và số lượng câu đúng không chứng minh nội dung toán đúng. Kiểm tra cả quan hệ đề–đáp án, miền/điều kiện, ký hiệu, hình/bảng và reference step. Phần trích xuất chưa chắc chắn giữ trạng thái cần duyệt. PDF lạ vẫn được tiếp nhận, nhưng không được tự xác nhận thành công khi ghép chưa đủ căn cứ.

Student view được kiểm tra để không chứa đáp án/lời giải gắn trong crop. Chấm chính thức còn qua gate khả năng checker và phiên bản rubric; không dùng kết quả OCR hay ý kiến model làm quyết định học tập.

## 4. Tính kế thừa khi thêm PDF

1. **Adapter cho engine:** native, PaddleOCR-VL, MinerU, Docling có cùng kiểu đầu ra trung gian.
2. **Profile cho bố cục:** từ khóa, cách đánh số, cột, header/footer và quy tắc nối trang nằm trong cấu hình, có profile auto/unknown.
3. **Schema và taxonomy:** mỗi loại đề/step dùng cùng hợp đồng có phiên bản; mapping chỉ chọn mã học thuật được hệ thống cho phép.
4. **Fallback có kiểm soát:** dùng parser thứ hai hoặc VLM trên vùng lỗi/bất đồng đã xác định; chờ duyệt khi chưa giải quyết được.
5. **Golden corpus:** giữ các trang và metadata đã kiểm tra để chạy hồi quy mỗi lần đổi model/profile.
6. **Cache/checkpoint:** khóa theo hash tài liệu + trang/vùng + engine/model/config revision; sửa một vùng chỉ vô hiệu phần phụ thuộc tương ứng.

Một số PDF mới có thể cần profile hoặc nhãn bổ sung. Cam kết hợp lý là tiếp nhận, phân luồng, giữ nguồn và phát hiện phần chưa chắc; khả năng nhận đúng mọi PDF cần được đo, không được suy ra từ file mẫu duy nhất.

## 5. Kế hoạch benchmark trước khi chọn model mặc định

### Tập đánh giá

- Dùng file pilot 57 trang để kiểm tra luồng ghép xuyên tài liệu. 120 đầu câu 151–270 là mốc kiểm tra hồi quy riêng của fixture, không viết cứng vào parser.
- Chọn trước 20–30 trang để gán bản chuẩn: một phần dùng điều chỉnh, phần kiểm tra giữ PDF/bố cục khác chưa dùng điều chỉnh. Tách theo PDF/tác giả hoặc họ bố cục, không chỉ chia ngẫu nhiên trang cùng một file.
- Phải có: dấu phủ định, phân số/số mũ/chỉ số, bảng biến thiên, hình/biểu đồ, câu qua trang, đáp án màu, trang scan, nhiều cột, câu nhiều ý và loại câu khác trả lời ngắn.
- Các ca hồi quy đã quan sát trong kho: lời giải Câu 152 nối trang 1–2 của pilot; trang cuối không có đầu câu mới; nguồn 12 trang 3 mất dấu phủ định trong text; nguồn 10 trang 3 là ảnh toàn trang; nguồn 8 trang 3 có bảng/biểu đồ và câu qua trang.

### Cấu hình A/B

| Run | Nội dung |
| --- | --- |
| Native baseline | Chữ/tọa độ/style native, không OCR model; cùng assembler và validator |
| A | PaddleOCR-VL-1.6 pipeline chính thức, cùng schema/assembler |
| B | MinerU2.5 checkpoint được ghim, cùng schema/assembler |
| C, tùy ngân sách | Docling standard với engine OCR/formula được ghi rõ |

Đo parser độc lập trước, sau đó đo thêm giá trị của VLM hỗ trợ ghép step/vùng khó. Không gộp thay model, thay prompt và thay assembler vào cùng một phép so sánh không ghi nhận.

### Đo gì

- OCR: sai ký tự và dấu tiếng Việt; lỗi ký hiệu Toán trọng yếu.
- Công thức: so khớp với nguồn và cấu trúc, kết hợp normalized edit/render-based metrics khi phù hợp. Một kết quả CAS đơn lẻ không xác nhận OCR đúng hay hai biểu thức có cùng miền.
- Bảng: cấu trúc ô/giá trị; bảng biến thiên đánh giá thêm điểm, dấu, mũi tên và khoảng.
- Reading order và source spans: thứ tự, bbox/trang, khả năng truy lại nguồn.
- Mức bài: precision/recall tách câu, nối trang và liên kết đúng đáp án/lời giải.
- Mức step: mục tiêu bước đúng, source span đúng, không tự bổ sung kết luận thiếu nguồn.
- Vận hành: giây/trang p50/p95, đỉnh RAM/VRAM, OOM, tỷ lệ chuyển duyệt và phút sửa/bài. Ghi GPU/dtype/resolution/batch và revision.

OmniDocBench là nguồn tham khảo cho cách đánh giá text, layout, formula, table và reading order. Nhóm cần bổ sung các phép đo ghép câu/lời giải và metadata chấm vì benchmark đọc tài liệu không đánh giá hết quy trình này.

### Điều kiện chọn

Chọn theo lỗi ký hiệu và liên kết bài trước, sau đó mới thời gian/tài nguyên và công sửa. Mọi item phát hành phải qua gate nguồn/nội dung/khả năng chấm. Đặt ngưỡng tự động sau khi đo và hiệu chỉnh trên dữ liệu được gán nhãn; không dùng confidence do model tự nêu làm xác suất đúng đã được hiệu chuẩn.

## 6. Chạy trên Kaggle

Notebook điều phối; module Python giữ logic. Đề xuất bốn chặng: profile/native; thử parser GPU; ghép item/reference step; review/export. Các backend có thể chạy ở notebook riêng để ghim dependency độc lập, rồi trao đổi bằng schema chung.

Preflight phải kiểm tra Python/CUDA/VRAM/dtype và chạy smoke test trước khi xử lý hàng loạt. Đọc yêu cầu của đúng bản model; không suy từ số tham số ra VRAM hay tốc độ. Khởi đầu batch nhỏ, lưu checkpoint theo trang. Lưu version đầu ra để phiên chạy sau nạp làm input; lưu notebook và quyền dataset theo cấu hình Kaggle thực tế.

Gói phát hành cho Coach Learning giữ manifest, blocks, question candidates, reference steps, review queue và assets. Adapter ánh xạ sang Question/AnswerSpec/MathSpec/rubric có phiên bản như thiết kế assessment trước đó. Bước import và khả năng chấm là gate riêng.

## 7. Nguồn chính thức đã đọc

- [PaddleOCR-VL-1.6 model card và cách inference](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6)
- [PaddleOCR-VL: FAQ liệt kê các ngôn ngữ, gồm Vietnamese](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PaddleOCR-VL/PaddleOCR-VL.en.md)
- [PaddleOCR repo: PP-StructureV3 và khác biệt tọa độ](https://github.com/PaddlePaddle/PaddleOCR)
- [MinerU2.5-2509-1.2B model card](https://huggingface.co/opendatalab/MinerU2.5-2509-1.2B)
- [MinerU repo hiện tại và phiên bản/API](https://github.com/opendatalab/MinerU)
- [Docling framework](https://github.com/docling-project/docling)
- [Docling: OCR và lựa chọn ngôn ngữ](https://github.com/docling-project/docling/blob/main/docs/concepts/OCR.md)
- [Docling: enrichments](https://docling-project.github.io/docling/usage/enrichments/)
- [Granite-Docling-258M model card](https://huggingface.co/ibm-granite/granite-docling-258M)
- [Qwen3-VL-4B-Instruct model card](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct)
- [Marker repo và giấy phép code/trọng số](https://github.com/datalab-to/marker)
- [GLM-OCR model card, gồm metadata ngôn ngữ](https://huggingface.co/zai-org/GLM-OCR/raw/main/README.md)
- [DeepSeek-OCR-2 repo](https://github.com/deepseek-ai/DeepSeek-OCR-2)
- [VietOCR repo](https://github.com/pbcquoc/vietocr)
- [OmniDocBench và các công đoạn/metric đánh giá](https://github.com/opendatalab/OmniDocBench)
- [Kaggle Notebooks](https://www.kaggle.com/docs/notebooks)
