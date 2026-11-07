# Coach Learning development tools

Use this canonical checkout for normal development. Create a feature branch here;
do not create additional Coach_Learning worktree folders unless the user requests it.
The product, Live Sync and development-only OCR Lab share this repository. Keep the
scope constructor shared; do not copy an independent fork of it into the Lab.
Models, local service keys, private captures and evaluation results belong in ignored
`.tmp/` storage. Setup and recovery: `LOCAL_SETUP.md`. Never publish private runtime
data or treat a local model/cache as an undeclared dependency of a clean checkout.

Graphify is a local development aid. Setup and usage: `docs/graphify/README.md`.
It must not become an application dependency, production service or runtime import.

For architecture, dependencies and change-impact questions, first query the existing
graph with `./tools/graphify/graphify.ps1 query "<question>"` or the project MCP
server `coach_graphify`. Use `explain` for a symbol and `path` for relationships.
Then verify relevant source locations; graph evidence can be incomplete or stale.
Use `rg` directly for exact text and configuration values. If the graph is absent,
continue with source inspection or build it when useful; do not block development.

The official Graphify skill is installed in `.agents/skills/graphify/` and can be
invoked as `$graphify`. In this repository, replace bare `graphify` commands from
the upstream skill with `./tools/graphify/graphify.ps1`. The supported build is
`./tools/graphify/build.ps1`: local AST only, no semantic LLM pass or API keys.
No parallel agent extraction, global Codex settings, Git hooks, watch services or
cloud upload are required. Do not enable them automatically.

After source changes, refresh the development graph with `build.ps1` when it is
being used for the task. Use `build.ps1 -Full` after large removals/refactors.
Generated `graphify-out/` and machine-specific `.codex/config.toml` are ignored;
commit reusable tooling/configuration and reviewable architecture documentation.
Keep `.graphifyignore` exclusions for secrets, personal data, databases, generated
files, dependencies and model binaries. Do not use live database introspection.

Graphify's code knowledge graph is separate from Coach Learning's curriculum and
knowledge-forest data. Respect deeper `AGENTS.md` instructions, including frontend
Next.js guidance. Preserve pre-existing working-tree changes.
