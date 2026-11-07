# Math Knowledge Graph – PDF Answer Key Pipeline

## 1. Mục tiêu
MVP đọc PDF đề + lời giải, phân đoạn thành Question/Solution, lưu dữ liệu và nguồn trang vào Neo4j.

## 2. Chạy Neo4j
```bash
docker compose up -d
```
Neo4j Browser: http://localhost:7474  
Bolt: bolt://localhost:7687

## 3. Cài đặt
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```
Sửa mật khẩu trong `.env` cho khớp `docker-compose.yml`. Đặt PDF tại `data/input/answer_key.pdf`.

## 4. Chạy pipeline
```bash
mkdir -p data/input
python -m src.main
```

## 5. Kiểm tra dữ liệu trong Neo4j
```cypher
MATCH (d:Document)-[:CONTAINS]->(q:Question)
OPTIONAL MATCH (q)-[:HAS_SOLUTION]->(s:Solution)
OPTIONAL MATCH (q)-[:FOUND_ON]->(p:SourcePage)
RETURN d, q, s, p
ORDER BY q.id;
```

## 6. Giới hạn quan trọng
- Parser hiện là MVP dựa trên nhãn Câu/Bài và Lời giải/Đáp án. Cần tùy biến theo bố cục PDF thực tế.
- PDF scan cần OCR; PDF nhiều cột, bảng biến thiên hoặc công thức phức tạp cần xử lý layout riêng.
- Chưa tự suy diễn các bước giải. `Solution.raw_text` giữ nguyên phần trích xuất; không gán số bước nếu tài liệu không đánh dấu rõ.
- Chưa tự động chuyển hình sang TikZ/PGFPlots. Nên giữ crop ảnh gốc và chỉ tạo LaTeX khi đã nhận dạng được dữ liệu hình.
- `latex_figures.py` có hàm crop vùng PDF và mẫu tạo đồ thị hàm số; biểu thức đưa vào phải được chuẩn hóa/kiểm duyệt.


## 7. Các bước nhận diện được bổ sung

Pipeline mở rộng tạo `data/output/recognition.json` gồm:

1. `solution_steps`: tách lời giải thành các bước ứng viên dựa trên xuống dòng, số thứ tự và từ nối như "Suy ra", "Do đó", "Vậy".
2. `operation_candidate`: gợi ý loại thao tác như biến đổi đại số, đạo hàm, tích phân, thế số, phân tích nhân tử.
3. `math_regions`: đánh dấu dòng có khả năng là công thức, bảng biến thiên hoặc tham chiếu hình/đồ thị.
4. `image_blocks`: liệt kê ảnh nhúng trong PDF cùng trang và bounding box.
5. `latex_export.py`: tạo mẫu LaTeX cho đồ thị hàm số và bảng biến thiên từ dữ liệu có cấu trúc đã được kiểm chứng.

### Chạy
```bash
python -m src.main
```

### Giới hạn
Đây là nhận diện heuristic, chưa phải OCR/AI hiểu toán. Dòng công thức có thể bị tách/gộp sai; block ảnh chưa được phân loại nội dung; bảng biến thiên và hình học chưa được tái dựng tự động. Mọi kết quả đều gắn cờ cần rà soát. Với PDF scan cần bổ sung OCR; với công thức ảnh cần mô hình nhận dạng công thức (ví dụ pix2tex/Math OCR) và bộ kiểm tra toán học.
