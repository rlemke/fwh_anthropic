"""Tests for the agent_sdk integration area.

The Claude Agent SDK is an *optional* dependency. These tests patch
the lazy importer (``_import_sdk``) so the suite stays runnable in
environments without ``claude-agent-sdk`` installed.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock SDK factory
# ---------------------------------------------------------------------------


def _async_iter(items):
    """Build an async iterator from a list of pre-built messages."""

    async def _gen():
        for item in items:
            yield item

    return _gen()


def _mock_sdk(*, messages, captured_options: dict | None = None):
    """Return a stand-in for the ``claude_agent_sdk`` module.

    ``messages`` is the list of objects to yield from ``query()``;
    ``captured_options`` (if given) receives the options object the
    caller passed in, so tests can assert on it.
    """
    sdk = SimpleNamespace()

    def _options(**kwargs):
        if captured_options is not None:
            captured_options["kwargs"] = kwargs
        return SimpleNamespace(**kwargs)

    def _query(*, prompt, options):  # noqa: ARG001 — captured via options
        if captured_options is not None:
            captured_options["prompt"] = prompt
        return _async_iter(messages)

    sdk.ClaudeAgentOptions = _options
    sdk.query = _query
    return sdk


def _assistant(text: str):
    return SimpleNamespace(type="assistant", text=text)


def _result(
    *,
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 25,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    text: str = "",
):
    return SimpleNamespace(
        type="result",
        stop_reason=stop_reason,
        result=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
    )


# ---------------------------------------------------------------------------
# _lib.run_agent — pure-function wrapper
# ---------------------------------------------------------------------------


class TestRunAgentSingleTurn:
    def test_returns_final_assistant_text(self):
        from anthropic_handlers.tools._lib import agent_sdk as ag

        sdk = _mock_sdk(
            messages=[
                _assistant("Working on it..."),
                _assistant("Here's the answer: 42"),
                _result(input_tokens=100, output_tokens=25),
            ]
        )
        with patch.object(ag, "_import_sdk", return_value=sdk):
            out = ag.run_agent(prompt="what's the meaning of life?")

        assert out["text"] == "Here's the answer: 42"
        assert out["turns"] == 2
        assert out["stop_reason"] == "end_turn"
        assert out["input_tokens"] == 100
        assert out["output_tokens"] == 25

    def test_trace_records_every_message(self):
        from anthropic_handlers.tools._lib import agent_sdk as ag

        sdk = _mock_sdk(
            messages=[
                _assistant("step 1"),
                _assistant("step 2"),
                _result(),
            ]
        )
        with patch.object(ag, "_import_sdk", return_value=sdk):
            out = ag.run_agent(prompt="multi-step")
        assert len(out["trace"]) == 3
        assert [t["type"] for t in out["trace"]] == ["assistant", "assistant", "result"]

    def test_cache_token_counts_surface(self):
        from anthropic_handlers.tools._lib import agent_sdk as ag

        sdk = _mock_sdk(
            messages=[
                _assistant("ok"),
                _result(
                    cache_creation_input_tokens=4096,
                    cache_read_input_tokens=8192,
                ),
            ]
        )
        with patch.object(ag, "_import_sdk", return_value=sdk):
            out = ag.run_agent(prompt="anything")
        assert out["cache_creation_input_tokens"] == 4096
        assert out["cache_read_input_tokens"] == 8192


class TestRunAgentOptionThreading:
    def test_options_carry_kwargs(self):
        from anthropic_handlers.tools._lib import agent_sdk as ag

        captured: dict = {}
        sdk = _mock_sdk(messages=[_result()], captured_options=captured)
        with patch.object(ag, "_import_sdk", return_value=sdk):
            ag.run_agent(
                prompt="hi",
                system="you are helpful",
                model="claude-opus-4-7",
                max_turns=3,
                allowed_tools=["Read", "Bash"],
                permission_mode="acceptEdits",
            )
        kw = captured["kwargs"]
        assert kw["system_prompt"] == "you are helpful"
        assert kw["model"] == "claude-opus-4-7"
        assert kw["max_turns"] == 3
        assert kw["allowed_tools"] == ["Read", "Bash"]
        assert kw["permission_mode"] == "acceptEdits"
        assert captured["prompt"] == "hi"

    def test_empty_allowed_tools_becomes_none(self):
        from anthropic_handlers.tools._lib import agent_sdk as ag

        captured: dict = {}
        sdk = _mock_sdk(messages=[_result()], captured_options=captured)
        with patch.object(ag, "_import_sdk", return_value=sdk):
            ag.run_agent(prompt="hi", allowed_tools=[])
        assert captured["kwargs"]["allowed_tools"] is None

    def test_blank_tool_strings_dropped(self):
        from anthropic_handlers.tools._lib import agent_sdk as ag

        captured: dict = {}
        sdk = _mock_sdk(messages=[_result()], captured_options=captured)
        with patch.object(ag, "_import_sdk", return_value=sdk):
            ag.run_agent(prompt="hi", allowed_tools=["Read", "", "  ", "Bash"])
        assert captured["kwargs"]["allowed_tools"] == ["Read", "Bash"]


class TestRunAgentValidation:
    def test_empty_prompt_raises(self):
        from anthropic_handlers.tools._lib import agent_sdk as ag

        with pytest.raises(ValueError, match="prompt"):
            ag.run_agent(prompt="")

    def test_zero_max_turns_raises(self):
        from anthropic_handlers.tools._lib import agent_sdk as ag

        with pytest.raises(ValueError, match="max_turns"):
            ag.run_agent(prompt="hi", max_turns=0)

    def test_missing_sdk_raises_helpful_error(self):
        """If the SDK isn't installed, the error message must point users at the extra."""
        from anthropic_handlers.tools._lib import agent_sdk as ag

        # Simulate the SDK not being importable by deleting any cached
        # entry and patching the import inside _import_sdk.
        sys.modules.pop("claude_agent_sdk", None)
        with patch.object(
            ag,
            "_import_sdk",
            side_effect=RuntimeError(
                "claude-agent-sdk is not installed. Install the optional extra:\n"
                "  pip install -e '.[agent_sdk]'"
            ),
        ):
            with pytest.raises(RuntimeError, match=r"\[agent_sdk\]"):
                ag.run_agent(prompt="hi")


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class TestRunAgentHandler:
    def test_parses_comma_separated_tools(self):
        from anthropic_handlers.handlers.agent_sdk import agent_sdk_handlers as ah
        from anthropic_handlers.tools._lib import agent_sdk as ag

        captured: dict = {}
        sdk = _mock_sdk(
            messages=[_assistant("did the thing"), _result()],
            captured_options=captured,
        )
        with patch.object(ag, "_import_sdk", return_value=sdk):
            out = ah._run_agent_handler({
                "prompt": "do it",
                "allowed_tools": "Read, Bash , Edit",
            })
        # Whitespace-stripped tool list reaches the SDK.
        assert captured["kwargs"]["allowed_tools"] == ["Read", "Bash", "Edit"]
        assert out["result"]["text"] == "did the thing"

    def test_trace_serialised_as_json_string(self):
        from anthropic_handlers.handlers.agent_sdk import agent_sdk_handlers as ah
        from anthropic_handlers.tools._lib import agent_sdk as ag

        sdk = _mock_sdk(messages=[_assistant("hi"), _result()])
        with patch.object(ag, "_import_sdk", return_value=sdk):
            out = ah._run_agent_handler({"prompt": "p"})
        trace = json.loads(out["result"]["trace_json"])
        assert isinstance(trace, list)
        assert trace[0]["type"] == "assistant"

    def test_permission_mode_threads_through(self):
        from anthropic_handlers.handlers.agent_sdk import agent_sdk_handlers as ah
        from anthropic_handlers.tools._lib import agent_sdk as ag

        captured: dict = {}
        sdk = _mock_sdk(messages=[_result()], captured_options=captured)
        with patch.object(ag, "_import_sdk", return_value=sdk):
            ah._run_agent_handler({
                "prompt": "p",
                "permission_mode": "bypassPermissions",
            })
        assert captured["kwargs"]["permission_mode"] == "bypassPermissions"

    def test_empty_permission_mode_falls_back_to_default(self):
        from anthropic_handlers.handlers.agent_sdk import agent_sdk_handlers as ah
        from anthropic_handlers.tools._lib import agent_sdk as ag

        captured: dict = {}
        sdk = _mock_sdk(messages=[_result()], captured_options=captured)
        with patch.object(ag, "_import_sdk", return_value=sdk):
            ah._run_agent_handler({"prompt": "p", "permission_mode": ""})
        assert captured["kwargs"]["permission_mode"] == "default"

    def test_no_step_log_doesnt_crash(self):
        from anthropic_handlers.handlers.agent_sdk import agent_sdk_handlers as ah
        from anthropic_handlers.tools._lib import agent_sdk as ag

        sdk = _mock_sdk(messages=[_assistant("ok"), _result()])
        with patch.object(ag, "_import_sdk", return_value=sdk):
            out = ah._run_agent_handler({"prompt": "p"})
        assert out["result"]["text"] == "ok"


