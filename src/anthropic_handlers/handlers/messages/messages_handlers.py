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

import json

from ..shared.anthropic_utils import (
    DEFAULT_MODEL,
    count_tokens,
    create_message,
    create_message_with_images,
    create_message_with_tools,
    redact_prompt,
    stream_message,
)

log = logging.getLogger(__name__)

NAMESPACE = "anthropic.messages"


def _create_message_handler(payload: dict) -> dict[str, Any]:
    prompt = payload["prompt"]
    system = payload.get("system", "")
    model = payload.get("model") or None
    max_tokens = int(payload.get("max_tokens", 1024))
    temperature = float(payload.get("temperature", 1.0))
    cache_system = bool(payload.get("cache_system", False))

    step_log = payload.get("_step_log")
    if step_log:
        cache_marker = " [cached]" if cache_system else ""
        step_log(
            f"CreateMessage: model={model or DEFAULT_MODEL}{cache_marker} "
            f"prompt={redact_prompt(prompt)}"
        )
    return {
        "result": create_message(
            prompt=prompt,
            system=system,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            cache_system=cache_system,
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


def _create_message_with_tools_handler(payload: dict) -> dict[str, Any]:
    tools_json = payload.get("tools_json", "")
    if not tools_json:
        raise ValueError("CreateMessageWithTools requires tools_json")
    tools = json.loads(tools_json)
    if not isinstance(tools, list):
        raise ValueError("tools_json must decode to a JSON list of tool definitions")

    prompt = payload.get("prompt", "") or ""
    messages_json = payload.get("messages_json", "") or ""
    if messages_json:
        messages_history = json.loads(messages_json)
        if not isinstance(messages_history, list):
            raise ValueError("messages_json must decode to a JSON list")
        request: Any = messages_history
        first_user_text = prompt or "<history>"
    else:
        if not prompt:
            raise ValueError(
                "CreateMessageWithTools requires either prompt or messages_json"
            )
        request = prompt
        first_user_text = prompt

    system = payload.get("system", "")
    model = payload.get("model") or None
    max_tokens = int(payload.get("max_tokens", 1024))
    temperature = float(payload.get("temperature", 1.0))
    cache_system = bool(payload.get("cache_system", False))

    step_log = payload.get("_step_log")
    if step_log:
        cache_marker = " [cached]" if cache_system else ""
        step_log(
            f"CreateMessageWithTools: model={model or DEFAULT_MODEL}{cache_marker} "
            f"tools={len(tools)} prompt={redact_prompt(first_user_text)}"
        )
    out = create_message_with_tools(
        prompt=request,
        tools=tools,
        system=system,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        cache_system=cache_system,
    )
    # FFL doesn't natively model arbitrary lists of objects; JSON-serialise
    # the bridge fields so workflows can carry them through to the next round.
    return {
        "result": {
            "text": out["text"],
            "tool_uses_json": json.dumps(out["tool_uses"]),
            "messages_json": json.dumps(out["messages"], default=str),
            "stop_reason": out["stop_reason"],
            "model": out["model"],
            "input_tokens": out["input_tokens"],
            "output_tokens": out["output_tokens"],
            "cache_creation_input_tokens": out["cache_creation_input_tokens"],
            "cache_read_input_tokens": out["cache_read_input_tokens"],
        }
    }


def _create_message_with_images_handler(payload: dict) -> dict[str, Any]:
    prompt = payload["prompt"]
    image_urls_raw = payload.get("image_urls", "") or ""
    image_paths_raw = payload.get("image_paths", "") or ""
    # FFL passes lists as comma-separated strings here — parse + strip empties.
    image_urls = [u.strip() for u in image_urls_raw.split(",") if u.strip()]
    image_paths = [p.strip() for p in image_paths_raw.split(",") if p.strip()]

    system = payload.get("system", "")
    model = payload.get("model") or None
    max_tokens = int(payload.get("max_tokens", 1024))
    temperature = float(payload.get("temperature", 1.0))
    cache_system = bool(payload.get("cache_system", False))

    step_log = payload.get("_step_log")
    if step_log:
        cache_marker = " [cached]" if cache_system else ""
        step_log(
            f"CreateMessageWithImages: model={model or DEFAULT_MODEL}{cache_marker} "
            f"images={len(image_urls) + len(image_paths)} prompt={redact_prompt(prompt)}"
        )
    return {
        "result": create_message_with_images(
            prompt=prompt,
            image_urls=image_urls or None,
            image_paths=image_paths or None,
            system=system,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            cache_system=cache_system,
        )
    }


def _create_message_stream_handler(payload: dict) -> dict[str, Any]:
    prompt = payload["prompt"]
    system = payload.get("system", "")
    model = payload.get("model") or None
    max_tokens = int(payload.get("max_tokens", 1024))
    temperature = float(payload.get("temperature", 1.0))
    cache_system = bool(payload.get("cache_system", False))

    step_log = payload.get("_step_log")
    cache_marker = " [cached]" if cache_system else ""
    if step_log:
        step_log(
            f"CreateMessageStream: model={model or DEFAULT_MODEL}{cache_marker} "
            f"prompt={redact_prompt(prompt)}"
        )

    # Surface each delta to the step log so the dashboard renders
    # progressive output. Each chunk is redacted to keep log lines short.
    def _on_chunk(delta: str) -> None:
        if step_log:
            step_log(f"chunk: {redact_prompt(delta, max_chars=40)}")

    out = stream_message(
        prompt=prompt,
        system=system,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        cache_system=cache_system,
        on_chunk=_on_chunk,
    )
    return {"result": out}


# RegistryRunner dispatch adapter
_DISPATCH: dict[str, Any] = {
    f"{NAMESPACE}.CreateMessage": _create_message_handler,
    f"{NAMESPACE}.CountTokens": _count_tokens_handler,
    f"{NAMESPACE}.CreateMessageWithTools": _create_message_with_tools_handler,
    f"{NAMESPACE}.CreateMessageWithImages": _create_message_with_images_handler,
    f"{NAMESPACE}.CreateMessageStream": _create_message_stream_handler,
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
