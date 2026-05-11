"""Messages integration — wraps the Messages API.

Reference: https://github.com/anthropics/anthropic-sdk-python

Public surface:

- :func:`create_message`            — single-turn ``messages.create`` (text only)
- :func:`count_tokens`              — ``messages.count_tokens`` for a prepared request
- :func:`create_message_with_tools` — single round with tool definitions; returns text + tool_use blocks + full message history so callers can drive multi-turn loops themselves
- :func:`run_tool_use_loop`         — Python-side convenience: full multi-turn tool loop with caller-supplied tool implementations (dict of name → callable)

Vision inputs, prompt caching breakpoints, and streaming are
deliberately *not* in this cut — each warrants its own facet to keep
the call surface narrow.

Each function:

- Uses the shared client from :mod:`anthropic_handlers.tools._lib.client`.
- Accepts typed kwargs (no payload dict) so CLIs and tests call directly.
- Returns plain dicts (no SDK Pydantic models) so results round-trip
  through FFL / MongoDB without custom serialisation.
"""

from __future__ import annotations

from typing import Any, Callable

from .client import DEFAULT_MODEL, get_client


def create_message(
    *,
    prompt: str,
    system: str = "",
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 1.0,
) -> dict[str, Any]:
    """Single-turn Messages call.

    Sends ``prompt`` as a single user turn, optionally with a ``system``
    prompt, and returns the assistant's text plus usage + stop reason.
    """
    if not prompt:
        raise ValueError("prompt must not be empty")

    client = get_client()
    model_id = model or DEFAULT_MODEL
    kwargs: dict[str, Any] = {
        "model": model_id,
        "max_tokens": int(max_tokens),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(temperature),
    }
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)

    # Collapse content blocks into a single string. The SDK returns a
    # list of typed blocks; for a non-tool-use response we only care
    # about the text blocks.
    text = "".join(
        getattr(block, "text", "") for block in response.content if getattr(block, "type", "") == "text"
    )
    usage = getattr(response, "usage", None)
    return {
        "text": text,
        "model": getattr(response, "model", model_id),
        "stop_reason": getattr(response, "stop_reason", ""),
        "input_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
        "output_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
    }


def count_tokens(
    *,
    prompt: str,
    system: str = "",
    model: str | None = None,
) -> dict[str, Any]:
    """Count input tokens for a request before sending it.

    Useful for budgeting + cache-eviction checks. Costs one accounting
    round-trip to Anthropic but no inference.
    """
    if not prompt:
        raise ValueError("prompt must not be empty")

    client = get_client()
    model_id = model or DEFAULT_MODEL
    kwargs: dict[str, Any] = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    response = client.messages.count_tokens(**kwargs)
    return {
        "input_tokens": getattr(response, "input_tokens", 0),
        "model": model_id,
    }


# ---------------------------------------------------------------------------
# Tool use
# ---------------------------------------------------------------------------


