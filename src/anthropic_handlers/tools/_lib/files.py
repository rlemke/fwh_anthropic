"""Files API integration.

Reference: https://docs.anthropic.com/en/docs/build-with-claude/files-api

The Files API stores documents on Anthropic's side so subsequent
Messages calls can reference them by ``file_id`` instead of uploading
inline content every time — useful for RAG-style flows where the
same long document is queried repeatedly.

Public surface:

- :func:`upload_file`  — upload a local file, get back ``file_id`` + metadata
- :func:`list_files`   — list all files (newest first by default)
- :func:`delete_file`  — delete a previously-uploaded file

The Files API was introduced as a beta in the Anthropic SDK; the code
below accesses ``client.beta.files`` first and falls back to
``client.files`` for forward-compat with a future GA. If you hit an
``AttributeError`` from this module, your SDK version may use a
slightly different surface — pin to a recent ``anthropic`` release.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from .client import get_client


def _files_api(client: Any) -> Any:
    """Locate the files namespace on the SDK client (beta first, then GA)."""
    beta = getattr(client, "beta", None)
    if beta is not None and hasattr(beta, "files"):
        return beta.files
    if hasattr(client, "files"):
        return client.files
    raise RuntimeError(
        "Anthropic SDK does not expose a `files` namespace. Upgrade `anthropic` "
        "to a recent version that supports the Files API."
    )


def upload_file(*, path: str, mime_type: str | None = None) -> dict[str, Any]:
    """Upload a local file to Anthropic's Files API.

    Returns the file's ``id`` + metadata. ``mime_type`` is autodetected
    from the filename when omitted; pass it explicitly to force a
    specific type (e.g. ``"application/pdf"`` for content-typed PDFs).
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"file not found: {path}")

    detected, _ = mimetypes.guess_type(p.name) if mime_type is None else (mime_type, None)
    if not detected:
        detected = "application/octet-stream"

    client = get_client()
    api = _files_api(client)
    with p.open("rb") as fh:
        uploaded = api.upload(file=(p.name, fh, detected))
    return _file_to_dict(uploaded)


def list_files(*, limit: int = 50) -> dict[str, Any]:
    """List uploaded files (most-recent-first).

    Returns ``{"files": [...], "count": <int>}``. Newer SDK versions
    expose pagination cursors; this thin wrapper materialises only
    the first page (up to ``limit`` entries).
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")

    client = get_client()
    api = _files_api(client)
    # The SDK's list() returns a SyncCursorPage / similar with a .data attr.
    listing = api.list(limit=int(limit))
    raw = getattr(listing, "data", listing)
    files = [_file_to_dict(f) for f in list(raw)[:limit]]
    return {"count": len(files), "files": files}


def delete_file(*, file_id: str) -> dict[str, Any]:
    """Delete a previously-uploaded file. Returns deletion-confirmation metadata."""
    if not file_id:
        raise ValueError("file_id must not be empty")

    client = get_client()
    api = _files_api(client)
    result = api.delete(file_id)
    return {
        "id": getattr(result, "id", file_id),
        "deleted": getattr(result, "deleted", True) or True,
        "type": getattr(result, "type", "file_deleted"),
    }


# ---------------------------------------------------------------------------
# Internal: SDK model → plain dict
# ---------------------------------------------------------------------------


def _file_to_dict(f: Any) -> dict[str, Any]:
    """Flatten a File model for FFL / JSON transport."""
    return {
        "id": getattr(f, "id", ""),
        "type": getattr(f, "type", "file"),
        "filename": getattr(f, "filename", "") or "",
        "mime_type": getattr(f, "mime_type", "") or "",
        "size_bytes": int(getattr(f, "size_bytes", 0) or 0),
        "created_at": str(getattr(f, "created_at", "")),
        "downloadable": bool(getattr(f, "downloadable", False)),
    }
