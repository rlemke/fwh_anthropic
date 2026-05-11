"""ComputerUse integration — wraps the Computer Use beta.

Reference: https://github.com/anthropics/anthropic-quickstarts

Status: scaffolded. No facets implemented yet. When wiring this area,
add pure-function SDK wrappers below and re-export them from
:mod:`anthropic_handlers.handlers.shared.anthropic_utils`.

Convention:

- Use `get_client()` from `.client` for the shared Anthropic instance.
- Return plain dicts (no Pydantic models from the SDK).
- Lazy-import any optional dependency inside functions so the area
  remains importable without its extras installed.
"""

from __future__ import annotations

# from .client import get_client, redact_prompt

# TODO: add pure-function wrappers here. Each becomes a facet/CLI.
