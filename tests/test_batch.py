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

        assert set(bh._DISPATCH.keys()) == {
            "anthropic.batch.SubmitBatch",
            "anthropic.batch.GetBatchStatus",
            "anthropic.batch.GetBatchResults",
        }
