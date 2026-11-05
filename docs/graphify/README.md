# Graphify cho phát triển và bảo trì Coach Learning

Graphify CLI chính thức: [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify).
Gói PyPI là **`graphifyy`** (hai chữ y), lệnh CLI là `graphify`.
Tích hợp này pin **0.9.102**, chỉ chạy trên máy phát triển. Không dùng Graphify Cloud,
không thêm vào dependency Backend/Frontend, không có service production hoặc migration.

Đối chiếu ngày 05/11/2026: README và mã nguồn upstream commit
`59b5ab1151e031fb42e39cfc9a50bf96f2d57ae0`, metadata PyPI và CLI của bản đã cài.
Graphify yêu cầu Python 3.10+; bộ script này dùng `tomllib` và được kiểm chứng trên
**Windows / PowerShell / Python 3.13.3**. Dùng Python 3.13 cho cùng môi trường;
Python 3.11–3.12 có thể kéo thêm dependency Leiden khác và chưa được kiểm chứng ở đây.

## Cài đặt và tạo graph

Chạy từ thư mục gốc repo:

```powershell
./tools/graphify/setup.ps1
./tools/graphify/build.ps1
./.tmp/graphify-runtime/.venv/Scripts/python.exe tools/graphify/check.py
```

Nếu PowerShell của máy chặn script, chạy từng script qua
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/graphify/setup.ps1`
(tương tự với `build.ps1`); không cần đổi execution policy toàn máy.
Cài đặt lần đầu cần Internet để tải package từ PyPI. Phân tích source và truy vấn
sau đó chạy cục bộ, không cần API key, không đọc `.env`, không gọi DB/AI của ứng dụng.

`setup.ps1` tạo virtualenv riêng tại `.tmp/graphify-runtime/.venv`, chép **nguyên bản
skill Codex chính thức và references** vào `.agents/skills/graphify`, kèm giấy phép,
và cấu hình server `coach_graphify` trong `.codex/config.toml` cục bộ. Chạy lại setup
cập nhật riêng block có marker; các cấu hình Codex khác được giữ nguyên. Lệnh setup
không cài vào user profile và không thay đổi `~/.codex/config.toml`.

Graphify upstream cài Codex skill vào `.codex/skills`. Tích hợp này đặt cùng nội dung
trong `.agents/skills` theo [tài liệu skill của OpenAI](https://developers.openai.com/codex/skills).
Không đăng ký hook no-op `PreToolUse` của upstream, Git hook hay tiến trình watch.
Không cần bật multi-agent: build dùng AST worker cục bộ, không dispatch coding agent.

`build.ps1` gọi `extract . --code-only --max-workers 2 --no-dedup`, rồi tạo report,
HTML và GraphML. Hai worker giới hạn tải máy; tắt dedup để tránh gộp nhầm symbol cùng
tên ở nhiều domain. Không có bước semantic LLM, đặt tên community bằng hub của graph.
Lần sau tận dụng cache/incremental. Sau refactor/xóa nhiều source:

```powershell
./tools/graphify/build.ps1 -Full
```

Nếu chạy trực tiếp `graphify.ps1 update .`, hãy chạy lại `build.ps1` trước khi dùng
report kiến trúc đã xuất; report tùy biến không tự cập nhật theo mọi lệnh CLI upstream.

## Tra cứu từ terminal hoặc Codex

```powershell
./tools/graphify/graphify.ps1 query 'AIGateway GeminiProvider' --budget 1200 --depth 1
./tools/graphify/graphify.ps1 explain AIGateway
./tools/graphify/graphify.ps1 path AnswerGroundedAIService AIGateway --undirected
./tools/graphify/graphify.ps1 query 'MathCanvasService MathSolutionService' --budget 1500
```

Ưu tiên tên class/function/path tiếng Anh trong source. Query là truy hồi subgraph,
không phải chatbot tự trả lời. Query quá rộng dễ bị cắt theo token budget; thu hẹp
từ khóa, dùng `--depth 1`, `explain`, hoặc tăng budget. `INFERRED` là quan hệ suy ra
từ phân giải code; luôn kiểm tra source và dòng đi kèm trước khi sửa nghiệp vụ.
`path --undirected` khám phá liên thông, không chứng minh chiều gọi runtime.

Trong Codex, có thể gõ `$graphify` hoặc yêu cầu:

> Dùng graph coach_graphify tìm các module gọi AIGateway và giải thích ảnh hưởng
> nếu sửa validation của AI response; đối chiếu source trước khi đề xuất thay đổi.

`AGENTS.md` hướng dẫn query graph trước các câu hỏi cấu trúc. Wrapper PowerShell
chọn đúng interpreter và root repo ngay cả khi gọi từ thư mục con.

MCP dùng **stdio**, chỉ bật bảy công cụ đọc graph: `query_graph`, `get_node`,
`get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`.
Không mở cổng HTTP. Cấu hình dùng đường dẫn tuyệt đối của máy nên được gitignore;
đồng đội chạy setup để tạo lại. Xem [cấu hình MCP Codex chính thức](https://developers.openai.com/codex/mcp).

Sau setup, mở lại Codex trong repo để nạp MCP vào phiên mới. Kiểm tra CLI nhận cấu hình:

```powershell
codex mcp get coach_graphify --json
./.tmp/graphify-runtime/.venv/Scripts/python.exe tools/graphify/check.py
```

Codex chỉ tải cấu hình project được tin cậy. Nếu MCP chưa xuất hiện, kiểm tra root
repo, trạng thái trusted project và đường dẫn executable bằng lệnh trên; chạy lại
setup sau khi di chuyển repo. Graph/CLI vẫn dùng được trước khi mở lại Codex.

## Kết quả và phạm vi

| File | Cách dùng |
|---|---|
| `graphify-out/graph.json` | Knowledge graph đầy đủ, schema/version và nguồn từng cạnh |
| `graphify-out/graph.html` | Sơ đồ tương tác; mở bằng trình duyệt |
| `graphify-out/graph.graphml` | Graph đầy đủ để mở trong Gephi/yEd |
| `graphify-out/GRAPH_REPORT.md` | Report community/hub/confidence của Graphify |
| `graphify-out/coverage.json` | File được phát hiện, file không hỗ trợ, lỗi scan, fingerprint |
| `graphify-out/verification.json` | Kết quả kiểm tra graph và MCP thực tế |
| [architecture.md](architecture.md) | Thống kê và kiến trúc Frontend–Backend–AI |
| [architecture.svg](architecture.svg) / [architecture.mmd](architecture.mmd) | Sơ đồ kiến trúc xuất riêng |
| [relationships.md](relationships.md) | Ranh giới runtime đã đối chiếu source |
| [module-relations.json](module-relations.json) | Ma trận quan hệ module để xử lý tiếp |
| [verification.md](verification.md) | Biên bản kiểm tra tích hợp, giới hạn và kết quả thực tế |

Graph lớn dùng community aggregation trong HTML khi vượt 1.800 nodes; JSON/GraphML
vẫn giữ đầy đủ. HTML upstream tải thư viện vis-network từ CDN, nên trình duyệt cần
Internet cho thư viện hiển thị. Dùng SVG, Mermaid hoặc GraphML nếu làm việc offline.
Không có bước upload source/graph lên dịch vụ Graphify.

"Toàn bộ codebase" ở đây bao gồm code ứng dụng, tests, migrations, Python seed/
generator, scripts, công cụ PDF và baseline. Phạm vi không giới hạn ở file đã commit.
`.graphifyignore` loại dữ liệu, JSON/CSV question payload, secrets, dump DB, file có
credential (`docker-compose.yml`), model, dependency, bản build và worktree lồng nhau.
File code cấu hình JSON/YAML được phân tích khi phù hợp, nhưng CSS, `.cmd`, template
và tài liệu không có parser AST tương ứng có thể không tạo node. Tài liệu/media
không chạy semantic pass. Không đồng nhất số file được phát hiện với số file có symbol.

Khi chưa cài `node_modules`, Graphify có thể ghi tên package (ví dụ `next`) vào
`source_file` của node module bên ngoài. Đây là stub dependency, không phải source
được đọc từ filesystem; checker đối chiếu tên với manifest và report không tính
những stub này vào số file source của repo.

Các cạnh HTTP hoặc quan hệ triển khai trong sơ đồ kiến trúc là **đối chiếu thủ công
có source**, tách khỏi graph AST và không được thêm như cạnh AST giả. Thiếu cạnh
Frontend–Backend trong graph không chứng minh hai lớp không giao tiếp.

## Kiểm chứng và bảo trì

`check.py` kiểm tra ID/cạnh, loại trừ dữ liệu nhạy cảm, phát hiện đủ source ứng dụng,
fingerprint source, rồi khởi động **server Graphify thật bằng stdio** và gọi
`graph_stats`, `query_graph`, `get_node`, `shortest_path`. Nó không khởi động ứng dụng
hoặc truy cập DB. Log build có thể lưu bằng:

```powershell
./tools/graphify/build.ps1 *> .tmp/graphify-runtime/build.log
```

Đây là công cụ hiểu cấu trúc code, không thay thế unit/integration tests, kiểm tra
security hoặc xác nhận tính đúng học thuật. Khi sửa code, refresh graph và review
diff tài liệu; không commit `graphify-out`, virtualenv hoặc cấu hình máy.

Để ngừng dùng, tắt `enabled` trong block MCP `coach_graphify` ở `.codex/config.toml`,
mở lại Codex và bỏ các dòng hướng dẫn Graphify trong `AGENTS.md` khi cả nhóm thống
nhất. Có thể xóa riêng các artifact/runtime sinh ra sau khi kiểm tra đúng đường dẫn;
không cần thay đổi dependency hay dữ liệu ứng dụng. Giữ lại các cấu hình Codex khác.
