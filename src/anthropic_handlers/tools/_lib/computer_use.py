"""Computer Use beta integration.

Reference:
- https://docs.anthropic.com/en/docs/build-with-claude/computer-use
- https://github.com/anthropics/anthropic-quickstarts (reference VM impl)

Computer Use is a Claude → virtual-desktop tool-use loop. The model
emits ``tool_use`` blocks requesting screen control actions (mouse,
keyboard, screenshots) plus optional bash + text-editor tools; the
caller executes each action against a sandboxed VM and feeds back the
result (typically a fresh screenshot). The loop continues until the
task is done.

Public surface:

- :func:`default_tools`           — build Anthropic's standard tool
  definitions (computer + bash + text_editor) with caller-tunable
  display dimensions.
- :func:`simulator_tool_impls`    — deterministic stub implementations.
  Useful for prompt-engineering dry runs and the FFL handler — *not*
  for real screen control.
- :func:`run_computer_use`        — drive the full loop, taking a
  caller-supplied ``tool_impls`` dict. Real users plug in xdotool /
  pyautogui / Docker-VM controllers here.

The SDK shape assumed::

    client.beta.messages.create(
        model=...,
        tools=[{"type": "computer_20241022", ...}, ...],
        betas=["computer-use-2024-10-22"],
        messages=...,
    )

If your SDK version uses a different beta-header convention or tool
type names, the small ``_invoke_messages`` helper is the only place
that needs to change.
"""

from __future__ import annotations

from typing import Any, Callable

from .client import DEFAULT_MODEL, get_client

# Tool-type identifiers per Anthropic's published beta tool versions.
# Pinned here so prompt-engineering remains reproducible — if you need
# a newer beta tool version, override via ``default_tools(versions=…)``.
DEFAULT_TOOL_VERSIONS: dict[str, str] = {
    "computer": "computer_20241022",
    "bash": "bash_20241022",
    "text_editor": "text_editor_20241022",
}
DEFAULT_BETA_HEADER: str = "computer-use-2024-10-22"


# ---------------------------------------------------------------------------
# Tool definitions + simulator impls
# ---------------------------------------------------------------------------


