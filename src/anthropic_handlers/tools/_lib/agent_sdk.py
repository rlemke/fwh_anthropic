"""Claude Agent SDK integration.

Reference: https://github.com/anthropics/claude-agent-sdk-python

The Agent SDK wraps Claude Code's headless runtime so Python callers
can stand up autonomous agents with planning, memory, tool use, and
permission gating out of the box. This module exposes a *single*
sync entry point — :func:`run_agent` — for the common "single
prompt, run to completion, return the final result" flow. Multi-turn
interactive sessions (:class:`ClaudeSDKClient`) can be wrapped later
as separate facets.

The SDK is **async** and is an *optional* dependency under
``[agent_sdk]``::

    pip install -e ".[agent_sdk]"

This module lazy-imports the SDK inside :func:`run_agent` so the
package remains importable in environments where ``claude-agent-sdk``
isn't installed; calling :func:`run_agent` without it raises a clear
error.

Assumed SDK shape — this code was written defensively. The exact API
may shift slightly between SDK versions; the wrapper is small enough
that adapting it is a localised change:

- ``claude_agent_sdk.query(prompt, options)`` returns an async iterable
  of ``Message`` objects (assistant text, user-side tool results, and a
  terminal ``ResultMessage`` carrying token usage + stop reason).
- ``claude_agent_sdk.ClaudeAgentOptions(...)`` configures the session
  (model, system_prompt, allowed_tools, permission_mode, max_turns).
"""

from __future__ import annotations

import asyncio
from typing import Any

from .client import DEFAULT_MODEL


def _import_sdk() -> Any:
    """Lazy-import ``claude_agent_sdk`` with a friendly error message."""
    try:
        import claude_agent_sdk  # noqa: PLC0415 — lazy import
    except ImportError as exc:  # pragma: no cover — covered via mocked tests
        raise RuntimeError(
            "claude-agent-sdk is not installed. Install the optional extra:\n"
            "  pip install -e '.[agent_sdk]'\n"
            "Or pin it directly: pip install 'claude-agent-sdk>=0.1'"
        ) from exc
    return claude_agent_sdk


def _normalise_allowed_tools(value: list[str] | None) -> list[str] | None:
    """Drop empty entries; treat empty list as ``None`` (= no restriction)."""
    if not value:
        return None
    cleaned = [t.strip() for t in value if t and t.strip()]
    return cleaned or None


def _message_to_trace_entry(message: Any) -> dict[str, Any]:
    """Convert an SDK message into a plain dict for the returned trace.

    The SDK's message types vary slightly across versions, but they
    all support ``type``-style discrimination. We capture enough to be
    useful for debugging and audit without depending on Pydantic.
    """
    entry: dict[str, Any] = {
        "type": getattr(message, "type", message.__class__.__name__),
    }
    # Common-named text payloads.
    for attr in ("text", "content", "role", "subtype", "result"):
        if hasattr(message, attr):
            val = getattr(message, attr)
            if isinstance(val, (str, int, float, bool)) or val is None:
                entry[attr] = val
            elif isinstance(val, (list, dict)):
                entry[attr] = val
            else:
                # SDK model types — coerce to string so the trace
                # round-trips through JSON cleanly.
                entry[attr] = str(val)
    return entry


def run_agent(
    *,
    prompt: str,
    system: str = "",
    model: str | None = None,
    max_turns: int = 10,
    allowed_tools: list[str] | None = None,
    permission_mode: str = "default",
) -> dict[str, Any]:
    """Run a Claude Agent SDK session for a single prompt.

    The agent runs to completion (or hits ``max_turns``) and returns
    the final assistant text plus a per-turn trace and token usage.

    ``allowed_tools`` is a list of tool names the agent may use
    (``None`` / empty = SDK defaults). ``permission_mode`` mirrors the
    SDK's enum (e.g. ``"default"``, ``"acceptEdits"``,
    ``"bypassPermissions"``) — passed through verbatim so callers
    using a newer SDK version aren't locked to a fixed set.

    Returns::

        {
            "text": "<final assistant text>",
            "turns": <int>,
            "stop_reason": "<string>",
            "trace": [<per-message dicts>],
            "input_tokens": <int>,
            "output_tokens": <int>,
            "cache_creation_input_tokens": <int>,
            "cache_read_input_tokens": <int>,
        }

    Raises :class:`RuntimeError` if ``claude-agent-sdk`` isn't
    installed (install via the ``[agent_sdk]`` extra).
    """
    if not prompt:
        raise ValueError("prompt must not be empty")
    if max_turns < 1:
        raise ValueError("max_turns must be >= 1")

    sdk = _import_sdk()
    model_id = model or DEFAULT_MODEL
    options = sdk.ClaudeAgentOptions(
        model=model_id,
        system_prompt=system or None,
        allowed_tools=_normalise_allowed_tools(allowed_tools),
        permission_mode=permission_mode,
        max_turns=int(max_turns),
    )

    return asyncio.run(_drive(sdk, prompt=prompt, options=options))


async def _drive(sdk: Any, *, prompt: str, options: Any) -> dict[str, Any]:
    """Consume the async iterator and assemble the final result dict."""
    trace: list[dict[str, Any]] = []
    last_text = ""
    stop_reason = ""
    usage: dict[str, int] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    turns = 0

    async for message in sdk.query(prompt=prompt, options=options):
        trace.append(_message_to_trace_entry(message))

        # Each assistant message bumps the turn count and may carry text
        # the user wants to see. The terminal ResultMessage carries the
        # final usage + stop_reason; SDK names that differ are handled
        # defensively.
        mtype = getattr(message, "type", message.__class__.__name__)

        if mtype in {"assistant", "AssistantMessage"}:
            turns += 1
            text_attr = getattr(message, "text", None) or getattr(message, "content", None)
            if isinstance(text_attr, str):
                last_text = text_attr
            elif isinstance(text_attr, list):
                # Block list, like Messages API. Concatenate text blocks.
                last_text = "".join(
                    b.get("text", "") if isinstance(b, dict)
                    else getattr(b, "text", "") if getattr(b, "type", "") == "text"
                    else ""
                    for b in text_attr
                )

        elif mtype in {"result", "ResultMessage"}:
            stop_reason = (
                getattr(message, "stop_reason", "")
                or getattr(message, "subtype", "")
                or ""
            )
            result_text = getattr(message, "result", "") or getattr(message, "text", "")
            if isinstance(result_text, str) and result_text:
                last_text = result_text
            # SDK usage may live directly on the message or on .usage.
            usage_obj = getattr(message, "usage", message)
            for key in usage:
                val = getattr(usage_obj, key, None)
                if isinstance(val, int):
                    usage[key] = val

    return {
        "text": last_text,
        "turns": turns,
        "stop_reason": stop_reason,
        "trace": trace,
        **usage,
    }
