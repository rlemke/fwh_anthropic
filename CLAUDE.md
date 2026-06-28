# CLAUDE.md — fwh_anthropic

This repository is a **standalone Facetwork example package** that
hosts FFL workflows + handlers for every public Anthropic surface
(Messages API, Batch API, Files API, Agent SDK, Claude Code, Computer
Use, MCP, …). The Facetwork platform (workflow compiler + runtime)
lives at `/Users/ralph_lemke/facetwork`; this repo only contains the
Anthropic-specific FFL, handlers, and CLI tools. The two are wired
together via the `facetwork.examples` entry point in `pyproject.toml`.

## Multi-area design

Unlike most `fwh_*` packages (`fwh_osm`, `fwh_noaa_weather`, …) which
each cover one *problem domain*, `fwh_anthropic` covers one *vendor
surface* split into many *integration areas*. Areas are independent —
adding a new area never touches another area's code. The Anthropic
SDK + auth + rate-limit infrastructure is shared in
`tools/_lib/client.py`; per-area code lives in `tools/_lib/<area>.py`
and `handlers/<area>/`.

```
                ┌────────────────────────────────────────────────┐
                │  tools/_lib/client.py (auth / retry / rate)    │
                └────────────────────────────────────────────────┘
                                │
        ┌───────────────┬───────┴──────┬───────────────┐
        ▼               ▼              ▼               ▼
   messages/        batch/          files/        agent_sdk/   …
   (handlers +      (handlers +     (handlers +   (handlers +
    _lib/msg.py +    _lib/batch.py + _lib/files.py +_lib/agent.py +
    ffl/msg.ffl)     ffl/batch.ffl)  ffl/files.ffl) ffl/agent.ffl)
```

## Quick orientation

```
fwh_anthropic/
├── pyproject.toml                       # declares the facetwork.examples entry point
├── src/anthropic_handlers/__init__.py   # exports `example: ExamplePackage`
├── src/anthropic_handlers/handlers/     # 6+ area subpackages + shared/ shim
├── src/anthropic_handlers/ffl/          # one .ffl per area + top-level catalog
├── src/anthropic_handlers/tools/        # CLI utilities + _lib/ (per-area + shared client)
├── tests/                               # area tests (lazy-imported per area)
└── agent-spec/                          # cross-cutting design specs + integration-areas spec
```

## Common operations

```bash
# Register this package with Facetwork's runner
pip install -e .
# Optionals — install per area:
pip install -e ".[agent_sdk,mcp]"

# From a Facetwork checkout:
scripts/seed-examples --include anthropic
scripts/start-runner --example anthropic -- --log-format text

# Inspect wiring status
src/anthropic_handlers/tools/list-areas.sh

# Mocked tests (default; no API calls)
pytest

# Live tests against the real Anthropic API (opt-in)
ANTHROPIC_API_KEY=sk-... pytest tests/live -m live --run-live
```

## Test gating

The unit suite mocks the Anthropic SDK at the `get_client()` boundary
— no network, no key needed. Live tests under `tests/live/` are
double-gated:

- `pyproject.toml` sets `addopts = -m 'not live'`, so default runs
  skip them.
- `tests/conftest.py` adds a `--run-live` flag; even when filtering
  to `-m live`, the tests skip unless `--run-live` is passed AND
  `ANTHROPIC_API_KEY` is set.

Don't remove either gate. The second one catches the easy mistake of
running `-m live` without intending to spend tokens.

## Tools / handlers / _lib pattern (per area)

Every area follows the canonical Facetwork pattern (see
`agent-spec/tools-pattern.agent-spec.yaml`):

- `tools/_lib/<area>.py` — pure-function wrappers around the Anthropic
  SDK. Imports `tools/_lib/client.py` for the shared `Anthropic()`
  client instance.
- `tools/<verb>-<noun>.py` + `.sh` — one CLI per facet.
- `handlers/<area>/<area>_handlers.py` — payload-dict adapters that
  call `tools/_lib/<area>.py` via `handlers/shared/anthropic_utils.py`.
- `ffl/<area>.ffl` — namespace declaration + event facets.

The shim uses **fully-qualified** imports
(`from anthropic_handlers.tools._lib.<area> import …`) so this package
coexists cleanly with sibling Facetwork example packages on
`sys.modules` (the bare-`_lib` collision pattern that bit
osm/noaa-weather initially).

## Area roster

All six initial areas are wired today — 16 facets total + one
cross-area composition workflow. Run `tools/list-areas.sh` for the
live count.

