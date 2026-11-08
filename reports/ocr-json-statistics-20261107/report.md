# Thống kê câu hỏi trong ba JSON OCR — 07/11/2026

Đếm trực tiếp `content.method.pretty.json` đang có ở `C:/CoachLearningPdf/`.

- Một bản ghi `EXERCISE` được tính là một câu; không tách các ý a/b/c/d.
- Loại các bản ghi `SOURCE_HEADING_NOT_EXERCISE` khỏi số câu hỏi.
- Phân nhóm theo `method.chapter`, `method.lesson`, `method.exercise_type`; giữ nguyên mã và tên nhãn chính.
- Nhãn ứng viên không cộng vào bảng dạng chính. Bảng ứng viên ở file CSV riêng, mỗi câu chỉ được tính một lần cho mỗi mã dạng; một câu có thể thuộc nhiều ứng viên.
- Nhãn hiện tại đều cần duyệt; đây là thống kê metadata, không phải xác nhận phân loại học thuật.
- Bản `ocr-direct-full - Copy` mới là phần xuất của 1.800 trang đầu trong PDF 2.947 trang; không coi là toàn bộ sách.
- Phần thống kê có các mã bài từ nguồn và mã suy luận tên gần giống nhau; giữ riêng. Nhãn bài ghép “1,2” cũng giữ riêng vì chưa có căn cứ tách 63 câu cho từng bài.

## Tổng theo chương

| Chương | Số câu | Có dạng chính | Chỉ có ứng viên dạng | Chưa có căn cứ dạng |
| --- | --- | --- | --- | --- |
| Ứng dụng đạo hàm để khảo sát và vẽ đồ thị của hàm số | 1484 | 823 | 142 | 519 |
| Nguyên hàm. Tích phân | 806 | 606 | 0 | 200 |
| CÁC SỐ ĐẶC TRƯNG ĐO MỨC ĐỘ PHÂN TÁN CHO MẪU SỐ LIỆU GHÉP NHÓM | 84 | 32 | 51 | 1 |
| XÁC SUẤT CÓ ĐIỀU KIỆN | 121 | 76 | 18 | 27 |
| TỔNG | 2495 | 1537 | 211 | 747 |

Tổng 2,497 bản ghi JSON, gồm 2,495 câu hỏi và 2 tiêu đề bài. Có 562 câu chưa có bài chính.

## 1. Ứng dụng đạo hàm để khảo sát và vẽ đồ thị của hàm số — 1484 câu

Nguồn: `ocr-direct-full - Copy/content.method.pretty.json`.

| Bài / chủ đề theo nhãn chính | Mã bài | Số câu | Có dạng chính | Chưa có dạng chính |
| --- | --- | --- | --- | --- |
| Tính đơn điệu của hàm số | MONOTONICITY_TOPIC | 95 | 95 | 0 |
| Cực trị của hàm số | EXTREMA_TOPIC | 174 | 159 | 15 |
| Chưa có nhãn chính | — | 368 | 0 | 368 |
| Giá trị lớn nhất và giá trị nhỏ nhất | GLOBAL_EXTREMA_TOPIC | 175 | 175 | 0 |
| Ứng dụng đạo hàm trong bài toán thực tiễn | DERIVATIVE_APPLICATION_TOPIC | 121 | 121 | 0 |
| Tiệm cận, khảo sát và vẽ đồ thị hàm số | FUNCTION_ANALYSIS_TOPIC | 551 | 273 | 278 |

### Tính đơn điệu của hàm số — 95 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Nhận biết tính đơn điệu từ đồ thị | MONOTONICITY_FROM_GRAPH | 5 |
| Xét tính đơn điệu bằng đạo hàm | MONOTONICITY_FROM_EXPRESSION | 25 |
| Tìm tham số theo điều kiện đơn điệu | PARAMETER_MONOTONICITY | 49 |
| Nhận biết tính đơn điệu từ bảng biến thiên | MONOTONICITY_FROM_VARIATION_TABLE | 6 |
| Nhận biết tính đơn điệu từ dấu đạo hàm | MONOTONICITY_FROM_DERIVATIVE_SIGN | 10 |

### Cực trị của hàm số — 174 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Nhận biết cực trị từ đồ thị | EXTREMA_FROM_GRAPH | 60 |
| Tìm cực trị bằng đạo hàm | FIND_FUNCTION_EXTREMA | 28 |
| Chưa có nhãn chính | — | 15 |
| Tìm tham số theo số lượng cực trị | PARAMETER_EXTREMA_COUNT | 46 |
| Nhận biết cực trị từ bảng biến thiên | EXTREMA_FROM_VARIATION_TABLE | 9 |
| Nhận biết cực trị từ dấu đạo hàm | EXTREMA_FROM_DERIVATIVE_SIGN | 16 |

