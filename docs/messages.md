# Messages API

**Namespace:** `anthropic.messages` ·
**FFL:** `src/anthropic_handlers/ffl/messages.ffl` ·
**Handlers:** `src/anthropic_handlers/handlers/messages/messages_handlers.py` ·
**Impl (`_lib`):** `src/anthropic_handlers/tools/_lib/messages.py` ·
**CLIs:** `tools/create-message*.sh`, `count-tokens.sh`, `stream-message.sh` ·
**Tests:** `tests/test_messages*.py`, `tests/live/test_messages_live.py`

## Overview

The **flagship area** — a wrapper over the Anthropic Messages API
(`client.messages.create` / `.count_tokens` / `.stream`). It is the foundational
capability every other messaging surface builds on and the largest area: **6 event
facets** covering text, token counting, tool use, vision, streaming, and Files-API RAG,
plus one convenience workflow (`ChatOnce`). Reference:
`https://github.com/anthropics/anthropic-sdk-python`.

## How it works

Each facet routes FFL → `handle(payload)` → `_DISPATCH` → a `_*_handler` in
`messages_handlers.py` → the matching `tools/_lib/messages.py` function → `get_client()`.
The handlers unpack the payload, log a redacted line via `_step_log` (`redact_prompt`),
and call the typed `_lib` function:

- **`create_message`** — one user turn (`messages=[{"role":"user","content":prompt}]`),
  optional `system`, returns collapsed text of the `text` blocks + usage + `stop_reason`.
- **`count_tokens`** — `client.messages.count_tokens`, returns `{input_tokens, model}`; no
  inference.
- **`create_message_with_tools`** — one tool-use round. Accepts a fresh `prompt` **or** a
  `messages` history, returns text, the `tool_use` blocks the model emitted, and the **full
  updated history** (`messages + [{"role":"assistant","content":blocks}]`). The handler
  JSON-serialises `tool_uses` → `tool_uses_json` and `messages` → `messages_json` for the
  next round. A turnkey Python loop, `run_tool_use_loop` (executes caller-supplied
  `tool_impls`, caps at `max_iterations`, raises on runaway), lives in `_lib` but is **not**
  an FFL facet — FFL has no `while`.
- **`create_message_with_images`** — vision. `image_urls` → URL blocks, `image_paths` →
  base64 blocks (`_image_block_from_path` reads the file, `mimetypes`-detects `image/*`, and
  errors on non-image types); text follows the images.
- **`create_message_stream`** — consumes the SSE stream server-side
  (`client.messages.stream` → `stream.text_stream` → `get_final_message`), emits each delta
  to the step log via `on_chunk` (so the dashboard shows progressive output), returns the
  assembled text plus `chunk_count`.
- **`create_message_with_file`** — Files-API RAG (see [composition.md](composition.md)):
  builds `{"type": file_type, "source":{"type":"file","file_id":…}}` blocks from a
  comma-separated `file_ids`, text follows.

## Fan-out

**Single-task per call — no fan-out.** No `foreach` in the FFL. The *internal* loops here
(`run_tool_use_loop` in `_lib`, the SSE stream) are sequential within one task, not fleet
fan-out. For parallel generation across many prompts use [batch.md](batch.md); the
`ChatOnce` workflow is two sequential steps (count → generate) in one run.

## Data & fields

Return schemas (all carry `input_tokens`/`output_tokens`/`cache_creation_input_tokens`/
`cache_read_input_tokens`):

- `MessageResult {text, model, stop_reason, …usage}`
- `TokenCount {input_tokens, model}`
- `ToolUseResult {text, tool_uses_json, messages_json, stop_reason, model, …usage}`
- `VisionResult {…, image_count, …}` · `StreamResult {…, chunk_count, …}` ·
  `FileMessageResult {…, file_count, …}`

JSON-bridge fields: **`tools_json`** / **`messages_json`** in (tool defs + history) and
**`tool_uses_json`** / **`messages_json`** out; **`file_ids`** / **`image_urls`** /
**`image_paths`** are comma-separated. Handler `_create_message_with_tools_handler`
validates `tools_json` decodes to a list and requires `prompt` *or* `messages_json`.

**Undeclared handler field — `temperature`.** Every `_*_handler` reads
`temperature = float(payload.get("temperature", 1.0))` and the `_lib` functions always send
`"temperature"` in the request kwargs — but **no `messages.ffl` facet declares a
`temperature` parameter**. So temperature is fixed at `1.0` from FFL and only reachable by
injecting the payload field another way. See Gotchas.

## External libraries / binaries

- **`anthropic`** (pip, required) — the only dependency; `base64` + `mimetypes` +
  `pathlib` (stdlib) for image encoding. No binary dependencies.

## Facets & workflows

| Facet / workflow | Kind | Effect / Cost | Purpose |
|---|---|---|---|
| `CreateMessage(prompt, system="", model="", max_tokens=1024, cache_system=false)` | event | external / **moderate** | single-turn text completion |
| `CountTokens(prompt, system="", model="")` | event | external / **cheap** | count input tokens, no inference |
| `CreateMessageWithTools(prompt="", tools_json, messages_json="", system="", model="", max_tokens=1024, cache_system=false)` | event | external / moderate | one tool-use round |
| `CreateMessageWithImages(prompt, image_urls="", image_paths="", …)` | event | external / moderate | vision (URL + local images) |
| `CreateMessageStream(prompt, system="", model="", max_tokens=1024, cache_system=false)` | event | external / moderate | streaming, deltas to step log |
| `CreateMessageWithFile(prompt, file_ids, file_type="document", …)` | event | external / moderate | Files-API RAG reference |
| `ChatOnce(prompt, system="", model="", max_tokens=1024)` | workflow | — | `CountTokens` then `CreateMessage` |

## Cache / output

No sidecar cache; no file output. **Prompt caching** is the real "cache": `cache_system=true`
marks the system prompt `cache_control=ephemeral` (`_system_param`); `cache_system=true`
with an empty `system` raises `ValueError`. Verify hits via
`cache_creation_input_tokens`/`cache_read_input_tokens` on the result. Streaming output is
mirrored to the step log, not written to disk.

## Gotchas & notes

- **`temperature` is hardcoded to `1.0` from FFL** (facets declare no such param) yet is
  always sent to `messages.create`. On Opus 4.7+/Sonnet 5/Fable 5 the API **rejects any
  `temperature` with a 400** — so pointing `model=` at one of those via FFL would fail on
  the sent `temperature=1.0`. The package default model `claude-sonnet-4-6` accepts it, so
  the default path works; a model override to a newer tier does not.
- **`create_message` requires a non-empty `prompt`** and `create_message_with_tools`
  requires non-empty `tools` (else `ValueError`) — use `CreateMessage` for text-only.
- **Vision media-type detection is by filename** — a mis-extensioned local image raises;
  pass a URL instead.
- **`run_tool_use_loop` raises on `max_iterations`** rather than returning a partial —
  runaway loops are loud, not silent (CLAUDE.md distributed-systems rule).

## Related specs

- [architecture.md](architecture.md) — shared client, JSON-bridge convention, dispatch.
- [files.md](files.md) + [composition.md](composition.md) — `CreateMessageWithFile` is the
  RAG half of `anthropic.compose.DocumentQA`.
- [batch.md](batch.md) — run the same Messages requests in bulk at ~50% cost.
