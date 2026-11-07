# Kiến trúc Coach Learning — Graphify

Sinh lúc 2026-11-08T06:48:40+07:00; Graphify `0.9.102`; HEAD `6260096858eb4e3f342daf4659a0149743b228e6`.
Snapshot gồm cả source chưa commit trong working tree. Không đại diện riêng cho HEAD hoặc production.

Đã phát hiện **1,638 file code**, tạo **15,835 nodes / 69,676 quan hệ / 449 communities**.
Có 1,611 file xuất hiện trên node. Fingerprint source: `2bc62a0083cd35f6486dfeb1ff0260e6cc536c34c0001b87397ec88785be7780`.
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
| Backend | 5,418 | 574 |
| Frontend | 2,354 | 369 |
| Other | 2,015 | 22 |
| Tests | 3,747 | 409 |
| Tools | 1,924 | 198 |

AI trong bảng chỉ gồm `backend/app/ai`, `rag`, `tutor`; adapter AI/OCR trong domain khác vẫn thuộc Backend.
Tests được tách riêng; node không có source xác định nằm trong Other. Đây là cách nhóm đường dẫn, không phải service triển khai độc lập.

## Quan hệ AST giữa các lớp

Các cặp không có hướng; số lượng là link lưu trong graph, không phải số request hay số luồng nghiệp vụ.
| Lớp A | Lớp B | Links |
|---|---|---:|
| AI | Backend | 530 |
| AI | Other | 272 |
| AI | Tests | 628 |
| AI | Tools | 15 |
| Backend | Other | 6,089 |
| Backend | Tests | 13,432 |
| Backend | Tools | 428 |
| Frontend | Other | 178 |
| Frontend | Tests | 744 |
| Other | Tests | 4,354 |
| Other | Tools | 1,331 |
| Tests | Tools | 1,333 |

Confidence: `EXTRACTED`: 59,391, `INFERRED`: 10,285.

## Các cặp module liên kết nhiều nhất

| Module A | Module B | Links |
|---|---|---:|
| `backend/app/questions` | `root` | 1,273 |
| `root` | `tools/pdf_metadata` | 1,257 |
| `backend/app/questions` | `backend/tests/questions` | 956 |
| `backend/tests/questions` | `root` | 916 |
| `frontend/src/app` | `frontend/src/lib` | 529 |
| `backend/app/math_solutions` | `backend/tests/math_solutions` | 504 |
| `backend/app/curriculum` | `root` | 465 |
| `backend/tests/math_solutions` | `root` | 421 |
| `backend/app/math_solutions` | `root` | 351 |
| `frontend/src/features/math-workspace` | `frontend/tests` | 323 |
| `backend/app/ai` | `backend/tests/ai` | 319 |
| `backend/app/question_acquisition` | `backend/tests/question_acquisition` | 314 |
| `backend/app/classes` | `backend/tests/classes` | 308 |
| `backend/app/question_supply` | `backend/tests/question_supply` | 299 |
| `root` | `train/comer_hme500` | 294 |
| `frontend/src/features/math-workspace` | `frontend/src/lib` | 254 |
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
