"""Aggregator for every Anthropic integration-area handler.

Each area subpackage exposes ``register_handlers(runner)``; this module
calls all of them so a single ``--example anthropic`` registers every
wired-up facet across every area. Areas that aren't yet implemented
register zero facets — which is correct behaviour during scaffolding.
"""

from __future__ import annotations


def register_all_handlers(poller) -> None:
    """Register all facets with an AgentPoller (legacy)."""
    from .agent_sdk.agent_sdk_handlers import register_agent_sdk_handlers
    from .batch.batch_handlers import register_batch_handlers
    from .claude_code.claude_code_handlers import register_claude_code_handlers
    from .computer_use.computer_use_handlers import register_computer_use_handlers
    from .files.files_handlers import register_files_handlers
    from .messages.messages_handlers import register_messages_handlers

    register_messages_handlers(poller)
    register_batch_handlers(poller)
    register_files_handlers(poller)
    register_agent_sdk_handlers(poller)
    register_claude_code_handlers(poller)
    register_computer_use_handlers(poller)


def register_all_registry_handlers(runner) -> None:
    """Register all facets with a RegistryRunner."""
    from .agent_sdk.agent_sdk_handlers import register_handlers as reg_agent_sdk
    from .batch.batch_handlers import register_handlers as reg_batch
    from .claude_code.claude_code_handlers import register_handlers as reg_claude_code
    from .computer_use.computer_use_handlers import register_handlers as reg_computer_use
    from .files.files_handlers import register_handlers as reg_files
    from .messages.messages_handlers import register_handlers as reg_messages

    reg_messages(runner)
    reg_batch(runner)
    reg_files(runner)
    reg_agent_sdk(runner)
    reg_claude_code(runner)
    reg_computer_use(runner)
