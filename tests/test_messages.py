"""Tests for the messages integration area.

The Anthropic client is mocked at the ``get_client`` boundary so no
real API calls are made. Each test reaches into
``anthropic_handlers.tools._lib.client.get_client`` via ``mocker`` /
``unittest.mock.patch``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock factory: builds an Anthropic-shaped fake whose ``messages.create``
# and ``messages.count_tokens`` return SDK-like objects.
# ---------------------------------------------------------------------------


def _mock_client(
    *,
    reply_text: str = "Hello, world.",
    stop_reason: str = "end_turn",
    input_tokens: int = 12,
    output_tokens: int = 7,
    count_tokens: int = 12,
):
    """Return a MagicMock shaped like ``anthropic.Anthropic``."""
    client = MagicMock()

    create_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=reply_text)],
        model="claude-sonnet-4-6",
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )
    client.messages.create = MagicMock(return_value=create_response)

    count_response = SimpleNamespace(input_tokens=count_tokens)
    client.messages.count_tokens = MagicMock(return_value=count_response)

    return client


# ---------------------------------------------------------------------------
# _lib.messages — pure-function wrappers
# ---------------------------------------------------------------------------


class TestCreateMessage:
    def test_returns_text_and_usage(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client(reply_text="2 + 2 = 4")
        with patch.object(msg_lib, "get_client", return_value=client):
            result = msg_lib.create_message(prompt="What is 2+2?")

        assert result["text"] == "2 + 2 = 4"
        assert result["stop_reason"] == "end_turn"
        assert result["input_tokens"] == 12
        assert result["output_tokens"] == 7
        # The SDK call used messages= with the user prompt
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["messages"] == [{"role": "user", "content": "What is 2+2?"}]
        assert "system" not in kwargs

    def test_includes_system_when_provided(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client()
        with patch.object(msg_lib, "get_client", return_value=client):
            msg_lib.create_message(
                prompt="hi", system="You are a helpful chatbot."
            )
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["system"] == "You are a helpful chatbot."

    def test_uses_default_model_when_none(self):
        from anthropic_handlers.tools._lib import client as client_mod
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client()
        with patch.object(msg_lib, "get_client", return_value=client):
            msg_lib.create_message(prompt="hi")

        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["model"] == client_mod.DEFAULT_MODEL

    def test_uses_override_model(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client()
        with patch.object(msg_lib, "get_client", return_value=client):
            msg_lib.create_message(prompt="hi", model="claude-opus-4-7")
        assert client.messages.create.call_args.kwargs["model"] == "claude-opus-4-7"

    def test_empty_prompt_raises(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        with pytest.raises(ValueError, match="prompt"):
            msg_lib.create_message(prompt="")

    def test_skips_non_text_blocks(self):
        """Tool-use blocks shouldn't bleed into the .text concat."""
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client()
        client.messages.create.return_value = SimpleNamespace(
            content=[
                SimpleNamespace(type="tool_use", text="<should-not-appear>"),
                SimpleNamespace(type="text", text="Final answer."),
            ],
            model="claude-sonnet-4-6",
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=5, output_tokens=3),
        )
        with patch.object(msg_lib, "get_client", return_value=client):
            result = msg_lib.create_message(prompt="hi")
        assert result["text"] == "Final answer."


