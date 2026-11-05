# Quan hệ Frontend, Backend và AI

Đối chiếu source working tree ngày 05/11/2026. Xem số liệu AST sinh tự động trong
[architecture.md](architecture.md). Những mô tả dưới đây là ranh giới runtime đã
đọc source, không phải cạnh HTTP do Graphify tự phát hiện hoặc kiểm chứng runtime end-to-end.

## Frontend → Backend

Frontend dùng Next.js App Router, React và TypeScript. Các feature gọi API client
trong [`frontend/src/lib/api/client.ts`](../../frontend/src/lib/api/client.ts).
Những route Next.js sau proxy request đến FastAPI bằng `getBackendBaseUrl()`:

| Chức năng | Frontend / proxy | Backend tương ứng |
|---|---|---|
| Math workspace | `src/app/api/v2/math-solutions/attempts/[...path]/route.ts` | `app/api/v2/router.py` → `app/math_solutions/v2_router.py`, `math_ink`, `math_ocr` |
| AI review bài làm | `src/app/api/v3/math-solutions/attempts/[attemptId]/ai-review/route.ts` | `app/math_solutions/ai_review_router.py` |
| Paper upload/OCR | `src/lib/api/paper-proxy.ts` và route v3 paper | `app/math_paper/router.py` |
| Math Canvas | `src/app/api/v3/math-canvas/[...path]/route.ts` | `app/math_canvas/router.py` |
| Luyện tập PDF | `src/app/api/practice/pdf/[...path]/route.ts` | `app/pdf_practice/router.py` |

Các đường dẫn Frontend trong bảng bắt đầu tại `frontend/`, Backend tại `backend/`.
[`backend/app/application.py`](../../backend/app/application.py) gắn root API và mount
hai sub-application `/api/v2`, `/api/v3`. Router v3 được đăng ký trong
[`backend/app/api/v3/application.py`](../../backend/app/api/v3/application.py), không
phải chỉ tìm trong root `api/router.py`.

Graph AST cho thấy import/call bên trong từng ngôn ngữ. Giao tiếp HTTP giữa hai
phía phải đối chiếu URL, method, request/response contract và auth; graph không tự
chứng minh parity contract. Browser OCR/ONNX và dựng 3D/Math Canvas còn có phần tính
toán ngay trên Frontend, không phải mọi thao tác đều gọi AI Backend.

## Backend → AI và dữ liệu

Backend là modular monolith. Module AI là một phần của Backend, không có service
Graphify hoặc AI service mới được triển khai trong thay đổi này.

| Quan hệ | Bằng chứng source | Ý nghĩa bảo trì |
|---|---|---|
| Domain → AIGateway | `app/hints/service.py`, `app/knowledge_gap/service.py`, `app/ai/student_tutor_service.py` import `AIGateway` | Sửa interface gateway có ảnh hưởng nhiều domain; xem thêm callers qua `explain AIGateway` |
| Dependency injection → Provider | `app/ai/dependencies.py`: `create_ai_provider`, `get_ai_gateway_singleton`, `get_ai_gateway` | Factory hiện chọn `GeminiProvider` hoặc `MockAIProvider` theo settings |
| AIGateway → policy / validator / routing | `app/ai/gateway.py` import `AIToolPolicy`, `AIOutputValidator`, `ModelRoutingPolicy` | Cần kiểm tra policy và schema khi thay đổi response; graph chỉ hỗ trợ tìm điểm ảnh hưởng |
| AI review → Gateway | `app/math_solutions/answer_grounded_ai.py`: `AnswerGroundedAIService` gọi `generate_structured` | Review có context/rubric riêng; không suy ra AI sở hữu toàn bộ chấm điểm từ cạnh này |
| RAG → Embedding/Gateway và ORM | `app/rag/embedding_service.py`, `app/rag/search_service.py`, `app/rag/models.py` | Retrieval có dữ liệu/permission riêng; không truy cập DB thật để xây graph |
| Paper OCR → Gemini trực tiếp | `app/math_paper/ocr.py`: `GeminiPaperTranscriber` gọi `httpx.AsyncClient` | Đây là đường gọi AI trực tiếp bên cạnh gateway; sơ đồ không giả định mọi lời gọi đều đi qua AIGateway |
| Learning core → deterministic strategy | `app/mastery/strategy.py`: `DeterministicMasteryCalculationStrategy`; `app/recommendations/priority_service.py` | Tích hợp Graphify không đổi scoring, mastery hay đề xuất học tập |
| Domain → Persistence | `app/database/session.py`, các model/service domain, `backend/migrations/` | Cấu trúc ORM/Alembic nằm trong graph code; không introspect DB, không chạy migration |

Các đường dẫn trong bảng bắt đầu tại `backend/`, trừ nơi có tiền tố đầy đủ.
`backend/app/ai/tool_policy.py` có allowlist và kiểm tra mutation; đây là bằng chứng
về thiết kế policy, không phải chứng nhận rằng mọi runtime path đã được audit.

## Công cụ offline và ranh giới Graphify

`tools/pdf_metadata` chứa pipeline trích xuất, OCR, audit và dựng dataset.
`tools/learning_baseline` chứa các baseline/scheduler và scenario fixtures.
Code được index để agent tìm quan hệ nội bộ, nhưng cạnh import không chứng minh
artifact đã được đưa vào luồng API hiện tại. Không nối baseline B3 vào live planner
trong tích hợp này.

Graphify đọc source thành graph cục bộ. Codex truy cập graph qua CLI/stdio MCP;
không có cạnh runtime từ Frontend/Backend sang Graphify, không đưa vào package
ứng dụng, DB, Docker Compose hoặc CI/deploy. Knowledge graph code này độc lập với
curriculum graph và Knowledge Forest dùng trong sản phẩm.

## Dùng graph để đánh giá thay đổi

1. Query hoặc explain symbol/domain dự định sửa.
2. Xem source_file/source_location và confidence `EXTRACTED` / `INFERRED`.
3. Dùng path để khám phá kết nối; `--undirected` chỉ là đường liên thông.
4. Với HTTP, đối chiếu proxy, router mount và contract ở cả hai phía.
5. Chạy kiểm tra nghiệp vụ phù hợp với thay đổi; cập nhật graph và báo cáo sau đó.

Số link trong `module-relations.json` là số cạnh AST, nhóm thành cặp module không
có hướng để tránh diễn giải sai graph liên thông thành call graph có hướng.
Node thư viện ngoài không có source, parser chưa hỗ trợ và dynamic dispatch có
thể thiếu hoặc làm sai lệch topology; không dùng hub count làm chỉ số chất lượng code.
