# Báo cáo Sẵn sàng Dữ liệu Toán 12 (Math 12 Data Readiness Report)
## Chuyên đề Trọng điểm: Tính Đơn Điệu của Hàm Số & Lỗi Xét Dấu Đạo Hàm

- **Dự án**: Coach Learning (EduMS)
- **Mã Sprint**: SPRINT-01 (DATA-READY-01)
- **Mã tài liệu**: DATA-M12-01
- **Phạm vi dạng bài**: `MONOTONICITY_FROM_EXPRESSION` (Toán 12 GDPT 2018)
- **Trạng thái**: HOÀN TẤT THẨM ĐỊNH NGUỒN VÀ RÀO CẢN (AUDITED & BLOCKED)

---

## 1. Kết quả Kiểm tra Thực tế (Factual Audit Results)

Đã tiến hành kiểm tra trực tiếp trên cả hai nguồn: **Cơ sở dữ liệu PostgreSQL thời gian thực** và **Hệ thống tệp dữ liệu lưu trữ trong repository** (`backend/data/`).

### 1.1. Tình trạng trong Cơ sở dữ liệu Runtime (PostgreSQL Runtime Status)
- **Tổng số câu hỏi trong bảng `questions`**: **0** (Chưa có câu hỏi nào được nạp vào production database).
- **Số câu hỏi trạng thái `APPROVED`**: **0**.
- **Số dạng bài Toán 12 đã nạp vào bảng `problem_types`**: **9** (Bao gồm đầy đủ mã chuẩn: `MONOTONICITY_FROM_EXPRESSION`, `PARAMETER_MONOTONICITY`, `FIND_FUNCTION_EXTREMA`, `COMPLETE_FUNCTION_ANALYSIS`...).
- **Số câu hỏi gán cho dạng bài `MONOTONICITY_FROM_EXPRESSION`**: **0**.

### 1.2. Tình trạng trong Tệp Dữ liệu Repository (`backend/data/`)
Trong thư mục `backend/data/questions/math/grade12/derivative_applications_v0_1/`:
- **Tổng số nhóm câu hỏi cấu trúc (Structural Groups)**: 67 nhóm.
- **Số nhóm đã qua rà soát học thuật (Reviewed Groups)**: 67 nhóm.
- **Số nhóm đạt xác minh học thuật (Academic Verified Groups)**: 39 nhóm (tương ứng 152 câu hỏi con).
- **Số nhóm bị giữ lại để đối soát (Academic Hold)**: 10 nhóm.
- **Số nhóm bị bác bỏ (Academic Rejected)**: 18 nhóm.
- **Tình trạng đủ điều kiện phát hành sản xuất (`production_release_eligible_groups`)**: **0**.
- **Tình trạng sẵn sàng nạp database (`database_import_ready_groups`)**: **0**.

---

## 2. Phân định Cấp bậc Độ tin cậy Dữ liệu (Data Provenance & Release Hierarchy)

Dự án áp dụng quy chuẩn kiểm soát chất lượng dữ liệu 5 cấp bậc nghiêm ngặt. **Nghiêm cấm việc xem dữ liệu REVIEWED hoặc VERIFIED tự động tương đương APPROVED hoặc PRODUCTION_ELIGIBLE**:

| Cấp bậc | Định nghĩa | Tình trạng hiện tại của bộ Đạo hàm |
| :--- | :--- | :--- |
| **1. `SOURCE_VERIFIED`** | Dữ liệu thô từ tài liệu nguồn đã được đối soát SHA-256 tệp gốc, xác định rõ nguồn sách/đề thi. | **ĐẠT** (67/67 nhóm có mã băm và nguồn truy nguyên). |
| **2. `STAGING`** | Dữ liệu đã được bóc tách vào schema JSON trung gian trong thư mục `staging/`, có thể xem trước. | **ĐẠT** (Nằm trong thư mục `staging/`). |
| **3. `REVIEWED`** | Đã được giáo viên/chuyên gia đọc duyệt vòng 1 để phân loại sơ bộ (verified, hold, reject). | **ĐẠT** (67 nhóm đã qua review sơ bộ). |
| **4. `APPROVED`** | Đạt chuẩn học thuật: lời giải chính xác 100%, không sai sót toán học, đáp án duy nhất, biểu thức LaTeX chuẩn. | **ĐẠT MỘT PHẦN** (39 nhóm verified, nhưng chưa có rubric chấm từng bước). |
| **5. `PRODUCTION_ELIGIBLE`** | Vượt qua toàn bộ các cổng: (1) Học thuật approved, (2) Bản quyền giải phóng (Rights Cleared), (3) Đầy đủ hình ảnh/vector, (4) Được Hội đồng duyệt nhập kho chính thức. | **0 / 39 (BLOCKED 100%)**. |

---

## 3. Phân tích Chi tiết Dữ liệu Chuyên đề Tính Đơn Điệu (`MONOTONICITY_FROM_EXPRESSION`)

