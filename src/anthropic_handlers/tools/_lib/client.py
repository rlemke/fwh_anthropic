"""Shared Anthropic client helpers.

Holds the single source of truth for:

- Auth (``ANTHROPIC_API_KEY``) + default model selection
- The cached ``Anthropic()`` client instance
- Redaction helpers for logs (never leak the API key or full prompts at INFO+)
- A retry decorator with sensible defaults (429 / 5xx / network errors)

Per-area ``_lib/<area>.py`` modules use these — they should not
``import anthropic`` directly.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

log = logging.getLogger("anthropic_handlers")

DEFAULT_MODEL = os.environ.get("ANTHROPIC_DEFAULT_MODEL", "claude-sonnet-4-6")


@lru_cache(maxsize=1)
def get_client() -> Any:
    """Return a cached ``anthropic.Anthropic()`` client.

    Lazy-imported so this module is safely importable without the
    ``anthropic`` SDK being available (e.g. during scaffolding tests).
    Raises a clear error if ``ANTHROPIC_API_KEY`` isn't set.
    """
    try:
        import anthropic  # noqa: PLC0415 — lazy import
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The 'anthropic' SDK is not installed. Install fwh_anthropic with "
            "`pip install -e .` (the SDK is a required dependency)."
        ) from exc

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Export it before calling any "
            "anthropic_handlers function that touches the API."
        )
    return anthropic.Anthropic()


def redact_prompt(text: str, max_chars: int = 80) -> str:
    """Return a short, log-safe preview of a prompt string."""
    if not isinstance(text, str):
        return f"<{type(text).__name__}>"
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"… <+{len(text) - max_chars} chars>"
