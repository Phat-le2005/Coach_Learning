"""Install the official Codex skill and a project-local stdio MCP entry."""
from __future__ import annotations

import json
import importlib.metadata
from pathlib import Path
import shutil
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ["query_graph", "get_node", "get_neighbors", "get_community", "god_nodes", "graph_stats", "shortest_path"]
START, END = "# BEGIN COACH GRAPHIFY", "# END COACH GRAPHIFY"


def main() -> None:
    # Copy the exact packaged Codex skill, including its references, into the
    # repository location documented by OpenAI. No user-global installation.
    import graphify

    package = Path(graphify.__file__).parent
    target = ROOT / ".agents/skills/graphify"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(package / "skill-codex.md", target / "SKILL.md")
    shutil.copytree(package / "skills/codex/references", target / "references", dirs_exist_ok=True)
    distribution = importlib.metadata.distribution("graphifyy")
    for entry in distribution.files or []:
        if "licenses" in entry.parts and entry.name in {"LICENSE", "LICENSE-MIT", "NOTICE"}:
            shutil.copy2(distribution.locate_file(entry), target / entry.name)
    config_path = ROOT / ".codex/config.toml"
    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    parsed = tomllib.loads(existing)
    if START not in existing and "coach_graphify" in parsed.get("mcp_servers", {}):
        raise SystemExit("Existing coach_graphify entry has no managed marker; review it before setup.")
    quote = lambda value: json.dumps(str(value), ensure_ascii=False)
    block = "\n".join([
        START,
        "[mcp_servers.coach_graphify]",
        f"command = {quote(Path(sys.executable).resolve())}",
        'args = ["-m", "graphify.serve", "--graph", ' + quote(ROOT / "graphify-out/graph.json") + "]",
        f"cwd = {quote(ROOT)}",
        'env = { PYTHONUTF8 = "1" }',
        "enabled = true",
        "startup_timeout_sec = 60",
        "tool_timeout_sec = 60",
        "enabled_tools = " + json.dumps(TOOLS),
        END,
    ])
    if START in existing:
        if existing.count(START) != 1 or existing.count(END) != 1:
            raise SystemExit("Invalid managed Graphify config markers.")
        first, remainder = existing.split(START, 1)
        _, last = remainder.split(END, 1)
        updated = first + block + last
    else:
        updated = existing.rstrip() + "\n\n" + block + "\n"
    tomllib.loads(updated)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(updated, encoding="utf-8")
    print("Installed official Codex skill in .agents/skills/graphify; configured coach_graphify stdio MCP.")


if __name__ == "__main__":
    main()
