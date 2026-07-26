# Claude Agent SDK

**Namespace:** `anthropic.agent` ·
**FFL:** `src/anthropic_handlers/ffl/agent_sdk.ffl` ·
**Handlers:** `src/anthropic_handlers/handlers/agent_sdk/agent_sdk_handlers.py` ·
**Impl (`_lib`):** `src/anthropic_handlers/tools/_lib/agent_sdk.py` ·
**CLIs:** `tools/run-agent.sh` ·
**Tests:** `tests/test_agent_sdk.py`

## Overview

Wraps the **Claude Agent SDK** (`claude-agent-sdk-python`) — Claude Code's autonomous-agent
runtime (planning, tool use, memory, permission gating) as a Python-callable API. **1 event
facet**, `RunAgent`, covering the "single prompt, run to completion, return the final result"
pattern; multi-turn interactive sessions (`ClaudeSDKClient`) are noted in the FFL as future
facets. Reference: `https://github.com/anthropics/claude-agent-sdk-python`.

## How it works

`RunAgent` → `run_agent()` in `_lib`. The SDK is **async** and an **optional dependency**, so
it is lazy-imported via `_import_sdk()` (raises a clear `RuntimeError` with install hints if
absent). `run_agent` builds `claude_agent_sdk.ClaudeAgentOptions(model, system_prompt,
allowed_tools, permission_mode, max_turns)` and runs the async driver with `asyncio.run(_drive(...))`.

`_drive` consumes the async iterator from `sdk.query(prompt, options)`: each message is
recorded to the trace (`_message_to_trace_entry`), `assistant`/`AssistantMessage` messages bump
the turn count and capture the latest text, and the terminal `result`/`ResultMessage` supplies
`stop_reason` + final text + token usage. The wrapper is written defensively (type-name
variants handled) because the SDK API shifts between versions. `allowed_tools` is normalised
(`_normalise_allowed_tools` drops empties; empty ⇒ no restriction).

## Fan-out

**Single-task per call, but internally multi-turn.** `RunAgent` runs a full agent loop (up to
`max_turns`) inside one Facetwork task — that is an *agent* loop, not fleet fan-out. Fan-out
across many prompts/repos is a caller concern (or use many independent tasks).

## Data & fields

`AgentResult {text, turns, stop_reason, trace_json, input_tokens, output_tokens,
cache_creation_input_tokens, cache_read_input_tokens}`. **`trace_json`** carries the per-message
trace (JSON-serialised list of dicts). `allowed_tools` is passed as a **comma-separated string**
in FFL (e.g. `Read,Write,Edit,Bash,Glob,Grep` plus any `@tool`-registered custom tools);
`permission_mode` mirrors the SDK enum verbatim (`default`, `acceptEdits`, `bypassPermissions`,
`plan`).

## External libraries / binaries

- **`claude-agent-sdk>=0.1`** (pip, **optional** — `[agent_sdk]` extra) — lazy-imported;
  `RunAgent` raises `RuntimeError` if it isn't installed. `asyncio` (stdlib) drives the async
  SDK from the sync facet.
- **`anthropic`** — only for `DEFAULT_MODEL`; this area does not call the SDK client directly.
- No binary dependencies (contrast [claude-code.md](claude-code.md), which shells out).

## Facets & workflows

| Facet | Kind | Effect / Cost | Purpose |
|---|---|---|---|
| `RunAgent(prompt, system="", model="", max_turns=10, allowed_tools="", permission_mode="default")` | event | external / **expensive** | run the Agent SDK to completion, return final text + trace + usage |

`expensive` — a multi-turn autonomous run (planning + tool use + memory) over many inference
calls.

## Cache / output

No sidecar cache, no file output of its own (any files the agent writes are on the host's
filesystem via the agent's own tools, outside Facetwork's cache model). Token usage +
`trace_json` are the result; cache-token fields are surfaced if the SDK reports them.

## Gotchas & notes

- **Optional dep.** Install `pip install -e '.[agent_sdk]'` (or `pip install 'claude-agent-sdk>=0.1'`)
  before running; the package still imports without it (lazy import).
- **Defensive to SDK drift.** Message-type discrimination handles both `type`-string and
  class-name variants; if a future SDK reshapes `query`/`ResultMessage`, the change is localised
  to `_drive`.
- **`max_turns < 1` raises `ValueError`**; `permission_mode` is passed through verbatim so newer
  SDK modes aren't locked out.

## Related specs

- [claude-code.md](claude-code.md) — the sibling area that drives the `claude` **CLI** via
  subprocess instead of the SDK.
- [architecture.md](architecture.md) — optional-dep policy, dispatch, `trace_json`.
