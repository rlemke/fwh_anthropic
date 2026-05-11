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

        assert out == {"result": {
            "text": "OK.",
            "model": "claude-sonnet-4-6",
            "stop_reason": "end_turn",
            "input_tokens": 12,
            "output_tokens": 7,
        }}

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

        assert set(mh._DISPATCH.keys()) == {
            "anthropic.messages.CreateMessage",
            "anthropic.messages.CountTokens",
        }

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
        assert runner.register_handler.call_count == 2
        registered = {
            call.kwargs["facet_name"] for call in runner.register_handler.call_args_list
        }
        assert registered == {
            "anthropic.messages.CreateMessage",
            "anthropic.messages.CountTokens",
        }


class TestPackageRegistration:
    def test_register_all_registry_handlers_includes_messages(self):
        """ExamplePackage's top-level register hook must wire the messages area."""
        import anthropic_handlers

        runner = MagicMock()
        anthropic_handlers.example.register_handlers(runner)
        registered = {
            call.kwargs["facet_name"] for call in runner.register_handler.call_args_list
        }
        assert "anthropic.messages.CreateMessage" in registered
        assert "anthropic.messages.CountTokens" in registered
        # Exactly 2 facets right now (the other areas are still stubs).
        assert len(registered) == 2
