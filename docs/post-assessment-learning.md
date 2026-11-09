# Đề xuất sau khi chấm lời giải

Khung “Bạn nên học gì tiếp?” nằm dưới tổng kết từng bước trong Math Workspace.
Điểm bài và năng lực tích lũy được trình bày riêng. Hai bước hợp lý không có
nghĩa đã đạt đủ rubric hoặc nắm vững kiến thức; vòng điểm dùng `final_score`
đã lưu khi có quyết định chấm chính thức.

## Dữ liệu và quyết định

`NextLearningService` đọc quyết định `EvaluationDecision` của học sinh đang
đăng nhập, liên kết kiến thức/dạng bài của câu hỏi hoặc snapshot giáo viên,
bằng chứng tiêu chí, mastery và lịch ôn hiện có. Nó không chấm lại, cập nhật
mastery, suy lỗi từ văn bản AI, hoặc tạo lịch ôn mới.

- Chưa có quyết định chính thức: chỉ nhắc đối chiếu, không tạo điểm/đề xuất riêng.
- Bài kiểm tra lớp chưa nộp toàn bộ: chưa mở đề xuất cá nhân.
- Điểm dưới 85%, chưa đúng hoặc tiêu chí chưa đạt đủ: ưu tiên củng cố nội dung
  đã được gắn với bài. Khi có kết quả tiêu chí theo concept, chọn concept còn yếu.
- Đã hoàn thành tốt: tiếp tục một mục tiêu liên quan theo Learning Core, không
  tự gắn nhãn “đã vững” từ một bài làm.
- Bằng chứng phải khớp học sinh, môn, quyết định và điểm hiện tại trước khi dùng
  kết quả tiêu chí. Không dùng tiêu chí cũ khi điểm được điều chỉnh.
- Chưa có mapping hoặc bài phù hợp: trả trạng thái thiếu dữ liệu rõ ràng.

Tái sử dụng `LearningPriorityService`, `MasteryAggregationService`,
`QuestionRecommendationService`. Bộ chọn câu có thêm bộ lọc tùy chọn, không đổi
luồng cũ: bài được duyệt, tự luận độc lập, đủ mapping, có nguồn đáp án/lời giải,
không bị lỗi trình bày đã biết; loại câu đã mở/làm và câu gần đây. Preview không
chứa đáp án hoặc lời giải của câu mới.

## API

- `GET /api/v3/math-solutions/attempts/{id}/next-learning`: chỉ đọc, không gọi AI.
- `POST` cùng đường dẫn: gửi `decision_id`, `question_id`. Máy chủ tính lại đề xuất
  trước khi tạo phiên và mở **đúng câu** đã đề xuất. Câu không còn hợp lệ trả 409
  để tải lại. Khóa bài nguồn và create key ổn định chống tạo trùng khi gửi lại.
- `POST .../next-learning/explain`: chỉ khi bấm “Gợi ý cách ôn cùng AI”. Dùng
  Gateway HINT, deadline 8s, giải thích từ các dữ kiện đã chọn; không chọn câu,
  đổi điểm hoặc ghi dữ liệu học tập. Nếu AI không sẵn sàng, trả lý do từ Learning
  Core và gắn đúng nguồn. Có giới hạn request AI hiện có.

BFF yêu cầu phiên học sinh, UUID hợp lệ, và CSRF cho mọi POST. API backend kiểm
tra quyền sở hữu; response không cache. Không có migration hoặc cấu hình mới.

## Giao diện

Card hiển thị đường đi “Đối chiếu bài → Chọn mục tiêu → Luyện & ôn”, điểm đã lưu,
tiêu chí cần hoàn thiện, kiến thức ưu tiên, thanh năng lực tích lũy, lịch ôn đã có
và preview bài luyện. Có liên kết tới kho lý thuyết theo tên mục tiêu và kế hoạch
học hiện có; khi quay về kế hoạch, `after_attempt` giữ ngữ cảnh để hiển thị lại
mục tiêu từ bài vừa làm trong “Lịch học & việc cần làm”. API vẫn xác thực quyền
sở hữu; tham số URL không phải quyền truy cập. Mở trang chủ bình thường không
phát sinh truy vấn này. Tìm lý thuyết vẫn dùng bộ phân giải tài liệu hiện tại, không bảo đảm
có tài liệu trùng tên và không tự nhận đó là nguồn đã được ánh xạ.

Loading/lỗi mạng không che kết quả chấm. Có tải lại, trạng thái thiếu nguồn câu
và trạng thái chờ chấm. Đã bỏ nút tiếp tục trùng trong tổng kết; header chỉ giữ
điều hướng câu tiếp cho bài lớp. Mobile dùng một cột và ẩn đúng cột bài viết gốc
khi đang xem kết quả; không dùng inline display ghi đè quy tắc ẩn.

## Kiểm thử và xem giao diện

Từ `backend`:

```powershell
.venv/Scripts/python.exe -m pytest tests/math_solutions/test_next_learning.py tests/recommendations -q
```

Từ `frontend`:

```powershell
npm run test:next-learning
npx playwright test --config playwright.next-learning.config.ts
```

Playwright mở frontend riêng ở 3112 và backend fixture ở 8898, không dùng DB hay
Gemini thật. Ảnh và report ở `.tmp/next-learning-20261109/browser/`. Mẫu 50 điểm,
35% năng lực, ngày ôn và câu hỏi trong ảnh đều là dữ liệu kiểm thử, không phải
kết quả học sinh thật. Luồng chạy thực đọc API backend và dữ liệu đã lưu.
