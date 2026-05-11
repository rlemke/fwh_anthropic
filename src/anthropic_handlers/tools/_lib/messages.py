"""Messages integration — wraps the Messages API.

Reference: https://github.com/anthropics/anthropic-sdk-python

Public surface (in order of richness — each facet builds on the previous):

- :func:`create_message`  — single-turn ``messages.create`` (system + prompt → text)
- :func:`count_tokens`    — ``messages.count_tokens`` for a prepared request

Each function:

- Uses the shared client from :mod:`anthropic_handlers.tools._lib.client`.
- Accepts typed kwargs (no payload dict) so CLIs and tests can call it directly.
- Returns a plain dict (no SDK Pydantic models) so results round-trip
  through FFL / MongoDB without custom serialisation.

Multi-turn conversations, tool use, vision inputs, prompt caching, and
streaming are deliberately *not* in this first cut — they each warrant
their own facet+CLI so the call surface stays narrow.
"""

from __future__ import annotations

from typing import Any

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
