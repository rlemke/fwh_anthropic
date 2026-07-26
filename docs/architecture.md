# Multi-area Architecture & Shared Infrastructure

**Namespace(s):** `anthropic` (catalog marker) ·
**FFL:** `src/anthropic_handlers/ffl/anthropic.ffl` ·
**Entry point:** `src/anthropic_handlers/__init__.py` (`domain`) ·
**Shared client:** `src/anthropic_handlers/tools/_lib/client.py` ·
**Shim:** `src/anthropic_handlers/handlers/shared/anthropic_utils.py` ·
**Aggregator:** `src/anthropic_handlers/handlers/__init__.py` ·
**Catalog:** `src/anthropic_handlers/catalog.yaml` + `catalog.py`

## Overview

`fwh_anthropic` is unlike most `fwh_*` packages: it covers one **vendor surface**
(the Anthropic / Claude APIs and CLIs) split into many independent **integration
areas**, not one problem domain. Six areas are wired today — `messages`, `batch`,
`files`, `agent_sdk`, `code`, `computer` — for **16 event facets total**, plus one
cross-area composition workflow (`anthropic.compose.DocumentQA`) and two per-area
workflows (`anthropic.messages.ChatOnce`, `DocumentQA`). Areas are orthogonal:
adding one never touches another's code.

This spec is the cross-cutting entry point — the shared client/auth layer, the
`tools/_lib ↔ handlers ↔ ffl` pattern every area repeats, the JSON-bridge field
convention that connects areas, the registration/discovery machinery, and the
test-gating contract. Read it before the per-area specs.

## How it works

**One shared client, per-area wrappers.** `tools/_lib/client.py` owns auth and the
cached SDK client; each `tools/_lib/<area>.py` imports `get_client` / `DEFAULT_MODEL`
from it rather than `import anthropic` directly (CLAUDE.md code-review rule). The
call path for every facet is uniform:

```
FFL event facet (ffl/<area>.ffl)
  → RegistryRunner claims the task, calls handle(payload)
  → handlers/<area>/<area>_handlers.py : _DISPATCH[payload["_facet_name"]]
  → handlers/shared/anthropic_utils.py  (re-export shim, fully-qualified imports)
  → tools/_lib/<area>.py                (pure SDK wrapper, typed kwargs)
  → tools/_lib/client.py : get_client() (cached anthropic.Anthropic())
```

Every `_lib` function returns **plain dicts** (never SDK Pydantic models) so results
round-trip through FFL/Mongo without custom serialisation.

**Registration.** Each area's `*_handlers.py` defines a `_DISPATCH` map of
`"<namespace>.<Facet>" → callable`, a `handle(payload)` entrypoint that dispatches on
`payload["_facet_name"]`, and two registrars: `register_handlers(runner)` (RegistryRunner
— `runner.register_handler(facet_name, module_uri="file://…", entrypoint="handle")`) and
`register_<area>_handlers(poller)` (legacy AgentPoller). `handlers/__init__.py`'s
`register_all_registry_handlers(runner)` calls all six area registrars, so a single
runner registers every wired facet.

**Discovery.** `pyproject.toml` declares the entry point under **`facetwork.domains`**
(`anthropic = "anthropic_handlers:domain"`), and `__init__.py` exports
`domain = DomainPackage(name="anthropic", ffl_dir=…/ffl, register_handlers=register_all_registry_handlers)`.
(Note: the repo README/CLAUDE.md prose still describe this as a `facetwork.examples`
`ExamplePackage` — the *code* uses `facetwork.domains` / `DomainPackage`; the code is
authoritative.) Package data ships the FFL under `ffl/*.ffl` + `handlers/**/ffl/*.ffl`
plus `catalog.yaml`.

## Fan-out

