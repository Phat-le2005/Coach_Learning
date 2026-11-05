"""Check graph integrity, source coverage and a real stdio MCP conversation."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tomllib
import warnings

from mcp import ClientSession, StdioServerParameters, stdio_client

from export_architecture import ROOT, relative


async def check_mcp(config: dict, expected_nodes: int) -> dict:
    params = StdioServerParameters(command=config["command"], args=config["args"],
                                   cwd=config["cwd"], env=config["env"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert set(config["enabled_tools"]) <= names, "Configured MCP tool is unavailable"
            calls = [
                ("graph_stats", {}, str(expected_nodes)),
                ("query_graph", {"question": "AIGateway GeminiProvider", "depth": 1, "token_budget": 800}, "AIGateway"),
                ("get_node", {"label": "AIGateway"}, "backend/app/ai/gateway.py"),
                ("shortest_path", {"source": "AnswerGroundedAIService", "target": "AIGateway", "undirected": True}, "INFERRED"),
            ]
            passed = []
            for name, arguments, expected in calls:
                result = await session.call_tool(name, arguments)
                content = "\n".join(getattr(item, "text", "") for item in result.content)
                is_error = getattr(result, "isError", getattr(result, "is_error", False))
                assert not is_error, f"MCP {name} returned an error: {content[:200]}"
                assert expected in content.replace(",", ""), f"Unexpected MCP {name} response"
                passed.append(name)
            return {"transport": "stdio", "enabled_tools": config["enabled_tools"], "calls_passed": passed}


async def main(baseline: Path | None) -> None:
    graph = json.loads((ROOT / "graphify-out/graph.json").read_text(encoding="utf-8"))
    ids = {node["id"] for node in graph["nodes"]}
    assert len(ids) == len(graph["nodes"]), "Duplicate graph node IDs"
    edges = graph.get("links", graph.get("edges", []))
    assert all(edge["source"] in ids and edge["target"] in ids for edge in edges), "Dangling edges"
    coverage = json.loads((ROOT / "graphify-out/coverage.json").read_text(encoding="utf-8"))
    assert not coverage["walk_errors"], "Source scan encountered filesystem errors"
    indexed = set(coverage["code_files"])
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    declared_packages = set().union(*(package.get(key, {}) for key in
        ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")))
    # Without node_modules, Graphify represents an imported package as a module
    # stub whose source_file is its package name, rather than a filesystem path.
    external_refs = {relative(node.get("source_file", "")) for node in graph["nodes"]
                     if node.get("type") == "module"
                     and node.get("source_file") == node.get("label")
                     and node.get("source_file") in declared_packages}
    graph_sources = {relative(node.get("source_file", "")) for node in graph["nodes"]} - {""} - external_refs
    assert not graph_sources - indexed, "Graph retains sources outside the current AST scan"
    forbidden = (".tmp/", ".agents/", ".codex/", ".worktrees/", "frontend/public/", "data/", "output/", "artifacts/")
    assert not any(path.startswith(forbidden) or "/node_modules/" in path or "/.venv/" in path for path in indexed)
    assert not any(Path(path).name.startswith(".env") or Path(path).suffix in {".dump", ".onnx", ".sql"} for path in indexed)
    # Every Python/TS/JS source in the application directories must be detected.
    # CSS and binary/static assets are outside the AST grammar's scope.
    expected = {relative(str(path)) for start in ("backend/app", "frontend/src")
                for path in (ROOT / start).rglob("*")
                if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".js", ".mjs"}}
    assert not expected - indexed, f"Application source omitted: {sorted(expected - indexed)}"
    fingerprint = hashlib.sha256()
    for source in sorted(indexed):
        fingerprint.update(source.encode("utf-8"))
        fingerprint.update(hashlib.sha256((ROOT / source).read_bytes()).digest())
    assert fingerprint.hexdigest() == coverage["stats"]["source_sha256"], "Graph exports are stale; run build.ps1"
    assert graph["graph"].get("graphify_version") == "0.9.102", "Unexpected Graphify version"
    assert coverage["stats"]["semantic_llm_tokens"] == 0
    config = tomllib.loads((ROOT / ".codex/config.toml").read_text(encoding="utf-8"))["mcp_servers"]["coach_graphify"]
    assert config["enabled"] and len(config["enabled_tools"]) == 7
    result = {"graph_integrity": "passed", "source_coverage": f"{len(expected)}/{len(expected)} application source files detected",
              "excluded_inputs": "passed", "source_fingerprint": "current",
              "external_package_stubs": sorted(external_refs),
              "mcp": await check_mcp(config, len(ids))}
    if baseline:
        before = json.loads(baseline.read_text(encoding="utf-8"))
        changed = [name for name, digest in before.items()
                   if not (ROOT / name).is_file() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
        assert not changed, f"Pre-existing source changed: {changed}"
        result["pre_existing_source"] = f"{len(before)} files unchanged (SHA-256)"
    (ROOT / "graphify-out/verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        asyncio.run(asyncio.wait_for(main(args.baseline), timeout=90))
