"""Message Batches event-facet handlers.

Wires :mod:`anthropic_handlers.tools._lib.batch` into the
``anthropic.batch.*`` FFL namespace. Three facets — submit, status,
results — that callers compose into a workflow with their own
polling cadence (Facetwork has no ``while``, so polling is typically
expressed as an explicit retry loop in the surrounding workflow).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from ..shared.anthropic_utils import (
    get_batch_results,
    get_batch_status,
    run_batch,
    submit_batch,
)

log = logging.getLogger(__name__)

NAMESPACE = "anthropic.batch"


def _submit_batch_handler(payload: dict) -> dict[str, Any]:
    requests_json = payload.get("requests_json", "")
    if not requests_json:
        raise ValueError("SubmitBatch requires requests_json")
    requests = json.loads(requests_json)
    if not isinstance(requests, list):
        raise ValueError("requests_json must decode to a JSON list")

    step_log = payload.get("_step_log")
    if step_log:
        step_log(f"SubmitBatch: {len(requests)} requests")
    out = submit_batch(requests=requests)
    return {"result": _flatten_batch(out)}


def _get_batch_status_handler(payload: dict) -> dict[str, Any]:
    batch_id = payload["batch_id"]
    step_log = payload.get("_step_log")
    if step_log:
        step_log(f"GetBatchStatus: {batch_id}")
    out = get_batch_status(batch_id=batch_id)
    return {"result": _flatten_batch(out)}


def _get_batch_results_handler(payload: dict) -> dict[str, Any]:
    batch_id = payload["batch_id"]
    step_log = payload.get("_step_log")
    if step_log:
        step_log(f"GetBatchResults: {batch_id}")
    out = get_batch_results(batch_id=batch_id)
    return {
        "result": {
            "batch_id": out["batch_id"],
            "result_count": out["result_count"],
            "results_json": json.dumps(out["results"], default=str),
        }
    }


def _flatten_batch(batch: dict[str, Any]) -> dict[str, Any]:
    """Flatten _lib.batch's dict shape for FFL transport (no nested dicts)."""
    counts = batch.get("request_counts") or {}
    return {
        "id": batch.get("id", ""),
        "type": batch.get("type", ""),
        "processing_status": batch.get("processing_status", ""),
        "created_at": batch.get("created_at", ""),
        "expires_at": batch.get("expires_at", ""),
        "ended_at": batch.get("ended_at", ""),
        "results_url": batch.get("results_url", ""),
        "processing": int(counts.get("processing", 0)),
        "succeeded": int(counts.get("succeeded", 0)),
        "errored": int(counts.get("errored", 0)),
        "canceled": int(counts.get("canceled", 0)),
        "expired": int(counts.get("expired", 0)),
    }


def _run_batch_handler(payload: dict) -> dict[str, Any]:
    requests_json = payload.get("requests_json", "")
    if not requests_json:
        raise ValueError("RunBatch requires requests_json")
    requests = json.loads(requests_json)
    if not isinstance(requests, list):
        raise ValueError("requests_json must decode to a JSON list")
    poll_interval_seconds = float(payload.get("poll_interval_seconds", 10.0))
    timeout_seconds = float(payload.get("timeout_seconds", 600.0))

    step_log = payload.get("_step_log")
    if step_log:
        step_log(
            f"RunBatch: {len(requests)} requests "
            f"poll={poll_interval_seconds}s timeout={timeout_seconds}s"
        )

    def _on_status(meta: dict[str, Any]) -> None:
        if step_log:
            counts = meta.get("request_counts") or {}
            step_log(
                f"batch {meta.get('id', '?')} status={meta.get('processing_status', '?')} "
                f"succeeded={counts.get('succeeded', 0)} "
                f"errored={counts.get('errored', 0)} "
                f"processing={counts.get('processing', 0)}"
            )

    out = run_batch(
        requests=requests,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
        on_status=_on_status,
    )
    batch_meta = out["batch"]
    return {
        "result": {
            "batch_id": batch_meta.get("id", ""),
            "processing_status": batch_meta.get("processing_status", ""),
            "poll_count": int(out["poll_count"]),
            "elapsed_seconds": float(out["elapsed_seconds"]),
            "result_count": len(out["results"]),
            "results_json": json.dumps(out["results"], default=str),
        }
    }


_DISPATCH: dict[str, Any] = {
    f"{NAMESPACE}.SubmitBatch": _submit_batch_handler,
    f"{NAMESPACE}.GetBatchStatus": _get_batch_status_handler,
    f"{NAMESPACE}.GetBatchResults": _get_batch_results_handler,
    f"{NAMESPACE}.RunBatch": _run_batch_handler,
}


def handle(payload: dict) -> dict:
    facet_name = payload["_facet_name"]
    handler = _DISPATCH.get(facet_name)
    if handler is None:
        raise ValueError(f"Unknown facet: {facet_name}")
    return handler(payload)


def register_handlers(runner) -> None:
    for facet_name in _DISPATCH:
        runner.register_handler(
            facet_name=facet_name,
            module_uri=f"file://{os.path.abspath(__file__)}",
            entrypoint="handle",
        )


def register_batch_handlers(poller) -> None:
    for fqn, func in _DISPATCH.items():
        poller.register(fqn, func)
        log.debug("Registered batch handler: %s", fqn)
