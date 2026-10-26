# Kiểm tra dữ liệu câu hỏi Toán 12 — 25/10/2026

Phạm vi: database local đang phục vụ trang làm bài và các bộ dữ liệu Toán 12 trong repo. Kiểm tra chỉ đọc; không sửa câu hỏi, đáp án, trạng thái hay taxonomy. Chi tiết đủ **81 ProblemType** nằm trong [CSV theo dạng bài](math12_question_data_audit_2026-10-25.csv); từng Question có cờ lỗi nằm trong [CSV theo câu hỏi](math12_question_issues_2026-10-25.csv).

## Kết quả chính

| Chỉ số | Kết quả |
|---|---:|
| Question trong database, đều `APPROVED` | 559 |
| QuestionGroup, đều `APPROVED` | 61 |
| ProblemType tổng / active / inactive | 81 / 75 / 6 |
| Active ProblemType chưa có câu nào | 17 |
| Active ProblemType có câu nhưng tất cả nghi lỗi trình bày | 12 |
| Question nghi lỗi trích PDF trong nội dung hoặc lựa chọn | 293 |
| QuestionGroup thiếu ít nhất một đáp án con | 18 |
| QuestionGroup có ít nhất một câu con nghi lỗi trình bày | 16 |
| Question `APPROVED` thiếu ProblemType / Concept / LearningOutcome | 1 / 5 / 5 |
| Question SHORT_ANSWER thiếu đáp án | 4 |
| Question OPEN_RESPONSE thiếu đáp án tham chiếu cho AI | 1 |
| Question có nguồn review chưa VERIFIED nhưng đang `APPROVED` | 72 (12 câu đơn + 60 câu con thuộc 15 group) |

**Cách phát hiện lỗi trình bày:** có ký tự Unicode Private Use từ font PDF, hoặc ít nhất 10 dòng có từ 6 dòng ký hiệu dài 1–3 ký tự và chiếm tối thiểu một nửa số dòng. Đây là **cờ cần đối chiếu nguồn**, không phải kết luận nội dung toán hoặc đáp án sai. Một câu không bị cờ cũng chưa chắc đã được trình bày chính xác.

## Theo chương

Số Question theo chương là số bản ghi duy nhất có mapping tới ProblemType trong chương. Một câu có thể liên kết nhiều dạng, nên tổng theo từng dạng trong CSV có thể lớn hơn số Question.

| Chapter | PT active | PT chưa có câu | PT không có câu trình bày được | Question liên kết | Question nghi lỗi trình bày |
|---|---:|---:|---:|---:|---:|
| `DERIVATIVE_APPLICATIONS` | 24 | 4 | 4 | 152 | 0 |
| `VECTORS_GEOMETRY` | 15 | 6 | 11 | 114 | 98 |
| `GROUPED_DATA_DISPERSION` | 12 | 5 | 6 | 47 | 4 |
| `INTEGRALS` | 8 | 1 | 2 | 83 | 63 |
| `OXYZ_CHAPTER` | 12 | 0 | 5 | 145 | 123 |
| `PROBABILITY_CHAPTER` | 4 | 1 | 1 | 17 | 5 |
| `EXPONENTIAL_LOGARITHM` | 0 | 0 | 0 | 0 | 0 |

Database còn chapter `EXPONENTIAL_LOGARITHM` và một ProblemType inactive. Scope registry đánh dấu chương này thuộc lớp 11, ngoài phạm vi Toán 12; không tính là thiếu câu Toán 12.

### 17 dạng active chưa có Question

- Đạo hàm: `PARAMETER_MONOTONICITY`, `PARAMETER_EXTREMA_COUNT`, `COMPLETE_FUNCTION_ANALYSIS_CUBIC`, `REAL_WORLD_MONOTONICITY_INTERPRETATION`.
- Vectơ: `VECTOR_SCALAR_MULTIPLICATION_3D`, `POINT_COORDINATES_3D`, `VECTOR_COORDINATES_FROM_POINTS_3D`, `VECTOR_COORDINATE_LINEAR_OPERATIONS_3D`, `VECTOR_COORDINATE_DOT_PRODUCT_3D`, `MIDPOINT_CENTROID_COORDINATES_3D`.
- Thống kê: `IDENTIFY_MORE_STABLE_GROUPED_DATA`, `INTERPRET_GROUPED_DISPERSION_MEASURE`, `CONCLUDE_FROM_GROUPED_DISPERSION`, `PARAMETER_FROM_GROUPED_VARIANCE_SD`, `MULTI_MEASURE_GROUPED_DISPERSION_ANALYSIS`.
- Tích phân: `CALCULATE_DEFINITE_INTEGRAL`.
- Xác suất: `TOTAL_PROBABILITY`.

### 12 dạng active có câu nhưng mọi câu đều bị cờ trình bày

- Vectơ: `VECTOR_SUM_DIFFERENCE_3D`, `VECTOR_DOT_PRODUCT_3D`, `VECTOR_ANGLE_3D`, `VECTOR_GEOMETRIC_DECOMPOSITION_3D`, `VECTOR_LENGTH_DISTANCE_3D`.
- Thống kê: `COMPARE_GROUPED_VARIANCE_SD`.
- Tích phân: `VOLUME_BY_CROSS_SECTION`.
- Oxyz: `LINE_EQUATION_DIRECTION_VECTOR`, `LINE_PLANE_INTERSECTION`, `LINE_RELATION`, `LINE_DISTANCE_IN_OXYZ`, `PLANE_SPHERE_RELATION`.

