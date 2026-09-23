# Báo cáo Tập Dữ liệu Nhận Diện Quan Niệm Sai Lầm (`misconception_dataset_v1`)

## 1. Tổng Quan Kích Thước & Phân Cụm
- **Tổng số mẫu (Sample count)**: `26`
- **Số cụm câu hỏi duy nhất (Unique question clusters)**: `22`
- **Số mẫu trùng/gần trùng lặp đã gom cụm (Duplicates grouped)**: `4`

## 2. Phân Chia Tập Huấn Luyện / Đánh Giá / Kiểm Thử (Split Statistics)
| Phân tập (Split) | Số mẫu (Samples) | Tỷ lệ (%) | Số cụm câu hỏi (Clusters) |
| :--- | :--- | :--- | :--- |
| `train` | 18 | 69.23% | 15 |
| `validation` | 3 | 11.54% | 2 |
| `test` | 5 | 19.23% | 5 |

### Kiểm Tra Rò Rỉ Dữ Liệu (Leakage Verification)
- **Trạng thái**: `✅ LEAK-FREE`
- **Train-Val Cluster Overlap**: `0`
- **Train-Test Cluster Overlap**: `0`
- **Val-Test Cluster Overlap**: `0`
- **Ghi chú**: Zero question leakage verified across all splits.

## 3. Phân Phối Dạng Bài (ProblemType Distribution)
| Dạng bài (ProblemType) | Số mẫu | Tỷ lệ (%) |
| :--- | :--- | :--- |
| `MONOTONICITY_FROM_EXPRESSION` | 5 | 19.23% |
| `PARAMETER_MONOTONICITY` | 3 | 11.54% |
| `FIND_FUNCTION_EXTREMA` | 3 | 11.54% |
| `EXP_LOG_EQUATION` | 3 | 11.54% |
| `CALCULATE_INTEGRAL` | 3 | 11.54% |
| `VECTOR_3D_RELATION` | 3 | 11.54% |
| `BASIC_PROBABILITY` | 2 | 7.69% |
| `OXYZ_LINE_PLANE_INTERSECTION` | 2 | 7.69% |
| `COMPLETE_FUNCTION_ANALYSIS` | 2 | 7.69% |

## 4. Phân Phối Khái Niệm (Concept Distribution)
| Khái niệm (Concept) | Tần suất xuất hiện |
| :--- | :--- |
| `DERIVATIVE` | 8 |
| `EXTREMA` | 5 |
| `OXYZ` | 5 |
| `MONOTONICITY` | 4 |
| `INEQUALITY_SOLVING` | 3 |
| `LOGARITHM` | 3 |
| `INTEGRAL` | 3 |
| `VECTOR` | 3 |
| `PARAMETER_REASONING` | 2 |
| `PROBABILITY` | 2 |
| `FUNCTION_ANALYSIS` | 2 |
| `GEOMETRY_3D` | 1 |

## 5. Phân Phối Nhãn Quan Niệm Sai Lầm (Class Distribution)
| Mã sai lầm (Misconception Label) | Số mẫu | Tỷ lệ (%) |
| :--- | :--- | :--- |
| `DERIVATIVE_SIGN_DIRECTION` | 3 | 11.54% |
| `PARAMETER_CONDITION_NOT_GLOBAL` | 3 | 11.54% |
| `DERIVATIVE_ZERO_ALWAYS_EXTREMUM` | 3 | 11.54% |
| `LOG_SUM_DISTRIBUTION` | 3 | 11.54% |
| `INDEFINITE_INTEGRAL_MISSING_CONSTANT` | 3 | 11.54% |
| `VECTOR_COORDINATE_SIGN_ERROR` | 3 | 11.54% |
| `PROBABILITY_INDEPENDENCE_ASSUMED` | 2 | 7.69% |
| `OXYZ_NORMAL_VECTOR_MISUSED` | 2 | 7.69% |
| `FUNCTION_GRAPH_AXES_MISREAD` | 2 | 7.69% |
| `DERIVATIVE_ARITHMETIC_SLIP` | 2 | 7.69% |

## 6. Phân Phối Danh Mục Lỗi & Mức Độ Nghiêm Trọng
### Danh Mục Lỗi (Error Category)
| Danh mục | Số mẫu |
| :--- | :--- |
| `CONCEPTUAL` | 11 |
| `PROCEDURAL` | 8 |
| `CALCULATION` | 3 |
| `READING` | 2 |
| `CARELESS` | 2 |

### Mức Độ Nghiêm Trọng (Severity)
| Mức độ | Số mẫu |
| :--- | :--- |
| `HIGH` | 12 |
| `MEDIUM` | 5 |
| `LOW` | 5 |
| `CRITICAL` | 4 |

### Loại Gợi Ý Sư Phạm (Recommended Hint Type)
| Loại gợi ý | Số mẫu |
| :--- | :--- |
| `NEXT_STEP` | 13 |
| `CONCEPT_RECALL` | 6 |
| `STRATEGY_DIRECTION` | 5 |
| `WORKED_EXAMPLE` | 2 |

## 7. Phân Tích Giá Trị Khuyết Thiếu (Missing Values Analysis)
| Thuộc tính (Field) | Số lượng khuyết thiếu | Trạng thái kiểm soát |
| :--- | :--- | :--- |
| `question` | 0 | ✅ 100% Đầy đủ |
| `problem_type` | 0 | ✅ 100% Đầy đủ |
| `concepts` | 0 | ✅ 100% Đầy đủ |
| `learning_outcomes (optional)` | 10 | Tùy chọn (Optional) |
| `taxonomy` | 0 | ✅ 100% Đầy đủ |
| `student_solution` | 0 | ✅ 100% Đầy đủ |
| `reference_solution` | 0 | ✅ 100% Đầy đủ |
| `verified_misconception_label` | 0 | ✅ 100% Đầy đủ |
| `error_category` | 0 | ✅ 100% Đầy đủ |
| `severity` | 0 | ✅ 100% Đầy đủ |
| `recommended_hint_type` | 0 | ✅ 100% Đầy đủ |