class TestCountTokens:
    def test_returns_input_tokens(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client(count_tokens=42)
        with patch.object(msg_lib, "get_client", return_value=client):
            result = msg_lib.count_tokens(prompt="check this")
        assert result["input_tokens"] == 42

    def test_includes_system_when_provided(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client()
        with patch.object(msg_lib, "get_client", return_value=client):
            msg_lib.count_tokens(prompt="hi", system="be brief")
        kwargs = client.messages.count_tokens.call_args.kwargs
        assert kwargs["system"] == "be brief"

    def test_empty_prompt_raises(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        with pytest.raises(ValueError, match="prompt"):
            msg_lib.count_tokens(prompt="")


# ---------------------------------------------------------------------------
# handlers.messages.messages_handlers — payload-shape adapters
# ---------------------------------------------------------------------------


class TestMessagesHandlers:
    def test_create_message_handler_wraps_result(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client(reply_text="OK.")
        with patch.object(msg_lib, "get_client", return_value=client):
            out = mh._create_message_handler({"prompt": "test"})

        assert out["result"]["text"] == "OK."
        assert out["result"]["model"] == "claude-sonnet-4-6"
        assert out["result"]["stop_reason"] == "end_turn"
        assert out["result"]["input_tokens"] == 12
        assert out["result"]["output_tokens"] == 7
        # Cache fields default to 0 when the request didn't use caching.
        assert out["result"]["cache_creation_input_tokens"] == 0
        assert out["result"]["cache_read_input_tokens"] == 0

    def test_count_tokens_handler_wraps_result(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client(count_tokens=99)
        with patch.object(msg_lib, "get_client", return_value=client):
            out = mh._count_tokens_handler({"prompt": "check"})

        assert out["count"]["input_tokens"] == 99

    def test_create_message_handler_threads_kwargs(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client()
        with patch.object(msg_lib, "get_client", return_value=client):
            mh._create_message_handler({
                "prompt": "hi",
                "system": "you are a helper",
                "model": "claude-opus-4-7",
                "max_tokens": 256,
                "temperature": 0.5,
            })
        kw = client.messages.create.call_args.kwargs
        assert kw["model"] == "claude-opus-4-7"
        assert kw["max_tokens"] == 256
        assert kw["temperature"] == 0.5
        assert kw["system"] == "you are a helper"


# ---------------------------------------------------------------------------
# Dispatch + registration
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_dispatch_has_expected_facets(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh

        # CreateMessage + CountTokens always; tool-use facet is covered
        # in tests/test_messages_tool_use.py.
        assert {
            "anthropic.messages.CreateMessage",
            "anthropic.messages.CountTokens",
        } <= set(mh._DISPATCH.keys())

    def test_handle_routes_to_create_message(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client(reply_text="routed.")
        with patch.object(msg_lib, "get_client", return_value=client):
            out = mh.handle({
                "_facet_name": "anthropic.messages.CreateMessage",
                "prompt": "hi",
            })
        assert out["result"]["text"] == "routed."

    def test_handle_rejects_unknown_facet(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh

        with pytest.raises(ValueError, match="Unknown facet"):
            mh.handle({"_facet_name": "anthropic.messages.NotAFacet"})

    def test_register_handlers_registers_each_facet(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh

        runner = MagicMock()
        mh.register_handlers(runner)
        registered = {
            call.kwargs["facet_name"] for call in runner.register_handler.call_args_list
        }
        # Each _DISPATCH entry registers exactly once.
        assert registered == set(mh._DISPATCH.keys())
        assert runner.register_handler.call_count == len(mh._DISPATCH)
        assert {
            "anthropic.messages.CreateMessage",
            "anthropic.messages.CountTokens",
        } <= registered


class TestPackageRegistration:
    def test_register_all_registry_handlers_includes_messages(self):
        """ExamplePackage's top-level register hook must wire the messages area."""
        import anthropic_handlers

        runner = MagicMock()
        anthropic_handlers.domain.register_handlers(runner)
        registered = {
            call.kwargs["facet_name"] for call in runner.register_handler.call_args_list
        }
        assert "anthropic.messages.CreateMessage" in registered
        assert "anthropic.messages.CountTokens" in registered
        # Other wired areas (e.g. anthropic.agent.*) may add to the set.
        assert any(f.startswith("anthropic.messages.") for f in registered)


# ---------------------------------------------------------------------------
# CreateMessageWithFile — cross-area (Messages references Files-API uploads)
# ---------------------------------------------------------------------------


def _file_message_mock_client(*, reply_text="The doc says X."):
    """Client whose messages.create echoes how many file blocks it received."""
    client = MagicMock()
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=reply_text)],
        model="claude-sonnet-4-6",
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=20, output_tokens=4),
    )
    client.messages.create = MagicMock(return_value=response)
    return client


class TestCreateMessageWithFile:
    def test_packs_files_as_document_blocks_then_text(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _file_message_mock_client()
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.create_message_with_file(
                prompt="Summarise this contract.",
                file_ids=["file_a", "file_b"],
            )
        kwargs = client.messages.create.call_args.kwargs
        content = kwargs["messages"][0]["content"]
        # Two file blocks followed by one text block, in order.
        assert [b["type"] for b in content] == ["document", "document", "text"]
        assert content[0]["source"] == {"type": "file", "file_id": "file_a"}
        assert content[1]["source"] == {"type": "file", "file_id": "file_b"}
        assert content[2]["text"] == "Summarise this contract."
        assert out["file_count"] == 2
        assert out["text"] == "The doc says X."

    def test_supports_image_blocks(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _file_message_mock_client()
        with patch.object(msg_lib, "get_client", return_value=client):
            msg_lib.create_message_with_file(
                prompt="What's in this picture?",
                file_ids=["file_img"],
                file_type="image",
            )
        content = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert content[0]["type"] == "image"

    def test_rejects_unknown_file_type(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        with pytest.raises(ValueError, match="file_type"):
            msg_lib.create_message_with_file(
                prompt="hi", file_ids=["file_a"], file_type="audio",
            )

    def test_empty_file_ids_raises(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        with pytest.raises(ValueError, match="file_ids"):
            msg_lib.create_message_with_file(prompt="hi", file_ids=[])

    def test_handler_parses_comma_separated_ids(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _file_message_mock_client(reply_text="seen 3 files")
        with patch.object(msg_lib, "get_client", return_value=client):
            out = mh._create_message_with_file_handler({
                "prompt": "describe these",
                "file_ids": "file_a, file_b ,file_c",
                "file_type": "document",
            })
        assert out["result"]["text"] == "seen 3 files"
        assert out["result"]["file_count"] == 3
        content = client.messages.create.call_args.kwargs["messages"][0]["content"]
        ids = [b["source"]["file_id"] for b in content if b["type"] != "text"]
        assert ids == ["file_a", "file_b", "file_c"]

    def test_handler_rejects_missing_file_ids(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh

        with pytest.raises(ValueError, match="file_ids"):
            mh._create_message_with_file_handler({"prompt": "hi", "file_ids": "  ,  "})

    def test_dispatch_routes_create_message_with_file(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh

        assert "anthropic.messages.CreateMessageWithFile" in mh._DISPATCH
