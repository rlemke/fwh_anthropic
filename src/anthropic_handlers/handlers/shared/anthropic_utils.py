"""Handler-side compatibility shim for the anthropic integration areas.

The real implementation lives in ``anthropic_handlers.tools._lib``. It
is shared verbatim by:

- the ``tools/*.py`` CLIs under ``src/anthropic_handlers/tools/``, and
- the FFL handlers in this package's ``handlers/<area>/`` subpackages.

Imports use the fully-qualified
``anthropic_handlers.tools._lib.<module>`` path so this package
coexists cleanly with sibling Facetwork example packages on
``sys.modules`` (the bare-``_lib`` collision pattern that bit
osm/noaa-weather initially).

Re-exports are added as each area gets wired up. The shared
``client`` module is always available.
"""

from __future__ import annotations

# Always-available: shared SDK client + helpers.
from anthropic_handlers.tools._lib import client  # noqa: F401
from anthropic_handlers.tools._lib.client import (  # noqa: F401
    DEFAULT_MODEL,
    get_client,
    redact_prompt,
)

# Per-area modules — present but most are TODO. The messages area is
# wired up; the others re-export their public API as they get filled in.
from anthropic_handlers.tools._lib import agent_sdk, batch, claude_code, computer_use, files, messages  # noqa: F401

# --- messages area -----------------------------------------------------------
from anthropic_handlers.tools._lib.messages import (  # noqa: F401
    count_tokens,
    create_message,
    create_message_with_file,
    create_message_with_images,
    create_message_with_tools,
    run_tool_use_loop,
    stream_message,
)

# --- agent_sdk area ----------------------------------------------------------
from anthropic_handlers.tools._lib.agent_sdk import run_agent  # noqa: F401

# --- claude_code area --------------------------------------------------------
from anthropic_handlers.tools._lib.claude_code import run_claude_code  # noqa: F401

# --- batch area --------------------------------------------------------------
from anthropic_handlers.tools._lib.batch import (  # noqa: F401
    get_batch_results,
    get_batch_status,
    run_batch,
    submit_batch,
)

# --- files area --------------------------------------------------------------
from anthropic_handlers.tools._lib.files import (  # noqa: F401
    delete_file,
    list_files,
    upload_file,
)

# --- computer_use area -------------------------------------------------------
from anthropic_handlers.tools._lib.computer_use import (  # noqa: F401
    default_tools,
    run_computer_use,
    simulator_tool_impls,
)

__all__ = [
    # Shared SDK client + helpers
    "client",
    "DEFAULT_MODEL",
    "get_client",
    "redact_prompt",
    # Per-area module re-exports
    "agent_sdk",
    "batch",
    "claude_code",
    "computer_use",
    "files",
    "messages",
    # Messages API public surface
    "count_tokens",
    "create_message",
    "create_message_with_file",
    "create_message_with_images",
    "create_message_with_tools",
    "run_tool_use_loop",
    "stream_message",
    # Agent SDK public surface
    "run_agent",
    # Claude Code public surface
    "run_claude_code",
    # Batch public surface
    "get_batch_results",
    "get_batch_status",
    "run_batch",
    "submit_batch",
    # Files public surface
    "delete_file",
    "list_files",
    "upload_file",
    # Computer Use public surface
    "default_tools",
    "run_computer_use",
    "simulator_tool_impls",
]
