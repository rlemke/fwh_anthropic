#!/usr/bin/env python3
"""run-claude-code — invoke `claude -p` non-interactively.

Wraps :func:`anthropic_handlers.tools._lib.claude_code.run_claude_code`.
The result dict (stdout, stderr, exit_code, success, command) is
printed as JSON to stdout. The model's stdout text *itself* is
captured into the JSON ``stdout`` field — that way callers piping
this CLI's stdout into ``jq`` get structured data rather than mixed
log + payload output. For raw Claude Code stdout, see
``--print-stdout-only``.

Requires the ``claude`` binary on PATH.
"""

from __future__ import annotations

import argparse
import json
import sys

from anthropic_handlers.tools._lib.claude_code import run_claude_code
from anthropic_handlers.tools._lib.client import DEFAULT_MODEL, redact_prompt


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--prompt", required=True)
    p.add_argument(
        "--working-dir",
        default=None,
        dest="working_dir",
        help="Directory to run claude in (defaults to current shell cwd)",
    )
    p.add_argument(
        "--allowed-tool",
        action="append",
        default=[],
        dest="allowed_tools",
        help="Tool name claude may use (repeatable; passed via --allowed-tools)",
    )
    p.add_argument(
        "--model",
        default=None,
        help=f"Override the default model (current default: {DEFAULT_MODEL})",
    )
    p.add_argument(
        "--permission-mode",
        default=None,
        dest="permission_mode",
        help="claude --permission-mode flag (default, acceptEdits, bypassPermissions, plan)",
    )
    p.add_argument("--timeout", type=float, default=600.0, dest="timeout_seconds")
    p.add_argument(
        "--print-stdout-only",
        action="store_true",
        dest="print_stdout_only",
        help="Print Claude Code's raw stdout to this CLI's stdout (skip the JSON envelope)",
    )
    args = p.parse_args()

    print(
        f"RunClaudeCode: model={args.model or DEFAULT_MODEL} "
        f"prompt={redact_prompt(args.prompt)}",
        file=sys.stderr,
    )
    result = run_claude_code(
        prompt=args.prompt,
        working_dir=args.working_dir,
        allowed_tools=args.allowed_tools or None,
        model=args.model,
        permission_mode=args.permission_mode,
        timeout_seconds=args.timeout_seconds,
    )
    if args.print_stdout_only:
        sys.stdout.write(result["stdout"])
        return 0 if result["success"] else 1
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
