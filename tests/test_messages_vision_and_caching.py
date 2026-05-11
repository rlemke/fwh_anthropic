"""Vision + prompt-caching surface tests for the messages area.

Mocks ``anthropic.Anthropic`` at the ``get_client`` boundary so no
real API calls are made.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------


def _block(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def _response(
    *,
    text: str = "Looks like a cat.",
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 20,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    model: str = "claude-sonnet-4-6",
):
    return SimpleNamespace(
        content=[_block(type="text", text=text)],
        model=model,
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
        ),
    )


def _mock_client(response):
    client = MagicMock()
    client.messages.create = MagicMock(return_value=response)
    return client


# 1x1 transparent PNG (header + IHDR + IDAT + IEND, hand-built).
_PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a"  # magic
    "0000000d49484452000000010000000108060000001f15c489"  # IHDR
    "0000000d49444154789c6300010000000500010d0a2db40000"  # IDAT (tiny zlib stream)
    "000049454e44ae426082"  # IEND
)


# ---------------------------------------------------------------------------
# Vision: _lib.create_message_with_images
# ---------------------------------------------------------------------------


class TestCreateMessageWithImagesURL:
    def test_sends_url_image_block(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client(_response(text="orange tabby"))
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.create_message_with_images(
                prompt="describe this cat",
                image_urls=["https://example.com/cat.jpg"],
            )
        assert out["text"] == "orange tabby"
        assert out["image_count"] == 1

        kwargs = client.messages.create.call_args.kwargs
        user_content = kwargs["messages"][0]["content"]
        # Image first, text last.
        assert user_content[0] == {
            "type": "image",
            "source": {"type": "url", "url": "https://example.com/cat.jpg"},
        }
        assert user_content[-1] == {"type": "text", "text": "describe this cat"}

    def test_multiple_urls_in_order(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client(_response())
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.create_message_with_images(
                prompt="compare these",
                image_urls=["https://example.com/a.jpg", "https://example.com/b.jpg"],
            )
        assert out["image_count"] == 2
        content = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert content[0]["source"]["url"] == "https://example.com/a.jpg"
        assert content[1]["source"]["url"] == "https://example.com/b.jpg"


class TestCreateMessageWithImagesPath:
    def test_reads_and_base64_encodes_local_png(self, tmp_path):
        from anthropic_handlers.tools._lib import messages as msg_lib

        img = tmp_path / "tiny.png"
        img.write_bytes(_PNG_1X1)

        client = _mock_client(_response())
        with patch.object(msg_lib, "get_client", return_value=client):
            msg_lib.create_message_with_images(
                prompt="what's in this image?", image_paths=[str(img)]
            )
        content = client.messages.create.call_args.kwargs["messages"][0]["content"]
        block = content[0]
        assert block["type"] == "image"
        assert block["source"]["type"] == "base64"
        assert block["source"]["media_type"] == "image/png"
        assert block["source"]["data"] == base64.b64encode(_PNG_1X1).decode("ascii")

    def test_unknown_extension_raises(self, tmp_path):
        from anthropic_handlers.tools._lib import messages as msg_lib

        bad = tmp_path / "no_extension"
        bad.write_bytes(b"some bytes")
        with pytest.raises(ValueError, match="media type"):
            msg_lib.create_message_with_images(
                prompt="hi", image_paths=[str(bad)]
            )

    def test_missing_file_raises(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        with pytest.raises(FileNotFoundError):
            msg_lib.create_message_with_images(
                prompt="hi", image_paths=["/nope/does_not_exist.png"]
            )


class TestCreateMessageWithImagesMixed:
    def test_urls_before_paths_in_content(self, tmp_path):
        from anthropic_handlers.tools._lib import messages as msg_lib

        img = tmp_path / "tiny.png"
        img.write_bytes(_PNG_1X1)
        client = _mock_client(_response())
        with patch.object(msg_lib, "get_client", return_value=client):
            msg_lib.create_message_with_images(
                prompt="describe both",
                image_urls=["https://example.com/x.jpg"],
                image_paths=[str(img)],
            )
        content = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert content[0]["source"]["type"] == "url"
        assert content[1]["source"]["type"] == "base64"
        assert content[2]["type"] == "text"


class TestCreateMessageWithImagesValidation:
    def test_no_images_raises(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        with pytest.raises(ValueError, match="image_urls or image_paths"):
            msg_lib.create_message_with_images(prompt="hi")

    def test_empty_prompt_raises(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        with pytest.raises(ValueError, match="prompt"):
            msg_lib.create_message_with_images(
                prompt="", image_urls=["https://example.com/a.jpg"]
            )


# ---------------------------------------------------------------------------
# Prompt caching: cache_system kwarg on create_message + create_message_with_tools
# ---------------------------------------------------------------------------


class TestCreateMessageCaching:
    def test_default_keeps_plain_string_system(self):
        """Without cache_system=True the SDK still gets the plain string."""
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client(_response())
        with patch.object(msg_lib, "get_client", return_value=client):
            msg_lib.create_message(prompt="hi", system="be brief")
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["system"] == "be brief"

    def test_cache_system_wraps_as_block_with_cache_control(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client(
            _response(cache_creation_input_tokens=8200, cache_read_input_tokens=0)
        )
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.create_message(
                prompt="hi", system="<huge system prompt>", cache_system=True
            )
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["system"] == [
            {
                "type": "text",
                "text": "<huge system prompt>",
                "cache_control": {"type": "ephemeral"},
            }
        ]
        assert out["cache_creation_input_tokens"] == 8200
        assert out["cache_read_input_tokens"] == 0

    def test_cache_system_without_system_raises(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        with pytest.raises(ValueError, match="cache_system=True"):
            msg_lib.create_message(prompt="hi", cache_system=True)

    def test_cache_read_surfaces_in_usage(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        # Second call simulates a cache hit: a non-zero cache_read.
        client = _mock_client(
            _response(cache_creation_input_tokens=0, cache_read_input_tokens=8200)
        )
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.create_message(
                prompt="hi again", system="<huge system prompt>", cache_system=True
            )
        assert out["cache_read_input_tokens"] == 8200


class TestCreateMessageWithToolsCaching:
    def test_cache_system_wraps_system(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        tools = [{
            "name": "do_thing",
            "description": "...",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }]
        client = _mock_client(_response())
        with patch.object(msg_lib, "get_client", return_value=client):
            msg_lib.create_message_with_tools(
                prompt="hi",
                tools=tools,
                system="big system block",
                cache_system=True,
            )
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}

    def test_cache_system_without_system_raises(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        tools = [{
            "name": "x",
            "description": "",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        }]
        with pytest.raises(ValueError, match="cache_system=True"):
            msg_lib.create_message_with_tools(
                prompt="hi", tools=tools, cache_system=True
            )


class TestVisionWithCaching:
    def test_cache_system_works_with_vision(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client(
            _response(cache_creation_input_tokens=1200, cache_read_input_tokens=0)
        )
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.create_message_with_images(
                prompt="describe",
                image_urls=["https://example.com/x.jpg"],
                system="vision-specialist system prompt",
                cache_system=True,
            )
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert out["cache_creation_input_tokens"] == 1200


# ---------------------------------------------------------------------------
# Handler-level coverage
# ---------------------------------------------------------------------------


class TestCreateMessageWithImagesHandler:
    def test_parses_comma_separated_strings(self, tmp_path):
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import messages as msg_lib

        img = tmp_path / "tiny.png"
        img.write_bytes(_PNG_1X1)

        client = _mock_client(_response(text="ok"))
        with patch.object(msg_lib, "get_client", return_value=client):
            out = mh._create_message_with_images_handler({
                "prompt": "describe",
                "image_urls": "https://a/x.jpg, https://a/y.jpg",
                "image_paths": str(img),
            })
        assert out["result"]["text"] == "ok"
        assert out["result"]["image_count"] == 3
        content = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert content[0]["source"]["url"] == "https://a/x.jpg"
        assert content[1]["source"]["url"] == "https://a/y.jpg"
        assert content[2]["source"]["type"] == "base64"

    def test_empty_image_lists_raises(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh

        with pytest.raises(ValueError, match="image_urls or image_paths"):
            mh._create_message_with_images_handler({"prompt": "hi"})

    def test_threads_cache_system_through(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client(_response())
        with patch.object(msg_lib, "get_client", return_value=client):
            mh._create_message_with_images_handler({
                "prompt": "p",
                "image_urls": "https://a/x.jpg",
                "system": "be brief",
                "cache_system": True,
            })
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


class TestCreateMessageCachingHandler:
    def test_handler_threads_cache_system(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client(_response(cache_creation_input_tokens=42))
        with patch.object(msg_lib, "get_client", return_value=client):
            out = mh._create_message_handler({
                "prompt": "hi",
                "system": "<long>",
                "cache_system": True,
            })
        assert out["result"]["cache_creation_input_tokens"] == 42
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


class TestDispatchWithImages:
    def test_dispatch_includes_images_facet(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh

        assert "anthropic.messages.CreateMessageWithImages" in mh._DISPATCH

    def test_dispatch_includes_images_after_extension(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh

        # Images facet is wired alongside the others; size is asserted
        # exactly in tests/test_messages_streaming.py::TestDispatchWithStream.
        assert "anthropic.messages.CreateMessageWithImages" in mh._DISPATCH
        assert len(mh._DISPATCH) >= 4
