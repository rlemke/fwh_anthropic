"""Computer Use event-facet handlers.

Wires :mod:`anthropic_handlers.tools._lib.computer_use` into the
``anthropic.computer.*`` FFL namespace.

**Important:** the FFL facet uses *simulator* tool implementations by
default. Stubs return obvious placeholder values so the loop
terminates and prompt engineering is reproducible — but they do NOT
control a real screen. For production use, drive
:func:`anthropic_handlers.tools._lib.computer_use.run_computer_use`
directly from Python with caller-supplied ``tool_impls`` (xdotool,
pyautogui, Docker-VM controller, etc.).

Reference: https://docs.anthropic.com/en/docs/build-with-claude/computer-use
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from ..shared.anthropic_utils import (
    DEFAULT_MODEL,
    redact_prompt,
    run_computer_use,
    simulator_tool_impls,
)

log = logging.getLogger(__name__)

NAMESPACE = "anthropic.computer"


def _run_computer_use_session_handler(payload: dict) -> dict[str, Any]:
    task = payload["task"]
    system = payload.get("system", "")
    model = payload.get("model") or None
    max_iterations = int(payload.get("max_iterations", 20))
    display_width_px = int(payload.get("display_width_px", 1024))
    display_height_px = int(payload.get("display_height_px", 768))
    display_number = int(payload.get("display_number", 1))
    enable_bash = bool(payload.get("enable_bash", True))
    enable_text_editor = bool(payload.get("enable_text_editor", True))

    step_log = payload.get("_step_log")
    if step_log:
        step_log(
            f"RunComputerUseSession: model={model or DEFAULT_MODEL} "
            f"{display_width_px}x{display_height_px} max_iterations={max_iterations} "
            f"[SIMULATOR] task={redact_prompt(task)}"
        )

    out = run_computer_use(
        task=task,
        tool_impls=simulator_tool_impls(),
        system=system,
        model=model,
        max_iterations=max_iterations,
        display_width_px=display_width_px,
        display_height_px=display_height_px,
        display_number=display_number,
        enable_bash=enable_bash,
        enable_text_editor=enable_text_editor,
    )
    # FFL can't natively model arbitrary lists of dicts; JSON-bridge
    # the per-action trace so workflows can audit it downstream.
    return {
        "result": {
            "text": out["text"],
            "iterations": out["iterations"],
            "stop_reason": out["stop_reason"],
            "trace_json": json.dumps(out["trace"], default=str),
            "input_tokens": out["input_tokens"],
            "output_tokens": out["output_tokens"],
            "mode": "simulator",
        }
    }


_DISPATCH: dict[str, Any] = {
    f"{NAMESPACE}.RunComputerUseSession": _run_computer_use_session_handler,
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


def register_computer_use_handlers(poller) -> None:
    for fqn, func in _DISPATCH.items():
        poller.register(fqn, func)
        log.debug("Registered computer_use handler: %s", fqn)
