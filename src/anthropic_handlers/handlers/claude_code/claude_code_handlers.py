"""Claude Code CLI event-facet handlers.

Wires :func:`anthropic_handlers.tools._lib.claude_code.run_claude_code`
into the ``anthropic.code.*`` FFL namespace.

Reference: https://github.com/anthropics/claude-code
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ..shared.anthropic_utils import DEFAULT_MODEL, redact_prompt, run_claude_code

log = logging.getLogger(__name__)

NAMESPACE = "anthropic.code"


def _run_claude_code_handler(payload: dict) -> dict[str, Any]:
    prompt = payload["prompt"]
    working_dir = payload.get("working_dir") or None
    model = payload.get("model") or None
    permission_mode = payload.get("permission_mode") or None

    allowed_tools_raw = payload.get("allowed_tools", "") or ""
    allowed_tools = [t.strip() for t in allowed_tools_raw.split(",") if t.strip()]

    timeout = payload.get("timeout_seconds")
    timeout_seconds = float(timeout) if timeout not in (None, "") else 600.0

    step_log = payload.get("_step_log")
    if step_log:
        cwd_marker = f" cwd={working_dir}" if working_dir else ""
        step_log(
            f"RunClaudeCode: model={model or DEFAULT_MODEL}{cwd_marker} "
            f"prompt={redact_prompt(prompt)}"
        )

    return {
        "result": run_claude_code(
            prompt=prompt,
            working_dir=working_dir,
            allowed_tools=allowed_tools or None,
            model=model,
            permission_mode=permission_mode,
            timeout_seconds=timeout_seconds,
        )
    }


_DISPATCH: dict[str, Any] = {
    f"{NAMESPACE}.RunClaudeCode": _run_claude_code_handler,
}


def handle(payload: dict) -> dict:
    facet_name = payload["_facet_name"]
    handler = _DISPATCH.get(facet_name)
    if handler is None:
        raise ValueError(f"Unknown facet: {facet_name}")
    return handler(payload)


def register_handlers(runner) -> None:
    for facet_name in _DISPATCH:
        runner.register_handler(
            facet_name=facet_name,
            module_uri=f"file://{os.path.abspath(__file__)}",
            entrypoint="handle",
        )


def register_claude_code_handlers(poller) -> None:
    for fqn, func in _DISPATCH.items():
        poller.register(fqn, func)
        log.debug("Registered claude_code handler: %s", fqn)
