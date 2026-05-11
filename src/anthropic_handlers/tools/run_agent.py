#!/usr/bin/env python3
"""run-agent — drive a Claude Agent SDK session against a single prompt.

Wraps :func:`anthropic_handlers.tools._lib.agent_sdk.run_agent`. Prints
the per-turn trace to stderr (one entry per SDK message) and the final
assembled JSON result to stdout. Requires ``ANTHROPIC_API_KEY`` and the
``claude-agent-sdk`` package — install with::

    pip install -e '.[agent_sdk]'
"""

from __future__ import annotations

import argparse
import json
import sys

from anthropic_handlers.tools._lib.agent_sdk import run_agent
from anthropic_handlers.tools._lib.client import DEFAULT_MODEL, redact_prompt


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--prompt", required=True)
    p.add_argument("--system", default="", help="Optional system prompt")
    p.add_argument(
        "--model",
        default=None,
        help=f"Override the default model (current default: {DEFAULT_MODEL})",
    )
    p.add_argument("--max-turns", type=int, default=10, dest="max_turns")
    p.add_argument(
        "--allowed-tool",
        action="append",
        default=[],
        dest="allowed_tools",
        help="Tool name the agent may use (repeatable, e.g. --allowed-tool Read --allowed-tool Bash)",
    )
    p.add_argument(
        "--permission-mode",
        default="default",
        dest="permission_mode",
        help="SDK permission mode (default, acceptEdits, bypassPermissions, plan, …)",
    )
    args = p.parse_args()

    tool_marker = f" tools={args.allowed_tools}" if args.allowed_tools else ""
    print(
        f"RunAgent: model={args.model or DEFAULT_MODEL} max_turns={args.max_turns} "
        f"perm={args.permission_mode}{tool_marker} "
        f"prompt={redact_prompt(args.prompt)}",
        file=sys.stderr,
    )
    result = run_agent(
        prompt=args.prompt,
        system=args.system,
        model=args.model,
        max_turns=args.max_turns,
        allowed_tools=args.allowed_tools or None,
        permission_mode=args.permission_mode,
    )
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
