"""Tests for the files integration area.

Mocks ``client.beta.files.*`` so no real Files API calls are made.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------


def _file(
    *,
    id="file_abc",
    filename="doc.pdf",
    mime_type="application/pdf",
    size_bytes=1024,
    downloadable=True,
):
    return SimpleNamespace(
        id=id,
        type="file",
        filename=filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        created_at="2026-05-11T00:00:00Z",
        downloadable=downloadable,
    )


def _mock_client_with_files_api(files_api):
    """Client whose ``client.beta.files`` is the supplied mock."""
    client = MagicMock()
    client.beta = SimpleNamespace(files=files_api)
    return client


# ---------------------------------------------------------------------------
# _lib.files
# ---------------------------------------------------------------------------


class TestUploadFile:
    def test_uploads_and_flattens(self, tmp_path):
        from anthropic_handlers.tools._lib import files as files_lib

        path = tmp_path / "doc.pdf"
        path.write_bytes(b"%PDF-1.4 placeholder")

        files_api = MagicMock()
        files_api.upload.return_value = _file(id="file_xyz", filename="doc.pdf")
        client = _mock_client_with_files_api(files_api)
        with patch.object(files_lib, "get_client", return_value=client):
            out = files_lib.upload_file(path=str(path))
        assert out == {
            "id": "file_xyz",
            "type": "file",
            "filename": "doc.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 1024,
            "created_at": "2026-05-11T00:00:00Z",
            "downloadable": True,
        }
        # Verify the SDK was called with a (filename, file_handle, mime) triple.
        call = files_api.upload.call_args.kwargs
        assert call["file"][0] == "doc.pdf"
        assert call["file"][2] == "application/pdf"

    def test_mime_type_override(self, tmp_path):
        from anthropic_handlers.tools._lib import files as files_lib

        # Use a "weird" extension to force mime override.
        path = tmp_path / "data.bin"
        path.write_bytes(b"x")
        files_api = MagicMock()
        files_api.upload.return_value = _file()
        client = _mock_client_with_files_api(files_api)
        with patch.object(files_lib, "get_client", return_value=client):
            files_lib.upload_file(path=str(path), mime_type="text/plain")
        assert files_api.upload.call_args.kwargs["file"][2] == "text/plain"

    def test_missing_file_raises(self):
        from anthropic_handlers.tools._lib import files as files_lib

        with pytest.raises(FileNotFoundError):
            files_lib.upload_file(path="/nope/missing.pdf")


class TestListFiles:
    def test_returns_count_and_dicts(self):
        from anthropic_handlers.tools._lib import files as files_lib

        files_api = MagicMock()
        listing = SimpleNamespace(data=[_file(id="a"), _file(id="b")])
        files_api.list.return_value = listing
        client = _mock_client_with_files_api(files_api)
        with patch.object(files_lib, "get_client", return_value=client):
            out = files_lib.list_files(limit=5)
        assert out["count"] == 2
        assert out["files"][0]["id"] == "a"

    def test_limit_must_be_positive(self):
        from anthropic_handlers.tools._lib import files as files_lib

        with pytest.raises(ValueError, match="limit"):
            files_lib.list_files(limit=0)

    def test_limit_caps_returned_files(self):
        """SDK might return more than ``limit``; the helper caps it."""
        from anthropic_handlers.tools._lib import files as files_lib

        files_api = MagicMock()
        listing = SimpleNamespace(data=[_file(id=f"f{i}") for i in range(10)])
        files_api.list.return_value = listing
        client = _mock_client_with_files_api(files_api)
        with patch.object(files_lib, "get_client", return_value=client):
            out = files_lib.list_files(limit=3)
        assert out["count"] == 3


class TestDeleteFile:
    def test_returns_deletion_confirmation(self):
        from anthropic_handlers.tools._lib import files as files_lib

        files_api = MagicMock()
        files_api.delete.return_value = SimpleNamespace(
            id="file_xyz", type="file_deleted", deleted=True
        )
        client = _mock_client_with_files_api(files_api)
        with patch.object(files_lib, "get_client", return_value=client):
            out = files_lib.delete_file(file_id="file_xyz")
        assert out == {"id": "file_xyz", "deleted": True, "type": "file_deleted"}
        files_api.delete.assert_called_once_with("file_xyz")

    def test_empty_id_raises(self):
        from anthropic_handlers.tools._lib import files as files_lib

        with pytest.raises(ValueError, match="file_id"):
            files_lib.delete_file(file_id="")


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class TestFilesHandlers:
    def test_list_handler_bridges_as_json(self):
        from anthropic_handlers.handlers.files import files_handlers as fh
        from anthropic_handlers.tools._lib import files as files_lib

        files_api = MagicMock()
        files_api.list.return_value = SimpleNamespace(data=[_file(id="a"), _file(id="b")])
        client = _mock_client_with_files_api(files_api)
        with patch.object(files_lib, "get_client", return_value=client):
            out = fh._list_files_handler({"limit": 5})
        decoded = json.loads(out["result"]["files_json"])
        assert [f["id"] for f in decoded] == ["a", "b"]
        assert out["result"]["count"] == 2

    def test_dispatch_keys(self):
        from anthropic_handlers.handlers.files import files_handlers as fh

        assert set(fh._DISPATCH.keys()) == {
            "anthropic.files.UploadFile",
            "anthropic.files.ListFiles",
            "anthropic.files.DeleteFile",
        }
