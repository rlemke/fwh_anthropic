"""Streaming surface tests for the messages area.

Mocks the SDK's ``messages.stream`` context manager — both
``__enter__`` / ``__exit__`` and the ``text_stream`` iterator —
so no real API calls are made.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------


def _final_message(
    *,
    text: str,
    stop_reason: str = "end_turn",
    input_tokens: int = 20,
    output_tokens: int = 8,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    model: str = "claude-sonnet-4-6",
):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model=model,
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
        ),
    )


def _mock_streaming_client(*, chunks: list[str], final):
    """Return a MagicMock whose ``messages.stream`` ctx mgr yields ``chunks``."""
    client = MagicMock()
    stream_obj = MagicMock()
    stream_obj.text_stream = iter(chunks)
    stream_obj.get_final_message.return_value = final

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=stream_obj)
    ctx.__exit__ = MagicMock(return_value=False)
    client.messages.stream = MagicMock(return_value=ctx)
    return client


# ---------------------------------------------------------------------------
# _lib.stream_message
# ---------------------------------------------------------------------------


class TestStreamMessage:
    def test_returns_final_text_and_chunk_count(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_streaming_client(
            chunks=["Hello, ", "world", "!"],
            final=_final_message(text="Hello, world!"),
        )
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.stream_message(prompt="say hi")

        assert out["text"] == "Hello, world!"
        assert out["chunk_count"] == 3
        assert out["stop_reason"] == "end_turn"
        assert out["input_tokens"] == 20
        assert out["output_tokens"] == 8
        assert out["cache_creation_input_tokens"] == 0
        assert out["cache_read_input_tokens"] == 0

    def test_on_chunk_is_invoked_per_delta(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_streaming_client(
            chunks=["a", "b", "c"],
            final=_final_message(text="abc"),
        )
        received: list[str] = []
        with patch.object(msg_lib, "get_client", return_value=client):
            msg_lib.stream_message(prompt="alphabet", on_chunk=received.append)
        assert received == ["a", "b", "c"]

    def test_skips_empty_chunks(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_streaming_client(
            chunks=["a", "", "b", ""],
            final=_final_message(text="ab"),
        )
        received: list[str] = []
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.stream_message(prompt="alphabet", on_chunk=received.append)
        # chunk_count and on_chunk both reflect the non-empty chunks only.
        assert out["chunk_count"] == 2
        assert received == ["a", "b"]

    def test_empty_prompt_raises(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        with pytest.raises(ValueError, match="prompt"):
            msg_lib.stream_message(prompt="")

    def test_cache_system_wraps_block(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_streaming_client(
            chunks=["hi"],
            final=_final_message(text="hi", cache_creation_input_tokens=1200),
        )
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.stream_message(
                prompt="hi", system="<big system>", cache_system=True
            )
        # The SDK saw a content-block system with cache_control.
        kwargs = client.messages.stream.call_args.kwargs
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
        # Cache token counts from the final message surface in the return.
        assert out["cache_creation_input_tokens"] == 1200

    def test_cache_system_without_system_raises(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        with pytest.raises(ValueError, match="cache_system=True"):
            msg_lib.stream_message(prompt="hi", cache_system=True)

    def test_forwards_model_override_to_stream(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_streaming_client(
            chunks=["a"], final=_final_message(text="a")
        )
        with patch.object(msg_lib, "get_client", return_value=client):
            msg_lib.stream_message(prompt="hi", model="claude-opus-4-7")
        assert client.messages.stream.call_args.kwargs["model"] == "claude-opus-4-7"


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class TestStreamMessageHandler:
    def test_emits_per_chunk_log_entries(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_streaming_client(
            chunks=["foo ", "bar"],
            final=_final_message(text="foo bar"),
        )
        log_lines: list[str] = []
        payload = {"prompt": "go", "_step_log": log_lines.append}

        with patch.object(msg_lib, "get_client", return_value=client):
            out = mh._create_message_stream_handler(payload)

        assert out["result"]["text"] == "foo bar"
        assert out["result"]["chunk_count"] == 2
        # One header line + one per chunk.
        chunk_lines = [line for line in log_lines if line.startswith("chunk:")]
        assert len(chunk_lines) == 2
        assert "foo" in chunk_lines[0]
        assert "bar" in chunk_lines[1]

    def test_threads_cache_system(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_streaming_client(
            chunks=["x"],
            final=_final_message(text="x", cache_read_input_tokens=4096),
        )
        with patch.object(msg_lib, "get_client", return_value=client):
            out = mh._create_message_stream_handler({
                "prompt": "hi",
                "system": "<long>",
                "cache_system": True,
            })
        kwargs = client.messages.stream.call_args.kwargs
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert out["result"]["cache_read_input_tokens"] == 4096

    def test_works_without_step_log(self):
        """No _step_log key in the payload shouldn't crash."""
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_streaming_client(
            chunks=["a", "b"], final=_final_message(text="ab")
        )
        with patch.object(msg_lib, "get_client", return_value=client):
            out = mh._create_message_stream_handler({"prompt": "hi"})
        assert out["result"]["text"] == "ab"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


class TestDispatchWithStream:
    def test_dispatch_includes_stream_facet(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh

        assert "anthropic.messages.CreateMessageStream" in mh._DISPATCH

    def test_dispatch_size_grows(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh

        # At least: CreateMessage + CountTokens + tools + images + stream.
        # Cross-area facets (CreateMessageWithFile etc.) may push this higher.
        assert len(mh._DISPATCH) >= 5
