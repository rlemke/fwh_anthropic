"""Cross-area composition tests.

These tests don't run FFL workflows end-to-end (that requires a live
runner). Instead they:

1. Confirm the composition FFL file references only facets that exist
   in the handler dispatch tables — catches dangling references.
2. Drive the composed handler sequence with mocks to prove the
   JSON-bridge / shape contracts line up across areas (e.g. a Files
   UploadFile result feeds CreateMessageWithFile cleanly).
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


COMPOSITION_FFL = (
    Path(__file__).resolve().parent.parent
    / "src" / "anthropic_handlers" / "ffl" / "composition.ffl"
)


class TestCompositionFFLReferencesAreWired:
    def test_composition_ffl_exists(self):
        assert COMPOSITION_FFL.is_file(), f"missing {COMPOSITION_FFL}"

    def test_document_qa_references_known_facets(self):
        text = COMPOSITION_FFL.read_text()
        # Pull every fully-qualified facet call (`anthropic.<area>.<Facet>(`).
        calls = set(re.findall(r"\banthropic\.[a-z_]+\.[A-Z][A-Za-z0-9_]+", text))

        from anthropic_handlers.handlers import register_all_registry_handlers
        runner = MagicMock()
        register_all_registry_handlers(runner)
        registered = {
            call.kwargs["facet_name"]
            for call in runner.register_handler.call_args_list
        }

        missing = calls - registered
        assert not missing, (
            f"composition.ffl references facets that aren't wired in any "
            f"handler: {sorted(missing)}"
        )

    def test_document_qa_workflow_is_present(self):
        text = COMPOSITION_FFL.read_text()
        assert "workflow DocumentQA(" in text


# ---------------------------------------------------------------------------
# Drive the cross-area handler call sequence with mocks
# ---------------------------------------------------------------------------


def _upload_response(*, file_id="file_xyz"):
    return SimpleNamespace(
        id=file_id,
        type="file",
        filename="doc.pdf",
        mime_type="application/pdf",
        size_bytes=2048,
        created_at="2026-05-11T00:00:00Z",
        downloadable=True,
    )


def _messages_response(*, text="The doc discusses X."):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model="claude-sonnet-4-6",
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=42, output_tokens=12),
    )


class TestDocumentQAComposition:
    def test_files_upload_id_feeds_messages_create_with_file(self, tmp_path):
        """Simulate the DocumentQA workflow with mocked clients.

        Step 1: anthropic.files.UploadFile → returns {id: ...}
        Step 2: anthropic.messages.CreateMessageWithFile uses that id.
        The test asserts the file_id flows from step 1 to step 2's
        content blocks without loss or reformatting.
        """
        from anthropic_handlers.handlers.files import files_handlers as fh
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import files as files_lib
        from anthropic_handlers.tools._lib import messages as msg_lib

        # Set up the document on disk
        path = tmp_path / "contract.pdf"
        path.write_bytes(b"%PDF-1.4 placeholder")

        # Files client — mocked at the beta.files namespace.
        files_api = MagicMock()
        files_api.upload.return_value = _upload_response(file_id="file_contract")
        files_client = MagicMock()
        files_client.beta = SimpleNamespace(files=files_api)

        # Messages client — mocked at client.messages.create.
        messages_client = MagicMock()
        messages_client.messages.create = MagicMock(
            return_value=_messages_response(text="It terminates 2027-01-01."),
        )

        with patch.object(files_lib, "get_client", return_value=files_client):
            upload = fh._upload_file_handler({"path": str(path)})

        file_id = upload["result"]["id"]
        assert file_id == "file_contract"

        with patch.object(msg_lib, "get_client", return_value=messages_client):
            answer = mh._create_message_with_file_handler({
                "prompt": "When does the contract terminate?",
                "file_ids": file_id,
                "file_type": "document",
            })

        # The id flowed through unchanged and reached the SDK as a file block.
        content = messages_client.messages.create.call_args.kwargs["messages"][0]["content"]
        file_blocks = [b for b in content if b["type"] != "text"]
        assert len(file_blocks) == 1
        assert file_blocks[0]["source"]["file_id"] == "file_contract"
        assert file_blocks[0]["source"]["type"] == "file"

        # And the final answer surfaced as the workflow's `text` output.
        assert answer["result"]["text"] == "It terminates 2027-01-01."
        assert answer["result"]["file_count"] == 1
