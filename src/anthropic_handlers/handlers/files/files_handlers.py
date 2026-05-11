"""Files API event-facet handlers.

Wires :mod:`anthropic_handlers.tools._lib.files` into the
``anthropic.files.*`` FFL namespace.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from ..shared.anthropic_utils import (
    delete_file,
    list_files,
    upload_file,
)

log = logging.getLogger(__name__)

NAMESPACE = "anthropic.files"


def _upload_file_handler(payload: dict) -> dict[str, Any]:
    path = payload["path"]
    mime_type = payload.get("mime_type") or None
    step_log = payload.get("_step_log")
    if step_log:
        step_log(f"UploadFile: {path}")
    return {"result": upload_file(path=path, mime_type=mime_type)}


def _list_files_handler(payload: dict) -> dict[str, Any]:
    limit = int(payload.get("limit", 50))
    step_log = payload.get("_step_log")
    if step_log:
        step_log(f"ListFiles: limit={limit}")
    out = list_files(limit=limit)
    return {
        "result": {
            "count": out["count"],
            "files_json": json.dumps(out["files"], default=str),
        }
    }


def _delete_file_handler(payload: dict) -> dict[str, Any]:
    file_id = payload["file_id"]
    step_log = payload.get("_step_log")
    if step_log:
        step_log(f"DeleteFile: {file_id}")
    return {"result": delete_file(file_id=file_id)}


_DISPATCH: dict[str, Any] = {
    f"{NAMESPACE}.UploadFile": _upload_file_handler,
    f"{NAMESPACE}.ListFiles": _list_files_handler,
    f"{NAMESPACE}.DeleteFile": _delete_file_handler,
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


def register_files_handlers(poller) -> None:
    for fqn, func in _DISPATCH.items():
        poller.register(fqn, func)
        log.debug("Registered files handler: %s", fqn)
