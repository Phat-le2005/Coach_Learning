# Kiểm chứng Graphify trước khi push — 05/11/2026

Môi trường: Windows, PowerShell, Python 3.13.3, `graphifyy[mcp,leiden]==0.9.102`.
Base GitHub: `5f7b134266ee60af2be18a3755664b4a9dda8dda`; snapshot gồm base này và các file tích hợp Graphify đang chuẩn bị commit.
Đợt publish được chuẩn bị thành đúng 7 commit riêng trên checkout sạch để giữ nguyên các thay đổi local có sẵn.

| Kiểm tra | Kết quả |
|---|---|
| Cài từ đầu trên checkout sạch | Setup thành công; virtualenv riêng; `pip check` không có dependency lỗi |
| Codex config | `codex mcp get coach_graphify --json` nhận server enabled; cấu hình chỉ thuộc project |
| Knowledge graph | 1,402 file code được phát hiện; 13,851 nodes; 63,513 links; 368 communities |
| Source ứng dụng | 798/798 application source files detected |
| Graph integrity | ID không trùng; không có cạnh thiếu endpoint; fingerprint source hiện hành |
| Source phạm vi graph | Source filesystem nằm trong scan; stub package bên ngoài được phân biệt với source thực |
| Loại trừ | Secrets, `.env`, DB dumps, dataset payload, model, dependencies, build output và cấu hình máy không nằm trong chỉ mục/payload commit |
| LLM | 0 input/output tokens cho semantic extraction và đặt tên community |
| CLI / MCP | Query, explain và path hoạt động; initialize/list_tools và graph_stats/query_graph/get_node/shortest_path qua stdio thành công |
| HTML tương tác | 368 community nodes, 2,147 links; canvas/sidebar/search/node details hoạt động; không có JavaScript page error |
| SVG | Render PNG và kiểm tra bố cục; không bị cắt chữ hoặc chồng nội dung |
| Python / PowerShell | Python compile và PowerShell parse thành công |
| Diff ứng dụng | Không sửa `backend/`, `frontend/`, `.github/`, Docker Compose, app dependencies hoặc migration |
| Bảo toàn local | File tích hợp gốc đã đối chiếu SHA-256 trước/sau khi chép; không pull/rebase/reset thư mục làm việc đang có thay đổi |

Graph JSON và GraphML giữ đầy đủ node; HTML dùng community aggregation khi vượt 1.800 nodes.
Kết quả máy đọc được nằm ở `graphify-out/verification.json`, `visual-verification.json`, `coverage.json` (được gitignore).
Số community có thể thay đổi giữa các lần clustering; các số liệu trên mô tả snapshot đã kiểm tra.

Parser vẫn báo vùng lỗi tại dòng 17 của `frontend/tests/ocr-math-preview.test.ts`; một số file không có symbol hoặc ngoài grammar.
Độ phủ file là phát hiện source, không đảm bảo mọi symbol/quan hệ được trích đầy đủ. Các cạnh EXTRACTED/INFERRED cần đối chiếu source.
Không sửa file test/nghiệp vụ hiện có để xử lý cảnh báo của parser.

Không chạy lại toàn bộ test nghiệp vụ hoặc khởi động ứng dụng mới vì đợt thay đổi chỉ gồm developer tooling/tài liệu.
Không chạy migration, seed, truy cập DB thật hoặc thêm service production.
Cần mở lại Codex để nạp MCP vào phiên mới; đã kiểm tra server độc lập qua stdio, không khẳng định phiên chat hot-reload server.
Đồng đội chạy setup/build để tạo cấu hình và graph riêng. Không commit graph, virtualenv, API key hay đường dẫn MCP của máy.
