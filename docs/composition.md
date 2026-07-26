# Cross-area Composition (DocumentQA)

**Namespace:** `anthropic.compose` ·
**FFL:** `src/anthropic_handlers/ffl/composition.ffl` ·
**Handlers:** none (composition of existing facets — no new event facet) ·
**Tests:** `tests/test_composition.py`, `tests/live/test_composition_live.py`

## Overview

The composition area is where **cross-area workflows** live — chains that wire facets from
multiple per-area namespaces to show end-to-end use of the package and to exercise the
JSON-bridge fields that connect areas. It ships **one workflow**, `DocumentQA`, the canonical
RAG pattern:

```
anthropic.files.UploadFile  →  anthropic.messages.CreateMessageWithFile
```

Upload a local document to the Files API, then ask Claude one question about it via a
Files-referenced Messages call. This file is **composition only — it declares no new event
facets** (its FFL docstring says so).

## How it works

`DocumentQA(path, question, system="", model="", max_tokens=1024)` is an `andThen` workflow with
two steps:

1. `uploaded = anthropic.files.UploadFile(path = $.path)` — see [files.md](files.md).
2. `answer = anthropic.messages.CreateMessageWithFile(prompt = $.question,
   file_ids = uploaded.result.id, file_type = "document", …)` — see [messages.md](messages.md).

It then `yield`s `DocumentQA(file_id, text, input_tokens, output_tokens, stop_reason)`. The
`file_id` is reusable — for multi-question loops, run the workflow once per question, or hold the
upload outside and call `CreateMessageWithFile` directly. Both referenced facets are real
event facets served by their areas; the workflow adds only the glue.

## Fan-out

**Sequential, single-run — no fan-out.** Two ordered steps in one workflow execution
(`UploadFile` must finish before `CreateMessageWithFile`, which reads `uploaded.result.id`).
Parallelism across many documents/questions is a caller concern.

## Data & fields

`DocumentQAResult {file_id, text, input_tokens, output_tokens, stop_reason}`. The cross-area
"seam" is the single scalar `file_id` threaded from `UploadFile`'s `result.id` into
`CreateMessageWithFile`'s `file_ids` (a **comma-separated** field — here a single id). This is
the smallest case of the package's cross-area convention: scalars/flat structs ride the schema
directly; list-of-dict payloads ride `*_json` bridge fields (see
[architecture.md](architecture.md)).

## External libraries / binaries

- **`anthropic`** (pip, required) — via the two composed facets. No dependencies of its own.

## Facets & workflows

| Workflow | Kind | Effect / Cost | Purpose |
|---|---|---|---|
| `DocumentQA(path, question, system="", model="", max_tokens=1024)` | workflow (entry point) | — (composed: `UploadFile` cheap + `CreateMessageWithFile` moderate) | upload a document, ask one question about it — the RAG pattern |

Indexed in `catalog.yaml` as an entry-point workflow with tags
`[rag, document-qa, files, messages, pdf, question-answering]` for reuse-first catalog matching.

## Cache / output

No sidecar cache. The uploaded document persists **on Anthropic's side** (Files API) and is
reusable across questions by `file_id`; the answer + token usage are returned inline. Set
`cache_system=true` on the underlying `CreateMessageWithFile` for prompt caching of a shared
system prompt across repeated questions (not exposed on the `DocumentQA` workflow surface — call
the facet directly for that).

## Gotchas & notes

- **Add new cross-area facets here, not in per-area files** (CLAUDE.md): keep event-facet
  definitions in their area `.ffl`, put multi-step glue in `composition.ffl`.
- **`file_id` reuse** — the same upload answers many questions; don't re-upload per question.
- **Future areas** (`mcp`, `evals`, `cookbook`, …) that compose across surfaces get their
  workflows here.

## Related specs

- [files.md](files.md) — the `UploadFile` half.
- [messages.md](messages.md) — the `CreateMessageWithFile` half.
- [architecture.md](architecture.md) — the JSON-bridge / comma-separated conventions and the
  catalog manifest that indexes this workflow.