def _normalise_messages(prompt_or_messages: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Accept either a bare prompt string or an explicit messages history."""
    if isinstance(prompt_or_messages, str):
        if not prompt_or_messages:
            raise ValueError("prompt must not be empty")
        return [{"role": "user", "content": prompt_or_messages}]
    if not prompt_or_messages:
        raise ValueError("messages history must not be empty")
    return list(prompt_or_messages)


def _content_block_to_dict(block: Any) -> dict[str, Any]:
    """Convert a single content block (SDK model) into a plain dict."""
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
    # Pass-through for any future block type (e.g. ``thinking``, ``redacted_thinking``).
    return {"type": btype, **{k: getattr(block, k) for k in dir(block) if not k.startswith("_") and k != "type"}}


def create_message_with_tools(
    *,
    prompt: str | list[dict[str, Any]],
    tools: list[dict[str, Any]],
    system: str = "",
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 1.0,
) -> dict[str, Any]:
    """Single round of a tool-use conversation.

    Accepts either a fresh ``prompt`` (one user turn) or an existing
    ``messages`` history. Returns text, any ``tool_use`` blocks the
    model emitted, the **full** updated message history (with the
    model's reply appended as the latest assistant turn), and usage.

    The caller is responsible for executing any returned tools and
    feeding ``tool_result`` blocks back via the messages history. For
    a turnkey loop, use :func:`run_tool_use_loop`.
    """
    if not tools:
        raise ValueError("tools must not be empty — use create_message() for text-only calls")

    messages = _normalise_messages(prompt)
    client = get_client()
    model_id = model or DEFAULT_MODEL

    kwargs: dict[str, Any] = {
        "model": model_id,
        "max_tokens": int(max_tokens),
        "messages": messages,
        "tools": tools,
        "temperature": float(temperature),
    }
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)
    blocks = [_content_block_to_dict(b) for b in (response.content or [])]
    text = "".join(b.get("text", "") for b in blocks if b["type"] == "text")
    tool_uses = [b for b in blocks if b["type"] == "tool_use"]
    usage = getattr(response, "usage", None)

    return {
        "text": text,
        "tool_uses": tool_uses,
        "stop_reason": getattr(response, "stop_reason", ""),
        "model": getattr(response, "model", model_id),
        "input_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
        "output_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
        # Updated history: caller appends tool_results and calls again.
        "messages": messages + [{"role": "assistant", "content": blocks}],
    }


def run_tool_use_loop(
    *,
    prompt: str,
    tools: list[dict[str, Any]],
    tool_impls: dict[str, Callable[..., Any]],
    system: str = "",
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 1.0,
    max_iterations: int = 8,
) -> dict[str, Any]:
    """Run the full Claude tool-use loop until completion or iteration cap.

    *tools* are the declarations Claude sees; *tool_impls* maps tool
    names to Python callables that accept the model's ``input`` dict
    and return a JSON-serialisable result (typically a dict or string).

    Returns the final assistant text, the trace of every tool call +
    result, the iteration count, total token usage across rounds, and
    the final ``stop_reason``.

    Raises :class:`RuntimeError` if the loop hits ``max_iterations``
    without Claude returning ``stop_reason="end_turn"`` — runaway
    loops should be loud, not silent.
    """
    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")
    missing = [t["name"] for t in tools if t["name"] not in tool_impls]
    if missing:
        raise ValueError(f"tool implementations missing for: {missing}")

    history: list[dict[str, Any]] | str = prompt
    trace: list[dict[str, Any]] = []
    input_tokens = 0
    output_tokens = 0
    last_text = ""
    last_stop_reason = ""

    for iteration in range(1, max_iterations + 1):
        round_result = create_message_with_tools(
            prompt=history,
            tools=tools,
            system=system,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        input_tokens += round_result["input_tokens"]
        output_tokens += round_result["output_tokens"]
        last_text = round_result["text"]
        last_stop_reason = round_result["stop_reason"]
        tool_uses = round_result["tool_uses"]
        history = round_result["messages"]

        if last_stop_reason != "tool_use" or not tool_uses:
            return {
                "text": last_text,
                "stop_reason": last_stop_reason,
                "iterations": iteration,
                "trace": trace,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }

        # Execute each tool the model requested and feed results back.
        tool_results = []
        for use in tool_uses:
            name = use["name"]
            tool_input = use.get("input", {}) or {}
            try:
                output = tool_impls[name](**tool_input)
                is_error = False
            except Exception as exc:  # pragma: no cover — surfaced into Claude's prompt
                output = f"tool {name!r} raised {type(exc).__name__}: {exc}"
                is_error = True
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": use["id"],
                "content": str(output) if not isinstance(output, (dict, list)) else output,
                "is_error": is_error,
            })
            trace.append({
                "iteration": iteration,
                "tool": name,
                "input": tool_input,
                "output": output,
                "is_error": is_error,
            })
        history = list(history) + [{"role": "user", "content": tool_results}]

    raise RuntimeError(
        f"run_tool_use_loop hit max_iterations={max_iterations} without end_turn "
        f"(last stop_reason={last_stop_reason!r}). Increase max_iterations or "
        f"check that tool implementations actually terminate the loop."
    )
