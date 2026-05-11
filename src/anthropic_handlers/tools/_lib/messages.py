"""Messages integration — wraps the Messages API.

Reference: https://github.com/anthropics/anthropic-sdk-python

Public surface:

- :func:`create_message`             — single-turn ``messages.create`` (text only)
- :func:`count_tokens`               — ``messages.count_tokens`` for a prepared request
- :func:`create_message_with_tools`  — single round with tool definitions; returns text + tool_use blocks + full message history so callers can drive multi-turn loops themselves
- :func:`create_message_with_images` — vision: send one or more images (URLs or local files) alongside the prompt
- :func:`run_tool_use_loop`          — Python-side convenience: full multi-turn tool loop with caller-supplied tool implementations (dict of name → callable)

Prompt caching is supported on ``create_message`` and
``create_message_with_tools`` via the ``cache_system`` kwarg — set to
``True`` to mark the system prompt with ``cache_control = ephemeral``
so Anthropic reuses the encoded prefix on subsequent calls.

Streaming is deliberately *not* in this cut.

Each function:

- Uses the shared client from :mod:`anthropic_handlers.tools._lib.client`.
- Accepts typed kwargs (no payload dict) so CLIs and tests call directly.
- Returns plain dicts (no SDK Pydantic models) so results round-trip
  through FFL / MongoDB without custom serialisation.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, Callable

from .client import DEFAULT_MODEL, get_client


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _system_param(system: str, *, cache: bool) -> Any:
    """Return the SDK-shaped ``system`` parameter.

    When ``cache`` is False (the default), the SDK accepts a plain
    string. When True, we have to use the block form so we can attach
    ``cache_control``.
    """
    if not cache:
        return system
    return [
        {
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _usage_fields(response: Any) -> dict[str, int]:
    """Pull token-usage fields off a Messages response, including cache stats."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(
            usage, "cache_creation_input_tokens", 0
        ) or 0,
        "cache_read_input_tokens": getattr(
            usage, "cache_read_input_tokens", 0
        ) or 0,
    }


