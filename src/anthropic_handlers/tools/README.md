# anthropic tools

CLI utilities for the anthropic integration areas. The structure
matches every other Facetwork `fwh_*` package:

- `_lib/<area>.py` — pure-function wrappers over the Anthropic SDK
  (the single source of truth for both CLIs and FFL handlers)
- `_lib/client.py` — shared `Anthropic()` client + retry / rate-limit /
  redaction helpers
- `_lib/areas.py` — static metadata about every area this package covers
- `<verb>-<noun>.sh` — one CLI per facet (added per area)
- `list-areas.sh` — inspect which areas are wired and how many facets they expose

## Currently shipped CLIs

| CLI | Purpose |
|-----|---------|
| `list-areas.sh` | Print the area roster + per-area facet count |

Per-facet CLIs (e.g. `create-message.sh`, `submit-batch.sh`,
`upload-file.sh`) are added as each area gets wired up.

## Conventions (when adding per-facet CLIs)

- Help: `<cli>.sh --help` — every CLI uses argparse.
- Stderr: one-line human summary mirroring the FFL step log.
- Stdout: pretty-printed JSON dict (the same shape the FFL handler emits).
- Exit code: 0 on success, non-zero on argparse error or API failure.
- Imports: use `from anthropic_handlers.tools._lib.<area> import …`
  (fully-qualified) so this package coexists cleanly with sibling
  Facetwork example packages on `sys.modules`.
- Redaction: never log `ANTHROPIC_API_KEY` or full prompt text at
  INFO+. Use `client.redact_prompt` for any preview.

## Example: see what's wired

```bash
src/anthropic_handlers/tools/list-areas.sh
# fwh_anthropic — 6 areas, 0 facets wired
#
#   AREA           NAMESPACE              WIRED   SURFACE
#   ────────────── ────────────────────── ──────  ────────────────────────────────────────────────────────────
#   messages       anthropic.messages     0       Messages API (prompt caching, vision, streaming, tool use)
#   batch          anthropic.batch        0       Message Batches API
#   files          anthropic.files        0       Files API + citations
#   agent_sdk      anthropic.agent        0       Claude Agent SDK
#   claude_code    anthropic.code         0       Claude Code CLI orchestration
#   computer_use   anthropic.computer     0       Computer Use beta
```

## Adding a per-facet CLI

1. Pick the area its surface belongs to (see `_lib/areas.py`).
2. Copy an existing CLI from a sibling repo (e.g.
   `fwh_jenkins/src/jenkins_pipeline/tools/maven_build.py`) as a
   template.
3. Import from `anthropic_handlers.tools._lib.<area>` — never call the
   Anthropic SDK directly from a CLI (rate-limit + retry policy lives
   in `_lib/client.py`).
4. Add a matching `.sh` wrapper and `chmod +x` both files.
5. If the new function corresponds to an FFL facet, wire it through
   the area's `<area>_handlers.py::_DISPATCH`.