Trong số chưa có dạng chính: 0 câu có ứng viên dạng; 15 câu chưa có căn cứ dạng.

### Chưa có nhãn chính — 368 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Chưa có nhãn chính | — | 368 |

Trong số chưa có dạng chính: 142 câu có ứng viên dạng; 226 câu chưa có căn cứ dạng.

### Giá trị lớn nhất và giá trị nhỏ nhất — 175 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Tìm GTLN/GTNN trên miền đơn giản | GLOBAL_EXTREMA_SIMPLE_DOMAIN | 57 |
| Tìm GTLN/GTNN trên đoạn bằng đạo hàm | GLOBAL_EXTREMA_DERIVATIVE_INTERVAL | 64 |
| Nhận biết giá trị lớn nhất/nhỏ nhất | GLOBAL_EXTREMA_RECOGNITION | 54 |

### Ứng dụng đạo hàm trong bài toán thực tiễn — 121 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Tối ưu hóa bài toán thực tiễn bằng đạo hàm | REAL_WORLD_DERIVATIVE_OPTIMIZATION | 121 |

### Tiệm cận, khảo sát và vẽ đồ thị hàm số — 551 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Nhận biết tiệm cận từ đồ thị | ASYMPTOTE_FROM_GRAPH | 198 |
| Chưa có nhãn chính | — | 278 |
| Nhận biết tính đối xứng của đồ thị | GRAPH_SYMMETRY_IDENTIFICATION | 19 |
| Xác định tiệm cận xiên | OBLIQUE_ASYMPTOTE_RATIONAL | 1 |
| Nhận dạng đồ thị từ đặc trưng | GRAPH_IDENTIFICATION_FROM_FEATURES | 55 |

Trong số chưa có dạng chính: 0 câu có ứng viên dạng; 278 câu chưa có căn cứ dạng.

## 2. Nguyên hàm. Tích phân — 806 câu

Nguồn: `ocr-direct-full - Copy/content.method.pretty.json`.

| Bài / chủ đề theo nhãn chính | Mã bài | Số câu | Có dạng chính | Chưa có dạng chính |
| --- | --- | --- | --- | --- |
| Nguyên hàm | ANTIDERIVATIVE_TOPIC | 373 | 373 | 0 |
| Chưa có nhãn chính | — | 194 | 0 | 194 |
| Tích phân và tính chất | DEFINITE_INTEGRAL_TOPIC | 70 | 70 | 0 |
| Ứng dụng tích phân tính diện tích và thể tích | INTEGRAL_GEOMETRIC_APPLICATION_TOPIC | 55 | 49 | 6 |
| Ứng dụng nguyên hàm và tích phân trong thực tiễn | INTEGRAL_PRACTICAL_APPLICATION_TOPIC | 114 | 114 | 0 |

### Nguyên hàm — 373 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Tính nguyên hàm | CALCULATE_ANTIDERIVATIVE | 174 |
| Nguyên hàm có điều kiện | ANTIDERIVATIVE_WITH_CONDITION | 199 |

### Chưa có nhãn chính — 194 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Chưa có nhãn chính | — | 194 |

Trong số chưa có dạng chính: 0 câu có ứng viên dạng; 194 câu chưa có căn cứ dạng.

### Tích phân và tính chất — 70 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Tính trực tiếp tích phân xác định | CALCULATE_DEFINITE_INTEGRAL | 70 |

### Ứng dụng tích phân tính diện tích và thể tích — 55 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Diện tích bằng tích phân | AREA_BY_INTEGRAL | 34 |
| Thể tích khối tròn xoay | VOLUME_BY_INTEGRAL | 11 |
| Thể tích theo thiết diện | VOLUME_BY_CROSS_SECTION | 4 |
| Chưa có nhãn chính | — | 6 |

Trong số chưa có dạng chính: 0 câu có ứng viên dạng; 6 câu chưa có căn cứ dạng.

### Ứng dụng nguyên hàm và tích phân trong thực tiễn — 114 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Ứng dụng nguyên hàm/tích phân vào đại lượng tích lũy | PRACTICAL_ACCUMULATION | 114 |