| Area | FFL namespace | What it wraps | Facets |
|------|---------------|---------------|--------|
| `messages` | `anthropic.messages` | Messages API (prompt caching, vision, streaming, tool use, file references) | 6 |
| `batch` | `anthropic.batch` | Message Batches API (submit/status/results + `RunBatch` driver) | 4 |
| `files` | `anthropic.files` | Files API (upload/list/delete) | 3 |
| `agent_sdk` | `anthropic.agent` | Claude Agent SDK | 1 |
| `claude_code` | `anthropic.code` | Claude Code CLI orchestration | 1 |
| `computer_use` | `anthropic.computer` | Computer Use beta (simulator-backed by default) | 1 |

Cross-area composition lives in `ffl/composition.ffl` under the
`anthropic.compose` namespace:

- `DocumentQA` — `Files.UploadFile` → `Messages.CreateMessageWithFile`

Future areas (to add as new directories):
`mcp`, `evals`, `cookbook`, `citations` (if split from messages),
`fine_tuning`, `prompt_evals`.

## Adding a new area

1. Decide the FFL namespace (`anthropic.<area>`) and the surface it covers.
2. Create `src/anthropic_handlers/tools/_lib/<area>.py` with thin wrappers
   over the Anthropic SDK. Import the shared client from `.client`.
3. Create `src/anthropic_handlers/handlers/<area>/<area>_handlers.py`
   with `_DISPATCH` + `handle(payload)` + `register_handlers(runner)`.
4. Re-export key symbols from
   `src/anthropic_handlers/handlers/shared/anthropic_utils.py`.
5. Add per-facet CLI wrappers under `src/anthropic_handlers/tools/`.
6. Drop the FFL declaration into `src/anthropic_handlers/ffl/<area>.ffl`.
7. Wire `register_handlers` into
   `src/anthropic_handlers/handlers/__init__.py::register_all_registry_handlers`.

See `agent-spec/integration-areas.agent-spec.yaml` for the contract a
new area should satisfy (naming, import discipline, optional deps,
tests).

## Cross-area conventions

FFL has no native support for arbitrary nested lists / maps, so cross-area
flows carry list-of-dict payloads through **JSON-bridge fields** (string
parameters that decode at the handler boundary). The conventions are:

| Field | Where | Decodes to |
|-------|-------|-----------|
| `tools_json` | `Messages.CreateMessageWithTools` | list of tool definitions |
| `messages_json` | `Messages.CreateMessageWithTools` | conversation history (role/content list) |
| `tool_uses_json` | `ToolUseResult` | list of tool_use blocks |
| `requests_json` | `Batch.SubmitBatch` / `RunBatch` | list of MessageBatchRequest |
| `results_json` | `BatchResults` / `RunBatchResult` | list of per-request results |
| `files_json` | `Files.ListFiles` | list of FileMetadata |
| `trace_json` | `ComputerUse.RunComputerUseSession` | list of per-action records |
| `file_ids` (comma-separated) | `Messages.CreateMessageWithFile` | list of file IDs |

When adding a new cross-area facet, follow the same rule: scalars and
flat structs go on the schema directly; anything list-of-dict gets a
`*_json` field.

## Code review checklist

- Keep `_lib/<area>.py` free of `facetwork.runtime` so CLIs stay
  runnable standalone.
- Always go through `tools/_lib/client.py` for SDK calls so retry +
  rate-limit policy stays consistent across areas.
- Optional dependencies for an area (`claude-agent-sdk`, `mcp`, …)
  must be listed under `[project.optional-dependencies]` in
  `pyproject.toml` and lazy-imported inside the area's `_lib/<area>.py`
  so importing the package without that extra installed still works.
- Mixin support: bake `with Retry(...) with PromptCache(...)` into FFL
  handlers where the SDK supports it, so users don't open-code retry
  logic.
- Never log the API key or full prompt text at INFO+. Use redaction
  helpers from `tools/_lib/client.py`.
- For convenience drivers that wrap polling loops (e.g.
  `batch.run_batch`), accept a `sleep_fn` parameter so tests can drive
  the loop deterministically without `time.sleep` actually firing.

## Domain research before implementation

When wiring a new Anthropic surface:

- Read the surface's official docs first (`api.anthropic.com/docs`,
  the Anthropic Python SDK README, or the area's README under
  `github.com/anthropics/<repo>`).
- Note rate limits, cost shape, idempotency, and resumability. These
  drive which Facetwork mixins the FFL surface should bake in.
- For long-running surfaces (Batch, Computer Use), set
  `FW_TASK_EXECUTION_TIMEOUT_MS` appropriately in the package's
  `runner_env` (see `osm-geocoder` for the precedent).
