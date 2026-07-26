<!-- SPEC TEMPLATE — every docs/<feature>.md follows this shape so the set reads
consistently. Delete this comment in real specs. Keep sections in this order;
omit a section only if it genuinely does not apply (say so in one line rather
than dropping the heading silently). Ground every claim in the actual FFL
docstrings / handler code / tools/_lib — do not invent behaviour. This is a
vendor-surface wrapper package (Anthropic APIs), not a geo/tag domain, so the
"Data & fields" heading replaces the OSM template's "Filtering & attributes". -->

# <Feature Name>

**Namespace(s):** `anthropic.<ns>` · **FFL:** `src/anthropic_handlers/ffl/<area>.ffl` ·
**Handlers:** `src/anthropic_handlers/handlers/<area>/<area>_handlers.py` ·
**Impl (`_lib`):** `src/anthropic_handlers/tools/_lib/<area>.py` ·
**CLIs:** `src/anthropic_handlers/tools/<verb>-<noun>.py` / `.sh` (if any)

## Overview
One or two paragraphs: which Anthropic surface this area wraps, the request it
answers, and where it sits in the package (per-area event facets vs. cross-area
composition). Link the upstream reference the FFL docstring cites.

## How it works
The data flow, step by step: FFL event facet → RegistryRunner dispatch
(`handle(payload)` → `_DISPATCH`) → the `handlers/<area>` payload adapter →
`handlers/shared/anthropic_utils` shim → `tools/_lib/<area>` function → the
shared `get_client()` Anthropic SDK client. Name the concrete SDK call
(`client.messages.create`, `client.messages.batches.*`, `client.beta.files.*`,
subprocess, async `claude_agent_sdk.query`, …) and the shape of the returned
dict (plain dicts, never SDK Pydantic models, so results round-trip through
FFL/Mongo).

## Fan-out
Does it fan out across the fleet? FFL here has no `foreach`, so most areas are
**single-task per call**. Say so, and note where parallelism actually lives —
server-side batching (`anthropic.batch`), the intended per-directory fan-out of
`anthropic.code`, or a caller-driven loop. Distinguish an *internal* multi-round
loop (tool use, computer use, agent turns) from fleet fan-out.

## Data & fields
The schema fields the facet returns and the JSON-bridge convention it uses.
FFL has no native nested list/map type, so list-of-dict payloads ride
**`*_json` string fields** (`tools_json`, `messages_json`, `tool_uses_json`,
`requests_json`, `results_json`, `files_json`, `trace_json`) and id lists ride
**comma-separated strings** (`file_ids`, `image_urls`, `image_paths`). Name the
real schema (`MessageResult`, `BatchMetadata`, `FileMetadata`, …) and its fields;
call out any handler-side payload field that is NOT declared in the FFL facet.

## External libraries / binaries
Every non-stdlib dependency this area relies on and what for — the `anthropic`
SDK (required), optional extras (`claude-agent-sdk` under `[agent_sdk]`, `mcp`
under `[mcp]`), a **binary** dependency (`claude` on PATH for `anthropic.code`),
`PyYAML` for the catalog. Distinguish a binary dependency from a pip one, and
required from optional/lazy-imported.

## Facets & workflows
The event facets and workflows, with signatures + a one-line purpose from the
FFL docstrings. Mark event facets (need a handler) vs. pure workflows, and note
the `with Effect(kind="external") with Cost(tier=…)` mixins each carries
(`cheap` = no-inference accounting/metadata; `moderate` = one inference message;
`expensive` = long agentic loop / whole batch run).

## Cache / output
This package has **no `$FW_CACHE_ROOT` sidecar cache and no GeoJSON/HTML/tile
output** — say so. What it does have: Anthropic **prompt caching** via the
`cache_system` kwarg (`cache_control={"type":"ephemeral"}`), surfaced through
`cache_creation_input_tokens` / `cache_read_input_tokens`; Anthropic-side
**Files API** storage (`anthropic.files`); token-usage accounting on every
result. Step results are plain dicts persisted in the run's Mongo state.

## Gotchas & notes
Known pitfalls: auth (`ANTHROPIC_API_KEY` required, `get_client()` raises
without it), the default model (`ANTHROPIC_DEFAULT_MODEL`, else
`claude-sonnet-4-6`), simulator-vs-real modes, beta-header pinning, optional-dep
lazy imports, `*_json` decode boundaries, redaction of prompts/keys in logs.

## Related specs
Links to the specs this area composes with or depends on (start from
[architecture.md](architecture.md), the shared-infrastructure spec).
