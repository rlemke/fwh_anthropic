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

# Per-area modules — present but TODO: each module's public API will
# be re-exported here as the area is wired up.
from anthropic_handlers.tools._lib import agent_sdk, batch, claude_code, computer_use, files, messages  # noqa: F401

__all__ = [
    "client",
    "DEFAULT_MODEL",
    "get_client",
    "redact_prompt",
    "agent_sdk",
    "batch",
    "claude_code",
    "computer_use",
    "files",
    "messages",
]