Cross-cutting — no fan-out of its own. FFL here declares no `foreach`; each facet is a
single distributed task. Fleet parallelism comes from many independent tasks racing on
the atomic claim (per Facetwork's per-runner polling model), not from a fan-out facet.
See [batch.md](batch.md) for server-side batching and [claude-code.md](claude-code.md)
for the intended per-directory fan-out.

## Data & fields

FFL has no native nested-list / map type, so cross-area flows carry structured payloads
through two conventions (CLAUDE.md "Cross-area conventions"):

| Convention | Fields | Decodes to |
|---|---|---|
| **JSON-bridge string** | `tools_json`, `messages_json`, `tool_uses_json`, `requests_json`, `results_json`, `files_json`, `trace_json` | list-of-dict, decoded at the handler boundary (`json.loads` / `json.dumps`) |
| **Comma-separated string** | `file_ids`, `image_urls`, `image_paths` | list of scalars, split + stripped in the handler |

Rule of thumb from CLAUDE.md: scalars and flat structs go on the schema directly;
anything list-of-dict gets a `*_json` field. The top-level `anthropic.ffl` declares only
one schema, `AnthropicCatalog {version, areas}`, a versioning marker — no facets.

**Catalog manifest.** `catalog.yaml` (loaded by `catalog.py::load_manifest` / `workflows()`
/ `facets()`) is a machine-readable index mirroring the platform's `fw_catalog_match`
(workflow-level, by intent `summary`+`tags`) and `fw_capabilities` (facet-level, with
`effect`/`cost` taken verbatim from the FFL mixins). `tests/test_catalog_manifest.py`
keeps it in sync with the FFL.

## External libraries / binaries

- **`anthropic>=0.40`** (pip, required) — the SDK; lazy-imported inside `get_client()` so
  the package imports without it during scaffolding, then raises a clear `RuntimeError`.
- **`PyYAML>=6.0`** (pip, required) — parses `catalog.yaml`.
- **`facetwork>=0.31.0`** (pip, required) — `DomainPackage`, runner, FFL runtime.
- **Optional extras** (per area, lazy-imported): `claude-agent-sdk>=0.1` (`[agent_sdk]`),
  `mcp>=0.9` (`[mcp]`, reserved for a future area). `batch` / `files` / `claude_code` /
  `computer_use` extras are declared but empty.
- **`claude` binary** (not pip) — required only by [claude-code.md](claude-code.md).

## Facets & workflows

No event facets of its own. The area roster (namespace → area, from CLAUDE.md + the FFL):

| Area | Namespace | Facets | Spec |
|---|---|---|---|
| messages | `anthropic.messages` | 6 + `ChatOnce` workflow | [messages.md](messages.md) |
| batch | `anthropic.batch` | 4 | [batch.md](batch.md) |
| files | `anthropic.files` | 3 | [files.md](files.md) |
| agent_sdk | `anthropic.agent` | 1 | [agent-sdk.md](agent-sdk.md) |
| claude_code | `anthropic.code` | 1 | [claude-code.md](claude-code.md) |
| computer_use | `anthropic.computer` | 1 | [computer-use.md](computer-use.md) |
| compose | `anthropic.compose` | `DocumentQA` workflow | [composition.md](composition.md) |

## Cache / output

**No `$FW_CACHE_ROOT` sidecar cache; no GeoJSON / HTML / tile / PMTiles output** — this
package produces API responses, not artifacts on disk. Two real notions of "cache/output":

- **Anthropic prompt caching** — every `create_message*` / `stream_message` call takes
  `cache_system` (default `false`); when true it sends the system prompt as a
  `{"type":"text", …, "cache_control":{"type":"ephemeral"}}` block (`_system_param`) and
  surfaces `cache_creation_input_tokens` / `cache_read_input_tokens` so callers verify hits.
- **Anthropic-side Files storage** — [files.md](files.md) uploads persist server-side until
  deleted; referenced by `file_id`, not stored locally.

Step results are plain dicts persisted in the run's Mongo state. Token usage is on every
result schema.

## Gotchas & notes

- **Auth is mandatory.** `get_client()` raises `RuntimeError` if `ANTHROPIC_API_KEY` is
  unset (and again if the `anthropic` SDK isn't installed). It is `@lru_cache(maxsize=1)`,
  so the key must be set **before** the first call in a process.
- **Default model** is `ANTHROPIC_DEFAULT_MODEL` or, absent that, the hardcoded
  `claude-sonnet-4-6` (`client.py:23`). Passing `model=""` in FFL means "use the default".
- **Import discipline.** The shim uses fully-qualified `anthropic_handlers.tools._lib.<area>`
  imports so the package coexists with sibling `fwh_*` packages on `sys.modules` (the bare
  `_lib` collision that bit osm/noaa-weather).
- **Logging redaction.** `redact_prompt()` truncates prompt previews; never log the API key
  or full prompt text at INFO+ (CLAUDE.md).
- **Doc-vs-code drift.** README/CLAUDE.md prose says `facetwork.examples` / `ExamplePackage`
  and "zero handlers wired"; the current code wires all 16 facets under `facetwork.domains` /
  `DomainPackage`. Trust the code.

## Related specs

- [messages.md](messages.md) — the flagship area; every other messaging facet builds on it.
- [composition.md](composition.md) — how the JSON-bridge convention connects areas.
- [batch.md](batch.md), [files.md](files.md), [agent-sdk.md](agent-sdk.md),
  [claude-code.md](claude-code.md), [computer-use.md](computer-use.md) — the individual areas.
