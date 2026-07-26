# Claude Code CLI

**Namespace:** `anthropic.code` ·
**FFL:** `src/anthropic_handlers/ffl/claude_code.ffl` ·
**Handlers:** `src/anthropic_handlers/handlers/claude_code/claude_code_handlers.py` ·
**Impl (`_lib`):** `src/anthropic_handlers/tools/_lib/claude_code.py` ·
**CLIs:** `tools/run-claude-code.sh` ·
**Tests:** `tests/test_claude_code.py`

## Overview

Orchestrates the **`claude` CLI** (Claude Code) as a subprocess so FFL workflows can drive the
same prompt across distributed runners — the "refactor 50 repos / audit 100 files" use case.
**1 event facet**, `RunClaudeCode`. Where [agent-sdk.md](agent-sdk.md) drives the *SDK* from
Python, this area drives the *CLI* via `subprocess`, letting you reuse prompts already crafted
for Claude Code's interactive session. Reference:
`https://github.com/anthropics/claude-code`.

## How it works

`RunClaudeCode` → `run_claude_code()` in `_lib`. It resolves the binary with
`shutil.which("claude")` (raises `RuntimeError` with install hints if absent), validates
`working_dir` exists, builds `claude -p <prompt>` and appends `--model`, `--allowed-tools`
(comma-joined), `--permission-mode`, and any `extra_args`, then runs
`subprocess.run(cmd, cwd=working_dir, capture_output=True, text=True, timeout=timeout_seconds,
check=False)`. Returns `{stdout, stderr, exit_code, success, command}`. `working_dir` becomes
the subprocess `cwd` — Claude Code's file-tool sandbox is rooted there.

## Fan-out

**Single-task per call, designed for fleet fan-out.** The area's whole reason to exist is
running one prompt against many directories in parallel — but the fan-out is orchestrated by a
**higher-level workflow / caller** issuing many `RunClaudeCode` tasks (one per `working_dir`),
not by a `foreach` in this FFL. Each task is one CLI invocation. Facetwork's per-runner polling
spreads the tasks across the fleet.

## Data & fields

`ClaudeCodeResult {stdout, stderr, exit_code, success}` (the `_lib` return also carries the
`command` list for audit). `allowed_tools` is a **comma-separated string** (`Read,Edit,Bash`);
`permission_mode` mirrors the CLI flag (`default`, `acceptEdits`, `bypassPermissions`, `plan`, …).
No JSON-bridge fields — output is captured process text.

## External libraries / binaries

- **`claude` binary** (NOT pip) — required on `PATH`; install via
  `npm install -g @anthropic-ai/claude-code`. This is the area's defining dependency.
- **stdlib only** on the Python side: `os`, `shutil`, `subprocess`. No `anthropic` SDK call
  (the CLI carries its own auth). `[claude_code]` extra declared but empty.

## Facets & workflows

| Facet | Kind | Effect / Cost | Purpose |
|---|---|---|---|
| `RunClaudeCode(prompt, working_dir="", allowed_tools="", model="", permission_mode="", timeout_seconds=600)` | event | external / **expensive** | run `claude -p` non-interactively, capture stdout/stderr/exit code |

`expensive` — a full agentic coding run in a subprocess.

## Cache / output

No sidecar cache; **file effects are on the host filesystem** (Claude Code edits files under
`working_dir` directly — outside Facetwork's cache/output model). The Facetwork result is the
captured `stdout`/`stderr`/`exit_code`. `timeout_seconds` bounds the run (raises
`subprocess.TimeoutExpired` when exceeded; `None` disables).

## Gotchas & notes

- **Binary must be on the runner's PATH.** Missing → `RuntimeError` with install hints. On a
  fleet, every runner that claims `anthropic.code` tasks needs `claude` installed.
- **`working_dir` is the sandbox root** — Claude Code writes files there directly; there is no
  Facetwork-managed cache boundary, so treat this facet as having real filesystem side effects.
- **Auth is the CLI's**, not `ANTHROPIC_API_KEY` via `get_client()` — this area never calls the
  SDK client.

## Related specs

- [agent-sdk.md](agent-sdk.md) — the Python-SDK sibling (same "autonomous coding" capability, no
  subprocess/binary).
- [architecture.md](architecture.md) — dispatch + registration.
