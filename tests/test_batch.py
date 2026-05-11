"""Tests for the batch integration area.

Mocks ``anthropic.Anthropic`` at the ``get_client`` boundary so no
real API calls are made.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------


def _counts(*, processing=0, succeeded=0, errored=0, canceled=0, expired=0):
    return SimpleNamespace(
        processing=processing,
        succeeded=succeeded,
        errored=errored,
        canceled=canceled,
        expired=expired,
    )


def _batch(
    *,
    id="msgbatch_abc",
    processing_status="in_progress",
    counts=None,
    ended_at=None,
    type="message_batch",
):
    return SimpleNamespace(
        id=id,
        type=type,
        processing_status=processing_status,
        request_counts=counts or _counts(processing=10),
        created_at="2026-05-11T00:00:00Z",
        expires_at="2026-05-12T00:00:00Z",
        ended_at=ended_at,
        results_url=None,
    )


def _result_succeeded(*, custom_id, text, input_tokens=10, output_tokens=5):
    message = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(type="succeeded", message=message),
    )


def _result_errored(*, custom_id, error_type="invalid_request", message="bad input"):
    err = SimpleNamespace(type=error_type, message=message)
    return SimpleNamespace(
        custom_id=custom_id,
        result=SimpleNamespace(type="errored", error=err),
    )


def _mock_client(*, batches=None):
    client = MagicMock()
    if batches:
        client.messages.batches = batches
    return client


# ---------------------------------------------------------------------------
# _lib.batch
# ---------------------------------------------------------------------------


class TestSubmitBatch:
    def test_submits_and_flattens_metadata(self):
        from anthropic_handlers.tools._lib import batch as batch_lib

        batches_api = MagicMock()
        batches_api.create.return_value = _batch(
            id="msgbatch_xyz",
            counts=_counts(processing=2),
        )
        client = _mock_client(batches=batches_api)
        with patch.object(batch_lib, "get_client", return_value=client):
            out = batch_lib.submit_batch(requests=[
                {"custom_id": "r1", "params": {"model": "...", "max_tokens": 10,
                                                "messages": [{"role": "user", "content": "hi"}]}},
            ])
        assert out["id"] == "msgbatch_xyz"
        assert out["processing_status"] == "in_progress"
        assert out["request_counts"]["processing"] == 2

    def test_empty_requests_raises(self):
        from anthropic_handlers.tools._lib import batch as batch_lib

        with pytest.raises(ValueError, match="requests"):
            batch_lib.submit_batch(requests=[])

    def test_non_dict_request_raises(self):
        from anthropic_handlers.tools._lib import batch as batch_lib

        with pytest.raises(ValueError, match="dict"):
            batch_lib.submit_batch(requests=["not a dict"])  # type: ignore[list-item]


class TestGetBatchStatus:
    def test_threads_id_to_retrieve(self):
        from anthropic_handlers.tools._lib import batch as batch_lib

        batches_api = MagicMock()
        batches_api.retrieve.return_value = _batch(
            id="msgbatch_xyz",
            processing_status="ended",
            counts=_counts(succeeded=10),
        )
        client = _mock_client(batches=batches_api)
        with patch.object(batch_lib, "get_client", return_value=client):
            out = batch_lib.get_batch_status(batch_id="msgbatch_xyz")
        assert out["id"] == "msgbatch_xyz"
        assert out["processing_status"] == "ended"
        assert out["request_counts"]["succeeded"] == 10
        batches_api.retrieve.assert_called_once_with("msgbatch_xyz")

    def test_empty_id_raises(self):
        from anthropic_handlers.tools._lib import batch as batch_lib

        with pytest.raises(ValueError, match="batch_id"):
            batch_lib.get_batch_status(batch_id="")


class TestGetBatchResults:
    def test_iterates_and_flattens_results(self):
        from anthropic_handlers.tools._lib import batch as batch_lib

        results = [
            _result_succeeded(custom_id="r1", text="ok 1", input_tokens=12, output_tokens=3),
            _result_succeeded(custom_id="r2", text="ok 2"),
            _result_errored(custom_id="r3"),
        ]
        batches_api = MagicMock()
        batches_api.results.return_value = iter(results)
        client = _mock_client(batches=batches_api)
        with patch.object(batch_lib, "get_client", return_value=client):
            out = batch_lib.get_batch_results(batch_id="msgbatch_xyz")
        assert out["result_count"] == 3
        assert out["results"][0] == {
            "custom_id": "r1", "type": "succeeded", "text": "ok 1",
            "stop_reason": "end_turn", "input_tokens": 12, "output_tokens": 3,
        }
        assert out["results"][2]["type"] == "errored"
        assert out["results"][2]["error_message"] == "bad input"


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class TestBatchHandlers:
    def test_submit_handler_decodes_requests_json(self):
        from anthropic_handlers.handlers.batch import batch_handlers as bh
        from anthropic_handlers.tools._lib import batch as batch_lib

        batches_api = MagicMock()
        batches_api.create.return_value = _batch(id="msgbatch_abc", counts=_counts(processing=1))
        client = _mock_client(batches=batches_api)
        with patch.object(batch_lib, "get_client", return_value=client):
            out = bh._submit_batch_handler({
                "requests_json": json.dumps([
                    {"custom_id": "r1", "params": {"model": "m", "max_tokens": 10,
                                                    "messages": [{"role": "user", "content": "hi"}]}},
                ]),
            })
        assert out["result"]["id"] == "msgbatch_abc"
        assert out["result"]["processing"] == 1

    def test_submit_handler_requires_requests_json(self):
        from anthropic_handlers.handlers.batch import batch_handlers as bh

        with pytest.raises(ValueError, match="requests_json"):
            bh._submit_batch_handler({})

    def test_results_handler_json_bridges(self):
        from anthropic_handlers.handlers.batch import batch_handlers as bh
        from anthropic_handlers.tools._lib import batch as batch_lib

        batches_api = MagicMock()
        batches_api.results.return_value = iter([
            _result_succeeded(custom_id="r1", text="answer"),
        ])
        client = _mock_client(batches=batches_api)
        with patch.object(batch_lib, "get_client", return_value=client):
            out = bh._get_batch_results_handler({"batch_id": "msgbatch_abc"})
        decoded = json.loads(out["result"]["results_json"])
        assert decoded[0]["custom_id"] == "r1"
        assert decoded[0]["text"] == "answer"
        assert out["result"]["result_count"] == 1

    def test_dispatch_keys(self):
        from anthropic_handlers.handlers.batch import batch_handlers as bh

        assert {
            "anthropic.batch.SubmitBatch",
            "anthropic.batch.GetBatchStatus",
            "anthropic.batch.GetBatchResults",
            "anthropic.batch.RunBatch",
        } <= set(bh._DISPATCH.keys())


# ---------------------------------------------------------------------------
# run_batch — submit + poll + retrieve convenience driver
# ---------------------------------------------------------------------------


class TestRunBatch:
    def _client_for_lifecycle(self, *, statuses, results):
        """Build a client whose retrieve() walks the supplied status list."""
        batches_api = MagicMock()
        # submit_batch calls .create — first response is the initial submit.
        batches_api.create.return_value = statuses[0]
        # Each retrieve() pops the next status off the queue.
        queue = list(statuses[1:])

        def _retrieve(_id: str):
            if not queue:
                raise AssertionError("retrieve called more times than expected")
            return queue.pop(0)

        batches_api.retrieve = MagicMock(side_effect=_retrieve)
        batches_api.results = MagicMock(return_value=iter(results))
        return _mock_client(batches=batches_api), batches_api

    def test_polls_until_ended_and_returns_results(self):
        from anthropic_handlers.tools._lib import batch as batch_lib

        client, batches_api = self._client_for_lifecycle(
            statuses=[
                _batch(id="msgbatch_abc", processing_status="in_progress",
                       counts=_counts(processing=2)),
                _batch(id="msgbatch_abc", processing_status="in_progress",
                       counts=_counts(processing=1, succeeded=1)),
                _batch(id="msgbatch_abc", processing_status="ended",
                       counts=_counts(succeeded=2), ended_at="2026-05-11T01:00:00Z"),
            ],
            results=[
                _result_succeeded(custom_id="r1", text="answer 1"),
                _result_succeeded(custom_id="r2", text="answer 2"),
            ],
        )
        sleep_calls: list[float] = []
        status_calls: list[str] = []
        with patch.object(batch_lib, "get_client", return_value=client):
            out = batch_lib.run_batch(
                requests=[
                    {"custom_id": "r1", "params": {"model": "m", "max_tokens": 10,
                                                    "messages": [{"role": "user", "content": "hi"}]}},
                    {"custom_id": "r2", "params": {"model": "m", "max_tokens": 10,
                                                    "messages": [{"role": "user", "content": "hi"}]}},
                ],
                poll_interval_seconds=0.1,
                timeout_seconds=10.0,
                sleep_fn=sleep_calls.append,
                on_status=lambda meta: status_calls.append(meta["processing_status"]),
            )

        assert out["batch"]["processing_status"] == "ended"
        assert out["poll_count"] == 2
        assert len(out["results"]) == 2
        assert out["results"][0]["text"] == "answer 1"
        # sleep_fn was called once per poll, with the requested interval.
        assert sleep_calls == [0.1, 0.1]
        # on_status fires once on submit + once per poll.
        assert status_calls == ["in_progress", "in_progress", "ended"]

    def test_skips_polling_when_already_ended(self):
        """A batch that ends on submit must not call retrieve at all."""
        from anthropic_handlers.tools._lib import batch as batch_lib

        batches_api = MagicMock()
        batches_api.create.return_value = _batch(
            id="msgbatch_inst",
            processing_status="ended",
            counts=_counts(succeeded=1),
            ended_at="2026-05-11T00:00:01Z",
        )
        batches_api.results.return_value = iter([
            _result_succeeded(custom_id="r1", text="instant"),
        ])
        client = _mock_client(batches=batches_api)
        with patch.object(batch_lib, "get_client", return_value=client):
            out = batch_lib.run_batch(
                requests=[{"custom_id": "r1", "params": {"model": "m",
                            "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}}],
                poll_interval_seconds=0.1,
                sleep_fn=lambda _: None,
            )
        assert out["poll_count"] == 0
        batches_api.retrieve.assert_not_called()
        assert out["results"][0]["text"] == "instant"

    def test_timeout_raises_with_actionable_message(self):
        from anthropic_handlers.tools._lib import batch as batch_lib

        # Submit returns in_progress, retrieve keeps returning in_progress.
        batches_api = MagicMock()
        batches_api.create.return_value = _batch(
            id="msgbatch_slow", processing_status="in_progress",
            counts=_counts(processing=5),
        )
        batches_api.retrieve.return_value = _batch(
            id="msgbatch_slow", processing_status="in_progress",
            counts=_counts(processing=5),
        )
        client = _mock_client(batches=batches_api)
        # Use a fake clock so the test doesn't actually wait.
        import time as time_mod
        tick = [0.0]

        def _fake_sleep(seconds: float) -> None:
            tick[0] += seconds

        with patch.object(batch_lib, "get_client", return_value=client), \
             patch.object(batch_lib.time, "monotonic", side_effect=lambda: tick[0]):
            with pytest.raises(TimeoutError, match="timeout_seconds"):
                batch_lib.run_batch(
                    requests=[{"custom_id": "r1", "params": {"model": "m",
                                "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}}],
                    poll_interval_seconds=1.0,
                    timeout_seconds=2.0,
                    sleep_fn=_fake_sleep,
                )

    def test_handler_decodes_and_returns_results_json(self):
        from anthropic_handlers.handlers.batch import batch_handlers as bh
        from anthropic_handlers.tools._lib import batch as batch_lib

        # Submit then retrieve both return "ended" → no polling.
        batches_api = MagicMock()
        batches_api.create.return_value = _batch(
            id="msgbatch_h", processing_status="ended",
            counts=_counts(succeeded=1),
        )
        batches_api.results.return_value = iter([
            _result_succeeded(custom_id="r1", text="handler ok"),
        ])
        client = _mock_client(batches=batches_api)
        # Replace time.sleep so no real wait occurs.
        with patch.object(batch_lib, "get_client", return_value=client), \
             patch.object(batch_lib.time, "sleep", lambda _s: None):
            out = bh._run_batch_handler({
                "requests_json": json.dumps([
                    {"custom_id": "r1", "params": {"model": "m", "max_tokens": 10,
                                                    "messages": [{"role": "user", "content": "hi"}]}},
                ]),
                "poll_interval_seconds": 0.01,
                "timeout_seconds": 1.0,
            })
        assert out["result"]["batch_id"] == "msgbatch_h"
        assert out["result"]["processing_status"] == "ended"
        assert out["result"]["result_count"] == 1
        decoded = json.loads(out["result"]["results_json"])
        assert decoded[0]["custom_id"] == "r1"
        assert decoded[0]["text"] == "handler ok"

    def test_handler_requires_requests_json(self):
        from anthropic_handlers.handlers.batch import batch_handlers as bh

        with pytest.raises(ValueError, match="requests_json"):
            bh._run_batch_handler({})
