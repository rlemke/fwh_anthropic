# Computer Use (beta, simulator-backed)

**Namespace:** `anthropic.computer` ·
**FFL:** `src/anthropic_handlers/ffl/computer_use.ffl` ·
**Handlers:** `src/anthropic_handlers/handlers/computer_use/computer_use_handlers.py` ·
**Impl (`_lib`):** `src/anthropic_handlers/tools/_lib/computer_use.py` ·
**CLIs:** `tools/run-computer-use.sh` ·
**Tests:** `tests/test_computer_use.py`

## Overview

Wraps Anthropic's **Computer Use beta** — Claude drives a virtual desktop via a
screen-control + bash + text-editor tool-use loop. **1 event facet**,
`RunComputerUseSession`. Critically, the FFL facet runs in **SIMULATOR MODE**: the tool
implementations are deterministic stubs that return placeholder results so the loop terminates
and prompt engineering is reproducible — **they do not control a real screen**. Real screen
control requires driving `_lib.run_computer_use` directly with your own `tool_impls`
(xdotool / pyautogui / Docker-VM controller). References:
`https://docs.anthropic.com/en/docs/build-with-claude/computer-use`,
`https://github.com/anthropics/anthropic-quickstarts`.

## How it works

`RunComputerUseSession` → `run_computer_use()` in `_lib`. It builds the canonical tool
definitions (`default_tools`: `computer` + optional `bash` + `text_editor`, sized to the
display dims), and — because the FFL handler passes no `tool_impls` — falls back to
`simulator_tool_impls()` (stub `computer`/`bash`/`str_replace_editor` returning
`{"simulated": True, …}`). The loop calls `_invoke_messages` (tries
`client.beta.messages.create(betas=[…])`, falls back to `extra_headers={"anthropic-beta": …}`),
collects `tool_use` blocks, runs each stub, feeds `tool_result` blocks back, and repeats until
`stop_reason != "tool_use"` or `max_iterations` (raises `RuntimeError` on the cap). Tool
versions and the beta header are pinned constants (`DEFAULT_TOOL_VERSIONS`:
`computer_20241022` / `bash_20241022` / `text_editor_20241022`; `DEFAULT_BETA_HEADER =
"computer-use-2024-10-22"`).

## Fan-out

**Single-task per call; internally multi-iteration.** The screen-control loop runs up to
`max_iterations` model rounds within one Facetwork task — an inference loop, not fleet fan-out.

## Data & fields

`ComputerUseResult {text, iterations, stop_reason, trace_json, input_tokens, output_tokens,
mode}`. **`trace_json`** carries the per-action trace (JSON-serialised). `mode` distinguishes
simulator from real. Display sizing (`display_width_px`, `display_height_px`, `display_number`)
is passed into the `computer` tool definition so the model sizes coordinates correctly;
`enable_bash` / `enable_text_editor` toggle the auxiliary tools.

## External libraries / binaries

- **`anthropic`** (pip, required) — the beta Messages endpoint. No binary dependencies in
  simulator mode. Real screen control needs a caller-supplied driver (xdotool / pyautogui /
  Docker VM) — not a dependency of this package. `[computer_use]` extra declared but empty.

## Facets & workflows

| Facet | Kind | Effect / Cost | Purpose |
|---|---|---|---|
| `RunComputerUseSession(task, system="", model="", max_iterations=20, display_width_px=1024, display_height_px=768, display_number=1, enable_bash=true, enable_text_editor=true)` | event | external / **expensive** | run a simulator-mode Computer Use session; the model loop is live, tool impls are stubs |

`expensive` — an agentic screen-control loop over many inference iterations.

## Cache / output

No sidecar cache, no file output. In simulator mode the tool results are placeholders
(`<simulated>`), so nothing touches a real screen or disk. Token usage + `trace_json` are the
result.

## Gotchas & notes

- **Simulator by default — this facet cannot control a real machine.** For real control, call
  `_lib.run_computer_use(tool_impls=…)` from Python with your own implementations; the FFL
  facet is for pipeline dry-runs and prompt engineering.
- **Pinned beta tool versions** (`*_20241022`) — `_invoke_messages` is the single place to
  change if your SDK uses a different beta-header convention or newer tool versions; override
  tool versions via `default_tools(versions=…)`.
- **`_invoke_messages` is defensive** — tries `betas=[…]`, falls back to
  `extra_headers={"anthropic-beta": …}` for older SDKs.

## Related specs

- [messages.md](messages.md) — the same tool-use mechanics (`tool_use` blocks, `tool_result`
  feedback) as `CreateMessageWithTools`, here specialised to computer tools.
- [architecture.md](architecture.md) — dispatch, `trace_json`, beta-header handling.
