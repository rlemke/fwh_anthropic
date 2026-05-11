# fwh_anthropic

A standalone [Facetwork](https://github.com/rlemke/facetwork) example package
that hosts FFL workflows and handlers wrapping the public surfaces
published at [github.com/anthropics](https://github.com/anthropics):

- **Messages API** — prompt caching, vision inputs, streaming, tool use
- **Batch API** — Message Batches for cost-efficient large-scale runs
- **Files API** — uploads, citations, document attachments
- **Agent SDK** — autonomous-agent facets backed by the Claude Agent SDK
- **Claude Code** — invoke the Claude Code CLI from FFL workflows
- **Computer Use** — long-running tool-use sessions managed by the runner
- **MCP** — Model Context Protocol clients/servers as facets
- **Evaluations & Cookbook** — pattern libraries lifted from the Anthropic cookbook

**This is currently a scaffold.** The package layout is in place and the
entry point resolves, but each area subpackage ships a stub
`register_handlers` that's ready to be filled in. As individual areas
are wired up, they're added to the matching `handlers/<area>/` +
`tools/_lib/<area>.py` + `ffl/<area>.ffl` trio — no other repo-level
changes required.

Discovered by the Facetwork runner via the `facetwork.examples` entry point
declared in `pyproject.toml`. After `pip install -e .`, Facetwork's
`scripts/start-runner --example anthropic` and `scripts/seed-examples`
pick this package up automatically (even with zero handlers wired today).

## Install

```bash
git clone https://github.com/rlemke/fwh_anthropic.git ~/fw_handlers/fwh_anthropic
cd ~/fw_handlers/fwh_anthropic
pip install -e .
```

This registers the package under the `facetwork.examples` entry-point group,
making it discoverable by any Facetwork installation in the same environment.

## Run from a Facetwork checkout

```bash
# When areas are wired up, FFL workflows show up in the dashboard like this:
scripts/seed-examples --include anthropic
scripts/start-runner --example anthropic -- --log-format text
```

At the current scaffolding stage, the runner reports
`anthropic: 0 handlers registered  [entry_point]` — that's expected.

## Inspect what areas are wired

```bash
src/anthropic_handlers/tools/list-areas.sh
```

Prints a table of every area subpackage and how many handlers it
currently exposes.

## Layout

```
fwh_anthropic/
├── pyproject.toml                            # facetwork.examples entry point
├── README.md
├── CLAUDE.md                                 # guidance for Claude Code in this repo
├── agent-spec/
│   ├── tools-pattern.agent-spec.yaml         # the canonical tools/_lib pattern
│   ├── cache-layout.agent-spec.yaml          # cache sidecar protocol
│   └── integration-areas.agent-spec.yaml     # how to add a new Anthropic-surface area
├── tests/
└── src/anthropic_handlers/
    ├── __init__.py                           # exports `example: ExamplePackage`
    ├── handlers/
    │   ├── __init__.py                       # register_all_registry_handlers (calls every area)
    │   ├── shared/anthropic_utils.py         # shim into tools/_lib (auth, retry, rate-limit, …)
    │   ├── messages/                         # Messages API (TODO)
    │   ├── batch/                            # Batch API (TODO)
    │   ├── files/                            # Files API (TODO)
    │   ├── agent_sdk/                        # Agent SDK (TODO)
    │   ├── claude_code/                      # Claude Code CLI (TODO)
    │   └── computer_use/                     # Computer Use (TODO)
    ├── ffl/                                  # one .ffl per area + a top-level catalog
    └── tools/
        ├── _lib/                             # client, auth, rate-limit + one module per area
        │   ├── client.py
        │   ├── messages.py
        │   ├── batch.py
        │   ├── files.py
        │   ├── agent_sdk.py
        │   ├── claude_code.py
        │   └── computer_use.py
        ├── list-areas.sh / .py               # inspect wiring status
        └── *.py / *.sh                       # per-facet CLIs (added per area)
```

## Required infrastructure

| Service | Purpose |
|---------|---------|
| MongoDB | Facetwork registry + workflow state |
| `ANTHROPIC_API_KEY` | All Messages / Batch / Files / Agent SDK / Computer Use areas |

The Claude Code area additionally needs `claude` on `PATH`; the MCP
area needs the `mcp` package; the Agent SDK area needs the
`claude-agent-sdk` package. Install only the optionals you'll use:

```bash
pip install -e ".[agent_sdk,mcp]"
```

## Adding a new area

1. Pick a name that matches the Anthropic surface (e.g. `evals`, `cookbook`, `citations`).
2. Add `src/anthropic_handlers/tools/_lib/<area>.py` with pure-function simulators / SDK wrappers.
3. Add `src/anthropic_handlers/handlers/<area>/__init__.py` exporting `register_handlers(runner)` + a `_DISPATCH` map.
4. Add `src/anthropic_handlers/ffl/<area>.ffl` declaring the namespace + event facets.
5. Wire it in `src/anthropic_handlers/handlers/__init__.py::register_all_registry_handlers`.
6. (Optional) Re-export key symbols from `handlers/shared/anthropic_utils.py`.

See [`agent-spec/integration-areas.agent-spec.yaml`](agent-spec/integration-areas.agent-spec.yaml)
for the contract a new area should satisfy.

## License

Apache 2.0 — see `LICENSE`.
