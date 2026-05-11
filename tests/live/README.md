# Live integration tests

Tests in this directory hit the real Anthropic API. They are gated by
two conditions:

1. The pytest marker `@pytest.mark.live` is collected normally (the
   default config in `pyproject.toml` excludes it via `-m 'not live'`).
2. The `--run-live` flag passes through `conftest.py`, which also
   requires `ANTHROPIC_API_KEY` to be set.

## Running

```bash
# Run only the live suite (typical use)
ANTHROPIC_API_KEY=sk-... pytest tests/live -m live --run-live

# Run a single area's live tests
ANTHROPIC_API_KEY=sk-... pytest tests/live/test_messages_live.py -m live --run-live -v

# Skip them in a normal run (default; no flag needed)
pytest tests/
```

## What they cover

Each per-area file does ONE minimal smoke test — enough to confirm the
wiring works end-to-end against the real API, not exhaustive coverage.
For shape/branch coverage, see the mocked tests under `tests/`.

- `test_messages_live.py` — `create_message` returns assistant text
- `test_batch_live.py` — submit + status; results retrieved if ended
  quickly (otherwise just checks the batch was created)
- `test_files_live.py` — upload a tiny inline PDF then delete it
- `test_composition_live.py` — full DocumentQA: upload → ask → delete

## Cost

Each test sends at most a few hundred tokens with `max_tokens=128`. A
full live run is typically well under one cent per execution.
