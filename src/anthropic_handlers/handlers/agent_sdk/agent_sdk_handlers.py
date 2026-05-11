"""AgentSdk event-facet handlers.

Status: scaffolded. _DISPATCH is empty; register_handlers is
a no-op. Wire facets in by:

1. Adding pure-function wrappers to anthropic_handlers.tools._lib.agent_sdk
2. Importing them here via the shim
3. Adding entries to _DISPATCH mapping facet names to handlers
4. The standard `handle` / `register_handlers` / `register_agent_sdk_handlers`
   functions below will then dispatch them automatically.

Reference: https://github.com/anthropics/claude-agent-sdk-python
"""

from __future__ import annotations

import logging
import os
from typing import Any

# from ..shared.anthropic_utils import …  # uncomment when wiring facets

log = logging.getLogger(__name__)

NAMESPACE = "anthropic.agent"


# RegistryRunner dispatch adapter — populate as facets are added.
_DISPATCH: dict[str, Any] = {}


def handle(payload: dict) -> dict:
    facet_name = payload["_facet_name"]
    handler = _DISPATCH.get(facet_name)
    if handler is None:
        raise ValueError(f"Unknown facet: {facet_name}")
    return handler(payload)


def register_handlers(runner) -> None:
    """Register all facets with a RegistryRunner. Empty during scaffolding."""
    for facet_name in _DISPATCH:
        runner.register_handler(
            facet_name=facet_name,
            module_uri=f"file://{os.path.abspath(__file__)}",
            entrypoint="handle",
        )


def register_agent_sdk_handlers(poller) -> None:
    """Register all facets with an AgentPoller (legacy). Empty during scaffolding."""
    for fqn, func in _DISPATCH.items():
        poller.register(fqn, func)
        log.debug("Registered agent_sdk handler: %s", fqn)
