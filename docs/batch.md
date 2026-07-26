# Message Batches API

**Namespace:** `anthropic.batch` ·
**FFL:** `src/anthropic_handlers/ffl/batch.ffl` ·
**Handlers:** `src/anthropic_handlers/handlers/batch/batch_handlers.py` ·
**Impl (`_lib`):** `src/anthropic_handlers/tools/_lib/batch.py` ·
**CLIs:** `tools/submit-batch.sh`, `get-batch-status.sh`, `get-batch-results.sh`, `run-batch.sh` ·
**Tests:** `tests/test_batch.py`, `tests/live/test_batch_live.py`

## Overview

Wraps the Anthropic **Message Batches API** (`client.messages.batches.*`) — submit many
Messages requests as one asynchronous batch, billed ~50% of synchronous calls with a
24-hour SLA. The area exposes **4 event facets**: three primitives (`SubmitBatch` /
`GetBatchStatus` / `GetBatchResults`) so callers compose their own polling cadence, plus a
turnkey `RunBatch` driver that submits, polls, and retrieves in one step. Reference:
`https://docs.anthropic.com/en/docs/build-with-claude/message-batches`.

## How it works

- **`submit_batch`** — `client.messages.batches.create(requests=…)`; validates each request
  is a dict (`custom_id` + `params`), returns batch metadata (`_batch_to_dict`) immediately.
  Does **not** wait.
- **`get_batch_status`** — `client.messages.batches.retrieve(batch_id)` → metadata; does not
  block.
- **`get_batch_results`** — `client.messages.batches.results(batch_id)`, coerced through
  `_iter_safely`, each entry flattened by `_result_to_dict` (success → `text` + usage;
  `errored` → `error_type`/`error_message`; `canceled`/`expired` → `note`).
- **`run_batch`** — the convenience driver: `submit_batch` → poll `get_batch_status` every
  `poll_interval_seconds` until `processing_status == "ended"` → `get_batch_results`. Takes a
  **`sleep_fn`** parameter (defaults to `time.sleep`) so tests drive the loop deterministically
  (CLAUDE.md code-review rule), and an `on_status` callback for progress. Raises
  `TimeoutError` on `timeout_seconds` (the batch keeps running server-side).

The handlers JSON-serialise the per-request results into the `results_json` bridge field and
flatten `request_counts` into the schema's per-state counts.

## Fan-out

**No FFL fan-out; the fan-out is server-side.** One `SubmitBatch`/`RunBatch` task hands the
whole request list to Anthropic, which processes them in parallel on its own infrastructure —
the Facetwork task stays single. This is the area to reach for instead of a `foreach` of
`CreateMessage` calls: it is cheaper and does not consume fleet slots per prompt.

## Data & fields

- `BatchMetadata {id, type, processing_status, created_at, expires_at, ended_at, results_url,
  processing, succeeded, errored, canceled, expired}` — the last five are the per-state
  request counts flattened from the SDK's `request_counts`.
- `BatchResults {batch_id, result_count, results_json}` and
  `RunBatchResult {batch_id, processing_status, poll_count, elapsed_seconds, result_count,
  results_json}`.

JSON-bridge: **`requests_json`** in (list of `MessageBatchRequest`-shaped objects, each
`custom_id` + `params`), **`results_json`** out (list of per-request dicts). Results arrive in
any order — key by `custom_id`.

## External libraries / binaries

- **`anthropic`** (pip, required); `time` (stdlib) for the poll loop. `[batch]` extra is
  declared but empty. No binary dependencies.

## Facets & workflows

| Facet | Kind | Effect / Cost | Purpose |
|---|---|---|---|
| `SubmitBatch(requests_json)` | event | external / **cheap** | submit; returns metadata, no wait |
| `GetBatchStatus(batch_id)` | event | external / **cheap** | poll status, no block |
| `GetBatchResults(batch_id)` | event | external / **cheap** | pull per-request results (batch must be `ended`) |
| `RunBatch(requests_json, poll_interval_seconds=10.0, timeout_seconds=600.0)` | event | external / **expensive** | submit + poll + retrieve in one step |

`RunBatch` is `expensive` because it runs a whole batch of inference within a polling budget;
the three primitives are `cheap` (metadata/accounting round-trips, no inference of their own).

## Cache / output

No sidecar cache, no file output. Results are returned inline as `results_json` (persisted in
the run's Mongo state). Prompt caching applies **inside** each batched request — put shared
context with `cache_control` in the `params` of `requests_json` (the batch shares it across
requests), per the Anthropic batch-caching pattern.

## Gotchas & notes

- **`GetBatchResults` requires a terminal (`ended`) batch** — polling cadence is the caller's
  responsibility with the three primitives; `RunBatch` handles it for you.
- **`RunBatch` timeout is not batch cancellation** — on `TimeoutError` the batch keeps running
  on Anthropic's side; call `GetBatchStatus` / `GetBatchResults` to pick up where the loop left
  off (the error message says so).
- **Deterministic tests** rely on the `sleep_fn` seam — don't remove it.

## Related specs

- [messages.md](messages.md) — each batched request is a Messages call; same `params` shape.
- [architecture.md](architecture.md) — the JSON-bridge convention (`requests_json` /
  `results_json`) and dispatch.