# ---------------------------------------------------------------------------
# Dispatch + ExamplePackage
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_dispatch_has_run_agent(self):
        from anthropic_handlers.handlers.agent_sdk import agent_sdk_handlers as ah

        assert set(ah._DISPATCH.keys()) == {"anthropic.agent.RunAgent"}

    def test_handle_routes(self):
        from anthropic_handlers.handlers.agent_sdk import agent_sdk_handlers as ah
        from anthropic_handlers.tools._lib import agent_sdk as ag

        sdk = _mock_sdk(messages=[_assistant("routed"), _result()])
        with patch.object(ag, "_import_sdk", return_value=sdk):
            out = ah.handle({"_facet_name": "anthropic.agent.RunAgent", "prompt": "p"})
        assert out["result"]["text"] == "routed"

    def test_handle_rejects_unknown_facet(self):
        from anthropic_handlers.handlers.agent_sdk import agent_sdk_handlers as ah

        with pytest.raises(ValueError, match="Unknown facet"):
            ah.handle({"_facet_name": "anthropic.agent.NotAFacet"})

    def test_register_handlers_registers_run_agent(self):
        from anthropic_handlers.handlers.agent_sdk import agent_sdk_handlers as ah

        runner = MagicMock()
        ah.register_handlers(runner)
        registered = {
            call.kwargs["facet_name"] for call in runner.register_handler.call_args_list
        }
        assert registered == {"anthropic.agent.RunAgent"}


class TestPackageIntegration:
    def test_package_registers_run_agent(self):
        import anthropic_handlers

        runner = MagicMock()
        anthropic_handlers.example.register_handlers(runner)
        registered = {
            call.kwargs["facet_name"] for call in runner.register_handler.call_args_list
        }
        assert "anthropic.agent.RunAgent" in registered
