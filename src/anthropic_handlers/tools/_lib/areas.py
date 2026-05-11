"""Static area-roster metadata for the `list-areas` CLI.

This is the single place that describes which Anthropic surfaces this
package intends to cover. Update whenever a new area subpackage is added.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AreaInfo:
    name: str
    ffl_namespace: str
    surface: str
    upstream: str
    handler_module: str


AREAS: list[AreaInfo] = [
    AreaInfo(
        name="messages",
        ffl_namespace="anthropic.messages",
        surface="Messages API (prompt caching, vision, streaming, tool use)",
        upstream="https://github.com/anthropics/anthropic-sdk-python",
        handler_module="anthropic_handlers.handlers.messages.messages_handlers",
    ),
    AreaInfo(
        name="batch",
        ffl_namespace="anthropic.batch",
        surface="Message Batches API",
        upstream="https://github.com/anthropics/anthropic-sdk-python",
        handler_module="anthropic_handlers.handlers.batch.batch_handlers",
    ),
    AreaInfo(
        name="files",
        ffl_namespace="anthropic.files",
        surface="Files API + citations",
        upstream="https://github.com/anthropics/anthropic-sdk-python",
        handler_module="anthropic_handlers.handlers.files.files_handlers",
    ),
    AreaInfo(
        name="agent_sdk",
        ffl_namespace="anthropic.agent",
        surface="Claude Agent SDK",
        upstream="https://github.com/anthropics/claude-agent-sdk-python",
        handler_module="anthropic_handlers.handlers.agent_sdk.agent_sdk_handlers",
    ),
    AreaInfo(
        name="claude_code",
        ffl_namespace="anthropic.code",
        surface="Claude Code CLI orchestration",
        upstream="https://github.com/anthropics/claude-code",
        handler_module="anthropic_handlers.handlers.claude_code.claude_code_handlers",
    ),
    AreaInfo(
        name="computer_use",
        ffl_namespace="anthropic.computer",
        surface="Computer Use beta",
        upstream="https://github.com/anthropics/anthropic-quickstarts",
        handler_module="anthropic_handlers.handlers.computer_use.computer_use_handlers",
    ),
]