### 3.1. Nguồn gốc Tài liệu & Tình trạng Pháp lý (Provenance & Rights)
Bộ dữ liệu ứng dụng đạo hàm hiện có trong repository xuất phát từ 3 nguồn:

| Mã nguồn | Tên tài liệu nguồn | Số nhóm verified | Tình trạng bản quyền (Rights Status) | Rào cản phát hành |
| :--- | :--- | :--- | :--- | :--- |
| `SRC_PROVINCIAL_TRIAL_2025_COLLECTION` | Tuyển tập đề thi thử tốt nghiệp THPT 2025 các Sở GD&ĐT | 7 | `REVIEW_REQUIRED` | Chưa thẩm định quyền khai thác thương mại/sản phẩm số. Có 1 nhóm thiếu ảnh gốc (`M12_DERIV_GROUP_0012`). |
| `SRC_TRUONG_NGOC_VY_40_2026` | Tài liệu 40 đề ôn thi 2026 (Tác giả Trương Ngọc Vỹ) | 28 | `REVIEW_REQUIRED` | Quyền tác giả cá nhân chưa được ký thỏa thuận bản quyền phát hành chính thức. |
| `SRC_MOET_EXAM_2025_SOLUTION_COMPILATION` | Tuyển tập lời giải đề minh họa & tham khảo Bộ GD&ĐT 2025 | 4 | `REVIEW_REQUIRED` | Bản quyền lời giải của đơn vị biên soạn thứ ba cần được rà soát pháp lý. |

### 3.2. Lời giải Chi tiết và Cấu trúc Bước giải (Detailed Solutions & Step Breakdown)
- **Hiện trạng**: Các câu hỏi trong staging hiện chỉ có trường `explanation` dạng văn bản tổng quát (chuỗi string giải thích đáp án trắc nghiệm).
- **Thiếu hụt cho Solution Engine**:
  - Chưa phân tách thành các bước toán học vi mô (`SolutionStep`).
  - Chưa chuẩn hóa biểu thức LaTeX từng bước (đạo hàm $y'$, phương trình $y'=0$).
  - Chưa có biểu diễn Bảng xét dấu dạng dữ liệu cấu trúc (`MathArtifact` - `SIGN_TABLE`).

### 3.3. Các Nhánh giải Tương đương (Alternative Valid Paths)
- Bài toán xét tính đơn điệu hàm đa thức bậc ba hoặc hàm phân thức bậc nhất/bậc nhất:
  - **Nhánh chính (Quy tắc dấu đạo hàm)**: Tính $y' \to$ Giải nghiệm $y'=0 \to$ Lập bảng xét dấu $\to$ Kết luận.
  - **Nhánh thử giá trị (Test Point Method)**: Tính $y' \to$ Chọn điểm đại diện $x_0 \in (a, b)$ để thử dấu $\to$ Kết luận.
  - **Nhánh bất đẳng thức (Algebraic Evaluation)**: Biến đổi $y' = (ax+b)^2 + c > 0, \forall x$.
- **Hiện trạng**: Dữ liệu staging hoàn toàn chưa có cấu trúc định nghĩa các nhánh giải tương đương.

### 3.4. Danh mục Quan niệm Sai lầm về Xét dấu Đạo hàm (Misconceptions Taxonomy)
Hệ thống hiện đã định nghĩa sẵn trong `backend/data/seed/misconceptions.py`:
1. **`DERIVATIVE_SIGN_DIRECTION`** (Loại: `CONCEPTUAL`):
   - *Mô tả*: Học sinh nhầm lẫn giữa dấu của đạo hàm và chiều biến thiên (ví dụ: $y' < 0$ thì kết luận đồng biến, hoặc $y' > 0$ thì kết luận nghịch biến).
   - *Ánh xạ*: Concept `DERIVATIVE`, ProblemType `MONOTONICITY_FROM_EXPRESSION`.
2. **`DERIVATIVE_ARITHMETIC_SLIP`** (Loại: `CARELESS`):
   - *Mô tả*: Tính đạo hàm đúng công thức nhưng nhầm dấu số học khi rút gọn hệ số.
3. **Các lỗi thực tế cần bổ sung thêm**:
   - *Lỗi quy tắc tam thức bậc hai*: Nhầm "trong trái ngoài cùng" thành "trong cùng ngoài khác" khi $a > 0$ hoặc $a < 0$.
   - *Lỗi qua nghiệm bội chẵn*: Quên không giữ nguyên dấu của $y'$ khi đi qua nghiệm kép/bội chẵn (ví dụ $y' = (x-1)^2(x+2)$).
   - *Lỗi khoảng gián đoạn của hàm phân thức*: Viết khoảng đồng biến/nghịch biến dưới dạng hợp $(-\infty, 1) \cup (1, +\infty)$ hoặc $\mathbb{R} \setminus \{1\}$ thay vì nêu rõ từng khoảng rời rạc.