def default_tools(
    *,
    display_width_px: int = 1024,
    display_height_px: int = 768,
    display_number: int = 1,
    enable_bash: bool = True,
    enable_text_editor: bool = True,
    versions: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Build the canonical Anthropic Computer Use tool definitions."""
    if display_width_px <= 0 or display_height_px <= 0:
        raise ValueError("display dimensions must be positive")
    v = {**DEFAULT_TOOL_VERSIONS, **(versions or {})}
    tools: list[dict[str, Any]] = [
        {
            "type": v["computer"],
            "name": "computer",
            "display_width_px": int(display_width_px),
            "display_height_px": int(display_height_px),
            "display_number": int(display_number),
        }
    ]
    if enable_bash:
        tools.append({"type": v["bash"], "name": "bash"})
    if enable_text_editor:
        tools.append({"type": v["text_editor"], "name": "str_replace_editor"})
    return tools


def simulator_tool_impls() -> dict[str, Callable[..., Any]]:
    """Return a dict of deterministic stub implementations.

    Each impl returns a JSON-serialisable result shaped like what the
    real tool would produce, so the model receives a syntactically-
    correct tool_result and the loop terminates cleanly. Values are
    obvious placeholders — never use these for real screen control.
    """

    def _computer(action: str = "screenshot", **kwargs: Any) -> dict[str, Any]:
        return {
            "tool": "computer",
            "action": action,
            "simulated": True,
            "kwargs": kwargs,
        }

    def _bash(command: str = "", **kwargs: Any) -> dict[str, Any]:  # noqa: ARG001
        return {
            "tool": "bash",
            "command": command,
            "simulated": True,
            "stdout": "<simulated>",
            "stderr": "",
            "exit_code": 0,
        }

    def _text_editor(command: str = "view", **kwargs: Any) -> dict[str, Any]:
        return {
            "tool": "str_replace_editor",
            "command": command,
            "simulated": True,
            "kwargs": kwargs,
        }

    return {
        "computer": _computer,
        "bash": _bash,
        "str_replace_editor": _text_editor,
    }


# ---------------------------------------------------------------------------
# Loop driver
# ---------------------------------------------------------------------------


def _invoke_messages(client: Any, **kwargs: Any) -> Any:
    """Call ``messages.create`` on the SDK with computer-use beta header.

    Tries ``client.beta.messages.create(...)`` first; falls back to the
    GA path if the SDK version doesn't surface beta. Adds the
    ``betas=`` kwarg defensively (some SDK versions accept it, some
    expect ``extra_headers={"anthropic-beta": ...}`` instead).
    """
    messages_api = getattr(getattr(client, "beta", None), "messages", None) or client.messages
    try:
        return messages_api.create(betas=[DEFAULT_BETA_HEADER], **kwargs)
    except TypeError:
        # Older SDKs don't accept ``betas=``; fall back to header form.
        extra = kwargs.pop("extra_headers", {}) or {}
        extra = {**extra, "anthropic-beta": DEFAULT_BETA_HEADER}
        return messages_api.create(extra_headers=extra, **kwargs)


def _content_block_to_dict(block: Any) -> dict[str, Any]:
    btype = getattr(block, "type", "")
    if btype == "text":
        return {"type": "text", "text": getattr(block, "text", "")}
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": getattr(block, "id", ""),
            "name": getattr(block, "name", ""),
            "input": getattr(block, "input", {}) or {},
        }
    return {"type": btype}


def run_computer_use(
    *,
    task: str,
    tool_impls: dict[str, Callable[..., Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    system: str = "",
    model: str | None = None,
    max_tokens: int = 4096,
    max_iterations: int = 20,
    display_width_px: int = 1024,
    display_height_px: int = 768,
    display_number: int = 1,
    enable_bash: bool = True,
    enable_text_editor: bool = True,
) -> dict[str, Any]:
    """Run a Computer Use session end-to-end.

    *tool_impls* maps tool name → callable. When omitted, simulator
    stubs are used (useful for tests and dry runs but **never** for
    real screen control). For production use, plug in xdotool /
    pyautogui / Docker-VM controllers for each tool name.

    *tools* lets advanced callers override the default tool list
    (e.g. to pin different beta versions or add custom tools); omit
    to use :func:`default_tools` with the kwargs above.

    Returns the final assistant text + per-action trace + iteration
    count + token usage. Raises :class:`RuntimeError` if the loop
    hits ``max_iterations`` without ``end_turn``.
    """
    if not task:
        raise ValueError("task must not be empty")
    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")

    if tools is None:
        tools = default_tools(
            display_width_px=display_width_px,
            display_height_px=display_height_px,
            display_number=display_number,
            enable_bash=enable_bash,
            enable_text_editor=enable_text_editor,
        )
    if tool_impls is None:
        tool_impls = simulator_tool_impls()

    declared_tool_names = {t["name"] for t in tools}
    missing = declared_tool_names - set(tool_impls.keys())
    if missing:
        raise ValueError(
            f"tool_impls missing for declared tools: {sorted(missing)} "
            f"— either supply implementations or use simulator_tool_impls()"
        )

    client = get_client()
    model_id = model or DEFAULT_MODEL
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]

    trace: list[dict[str, Any]] = []
    last_text = ""
    last_stop_reason = ""
    input_tokens = 0
    output_tokens = 0

    for iteration in range(1, max_iterations + 1):
        kwargs: dict[str, Any] = {
            "model": model_id,
            "max_tokens": int(max_tokens),
            "tools": tools,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = _invoke_messages(client, **kwargs)
        blocks = [_content_block_to_dict(b) for b in (response.content or [])]
        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens += getattr(usage, "input_tokens", 0) or 0
            output_tokens += getattr(usage, "output_tokens", 0) or 0

        last_text = "".join(b.get("text", "") for b in blocks if b["type"] == "text")
        last_stop_reason = getattr(response, "stop_reason", "")
        tool_uses = [b for b in blocks if b["type"] == "tool_use"]

        messages = list(messages) + [{"role": "assistant", "content": blocks}]

        if last_stop_reason != "tool_use" or not tool_uses:
            return {
                "text": last_text,
                "stop_reason": last_stop_reason,
                "iterations": iteration,
                "trace": trace,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }

        tool_results = []
        for use in tool_uses:
            name = use["name"]
            action_input = use.get("input", {}) or {}
            impl = tool_impls.get(name)
            if impl is None:
                # Should never happen (validated above), but be defensive.
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": use["id"],
                    "content": f"no implementation for tool {name!r}",
                    "is_error": True,
                })
                trace.append({
                    "iteration": iteration,
                    "tool": name,
                    "input": action_input,
                    "is_error": True,
                    "output": None,
                })
                continue
            try:
                output = impl(**action_input)
                is_error = False
            except Exception as exc:  # pragma: no cover — surfaced into Claude's prompt
                output = f"tool {name!r} raised {type(exc).__name__}: {exc}"
                is_error = True
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": use["id"],
                "content": output if isinstance(output, (dict, list, str)) else str(output),
                "is_error": is_error,
            })
            trace.append({
                "iteration": iteration,
                "tool": name,
                "input": action_input,
                "output": output,
                "is_error": is_error,
            })
        messages = list(messages) + [{"role": "user", "content": tool_results}]

    raise RuntimeError(
        f"run_computer_use hit max_iterations={max_iterations} without end_turn "
        f"(last stop_reason={last_stop_reason!r}). Increase max_iterations, "
        f"check tool implementations, or simplify the task."
    )