def create_message(
    *,
    prompt: str,
    system: str = "",
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 1.0,
    cache_system: bool = False,
) -> dict[str, Any]:
    """Single-turn Messages call.

    Sends ``prompt`` as a single user turn, optionally with a ``system``
    prompt, and returns the assistant's text plus usage + stop reason.

    When ``cache_system`` is True (and ``system`` is non-empty), the
    system prompt is sent as a content block with
    ``cache_control={"type": "ephemeral"}`` so Anthropic reuses the
    encoded prefix on subsequent calls. The returned dict surfaces
    ``cache_creation_input_tokens`` + ``cache_read_input_tokens`` so
    callers can verify caching is actually kicking in.
    """
    if not prompt:
        raise ValueError("prompt must not be empty")
    if cache_system and not system:
        raise ValueError("cache_system=True requires a non-empty system prompt")

    client = get_client()
    model_id = model or DEFAULT_MODEL
    kwargs: dict[str, Any] = {
        "model": model_id,
        "max_tokens": int(max_tokens),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(temperature),
    }
    if system:
        kwargs["system"] = _system_param(system, cache=cache_system)

    response = client.messages.create(**kwargs)

    # Collapse content blocks into a single string. The SDK returns a
    # list of typed blocks; for a non-tool-use response we only care
    # about the text blocks.
    text = "".join(
        getattr(block, "text", "") for block in response.content if getattr(block, "type", "") == "text"
    )
    return {
        "text": text,
        "model": getattr(response, "model", model_id),
        "stop_reason": getattr(response, "stop_reason", ""),
        **_usage_fields(response),
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
    cache_system: bool = False,
) -> dict[str, Any]:
    """Single round of a tool-use conversation.

    Accepts either a fresh ``prompt`` (one user turn) or an existing
    ``messages`` history. Returns text, any ``tool_use`` blocks the
    model emitted, the **full** updated message history (with the
    model's reply appended as the latest assistant turn), and usage.

    Set ``cache_system=True`` to mark the system prompt for prompt
    caching — useful when the tool-use loop hammers the same tools +
    instructions across many rounds.

    The caller is responsible for executing any returned tools and
    feeding ``tool_result`` blocks back via the messages history. For
    a turnkey loop, use :func:`run_tool_use_loop`.
    """
    if not tools:
        raise ValueError("tools must not be empty — use create_message() for text-only calls")
    if cache_system and not system:
        raise ValueError("cache_system=True requires a non-empty system prompt")

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
        kwargs["system"] = _system_param(system, cache=cache_system)

    response = client.messages.create(**kwargs)
    blocks = [_content_block_to_dict(b) for b in (response.content or [])]
    text = "".join(b.get("text", "") for b in blocks if b["type"] == "text")
    tool_uses = [b for b in blocks if b["type"] == "tool_use"]

    return {
        "text": text,
        "tool_uses": tool_uses,
        "stop_reason": getattr(response, "stop_reason", ""),
        "model": getattr(response, "model", model_id),
        **_usage_fields(response),
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


# ---------------------------------------------------------------------------
# Vision
# ---------------------------------------------------------------------------


def _image_block_from_url(url: str) -> dict[str, Any]:
    """Build a Messages image block from a URL."""
    if not url:
        raise ValueError("image URL must not be empty")
    return {"type": "image", "source": {"type": "url", "url": url}}


def _image_block_from_path(path: str) -> dict[str, Any]:
    """Build a Messages image block from a local file.

    Reads the file, base64-encodes it, and detects the media type via
    :mod:`mimetypes`. Common image formats (PNG, JPEG, GIF, WebP) are
    detected; for anything else the caller should pass a URL instead.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"image file not found: {path}")
    media_type, _ = mimetypes.guess_type(p.name)
    if not media_type or not media_type.startswith("image/"):
        raise ValueError(
            f"could not detect image media type for {path!r}; "
            "rename the file with a standard extension or pass a URL instead"
        )
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def create_message_with_images(
    *,
    prompt: str,
    image_urls: list[str] | None = None,
    image_paths: list[str] | None = None,
    system: str = "",
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 1.0,
    cache_system: bool = False,
) -> dict[str, Any]:
    """Single-turn vision call: text prompt + one or more images.

    ``image_urls`` are sent as URL blocks; ``image_paths`` are read
    from disk and sent as base64 blocks. Pass either or both — order
    is URLs first, then paths. At least one image must be provided.

    Returns the same shape as :func:`create_message`.
    """
    if not prompt:
        raise ValueError("prompt must not be empty")
    if not image_urls and not image_paths:
        raise ValueError(
            "at least one of image_urls or image_paths must be provided — "
            "use create_message() for text-only calls"
        )
    if cache_system and not system:
        raise ValueError("cache_system=True requires a non-empty system prompt")

    content: list[dict[str, Any]] = []
    for url in image_urls or []:
        content.append(_image_block_from_url(url))
    for path in image_paths or []:
        content.append(_image_block_from_path(path))
    # Text follows images — the docs recommend this for best results.
    content.append({"type": "text", "text": prompt})

    client = get_client()
    model_id = model or DEFAULT_MODEL
    kwargs: dict[str, Any] = {
        "model": model_id,
        "max_tokens": int(max_tokens),
        "messages": [{"role": "user", "content": content}],
        "temperature": float(temperature),
    }
    if system:
        kwargs["system"] = _system_param(system, cache=cache_system)

    response = client.messages.create(**kwargs)
    text = "".join(
        getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text"
    )
    return {
        "text": text,
        "model": getattr(response, "model", model_id),
        "stop_reason": getattr(response, "stop_reason", ""),
        "image_count": len(content) - 1,  # exclude the text block
        **_usage_fields(response),
    }