### 3.5. Cặp Câu hỏi Kiểm chứng Độc lập & Sửa sai (Verification & Repair Items)
- **Yêu cầu sư phạm**: Khi phát hiện học sinh sai ở bước lập bảng xét dấu, hệ thống KHÔNG được kết luận vội. Hệ thống cần:
  - Một **Câu hỏi Kiểm chứng Độc lập (Independent Verification Question)**: Bài toán cô lập kỹ năng (chỉ yêu cầu xét dấu tam thức bậc hai hoặc đọc dấu biểu thức đã có sẵn $y'$, loại bỏ độ phức tạp tính đạo hàm) để xác định lỗi thuộc về xét dấu hay đạo hàm.
  - Một **Câu hỏi Luyện sửa sai (Target Repair Question)**: Bài toán tương tự kèm giàn giáo hướng dẫn (guided hint).
- **Hiện trạng**: Chưa có liên kết cặp câu hỏi này trong dữ liệu staging.

### 3.6. Bảng Tiêu chí Chấm điểm (Solution Rubrics)
- **Hiện trạng**: Toàn bộ 39 nhóm câu hỏi verified đều **chưa có rubric chấm điểm từng bước**.
- **Yêu cầu chuẩn bị**: Cần xây dựng `SolutionRubric` chuẩn cho 6 câu toán mẫu với trọng số phân bổ rõ ràng:
  - Bước 1 (Tập xác định): 10%
  - Bước 2 (Đạo hàm $y'$): 25%
  - Bước 3 (Nghiệm $y'=0$): 20%
  - Bước 4 (Bảng xét dấu): 30%
  - Bước 5 (Kết luận khoảng đơn điệu): 15%

---

## 4. Ma trận Rào cản Dữ liệu (Data Blockers Matrix)

| STT | Rào cản (Blocker) | Phạm vi ảnh hưởng | Mức độ nghiêm trọng | Giải pháp khả thi để mở khóa |
| :---: | :--- | :--- | :---: | :--- |
| **B1** | **Bản quyền nguồn tư liệu (Rights Review Required)** | 39 nhóm verified trong staging | **P0 (Chặn Release)** | **Phương án A**: Thẩm định và ký văn bản chấp thuận bản quyền từ tác giả Trương Ngọc Vỹ và nguồn tuyển tập.<br>**Phương án B (Khuyến nghị cho Sprint 2)**: Ban biên tập nội bộ tự biên soạn mới bộ 6 câu hỏi nguyên bản (Original Authored Items), hoàn toàn thuộc quyền sở hữu của EduMS. |
| **B2** | **Thiếu Rubric chấm từng bước (`SolutionRubric`)** | Toàn bộ câu hỏi tự luận | **P0 (Chặn Engine)** | Ban hành chuẩn Rubric Schema và biên soạn rubric chuẩn cho 6 câu bài tập mẫu. |
| **B3** | **Thiếu cấu trúc Bảng xét dấu (`MathArtifact`)** | Dạng bài `MONOTONICITY_FROM_EXPRESSION` | **P1 (Chặn UI/Eval)** | Định nghĩa schema JSON cho `SIGN_TABLE` và tạo dữ liệu mẫu kiểm thử. |
| **B4** | **Thiếu câu hỏi kiểm chứng độc lập (Verification Pairing)** | Quy trình chẩn đoán quan niệm sai lầm | **P1 (Chặn Chẩn đoán)** | Thiết kế các câu hỏi kiểm tra thuần túy kỹ năng xét dấu để dùng làm bài test kiểm chứng. |
| **B5** | **Ảnh và tài nguyên đồ họa bị thiếu** | Nhóm `M12_DERIV_GROUP_0012` | **P2 (Đã cô lập)** | Đã đưa vào danh sách loại trừ phát hành (`release_exclusion.json`). Không ảnh hưởng đến các câu dạng đại số. |

---

## 5. Kết luận Sẵn sàng Dữ liệu (Readiness Conclusion)

Dữ liệu Toán 12 trong kho staging hiện tại có giá trị học thuật đối soát cao, nhưng **chưa đủ điều kiện pháp lý và cấu trúc kỹ thuật để đưa thẳng vào môi trường sản xuất của Solution Engine**.

**Đề xuất chiến lược cho Sprint tiếp theo (STEP-DATA-01)**:
Không chờ đợi thủ tục giải phóng bản quyền phức tạp của 39 nhóm câu hỏi bên ngoài. EduMS sẽ **tự biên soạn một bộ 6 câu hỏi nguyên bản (In-house Authored Slice)** về Tính đơn điệu của hàm số, chuẩn GDPT 2018, có đầy đủ:
1. Bản quyền tự do 100% thuộc về EduMS.
2. Lời giải chuẩn từng bước theo đúng schema `SolutionStep`.
3. Bảng xét dấu cấu trúc chuẩn `MathArtifact`.
4. Bảng tiêu chí chấm chi tiết `SolutionRubric`.
5. Cặp câu kiểm chứng độc lập cho lỗi `DERIVATIVE_SIGN_DIRECTION`.
Bộ dữ liệu này sẽ là hạt nhân dữ liệu vàng phục vụ kiểm thử và vận hành Vertical Slice.