## 3. CÁC SỐ ĐẶC TRƯNG ĐO MỨC ĐỘ PHÂN TÁN CHO MẪU SỐ LIỆU GHÉP NHÓM — 84 câu

Nguồn: `ocr-direct-grouped_statistics/content.method.pretty.json`.

| Bài / chủ đề theo nhãn chính | Mã bài | Số câu | Có dạng chính | Chưa có dạng chính |
| --- | --- | --- | --- | --- |
| KHOẢNG BIẾN THIÊN VÀ KHOẢNG TỨ PHÂN VỊ | DOC_LESSON_4881c5103f8de1af | 9 | 2 | 7 |
| PHƯƠNG SAI VÀ ĐỘ LỆCH CHUẨN | DOC_LESSON_f6f614689088ae60 | 6 | 1 | 5 |
| Khoảng biến thiên và khoảng tứ phân vị | GROUPED_RANGE_IQR_TOPIC | 2 | 2 | 0 |
| Vận dụng độ phân tán trong thực tiễn | GROUPED_DISPERSION_APPLICATION_TOPIC | 2 | 2 | 0 |
| Phương sai và độ lệch chuẩn | GROUPED_VARIANCE_SD_TOPIC | 1 | 1 | 0 |
| So sánh và diễn giải mức độ phân tán | GROUPED_DISPERSION_COMPARISON_TOPIC | 1 | 1 | 0 |
| KHOẢNG BIẾN THIÊN VÀ KHOẢNG TỨ PHÂN VỊ CỦA MẪU SỐ LIỆU GHÉP NHÓM PHƯƠNG SAI VÀ ĐỘ LỆCH CHUẨN CỦA MẪU SỐ LIỆU GHÉP NHÓM | DOC_LESSON_9f58e3577ec682ac | 63 | 23 | 40 |

### KHOẢNG BIẾN THIÊN VÀ KHOẢNG TỨ PHÂN VỊ — 9 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Tính khoảng biến thiên của mẫu ghép nhóm | CALCULATE_GROUPED_RANGE | 1 |
| Chưa có nhãn chính | — | 7 |
| Tính khoảng tứ phân vị của mẫu ghép nhóm | CALCULATE_GROUPED_IQR | 1 |

Trong số chưa có dạng chính: 6 câu có ứng viên dạng; 1 câu chưa có căn cứ dạng.

### PHƯƠNG SAI VÀ ĐỘ LỆCH CHUẨN — 6 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Chưa có nhãn chính | — | 5 |
| Tính độ lệch chuẩn của mẫu ghép nhóm | CALCULATE_GROUPED_STANDARD_DEVIATION | 1 |

Trong số chưa có dạng chính: 5 câu có ứng viên dạng; 0 câu chưa có căn cứ dạng.

### Khoảng biến thiên và khoảng tứ phân vị — 2 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Tính khoảng biến thiên của mẫu ghép nhóm | CALCULATE_GROUPED_RANGE | 1 |
| Tính khoảng tứ phân vị của mẫu ghép nhóm | CALCULATE_GROUPED_IQR | 1 |

### Vận dụng độ phân tán trong thực tiễn — 2 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Phân tích kết hợp nhiều số đo phân tán | MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS | 2 |

### Phương sai và độ lệch chuẩn — 1 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| Tính độ lệch chuẩn của mẫu ghép nhóm | CALCULATE_GROUPED_STANDARD_DEVIATION | 1 |

### So sánh và diễn giải mức độ phân tán — 1 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| So sánh mẫu bằng phương sai hoặc độ lệch chuẩn | COMPARE_GROUPED_VARIANCE_SD | 1 |

### KHOẢNG BIẾN THIÊN VÀ KHOẢNG TỨ PHÂN VỊ CỦA MẪU SỐ LIỆU GHÉP NHÓM PHƯƠNG SAI VÀ ĐỘ LỆCH CHUẨN CỦA MẪU SỐ LIỆU GHÉP NHÓM — 63 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| TÌM KHOẢNG BIẾN THIÊN CHO MẪU SỐ LIỆU GHÉP NHÓM | DOC_EXERCISE_TYPE_b62df27616783adf | 7 |
| TÌM TỨ PHÂN VỊ CHO MẪU SỐ LIỆU GHÉP NHÓM | DOC_EXERCISE_TYPE_1840e44363bd3162 | 8 |
| TÍNH PHƯƠNG SAI, ĐỘ LỆCH CHUẨN CỦA MẪU SỐ LIỆU GHÉP NHÓM | DOC_EXERCISE_TYPE_d2728923745070f3 | 8 |
| Chưa có nhãn chính | — | 40 |

