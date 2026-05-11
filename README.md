# fwh_anthropic

A standalone [Facetwork](https://github.com/rlemke/facetwork) example package
that hosts FFL workflows and handlers wrapping the public surfaces
published at [github.com/anthropics](https://github.com/anthropics).

| Area | Status | What it wraps |
|------|--------|--------------|
| **Messages API** | ✅ 6 facets | `CreateMessage`, `CountTokens`, `CreateMessageWithTools`, `CreateMessageWithImages`, `CreateMessageStream`, `CreateMessageWithFile` (Files-API RAG) |
| **Batch API** | ✅ 4 facets | `SubmitBatch`, `GetBatchStatus`, `GetBatchResults`, `RunBatch` (submit + poll + retrieve driver) |
| **Files API** | ✅ 3 facets | `UploadFile`, `ListFiles`, `DeleteFile` |
| **Agent SDK** | ✅ 1 facet | `RunAgent` (Claude Agent SDK) |
| **Claude Code** | ✅ 1 facet | `RunClaudeCode` (Claude Code CLI subprocess) |
| **Computer Use** | ✅ 1 facet | `RunComputerUseSession` (simulator-backed by default) |
| **Cross-area composition** | ✅ 1 workflow | `anthropic.compose.DocumentQA` (Files + Messages RAG) |

All six initial areas are wired (16 facets total). Adding a new area
(`mcp`, `evals`, `cookbook`, …) is purely additive — drop in
`handlers/<area>/` + `tools/_lib/<area>.py` + `ffl/<area>.ffl` and
wire it into `handlers/__init__.py`.

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
scripts/seed-examples --include anthropic
scripts/start-runner --example anthropic -- --log-format text
```

The runner reports `anthropic: 16 handlers registered  [entry_point]`.
All facets show up in the dashboard's namespace browser.

## Inspect what areas are wired

```bash
src/anthropic_handlers/tools/list-areas.sh
```

Prints a table of every area subpackage and how many handlers it
currently exposes.

## Live tests (opt-in)

The unit suite mocks all SDK calls. To smoke-test against the real
Anthropic API:

```bash
ANTHROPIC_API_KEY=sk-... pytest tests/live -m live --run-live
```

See `tests/live/README.md` for the full gating contract.

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
    │   ├── messages/                         # Messages API (6 facets)
    │   ├── batch/                            # Batch API (4 facets)
    │   ├── files/                            # Files API (3 facets)
    │   ├── agent_sdk/                        # Agent SDK (1 facet)
    │   ├── claude_code/                      # Claude Code CLI (1 facet)
    │   └── computer_use/                     # Computer Use (1 facet)
    ├── ffl/                                  # one .ffl per area + composition.ffl + anthropic.ffl
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

## Cross-area composition

`anthropic.compose.DocumentQA` in `ffl/composition.ffl` is the
canonical RAG pattern: upload a document with `anthropic.files.UploadFile`,
then ask Claude about it via `anthropic.messages.CreateMessageWithFile`.
The same pattern applies to any cross-area workflow — keep
event-facet definitions in their per-area `.ffl` file and put the
multi-step glue in `composition.ffl`.

## Adding a new area

1. Pick a name that matches the Anthropic surface (e.g. `evals`, `cookbook`, `citations`).
2. Add `src/anthropic_handlers/tools/_lib/<area>.py` with pure-function simulators / SDK wrappers.
3. Add `src/anthropic_handlers/handlers/<area>/__init__.py` exporting `register_handlers(runner)` + a `_DISPATCH` map.
4. Add `src/anthropic_handlers/ffl/<area>.ffl` declaring the namespace + event facets.
5. Wire it in `src/anthropic_handlers/handlers/__init__.py::register_all_registry_handlers`.
6. Add the area entry to `src/anthropic_handlers/tools/_lib/areas.py` so `list-areas.sh` picks it up.
7. (Optional) Re-export key symbols from `handlers/shared/anthropic_utils.py`.

See [`agent-spec/integration-areas.agent-spec.yaml`](agent-spec/integration-areas.agent-spec.yaml)
for the contract a new area should satisfy.

## License

Apache 2.0 — see `LICENSE`.
