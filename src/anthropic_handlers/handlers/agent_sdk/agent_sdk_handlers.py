"""Claude Agent SDK event-facet handlers.

Wires :func:`anthropic_handlers.tools._lib.agent_sdk.run_agent` into
the ``anthropic.agent.*`` FFL namespace.

Reference: https://github.com/anthropics/claude-agent-sdk-python
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from ..shared.anthropic_utils import (
    DEFAULT_MODEL,
    redact_prompt,
    run_agent,
)

log = logging.getLogger(__name__)

NAMESPACE = "anthropic.agent"


def _run_agent_handler(payload: dict) -> dict[str, Any]:
    prompt = payload["prompt"]
    system = payload.get("system", "")
    model = payload.get("model") or None
    max_turns = int(payload.get("max_turns", 10))

    # FFL passes lists as comma-separated strings here.
    allowed_tools_raw = payload.get("allowed_tools", "") or ""
    allowed_tools = [t.strip() for t in allowed_tools_raw.split(",") if t.strip()]

    permission_mode = payload.get("permission_mode") or "default"

    step_log = payload.get("_step_log")
    if step_log:
        tool_marker = f" tools=[{allowed_tools_raw}]" if allowed_tools else ""
        step_log(
            f"RunAgent: model={model or DEFAULT_MODEL} max_turns={max_turns} "
            f"perm={permission_mode}{tool_marker} prompt={redact_prompt(prompt)}"
        )

    out = run_agent(
        prompt=prompt,
        system=system,
        model=model,
        max_turns=max_turns,
        allowed_tools=allowed_tools or None,
        permission_mode=permission_mode,
    )
    # FFL can't natively model arbitrary lists of dicts; JSON-serialise
    # the per-turn trace so workflows can carry it through.
    return {
        "result": {
            "text": out["text"],
            "turns": out["turns"],
            "stop_reason": out["stop_reason"],
            "trace_json": json.dumps(out["trace"], default=str),
            "input_tokens": out["input_tokens"],
            "output_tokens": out["output_tokens"],
            "cache_creation_input_tokens": out["cache_creation_input_tokens"],
            "cache_read_input_tokens": out["cache_read_input_tokens"],
        }
    }


# RegistryRunner dispatch adapter
_DISPATCH: dict[str, Any] = {
    f"{NAMESPACE}.RunAgent": _run_agent_handler,
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


def register_agent_sdk_handlers(poller) -> None:
    """Register all facets with an AgentPoller (legacy)."""
    for fqn, func in _DISPATCH.items():
        poller.register(fqn, func)
        log.debug("Registered agent_sdk handler: %s", fqn)