Trong số chưa có dạng chính: 40 câu có ứng viên dạng; 0 câu chưa có căn cứ dạng.

## 4. XÁC SUẤT CÓ ĐIỀU KIỆN — 121 câu

Nguồn: `ocr-direct-probability/content.method.pretty.json`.

| Bài / chủ đề theo nhãn chính | Mã bài | Số câu | Có dạng chính | Chưa có dạng chính |
| --- | --- | --- | --- | --- |
| XÁC SUẤT CÓ ĐIỀU KIỆN | DOC_LESSON_249a20e5a118a79b | 71 | 51 | 20 |
| CÔNG THỨC XÁC SUẤT TOÀN PHẦN – CÔNG THỨC BAYES | DOC_LESSON_fc3ba5c0eace61d1 | 50 | 25 | 25 |

### XÁC SUẤT CÓ ĐIỀU KIỆN — 71 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| TÍNH XÁC SUẤT CÓ ĐIỀU KIỆN SỬ DỤNG CÔNG THỨC. | DOC_EXERCISE_TYPE_c5386433e386ca0a | 27 |
| TÍNH XÁC SUẤT CÓ ĐIỀU KIỆN SỬ DỤNG SƠ ĐỒ HÌNH CÂY. | DOC_EXERCISE_TYPE_ff8a08aa2ef8e644 | 6 |
| Tính trực tiếp xác suất có điều kiện | CONDITIONAL_PROBABILITY_DIRECT | 18 |
| Chưa có nhãn chính | — | 20 |

Trong số chưa có dạng chính: 0 câu có ứng viên dạng; 20 câu chưa có căn cứ dạng.

### CÔNG THỨC XÁC SUẤT TOÀN PHẦN – CÔNG THỨC BAYES — 50 câu

| Dạng theo nhãn chính | Mã dạng | Số câu |
| --- | --- | --- |
| MÔ TẢ CÔNG THỨC XÁC SUẤT TOÀN PHẦN THÔNG QUA BẢNG DỮ LIỆU THỐNG KÊ 2X2 VÀ SƠ ĐỒ HÌNH CÂY. | DOC_EXERCISE_TYPE_1895d4992e8f7a7e | 2 |
| MÔ TẢ CÔNG THỨC BAYES THÔNG QUA BẢNG DỮ LIỆU THỐNG KÊ 2X2 VÀ SƠ ĐỒ HÌNH CÂY. | DOC_EXERCISE_TYPE_a057e7ca13d2e23c | 2 |
| CÔNG THỨC XÁC SUẤT TOÀN PHẦN VÀ CÔNG THỨC BAYES. | DOC_EXERCISE_TYPE_f5cd4cbbfe86d681 | 7 |
| CÁC BÀI TOÁN THỰC TẾ LIÊN QUAN ĐẾN CÔNG THỨC XÁC SUẤT TOÀN PHẦN. | DOC_EXERCISE_TYPE_f775b45b5b22dde8 | 4 |
| CÁC BÀI TOÁN THỰC TẾ LIÊN QUAN ĐẾN CÔNG THỨC BAYES. | DOC_EXERCISE_TYPE_92c96fea1ad5ebde | 10 |
| Chưa có nhãn chính | — | 25 |

Trong số chưa có dạng chính: 18 câu có ứng viên dạng; 7 câu chưa có căn cứ dạng.

## Đối chiếu nguồn

| Nguồn | Bản ghi | Câu hỏi | Tiêu đề loại ra | Trang chứa câu hỏi | Số trang PDF khai báo |
| --- | --- | --- | --- | --- | --- |
| ocr-direct-full - Copy | 2290 | 2290 | 0 | 2–1789 | 2947 |
| ocr-direct-grouped_statistics | 86 | 84 | 2 | 2–93 | 95 |
| ocr-direct-probability | 121 | 121 | 0 | 3–73 | 73 |

Đã đối chiếu số lượng, thứ tự và ID với `content.draft.pretty.json`; ID không trùng trong/giữa ba file. Tổng các dạng bằng tổng bài; tổng các bài bằng tổng chương. SHA-256 từng file được lưu trong `summary.json`.

Các file kèm theo: `primary-detail.csv` (đếm cộng được theo nhãn chính), `candidate-detail.csv` (số lượt gợi ý, không cộng thành tổng câu), `summary.json` (cây thống kê và thông tin kiểm chứng).
