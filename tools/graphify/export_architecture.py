"""Export reviewable architecture summaries from the real Graphify graph.

AST relationships and reviewed HTTP/runtime boundaries stay separate. No LLM,
application imports, database access, or remote service is used here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
from html import escape
import importlib.metadata
import json
from pathlib import Path
import subprocess

from graphify.cluster import label_communities_by_hub
from graphify.detect import detect
from graphify.report import generate
from graphify.serve import _read_graph

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "graphify-out"
DOCS = ROOT / "docs/graphify"
AI_PREFIXES = ("backend/app/ai/", "backend/app/rag/", "backend/app/tutor/")


def relative(source: str) -> str:
    source = str(source).replace("\\", "/")
    prefix = ROOT.as_posix() + "/"
    return source[len(prefix):] if source.lower().startswith(prefix.lower()) else source


def layer(source: str) -> str:
    if "/tests/" in source or "/e2e/" in source:
        return "Tests"
    if source.startswith(AI_PREFIXES):
        return "AI"
    if source.startswith("frontend/"):
        return "Frontend"
    if source.startswith("backend/"):
        return "Backend"
    return "Tools" if source.startswith("tools/") else "Other"


def module(source: str) -> str:
    parts = source.split("/")
    if source.startswith(("backend/app/", "frontend/src/features/")):
        return "/".join(parts[:4] if parts[:3] == ["frontend", "src", "features"] else parts[:3])
    if source.startswith(("frontend/src/", "backend/tests/", "backend/data/", "tools/")):
        return "/".join(parts[:3] if not source.startswith("tools/") else parts[:2])
    return "/".join(parts[:2]) if len(parts) > 1 else "root"


DIAGRAM = '''flowchart LR
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
'''


def svg_diagram(stats: dict) -> str:
    def box(x, y, w, h, color, title, lines):
        text = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{color}" stroke="#334155"/>'
        text += f'<text x="{x+22}" y="{y+34}" class="heading">{escape(title)}</text>'
        for index, line in enumerate(lines):
            text += f'<text x="{x+22}" y="{y+65+index*25}" class="body">{escape(line)}</text>'
        return text

    def arrow(path, label, x, y, dashed=False):
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        return f'<path d="{path}" fill="none" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"{dash}/><text x="{x}" y="{y}" class="label">{escape(label)}</text>'

    items = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="930" viewBox="0 0 1440 930" role="img" aria-labelledby="title desc">',
        '<title id="title">Coach Learning architecture and Graphify development integration</title>',
        '<desc id="desc">Frontend connects by HTTP to FastAPI. Backend owns domain logic and persistence, and calls AI modules. Graphify reads source for development only.</desc>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"/></marker></defs>',
        '<style>text{font-family:Segoe UI,Arial,sans-serif}.heading{font-size:21px;font-weight:700;fill:#0f172a}.body{font-size:17px;fill:#334155}.label{font-size:14px;fill:#475569}</style>',
        '<rect width="1440" height="930" fill="#f8fafc"/>',
        '<text x="48" y="55" class="heading" style="font-size:30px">Coach Learning · Architecture map</text>',
        f'<text x="48" y="87" class="body">Local AST graph · {stats["nodes"]:,} nodes · {stats["edges"]:,} relationships · {stats["communities"]} communities</text>',
        box(48, 140, 370, 205, '#dbeafe', 'Frontend · Next.js / React', ['Student / Teacher / Parent views', 'API client + Next route proxies', 'Browser OCR / ONNX', 'Math Canvas / Three.js']),
        box(540, 140, 420, 205, '#dcfce7', 'Backend · FastAPI', ['Root API + /api/v2 + /api/v3', 'Practice / Assignments / Mastery', 'Recommendations / Curriculum', 'Math solutions / Paper / Canvas']),
        box(540, 440, 420, 205, '#ede9fe', 'AI · modules inside Backend', ['AIGateway · routing / validator / policy', 'Tutor / RAG / EmbeddingService', 'Paper OCR: direct Gemini HTTP', 'External provider or local Mock']),
        box(1080, 140, 312, 145, '#fef3c7', 'Persistence', ['PostgreSQL + pgvector', 'SQLAlchemy / Alembic']),
        box(1080, 440, 312, 145, '#fce7f3', 'AI provider', ['Gemini API', 'Mock provider (local)']),
        box(48, 440, 370, 205, '#e2e8f0', 'Offline development tools', ['PDF extraction / OCR pipeline', 'learning_baseline / B3 scheduler', 'Produces local artifacts', 'No automatic runtime integration']),
        box(48, 750, 1344, 125, '#f1f5f9', 'Graphify · development only', ['Source → local AST → graph.json / GRAPH_REPORT.md / HTML / GraphML', 'Codex: AGENTS.md + official skill + stdio MCP · isolated virtualenv · no production dependency']),
        arrow('M 418 215 H 540', 'HTTP', 450, 200),
        arrow('M 960 215 H 1080', 'ORM', 997, 199),
        arrow('M 750 345 V 440', 'AI calls', 765, 395),
        arrow('M 960 510 H 1080', 'API / Mock', 986, 494),
        arrow('M 890 440 V 377 H 1236 V 285', 'RAG retrieval', 1033, 364),
        arrow('M 233 750 V 645', 'source analysis', 245, 709, True),
        arrow('M 750 750 V 645', 'source analysis', 762, 709, True),
        '<text x="48" y="908" class="label">Solid: reviewed runtime boundaries. Dashed: development source analysis. See relationships.md for source evidence and limits.</text>',
        '</svg>',
    ]
    return "\n".join(items)


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    graph_path = OUT / "graph.json"
    raw = json.loads(graph_path.read_text(encoding="utf-8"))
    graph = _read_graph(str(graph_path))
    analysis = json.loads((OUT / ".graphify_analysis.json").read_text(encoding="utf-8"))
    communities = {int(key): value for key, value in analysis["communities"].items()}
    labels = label_communities_by_hub(graph, communities)
    (OUT / ".graphify_labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")
    detection = detect(ROOT)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    report = generate(graph, communities, {int(k): v for k, v in analysis.get("cohesion", {}).items()},
                      labels, analysis.get("gods", []), analysis.get("surprises", []), detection,
                      {"input": 0, "output": 0}, str(ROOT), built_at_commit=head)
    (OUT / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    code_files = detection["files"].get("code", [])
    code_paths = sorted(relative(path) for path in code_files)
    sources = {node["id"]: relative(node.get("source_file", "")) for node in raw["nodes"]}
    repository_sources = set(sources.values()) & set(code_paths)
    nodes = Counter(layer(source) for source in sources.values())
    files = Counter(layer(source) for source in repository_sources)
    matrix, confidence, relations = Counter(), Counter(), defaultdict(Counter)
    for edge in raw.get("links", raw.get("edges", [])):
        left, right = sources.get(edge["source"], ""), sources.get(edge["target"], "")
        tag = edge.get("confidence", "UNSPECIFIED")
        confidence[tag] += 1
        # Canonical unordered pairs: the AST graph is an undirected connectivity
        # graph, so aggregated counts must not be presented as directed calls.
        a, b = sorted((layer(left), layer(right)))
        matrix[a, b] += 1
        ma, mb = sorted((module(left), module(right)))
        if ma != mb:
            relations[ma, mb][tag] += 1
    fingerprint = hashlib.sha256()
    for source in code_paths:
        fingerprint.update(source.encode("utf-8"))
        fingerprint.update(hashlib.sha256((ROOT / source).read_bytes()).digest())
    stamp = datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")
    stats = {"nodes": len(raw["nodes"]), "edges": sum(confidence.values()), "communities": len(communities),
             "code_files_detected": len(code_paths), "files_with_nodes": len(repository_sources),
             "graphify_version": importlib.metadata.version("graphifyy"), "head_commit": head,
             "generated_at": stamp, "source_sha256": fingerprint.hexdigest(),
             "confidence": dict(confidence), "semantic_llm_tokens": 0}
    data = {"stats": stats, "layer_definition": {"AI": list(AI_PREFIXES), "Tests": "*/tests/* and */e2e/*"},
            "count_semantics": "Unordered pairs of stored AST links; not directed runtime calls.",
            "layers": [{"name": name, "nodes": nodes[name], "files_with_nodes": files[name]} for name in sorted(nodes)],
            "layer_relations": [{"a": a, "b": b, "edges": count} for (a, b), count in sorted(matrix.items())],
            "module_relations": [{"a": a, "b": b, "edges": sum(tags.values()), "confidence": dict(tags)}
                                 for (a, b), tags in sorted(relations.items(), key=lambda item: (-sum(item[1].values()), item[0]))]}
    (DOCS / "module-relations.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "coverage.json").write_text(json.dumps({"stats": stats, "code_files": code_paths,
        "unclassified": [relative(p) for p in detection["unclassified"]],
        "sensitive_skipped": [relative(p) for p in detection["skipped_sensitive"]],
        "walk_errors": detection["walk_errors"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (DOCS / "architecture.mmd").write_text(DIAGRAM, encoding="utf-8")
    (DOCS / "architecture.svg").write_text(svg_diagram(stats), encoding="utf-8")
    lines = ["# Kiến trúc Coach Learning — Graphify", "", f"Sinh lúc {stamp}; Graphify `{stats['graphify_version']}`; HEAD `{head}`.",
             "Snapshot gồm cả source chưa commit trong working tree. Không đại diện riêng cho HEAD hoặc production.", "",
             f"Đã phát hiện **{len(code_paths):,} file code**, tạo **{stats['nodes']:,} nodes / {stats['edges']:,} quan hệ / {stats['communities']} communities**.",
             f"Có {stats['files_with_nodes']:,} file xuất hiện trên node. Fingerprint source: `{stats['source_sha256']}`.",
             "Chỉ phân tích AST cục bộ; semantic LLM: **0 tokens**. Nhãn community lấy từ hub, không dùng model.", "",
             "![Sơ đồ kiến trúc](architecture.svg)", "", "```mermaid", DIAGRAM.rstrip(), "```", "",
             "## Phân bố node", "", "| Lớp | Nodes | File có node |", "|---|---:|---:|"]
    lines += [f"| {name} | {nodes[name]:,} | {files[name]:,} |" for name in sorted(nodes)]
    lines += ["", "AI trong bảng chỉ gồm `backend/app/ai`, `rag`, `tutor`; adapter AI/OCR trong domain khác vẫn thuộc Backend.",
              "Tests được tách riêng; node không có source xác định nằm trong Other. Đây là cách nhóm đường dẫn, không phải service triển khai độc lập.", "",
              "## Quan hệ AST giữa các lớp", "", "Các cặp không có hướng; số lượng là link lưu trong graph, không phải số request hay số luồng nghiệp vụ.",
              "| Lớp A | Lớp B | Links |", "|---|---|---:|"]
    lines += [f"| {a} | {b} | {count:,} |" for (a, b), count in sorted(matrix.items()) if a != b]
    lines += ["", "Confidence: " + ", ".join(f"`{key}`: {value:,}" for key, value in sorted(confidence.items())) + ".", "",
              "## Các cặp module liên kết nhiều nhất", "", "| Module A | Module B | Links |", "|---|---|---:|"]
    lines += [f"| `{row['a']}` | `{row['b']}` | {row['edges']:,} |" for row in data["module_relations"][:20]]
    lines += ["", "## Phạm vi và giới hạn", "",
              "- Chi tiết ranh giới HTTP, AI và offline: [relationships.md](relationships.md).",
              "- Graph tương tác: `graphify-out/graph.html`; GraphML: `graphify-out/graph.graphml`; graph đầy đủ: `graphify-out/graph.json`.",
              "- HTML dùng community aggregation khi vượt 1.800 nodes; JSON/GraphML giữ graph đầy đủ.",
              "- AST không tự chứng minh HTTP, dependency injection, dynamic calls hay tính đúng của nghiệp vụ. Thiếu cạnh không chứng minh hai module độc lập.",
              "- Node module bên ngoài có thể dùng tên package trong source_file khi chưa cài node_modules; không tính các stub này như file source của repo.",
              "- File không có symbol, code ngoài grammar, dữ liệu, CSS và tài liệu chưa chạy semantic có thể không có node; xem `graphify-out/coverage.json` và `build.log`.",
              "- Có cảnh báo parser ở test hiện có `frontend/tests/ocr-math-preview.test.ts`; không sửa test hoặc nghiệp vụ trong tích hợp này.",
              "- Không index secrets, dump DB, dữ liệu học sinh, model, dependency, file build hoặc bản sao worktree. Không gọi DB/API AI.",
              "- Chạy `tools/graphify/build.ps1` để cập nhật; graph hết hiệu lực sau khi source thay đổi cho đến lần build tiếp theo.", ""]
    (DOCS / "architecture.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
