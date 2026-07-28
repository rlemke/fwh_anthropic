# fwh_anthropic — Feature Specifications

This directory holds one **spec per integration area** of `fwh_anthropic` — the
Facetwork package that wraps the Anthropic / Claude APIs and CLIs. Each document follows a
common shape ([`SPEC_TEMPLATE.md`](SPEC_TEMPLATE.md)) and states, for that area: how the call
flows (FFL → handler → `tools/_lib` → shared SDK client), whether it **fans out**, the schema
**fields and JSON-bridge conventions** it uses, the **libraries / binaries** it needs, its
**facets & workflows** (with `Effect`/`Cost` mixins), and its **cache / output** story. Claims
are grounded in the FFL `/** … */` docstrings, the handler code, and `tools/_lib/*` — the
source of truth for each facet remains its FFL docstring; these specs are the area-level
narrative over them.

**Start here:** [**architecture.md**](architecture.md) — the cross-cutting spec (shared
client/auth, the `tools/_lib ↔ handlers ↔ ffl` pattern, the JSON-bridge convention, discovery
and registration). Then [**messages.md**](messages.md) — the flagship area (6 of the 16
facets) that every other messaging surface builds on.

## Cross-cutting

| Spec | What it covers |
|------|----------------|
| [architecture.md](architecture.md) | **Read first.** Multi-area design; shared `get_client()` / auth / default model; the uniform FFL→`handle`→`_DISPATCH`→shim→`_lib` call path; JSON-bridge (`*_json`) + comma-separated field conventions; `facetwork.domains` entry point + `DomainPackage`; the `catalog.yaml` capability manifest; test gating. |

## Integration areas

| Spec | Namespace | Facets | What it covers |
|------|-----------|--------|----------------|
| [messages.md](messages.md) | `anthropic.messages` | 6 + `ChatOnce` | **Flagship.** Messages API — text, `CountTokens`, tool use, vision, streaming, Files-API RAG; prompt caching via `cache_system`. |
| [batch.md](batch.md) | `anthropic.batch` | 4 | Message Batches API — `SubmitBatch`/`GetBatchStatus`/`GetBatchResults` primitives + the `RunBatch` submit-poll-retrieve driver (server-side fan-out, ~50% cost). |
| [files.md](files.md) | `anthropic.files` | 3 | Files API — `UploadFile`/`ListFiles`/`DeleteFile`; Anthropic-side storage referenced by `file_id`. |
| [agent-sdk.md](agent-sdk.md) | `anthropic.agent` | 1 | Claude Agent SDK — `RunAgent`, an autonomous run to completion (optional `[agent_sdk]` dep, async). |
| [claude-code.md](claude-code.md) | `anthropic.code` | 1 | Claude Code CLI — `RunClaudeCode` as a subprocess (needs the `claude` binary on PATH); built for per-directory fan-out. |
| [computer-use.md](computer-use.md) | `anthropic.computer` | 1 | Computer Use beta — `RunComputerUseSession`, **simulator-backed by default** (stub tools; live model loop). |

## Composition & domain apps

| Spec | Namespace | What it covers |
|------|-----------|----------------|
| [composition.md](composition.md) | `anthropic.compose` | Cross-area workflows — `DocumentQA` (Files + Messages RAG); no new event facets, glue only. |
| [ffl-examples.md](ffl-examples.md) | **Usage patterns.** A gallery of complete, compile-checked FFL examples over these facets — minimal ask, token-budget `when` gate, `foreach` over prompts, prompt caching, batch, agent→code chaining, mixins + `catch`. |

---

*See also the repo [`CLAUDE.md`](../CLAUDE.md) (multi-area authoring contract) and
[`README.md`](../README.md), the machine-readable capability manifest at
[`src/anthropic_handlers/catalog.yaml`](../src/anthropic_handlers/catalog.yaml) (workflows +
facets by intent), and the live/queryable interface — the MCP `fw_capabilities` /
`fw_catalog_match` / `fw_describe_handler` tools.*
