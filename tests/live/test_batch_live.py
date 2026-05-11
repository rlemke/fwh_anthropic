"""Live smoke test for the batch area.

Submits a single-request batch and confirms ``submit + get_status``
work against the real API. Does NOT poll to completion — the 24-hour
SLA makes that unreliable in CI. For an end-to-end batch run, drive
``run_batch`` from a higher-level script with a generous timeout.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.live


class TestSubmitBatchLive:
    def test_submit_then_status(self):
        from anthropic_handlers.tools._lib import batch as batch_lib

        submitted = batch_lib.submit_batch(requests=[
            {
                "custom_id": "live-smoke-r1",
                "params": {
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "Reply with 'ok'."}],
                },
            },
        ])
        batch_id = submitted["id"]
        assert batch_id
        assert submitted["processing_status"] in (
            "in_progress", "ended", "validating", "canceling",
        )

        status = batch_lib.get_batch_status(batch_id=batch_id)
        assert status["id"] == batch_id
        assert "request_counts" in status
