"""Live end-to-end test for the DocumentQA composition.

Exercises the Files + Messages path: upload a tiny PDF, ask Claude a
question that references it, then delete the file. This is the only
live test that touches two areas — the rest are per-area smokes.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.live


from tests.live.test_files_live import _TINY_PDF  # noqa: E402


class TestDocumentQALive:
    def test_upload_ask_delete(self, tmp_path):
        from anthropic_handlers.tools._lib import files as files_lib
        from anthropic_handlers.tools._lib import messages as msg_lib

        path = tmp_path / "doc_qa_live.pdf"
        path.write_bytes(_TINY_PDF)

        uploaded = files_lib.upload_file(path=str(path))
        file_id = uploaded["id"]
        try:
            answer = msg_lib.create_message_with_file(
                prompt="Reply with the literal phrase from the document, nothing else.",
                file_ids=[file_id],
                file_type="document",
                max_tokens=64,
                temperature=0.0,
            )
            assert isinstance(answer["text"], str)
            assert answer["file_count"] == 1
            assert answer["stop_reason"] in (
                "end_turn", "max_tokens", "stop_sequence",
            )
        finally:
            files_lib.delete_file(file_id=file_id)
