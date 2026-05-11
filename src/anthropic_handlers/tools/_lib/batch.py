"""Message Batches API integration.

Reference: https://docs.anthropic.com/en/docs/build-with-claude/message-batches

The Batches API runs many Messages requests asynchronously, billed at
roughly 50% the per-token rate of synchronous calls. Submission
returns immediately with a ``batch_id``; results stream back when the
batch completes (or hits its 24-hour cap).

This area exposes the three primitives so callers can compose their
own polling cadence, plus a convenience driver that handles the loop:

- :func:`submit_batch`      — submit a list of message requests
- :func:`get_batch_status`  — check completion status / per-state counts
- :func:`get_batch_results` — pull results once the batch ends
- :func:`run_batch`         — submit + poll + retrieve in one call
"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable

from .client import get_client


def submit_batch(
    *,
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    """Submit a batch of Messages requests.

    *requests* is a list of dicts shaped per the SDK's
    ``MessageBatchRequest`` (``custom_id`` + ``params={...}``). Returns
    the batch ID, type, status, request counts, and creation time.
    """
    if not requests:
        raise ValueError("requests must not be empty")
    if not all(isinstance(r, dict) for r in requests):
        raise ValueError("each request must be a dict (custom_id + params)")

    client = get_client()
    # SDK lives at client.messages.batches; access defensively so a
    # future renamed namespace doesn't crash module import.
    batches_api = client.messages.batches
    batch = batches_api.create(requests=requests)
    return _batch_to_dict(batch)


def get_batch_status(*, batch_id: str) -> dict[str, Any]:
    """Retrieve current status of a batch (does NOT block)."""
    if not batch_id:
        raise ValueError("batch_id must not be empty")

    client = get_client()
    batch = client.messages.batches.retrieve(batch_id)
    return _batch_to_dict(batch)


def get_batch_results(*, batch_id: str) -> dict[str, Any]:
    """Pull the per-request results for a batch.

    Streams the SDK's results iterator and assembles a plain-dict list.
    The batch must be in a terminal state (``ended``); polling cadence
    is the caller's responsibility (use :func:`get_batch_status`).
    """
    if not batch_id:
        raise ValueError("batch_id must not be empty")

    client = get_client()
    raw_results = client.messages.batches.results(batch_id)
    results = [_result_to_dict(r) for r in _iter_safely(raw_results)]
    return {
        "batch_id": batch_id,
        "result_count": len(results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Internal: SDK model → plain dict
# ---------------------------------------------------------------------------


def _iter_safely(maybe_iter: Any) -> Iterable[Any]:
    """Some SDK clients return iterators that aren't list-typed — coerce."""
    if maybe_iter is None:
        return []
    try:
        return list(maybe_iter)
    except TypeError:
        return [maybe_iter]


def _batch_to_dict(batch: Any) -> dict[str, Any]:
    """Convert a MessageBatch model to a plain dict.

    The SDK's request_counts shape carries per-state counts
    (processing / succeeded / errored / canceled / expired) — we
    surface each explicitly so workflow steps can branch on them.
    """
    counts_obj = getattr(batch, "request_counts", None)
    counts = {
        "processing": getattr(counts_obj, "processing", 0) or 0,
        "succeeded": getattr(counts_obj, "succeeded", 0) or 0,
        "errored": getattr(counts_obj, "errored", 0) or 0,
        "canceled": getattr(counts_obj, "canceled", 0) or 0,
        "expired": getattr(counts_obj, "expired", 0) or 0,
    } if counts_obj is not None else {
        "processing": 0, "succeeded": 0, "errored": 0,
        "canceled": 0, "expired": 0,
    }
    return {
        "id": getattr(batch, "id", ""),
        "type": getattr(batch, "type", "message_batch"),
        "processing_status": getattr(batch, "processing_status", ""),
        "request_counts": counts,
        "created_at": str(getattr(batch, "created_at", "")),
        "expires_at": str(getattr(batch, "expires_at", "")),
        "ended_at": str(getattr(batch, "ended_at", "")) if getattr(batch, "ended_at", None) else "",
        "results_url": getattr(batch, "results_url", "") or "",
    }


def _result_to_dict(result: Any) -> dict[str, Any]:
    """Flatten a per-request result into a JSON-friendly dict."""
    out: dict[str, Any] = {
        "custom_id": getattr(result, "custom_id", ""),
    }
    # The result object carries a discriminated union under .result.
    inner = getattr(result, "result", None)
    rtype = getattr(inner, "type", "") if inner is not None else ""
    out["type"] = rtype

    if rtype == "succeeded":
        message = getattr(inner, "message", None)
        if message is not None:
            text = "".join(
                getattr(b, "text", "")
                for b in (getattr(message, "content", None) or [])
                if getattr(b, "type", "") == "text"
            )
            out["text"] = text
            out["stop_reason"] = getattr(message, "stop_reason", "")
            usage = getattr(message, "usage", None)
            if usage is not None:
                out["input_tokens"] = getattr(usage, "input_tokens", 0) or 0
                out["output_tokens"] = getattr(usage, "output_tokens", 0) or 0
    elif rtype == "errored":
        err = getattr(inner, "error", None)
        out["error_type"] = getattr(err, "type", "") if err is not None else ""
        out["error_message"] = getattr(err, "message", "") if err is not None else ""
    elif rtype in ("canceled", "expired"):
        out["note"] = rtype
    return out


# ---------------------------------------------------------------------------
# Convenience driver
# ---------------------------------------------------------------------------


def run_batch(
    *,
    requests: list[dict[str, Any]],
    poll_interval_seconds: float = 10.0,
    timeout_seconds: float = 600.0,
    on_status: Callable[[dict[str, Any]], None] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Submit + poll + retrieve a batch in one call.

    Submits *requests*, polls :func:`get_batch_status` every
    *poll_interval_seconds*, and once the batch reaches a terminal
    state (``processing_status == "ended"``) calls
    :func:`get_batch_results` and returns the aggregated payload:

        {
            "batch": <metadata dict from get_batch_status>,
            "poll_count": <int>,
            "elapsed_seconds": <float>,
            "results": [<per-request dicts>],
        }

    *on_status* is an optional callback invoked on every poll with
    the current batch metadata (great for surfacing progress to the
    FFL step log). *sleep_fn* defaults to :func:`time.sleep` but can
    be patched out in tests.

    Raises :class:`TimeoutError` if the batch doesn't end within
    *timeout_seconds*. The submitted batch keeps running on
    Anthropic's side after the timeout — call
    :func:`get_batch_status` / :func:`get_batch_results` directly to
    pick up where the loop left off.
    """
    if poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be positive")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    sleep = sleep_fn or time.sleep
    submitted = submit_batch(requests=requests)
    batch_id = submitted["id"]
    if on_status is not None:
        on_status(submitted)

    start = time.monotonic()
    poll_count = 0
    status = submitted
    while status.get("processing_status") != "ended":
        elapsed = time.monotonic() - start
        if elapsed >= timeout_seconds:
            raise TimeoutError(
                f"run_batch hit timeout_seconds={timeout_seconds} waiting on "
                f"batch {batch_id!r} (last status={status.get('processing_status')!r}). "
                f"Use get_batch_status / get_batch_results to pick up where the "
                f"loop left off — the batch keeps running on Anthropic's side."
            )
        sleep(poll_interval_seconds)
        poll_count += 1
        status = get_batch_status(batch_id=batch_id)
        if on_status is not None:
            on_status(status)

    results = get_batch_results(batch_id=batch_id)
    return {
        "batch": status,
        "poll_count": poll_count,
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "results": results["results"],
    }
