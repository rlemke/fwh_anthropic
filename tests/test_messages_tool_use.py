"""Tool-use surface tests for the messages area.

Mocks ``anthropic.Anthropic`` at the ``get_client`` boundary so no
real API calls are made. The mock client maintains a queue of responses
so we can simulate the model emitting a ``tool_use`` block, the test
feeding back a ``tool_result``, and the model returning final text.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared mock factory
# ---------------------------------------------------------------------------


def _block(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def _response(*, content_blocks, stop_reason, input_tokens=10, output_tokens=5, model="claude-sonnet-4-6"):
    return SimpleNamespace(
        content=content_blocks,
        model=model,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _mock_client_with_queue(responses):
    """A mock client whose ``messages.create`` returns successive responses."""
    client = MagicMock()
    queue = list(responses)

    def _create(**kwargs):  # noqa: ARG001 — caller introspects via call_args_list
        if not queue:
            raise AssertionError("messages.create called more times than expected")
        return queue.pop(0)

    client.messages.create = MagicMock(side_effect=_create)
    return client


# ---------------------------------------------------------------------------
# _lib.create_message_with_tools — single round
# ---------------------------------------------------------------------------


WEATHER_TOOLS = [
    {
        "name": "get_weather",
        "description": "Return current weather for a location.",
        "input_schema": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
    }
]


class TestCreateMessageWithTools:
    def test_returns_text_only_response(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client_with_queue([
            _response(
                content_blocks=[_block(type="text", text="No tool needed.")],
                stop_reason="end_turn",
            )
        ])
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.create_message_with_tools(
                prompt="hello", tools=WEATHER_TOOLS
            )
        assert out["text"] == "No tool needed."
        assert out["tool_uses"] == []
        assert out["stop_reason"] == "end_turn"
        # tools were forwarded to the SDK
        assert client.messages.create.call_args.kwargs["tools"] == WEATHER_TOOLS

    def test_returns_tool_use_blocks(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client_with_queue([
            _response(
                content_blocks=[
                    _block(type="text", text="Let me check the weather."),
                    _block(
                        type="tool_use",
                        id="toolu_abc",
                        name="get_weather",
                        input={"location": "San Francisco"},
                    ),
                ],
                stop_reason="tool_use",
            )
        ])
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.create_message_with_tools(
                prompt="what's the weather in SF?", tools=WEATHER_TOOLS
            )
        assert out["text"] == "Let me check the weather."
        assert len(out["tool_uses"]) == 1
        use = out["tool_uses"][0]
        assert use["id"] == "toolu_abc"
        assert use["name"] == "get_weather"
        assert use["input"] == {"location": "San Francisco"}
        assert out["stop_reason"] == "tool_use"

    def test_messages_history_carries_assistant_turn(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client_with_queue([
            _response(
                content_blocks=[_block(type="text", text="hi back")],
                stop_reason="end_turn",
            )
        ])
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.create_message_with_tools(
                prompt="hi", tools=WEATHER_TOOLS
            )
        # Initial user + assistant reply
        assert out["messages"][0]["role"] == "user"
        assert out["messages"][1]["role"] == "assistant"
        # Assistant content is list of dict-form blocks
        assistant_content = out["messages"][1]["content"]
        assert isinstance(assistant_content, list)
        assert assistant_content[0] == {"type": "text", "text": "hi back"}

    def test_accepts_explicit_message_history(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client_with_queue([
            _response(
                content_blocks=[_block(type="text", text="continuing")],
                stop_reason="end_turn",
            )
        ])
        history = [
            {"role": "user", "content": "first turn"},
            {"role": "assistant", "content": "first reply"},
            {"role": "user", "content": "second turn"},
        ]
        with patch.object(msg_lib, "get_client", return_value=client):
            msg_lib.create_message_with_tools(prompt=history, tools=WEATHER_TOOLS)
        # The SDK saw the full history we passed (not wrapped/copied)
        assert client.messages.create.call_args.kwargs["messages"] == history

    def test_empty_tools_raises(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        with pytest.raises(ValueError, match="tools"):
            msg_lib.create_message_with_tools(prompt="hi", tools=[])

    def test_empty_prompt_raises(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        with pytest.raises(ValueError, match="prompt"):
            msg_lib.create_message_with_tools(prompt="", tools=WEATHER_TOOLS)


# ---------------------------------------------------------------------------
# _lib.run_tool_use_loop — multi-round Python convenience
# ---------------------------------------------------------------------------


class TestRunToolUseLoop:
    def test_completes_on_first_round_text_only(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client_with_queue([
            _response(
                content_blocks=[_block(type="text", text="2 + 2 = 4")],
                stop_reason="end_turn",
            )
        ])
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.run_tool_use_loop(
                prompt="what's 2+2?",
                tools=WEATHER_TOOLS,
                tool_impls={"get_weather": lambda **_: "irrelevant"},
            )
        assert out["text"] == "2 + 2 = 4"
        assert out["iterations"] == 1
        assert out["stop_reason"] == "end_turn"
        assert out["trace"] == []

    def test_runs_two_rounds_for_one_tool_call(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        # Round 1: model emits tool_use. Round 2: model returns final text.
        client = _mock_client_with_queue([
            _response(
                content_blocks=[
                    _block(type="text", text="Let me check."),
                    _block(
                        type="tool_use",
                        id="toolu_1",
                        name="get_weather",
                        input={"location": "SF"},
                    ),
                ],
                stop_reason="tool_use",
                input_tokens=20,
                output_tokens=10,
            ),
            _response(
                content_blocks=[_block(type="text", text="SF is sunny, 68°F.")],
                stop_reason="end_turn",
                input_tokens=30,
                output_tokens=12,
            ),
        ])
        impls = {"get_weather": MagicMock(return_value="sunny 68F")}
        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.run_tool_use_loop(
                prompt="weather in SF?", tools=WEATHER_TOOLS, tool_impls=impls
            )
        assert out["iterations"] == 2
        assert out["stop_reason"] == "end_turn"
        assert out["text"] == "SF is sunny, 68°F."
        # Token totals are summed across rounds
        assert out["input_tokens"] == 50
        assert out["output_tokens"] == 22
        # The tool was invoked once with the correct kwargs
        impls["get_weather"].assert_called_once_with(location="SF")
        # Trace records one entry per tool call
        assert len(out["trace"]) == 1
        assert out["trace"][0]["tool"] == "get_weather"
        assert out["trace"][0]["input"] == {"location": "SF"}
        assert out["trace"][0]["output"] == "sunny 68F"
        assert out["trace"][0]["is_error"] is False

    def test_tool_exception_surfaces_into_trace(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client_with_queue([
            _response(
                content_blocks=[_block(
                    type="tool_use", id="toolu_1", name="get_weather", input={"location": "Mars"}
                )],
                stop_reason="tool_use",
            ),
            _response(
                content_blocks=[_block(type="text", text="Can't get weather on Mars.")],
                stop_reason="end_turn",
            ),
        ])

        def _boom(**_):
            raise RuntimeError("no satellites there")

        with patch.object(msg_lib, "get_client", return_value=client):
            out = msg_lib.run_tool_use_loop(
                prompt="weather on Mars?",
                tools=WEATHER_TOOLS,
                tool_impls={"get_weather": _boom},
            )
        assert out["iterations"] == 2
        assert out["trace"][0]["is_error"] is True
        assert "no satellites" in out["trace"][0]["output"]

    def test_missing_tool_impl_raises_before_api_call(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        # No mocked client needed — the validation happens before any call.
        with pytest.raises(ValueError, match="tool implementations missing"):
            msg_lib.run_tool_use_loop(
                prompt="hi", tools=WEATHER_TOOLS, tool_impls={}
            )

    def test_hits_max_iterations(self):
        from anthropic_handlers.tools._lib import messages as msg_lib

        # Model keeps requesting tool calls forever.
        looping_response = _response(
            content_blocks=[_block(
                type="tool_use", id="toolu_x", name="get_weather", input={"location": "loop"}
            )],
            stop_reason="tool_use",
        )
        client = _mock_client_with_queue([looping_response] * 4)  # enough for the cap
        with patch.object(msg_lib, "get_client", return_value=client):
            with pytest.raises(RuntimeError, match="max_iterations"):
                msg_lib.run_tool_use_loop(
                    prompt="loop",
                    tools=WEATHER_TOOLS,
                    tool_impls={"get_weather": lambda **_: "yes"},
                    max_iterations=3,
                )


# ---------------------------------------------------------------------------
# handlers.messages — payload-shape adapter for CreateMessageWithTools
# ---------------------------------------------------------------------------


class TestCreateMessageWithToolsHandler:
    def test_wraps_result_with_json_bridge_fields(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client_with_queue([
            _response(
                content_blocks=[
                    _block(type="text", text="checking"),
                    _block(
                        type="tool_use", id="toolu_1", name="get_weather", input={"location": "SF"}
                    ),
                ],
                stop_reason="tool_use",
            )
        ])
        with patch.object(msg_lib, "get_client", return_value=client):
            out = mh._create_message_with_tools_handler({
                "prompt": "weather?",
                "tools_json": json.dumps(WEATHER_TOOLS),
            })
        result = out["result"]
        assert result["text"] == "checking"
        # JSON bridge fields decode back to the structured payload
        tool_uses = json.loads(result["tool_uses_json"])
        assert tool_uses[0]["name"] == "get_weather"
        messages = json.loads(result["messages_json"])
        assert messages[0]["role"] == "user"
        assert messages[-1]["role"] == "assistant"
        assert result["stop_reason"] == "tool_use"

    def test_requires_tools_json(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh

        with pytest.raises(ValueError, match="tools_json"):
            mh._create_message_with_tools_handler({"prompt": "hi"})

    def test_requires_prompt_or_messages(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh

        with pytest.raises(ValueError, match="prompt or messages_json"):
            mh._create_message_with_tools_handler({
                "tools_json": json.dumps(WEATHER_TOOLS),
            })

    def test_threads_messages_history_through_payload(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh
        from anthropic_handlers.tools._lib import messages as msg_lib

        client = _mock_client_with_queue([
            _response(
                content_blocks=[_block(type="text", text="ok")],
                stop_reason="end_turn",
            )
        ])
        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
        ]
        with patch.object(msg_lib, "get_client", return_value=client):
            mh._create_message_with_tools_handler({
                "tools_json": json.dumps(WEATHER_TOOLS),
                "messages_json": json.dumps(history),
            })
        # The SDK got the history we threaded through (the latest user turn
        # was *already in* history; we don't synthesise a new one).
        assert client.messages.create.call_args.kwargs["messages"] == history


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


class TestDispatchExtended:
    def test_dispatch_includes_tool_use_facet(self):
        from anthropic_handlers.handlers.messages import messages_handlers as mh

        assert "anthropic.messages.CreateMessageWithTools" in mh._DISPATCH

    def test_package_registers_messages_facets(self):
        import anthropic_handlers

        runner = MagicMock()
        anthropic_handlers.example.register_handlers(runner)
        registered = {
            call.kwargs["facet_name"] for call in runner.register_handler.call_args_list
        }
        # The four messages facets we've wired so far; other areas are still stubs.
        expected_subset = {
            "anthropic.messages.CreateMessage",
            "anthropic.messages.CountTokens",
            "anthropic.messages.CreateMessageWithTools",
            "anthropic.messages.CreateMessageWithImages",
        }
        assert expected_subset <= registered
        assert all(f.startswith("anthropic.messages.") for f in registered)
