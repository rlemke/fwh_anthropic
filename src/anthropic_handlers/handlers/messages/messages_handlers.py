"""Messages event-facet handlers.

Wires the public functions of
:mod:`anthropic_handlers.tools._lib.messages` into the
``anthropic.messages.*`` FFL namespace.

Reference: https://github.com/anthropics/anthropic-sdk-python
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..shared.anthropic_utils import (
    DEFAULT_MODEL,
    count_tokens,
    create_message,
    redact_prompt,
)

log = logging.getLogger(__name__)

NAMESPACE = "anthropic.messages"


def _create_message_handler(payload: dict) -> dict[str, Any]:
    prompt = payload["prompt"]
    system = payload.get("system", "")
    model = payload.get("model") or None
    max_tokens = int(payload.get("max_tokens", 1024))
    temperature = float(payload.get("temperature", 1.0))

    step_log = payload.get("_step_log")
    if step_log:
        step_log(
            f"CreateMessage: model={model or DEFAULT_MODEL} "
            f"prompt={redact_prompt(prompt)}"
        )
    return {
        "result": create_message(
            prompt=prompt,
            system=system,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    }


def _count_tokens_handler(payload: dict) -> dict[str, Any]:
    prompt = payload["prompt"]
    system = payload.get("system", "")
    model = payload.get("model") or None

    step_log = payload.get("_step_log")
    if step_log:
        step_log(
            f"CountTokens: model={model or DEFAULT_MODEL} "
            f"prompt={redact_prompt(prompt)}"
        )
    return {"count": count_tokens(prompt=prompt, system=system, model=model)}


# RegistryRunner dispatch adapter
_DISPATCH: dict[str, Any] = {
    f"{NAMESPACE}.CreateMessage": _create_message_handler,
    f"{NAMESPACE}.CountTokens": _count_tokens_handler,
}


def handle(payload: dict) -> dict:
    """RegistryRunner dispatch entrypoint."""
    facet_name = payload["_facet_name"]
    handler = _DISPATCH.get(facet_name)
    if handler is None:
        raise ValueError(f"Unknown facet: {facet_name}")
    return handler(payload)


def register_handlers(runner) -> None:
    """Register all facets with a RegistryRunner."""
    for facet_name in _DISPATCH:
        runner.register_handler(
            facet_name=facet_name,
            module_uri=f"file://{os.path.abspath(__file__)}",
            entrypoint="handle",
        )


def register_messages_handlers(poller) -> None:
    """Register all facets with an AgentPoller (legacy)."""
    for fqn, func in _DISPATCH.items():
        poller.register(fqn, func)
        log.debug("Registered messages handler: %s", fqn)
