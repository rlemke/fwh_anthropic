"""Live smoke test for the files area.

Uploads a tiny placeholder PDF, then deletes it. The upload itself is
free; deletion ensures the test leaves no residue.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.live


# Minimal valid PDF — Adobe's "Hello World" sample, ~270 bytes.
_TINY_PDF = (
    b"%PDF-1.1\n"
    b"%\xc2\xa5\xc2\xb1\xc3\xab\n"
    b"1 0 obj\n  << /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n  << /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n  << /Type /Page /Parent 2 0 R /Resources 4 0 R /Contents 6 0 R "
    b"/MediaBox [0 0 99 99] >>\nendobj\n"
    b"4 0 obj\n  << /Font << /F1 5 0 R >> >>\nendobj\n"
    b"5 0 obj\n  << /Type /Font /Subtype /Type1 /Name /F1 /BaseFont /Helvetica >>\nendobj\n"
    b"6 0 obj\n  << /Length 44 >>\nstream\n  BT /F1 18 Tf 0 50 Td (live test) Tj ET\nendstream\n"
    b"endobj\nxref\n0 7\n0000000000 65535 f \n"
    b"trailer\n  << /Size 7 /Root 1 0 R >>\nstartxref\n 0\n%%EOF\n"
)


class TestFilesUploadDeleteRoundtrip:
    def test_upload_then_delete(self, tmp_path):
        from anthropic_handlers.tools._lib import files as files_lib

        path = tmp_path / "live_smoke.pdf"
        path.write_bytes(_TINY_PDF)

        uploaded = files_lib.upload_file(path=str(path))
        file_id = uploaded["id"]
        assert file_id
        assert uploaded["filename"] == "live_smoke.pdf"

        try:
            confirm = files_lib.delete_file(file_id=file_id)
            assert confirm["id"] == file_id
            assert confirm["deleted"] is True
        except Exception:
            # If delete fails (e.g. the file was already cleaned up on
            # the server side), re-raise so the test surfaces it.
            raise
