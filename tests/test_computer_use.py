"""Tests for the computer_use integration area.

Mocks ``client.beta.messages.create`` with a queue so the loop can be
driven through multiple rounds (tool_use → tool_result → end_turn)
without any real VM or API calls.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _block(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def _response(*, content_blocks, stop_reason, input_tokens=10, output_tokens=5):
    return SimpleNamespace(
        content=content_blocks,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _mock_client_with_queue(responses):
    """Client whose ``beta.messages.create`` returns successive responses."""
    client = MagicMock()
    queue = list(responses)

    def _create(**kwargs):  # noqa: ARG001 — caller introspects via call_args_list
        if not queue:
            raise AssertionError("messages.create called more times than expected")
        return queue.pop(0)

    client.beta.messages.create = MagicMock(side_effect=_create)
    return client


# ---------------------------------------------------------------------------
# default_tools + simulator_tool_impls
# ---------------------------------------------------------------------------


class TestDefaultTools:
    def test_includes_computer_bash_text_editor_by_default(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        tools = cu.default_tools()
        names = [t["name"] for t in tools]
        assert names == ["computer", "bash", "str_replace_editor"]

    def test_computer_tool_carries_display_dims(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        tools = cu.default_tools(display_width_px=2048, display_height_px=1536, display_number=2)
        cpu = next(t for t in tools if t["name"] == "computer")
        assert cpu["display_width_px"] == 2048
        assert cpu["display_height_px"] == 1536
        assert cpu["display_number"] == 2
        # The type pins the Anthropic beta version.
        assert cpu["type"] == "computer_20241022"

    def test_can_disable_bash_and_text_editor(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        tools = cu.default_tools(enable_bash=False, enable_text_editor=False)
        assert [t["name"] for t in tools] == ["computer"]

    def test_invalid_dims_raise(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        with pytest.raises(ValueError, match="dimensions"):
            cu.default_tools(display_width_px=0)


class TestSimulatorImpls:
    def test_returns_three_callables(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        impls = cu.simulator_tool_impls()
        assert set(impls.keys()) == {"computer", "bash", "str_replace_editor"}
        for fn in impls.values():
            assert callable(fn)

    def test_computer_stub_returns_simulated_flag(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        impls = cu.simulator_tool_impls()
        result = impls["computer"](action="screenshot")
        assert result["simulated"] is True
        assert result["action"] == "screenshot"

    def test_bash_stub_shape(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        impls = cu.simulator_tool_impls()
        result = impls["bash"](command="ls -la")
        assert result["simulated"] is True
        assert result["exit_code"] == 0


# ---------------------------------------------------------------------------
# run_computer_use loop
# ---------------------------------------------------------------------------


class TestRunComputerUseSingleRound:
    def test_immediate_end_turn(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        client = _mock_client_with_queue([
            _response(
                content_blocks=[_block(type="text", text="Task understood.")],
                stop_reason="end_turn",
                input_tokens=15,
                output_tokens=4,
            )
        ])
        with patch.object(cu, "get_client", return_value=client):
            out = cu.run_computer_use(task="show me a screenshot")
        assert out["text"] == "Task understood."
        assert out["stop_reason"] == "end_turn"
        assert out["iterations"] == 1
        assert out["trace"] == []
        assert out["input_tokens"] == 15
        assert out["output_tokens"] == 4


class TestRunComputerUseMultiRound:
    def test_two_round_tool_exchange(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        # Round 1: model requests a screenshot.
        # Round 2: model returns final text.
        client = _mock_client_with_queue([
            _response(
                content_blocks=[
                    _block(type="text", text="Taking a screenshot."),
                    _block(
                        type="tool_use",
                        id="toolu_1",
                        name="computer",
                        input={"action": "screenshot"},
                    ),
                ],
                stop_reason="tool_use",
                input_tokens=20,
                output_tokens=10,
            ),
            _response(
                content_blocks=[_block(type="text", text="I see a desktop.")],
                stop_reason="end_turn",
                input_tokens=30,
                output_tokens=5,
            ),
        ])
        with patch.object(cu, "get_client", return_value=client):
            out = cu.run_computer_use(task="describe what's on the screen")

        assert out["iterations"] == 2
        assert out["text"] == "I see a desktop."
        assert out["input_tokens"] == 50
        assert out["output_tokens"] == 15
        # Trace records one action per tool_use.
        assert len(out["trace"]) == 1
        assert out["trace"][0]["tool"] == "computer"
        assert out["trace"][0]["input"] == {"action": "screenshot"}
        assert out["trace"][0]["is_error"] is False
        # The output passed back to Claude is the simulator stub's dict.
        assert out["trace"][0]["output"]["simulated"] is True

    def test_max_iterations_raises(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        # Model loops forever requesting tool calls.
        looping = _response(
            content_blocks=[_block(
                type="tool_use", id="toolu_x", name="computer", input={"action": "key", "key": "loop"}
            )],
            stop_reason="tool_use",
        )
        client = _mock_client_with_queue([looping] * 4)
        with patch.object(cu, "get_client", return_value=client):
            with pytest.raises(RuntimeError, match="max_iterations"):
                cu.run_computer_use(
                    task="never end",
                    max_iterations=3,
                )


class TestRunComputerUseValidation:
    def test_empty_task_raises(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        with pytest.raises(ValueError, match="task"):
            cu.run_computer_use(task="")

    def test_zero_max_iterations_raises(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        with pytest.raises(ValueError, match="max_iterations"):
            cu.run_computer_use(task="hi", max_iterations=0)

    def test_missing_tool_impl_for_declared_tool_raises(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        # Default tools include `bash`; passing an impl dict that lacks
        # bash should fail upfront — before any API call.
        with pytest.raises(ValueError, match="tool_impls missing"):
            cu.run_computer_use(
                task="hi",
                tool_impls={"computer": lambda **_: {}},  # missing bash + str_replace_editor
            )


class TestSDKShapeFallbacks:
    def test_uses_beta_namespace_when_available(self):
        from anthropic_handlers.tools._lib import computer_use as cu

        client = _mock_client_with_queue([
            _response(content_blocks=[_block(type="text", text="ok")], stop_reason="end_turn")
        ])
        with patch.object(cu, "get_client", return_value=client):
            cu.run_computer_use(task="hi")
        # The beta namespace was hit, and `betas=` was included.
        kwargs = client.beta.messages.create.call_args.kwargs
        assert kwargs["betas"] == [cu.DEFAULT_BETA_HEADER]


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class TestComputerUseHandler:
    def test_handler_uses_simulator_by_default(self):
        from anthropic_handlers.handlers.computer_use import computer_use_handlers as ch
        from anthropic_handlers.tools._lib import computer_use as cu

        client = _mock_client_with_queue([
            _response(content_blocks=[_block(type="text", text="done")], stop_reason="end_turn")
        ])
        with patch.object(cu, "get_client", return_value=client):
            out = ch._run_computer_use_session_handler({"task": "take a screenshot"})
        assert out["result"]["text"] == "done"
        assert out["result"]["mode"] == "simulator"

    def test_handler_threads_display_kwargs(self):
        from anthropic_handlers.handlers.computer_use import computer_use_handlers as ch
        from anthropic_handlers.tools._lib import computer_use as cu

        client = _mock_client_with_queue([
            _response(content_blocks=[_block(type="text", text="ok")], stop_reason="end_turn")
        ])
        with patch.object(cu, "get_client", return_value=client):
            ch._run_computer_use_session_handler({
                "task": "hi",
                "display_width_px": 1920,
                "display_height_px": 1080,
            })
        tools = client.beta.messages.create.call_args.kwargs["tools"]
        cpu = next(t for t in tools if t["name"] == "computer")
        assert cpu["display_width_px"] == 1920
        assert cpu["display_height_px"] == 1080

    def test_handler_trace_serialised_as_json(self):
        from anthropic_handlers.handlers.computer_use import computer_use_handlers as ch
        from anthropic_handlers.tools._lib import computer_use as cu

        client = _mock_client_with_queue([
            _response(
                content_blocks=[_block(
                    type="tool_use", id="toolu_1", name="computer",
                    input={"action": "screenshot"},
                )],
                stop_reason="tool_use",
            ),
            _response(
                content_blocks=[_block(type="text", text="done")],
                stop_reason="end_turn",
            ),
        ])
        with patch.object(cu, "get_client", return_value=client):
            out = ch._run_computer_use_session_handler({"task": "hi"})
        trace = json.loads(out["result"]["trace_json"])
        assert isinstance(trace, list)
        assert trace[0]["tool"] == "computer"

    def test_dispatch_has_run_computer_use_session(self):
        from anthropic_handlers.handlers.computer_use import computer_use_handlers as ch

        assert set(ch._DISPATCH.keys()) == {
            "anthropic.computer.RunComputerUseSession",
        }

    def test_package_registers_computer_use(self):
        import anthropic_handlers

        runner = MagicMock()
        anthropic_handlers.domain.register_handlers(runner)
        registered = {
            call.kwargs["facet_name"] for call in runner.register_handler.call_args_list
        }
        assert "anthropic.computer.RunComputerUseSession" in registered
