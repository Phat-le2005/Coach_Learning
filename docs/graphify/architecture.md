# Kiến trúc Coach Learning — Graphify

Sinh lúc 2026-11-08T07:25:31+07:00; Graphify `0.9.102`; HEAD `98c0ae252d76c823e6944160052e2668c2add083`.
Snapshot gồm cả source chưa commit trong working tree. Không đại diện riêng cho HEAD hoặc production.

Đã phát hiện **1,636 file code**, tạo **15,912 nodes / 69,982 quan hệ / 453 communities**.
Có 1,611 file xuất hiện trên node. Fingerprint source: `6b85b563bfa3f0267c8b97e8f928c54989b852010494d92cecd48c9501fee8a3`.
Chỉ phân tích AST cục bộ; semantic LLM: **0 tokens**. Nhãn community lấy từ hub, không dùng model.

![Sơ đồ kiến trúc](architecture.svg)

```mermaid
flowchart LR
  subgraph FE["Frontend · Next.js / React"]
    UI["Student / Teacher / Parent UI"]
    CLIENT["API client + Next route proxies"]
    OCR["Browser OCR / ONNX + Math Canvas / 3D"]
    UI --> CLIENT
    UI --> OCR
  end
  subgraph BE["Backend · FastAPI modular monolith"]
    API["Root API + /api/v2 + /api/v3"]
    CORE["Practice / Assignments / Mastery / Recommendations"]
    MATH["Math solutions / Paper / Canvas / PDF practice"]
    API --> CORE
    API --> MATH
  end
  subgraph AI["AI modules inside Backend"]
    GW["AIGateway + routing + validator + policy"]
    RAG["RAG / Tutor / EmbeddingService"]
    PAPER["GeminiPaperTranscriber"]
    RAG --> GW
  end
  DB[("PostgreSQL + pgvector")]
  PROVIDER["Gemini / Mock provider"]
  OFFLINE["Offline tools · PDF pipeline / learning_baseline"]
  DEV["Development only · Graphify AST → graph.json / MCP / HTML"]
  CLIENT -->|"HTTP · reviewed boundary"| API
  CORE -->|"domain service calls"| GW
  MATH -->|"AI review"| GW
  MATH -->|"Paper OCR"| PAPER
  GW --> PROVIDER
  PAPER -->|"direct HTTP OCR"| PROVIDER
  CORE -->|"SQLAlchemy"| DB
  MATH -->|"SQLAlchemy"| DB
  RAG -->|"retrieval"| DB
  OFFLINE -.->|"offline artifacts; no automatic runtime link"| MATH
  DEV -.->|"reads source only"| FE
  DEV -.->|"reads source only"| BE
```

## Phân bố node

| Lớp | Nodes | File có node |
|---|---:|---:|
| AI | 377 | 39 |
| Backend | 5,419 | 574 |
| Frontend | 2,440 | 372 |
| Other | 2,011 | 22 |
| Tests | 3,741 | 406 |
| Tools | 1,924 | 198 |

AI trong bảng chỉ gồm `backend/app/ai`, `rag`, `tutor`; adapter AI/OCR trong domain khác vẫn thuộc Backend.
Tests được tách riêng; node không có source xác định nằm trong Other. Đây là cách nhóm đường dẫn, không phải service triển khai độc lập.

## Quan hệ AST giữa các lớp

Các cặp không có hướng; số lượng là link lưu trong graph, không phải số request hay số luồng nghiệp vụ.
| Lớp A | Lớp B | Links |
|---|---|---:|
| AI | Backend | 526 |
| AI | Other | 272 |
| AI | Tests | 628 |
| AI | Tools | 15 |
| Backend | Other | 6,093 |
| Backend | Tests | 13,423 |
| Backend | Tools | 428 |
| Frontend | Other | 179 |
| Frontend | Tests | 752 |
| Other | Tests | 4,351 |
| Other | Tools | 1,331 |
| Tests | Tools | 1,333 |

Confidence: `EXTRACTED`: 59,734, `INFERRED`: 10,248.

## Các cặp module liên kết nhiều nhất

| Module A | Module B | Links |
|---|---|---:|
| `backend/app/questions` | `root` | 1,273 |
| `root` | `tools/pdf_metadata` | 1,257 |
| `backend/app/questions` | `backend/tests/questions` | 956 |
| `backend/tests/questions` | `root` | 916 |
| `frontend/src/app` | `frontend/src/lib` | 594 |
| `backend/app/math_solutions` | `backend/tests/math_solutions` | 496 |
| `backend/app/curriculum` | `root` | 465 |
| `backend/tests/math_solutions` | `root` | 421 |
| `backend/app/math_solutions` | `root` | 351 |
| `frontend/src/features/math-workspace` | `frontend/tests` | 323 |
| `backend/app/ai` | `backend/tests/ai` | 319 |
| `backend/app/question_acquisition` | `backend/tests/question_acquisition` | 314 |
| `backend/app/classes` | `backend/tests/classes` | 308 |
| `backend/app/question_supply` | `backend/tests/question_supply` | 299 |
| `root` | `train/comer_hme500` | 294 |
| `frontend/src/features/math-workspace` | `frontend/src/lib` | 257 |
| `backend/tests/curriculum` | `root` | 236 |
| `backend/migrations` | `root` | 235 |
| `root` | `tools/ocr-v2-lab` | 218 |
| `backend/app/questions` | `backend/tests/math_solutions` | 209 |

## Phạm vi và giới hạn

- Chi tiết ranh giới HTTP, AI và offline: [relationships.md](relationships.md).
- Graph tương tác: `graphify-out/graph.html`; GraphML: `graphify-out/graph.graphml`; graph đầy đủ: `graphify-out/graph.json`.
- HTML dùng community aggregation khi vượt 1.800 nodes; JSON/GraphML giữ graph đầy đủ.
- AST không tự chứng minh HTTP, dependency injection, dynamic calls hay tính đúng của nghiệp vụ. Thiếu cạnh không chứng minh hai module độc lập.
- Node module bên ngoài có thể dùng tên package trong source_file khi chưa cài node_modules; không tính các stub này như file source của repo.
- File không có symbol, code ngoài grammar, dữ liệu, CSS và tài liệu chưa chạy semantic có thể không có node; xem `graphify-out/coverage.json` và `build.log`.
- Có cảnh báo parser ở test hiện có `frontend/tests/ocr-math-preview.test.ts`; không sửa test hoặc nghiệp vụ trong tích hợp này.
- Không index secrets, dump DB, dữ liệu học sinh, model, dependency, file build hoặc bản sao worktree. Không gọi DB/API AI.
- Chạy `tools/graphify/build.ps1` để cập nhật; graph hết hiệu lực sau khi source thay đổi cho đến lần build tiếp theo.
