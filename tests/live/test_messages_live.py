"""Live smoke test for the messages area.

Sends a tiny prompt against the real Anthropic API and asserts the
shape of the returned dict. Skipped unless ``--run-live`` is passed
and ``ANTHROPIC_API_KEY`` is set (see ``tests/conftest.py``).
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.live


class TestCreateMessageLive:
    def test_arithmetic_prompt_returns_text(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        out = msg_lib.create_message(
            prompt="Reply with just the digit: 2 + 2 = ?",
            max_tokens=16,
            temperature=0.0,
        )
        assert isinstance(out["text"], str)
        assert out["text"].strip() != ""
        assert out["stop_reason"] in ("end_turn", "max_tokens", "stop_sequence")
        assert out["input_tokens"] > 0
        assert out["output_tokens"] > 0


class TestCountTokensLive:
    def test_returns_positive_token_count(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        out = msg_lib.count_tokens(prompt="Hello, world!")
        assert out["input_tokens"] > 0