## Lỗi review nghiêm trọng trong database

- **14/14 group nguồn Vectơ** hiện `APPROVED` trong database. Review gốc chỉ có **1 VERIFIED**; **4 HOLD_MIXED_VECTOR_OXYZ** và **9 REJECTED_OUT_OF_SCOPE_OXYZ** cũng đã được đưa vào DB như group được duyệt.
- **2 group Thống kê** `M12_DISP_CAND_0032` và `M12_DISP_CAND_0035` đang `APPROVED` dù review là `HOLD_MIXED_SCOPE`.
- Câu đơn Vectơ: **7 REJECTED_DUPLICATE**, **3 EXCLUDE_OUT_OF_SCOPE_GRADE12**, **1 HOLD_VECTOR_OXYZ_BOUNDARY** đang `APPROVED`. Câu đơn Thống kê `M12_DISP_CAND_0014` đang `APPROVED` dù là `REJECTED_DUPLICATE`.
- Tổng **27 đơn vị nguồn review chưa VERIFIED** tương ứng **72 Question** trong DB (15 group × 4 câu con + 12 câu đơn). Cờ này phản ánh đúng trạng thái trong các file review đã có; không phải đánh giá lại toán học.

## Đáp án và mapping

- **18 group** thiếu khóa ở một hoặc nhiều câu con: 14 Vectơ, 2 Tích phân (`M12_INT_CAND_0057`, `M12_INT_CAND_0065`), 2 Thống kê (`M12_DISP_CAND_0032`, `M12_DISP_CAND_0035`). Group review nguồn Tích phân có mẫu đáp án, nhưng DB chưa gán xuống đủ bốn câu con. `PracticeService.answer_group` đòi cả bốn câu con chấm tự động được, nên các group này có thể trả `422 QUESTION_GROUP_AUTO_EVALUATION_REQUIRED`.
- Bốn câu `SHORT_ANSWER` thiếu đáp án: `M12_VECTOR_CAND_0046`, `0049`, `0051`, `0054`.
- Câu demo `c0000000-0000-0000-0000-000000000001` thiếu cả ProblemType, Concept, LearningOutcome và đáp án tham chiếu AI.
- Bốn câu con `TRUE_FALSE` nguồn Oxyz thiếu Concept và LearningOutcome (ID và mapping chi tiết trong CSV theo câu hỏi).
- Một cặp `content_hash` trùng: `M12_OXYZ_CAND_0301` và `M12_VECTOR_CAND_0012`; câu Vectơ đã bị review `REJECTED_OUT_OF_SCOPE_OXYZ` nhưng vẫn `APPROVED` trong DB. Cần đối chiếu nguồn trước khi quyết định trùng học thuật.
- Điểm tốt: 255 câu MULTIPLE_CHOICE đều có đúng 4 lựa chọn và khóa đáp án khớp nhãn; không phát hiện Question mapping sang subject khác. 61 group đều có cấu trúc bốn câu con.

## Vì sao validator PASS nhưng học sinh vẫn thấy lỗi?

Các lệnh `validate_grade12_scope`, `validate_curriculum_staging`, `validate_vector_academic_review`, `validate_grouped_data_dispersion_academic_review`, `validate_integrals_academic_review`, `validate_oxyz_academic_review`, `validate_conditional_probability_academic_review`, `validate_question_group_review`, các validator visual, và `validate_final_readiness` đều trả mã thoát 0 trong lần kiểm tra này. Chúng kiểm tra file curated và contract của từng giai đoạn, **không xác nhận bản Question đang trong database hiển thị đúng**.

Đáng chú ý, `validate_final_readiness` báo PASS về nhất quán file nhưng vẫn ghi `database_import_allowed=false`, `production_release_allowed=false`, `rights_status=REVIEW_REQUIRED`. Database local đồng thời có 559 Question `APPROVED`. Hai trạng thái này cần được đối chiếu với quyết định import/phát hành thực tế, nhất là trước khi cho học sinh làm và chấm.

## Thứ tự xử lý đề xuất

1. Đối chiếu 27 đơn vị review chưa VERIFIED và 18 group thiếu khóa; ngăn chúng tham gia chọn câu/chấm cho đến khi quyết định nguồn được áp dụng đúng. Không tự tạo đáp án còn thiếu.
2. Từ bản nguồn đã được phép sử dụng, biên tập **display text/LaTeX hoặc ảnh câu hỏi** cho 293 câu bị cờ. Câu Oxyz `M12_OXYZ_CAND_0176` trong ảnh người dùng là một ví dụ có ký tự font PDF và thứ tự phương trình bị vỡ. Không suy đoán công thức từ text trích xuất.
3. Bổ sung câu hỏi nguồn thật cho 17 dạng chưa có; ưu tiên 12 dạng có câu nhưng toàn bộ không trình bày được. Giữ các lỗ hổng coverage đã được review như lỗ hổng thật cho đến khi có dữ liệu mới.
4. Sau khi review, chạy lại validator file, kiểm tra database runtime, thử trang làm bài và kiểm thử chấm group. Không dùng kết quả PASS của validator file thay cho xác nhận release.
