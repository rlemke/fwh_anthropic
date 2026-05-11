"""Shared library for the anthropic integration-area handlers.

- ``client``         — shared ``Anthropic()`` client + retry / rate-limit / redaction helpers
- ``messages``       — Messages API wrappers (TODO)
- ``batch``          — Batch API wrappers (TODO)
- ``files``          — Files API wrappers (TODO)
- ``agent_sdk``      — Claude Agent SDK wrappers (TODO)
- ``claude_code``    — Claude Code CLI wrappers (TODO)
- ``computer_use``   — Computer Use wrappers (TODO)

Each area module imports the shared client from ``.client`` and may
lazy-import optional dependencies (``claude-agent-sdk``, ``mcp``, …)
inside functions so the package remains importable without every
extra installed.
"""
