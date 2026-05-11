#!/usr/bin/env python3
"""run-computer-use — drive a Computer Use session.

**Defaults to simulator mode** — stub tool implementations return
deterministic placeholder values so the loop terminates without a
real VM. That's useful for prompt-engineering dry runs.

For real screen control, this CLI isn't the right entry point —
import :func:`anthropic_handlers.tools._lib.computer_use.run_computer_use`
from Python and supply your own ``tool_impls`` (xdotool / pyautogui /
Docker VM controller, etc.). Anthropic's reference Docker impl lives
at https://github.com/anthropics/anthropic-quickstarts.

Requires ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import argparse
import json
import sys

from anthropic_handlers.tools._lib.client import DEFAULT_MODEL, redact_prompt
from anthropic_handlers.tools._lib.computer_use import (
    run_computer_use,
    simulator_tool_impls,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--task", required=True, help="Plain-English task description")
    p.add_argument("--system", default="", help="Optional system prompt")
    p.add_argument(
        "--model",
        default=None,
        help=f"Override the default model (current default: {DEFAULT_MODEL})",
    )
    p.add_argument("--max-iterations", type=int, default=20, dest="max_iterations")
    p.add_argument("--display-width", type=int, default=1024, dest="display_width_px")
    p.add_argument("--display-height", type=int, default=768, dest="display_height_px")
    p.add_argument("--display-number", type=int, default=1, dest="display_number")
    p.add_argument(
        "--no-bash",
        action="store_false",
        dest="enable_bash",
        help="Disable the bash tool in the session",
    )
    p.add_argument(
        "--no-text-editor",
        action="store_false",
        dest="enable_text_editor",
        help="Disable the text-editor tool in the session",
    )
    args = p.parse_args()

    print(
        f"RunComputerUseSession: model={args.model or DEFAULT_MODEL} "
        f"{args.display_width_px}x{args.display_height_px} "
        f"[SIMULATOR] task={redact_prompt(args.task)}",
        file=sys.stderr,
    )
    result = run_computer_use(
        task=args.task,
        tool_impls=simulator_tool_impls(),
        system=args.system,
        model=args.model,
        max_iterations=args.max_iterations,
        display_width_px=args.display_width_px,
        display_height_px=args.display_height_px,
        display_number=args.display_number,
        enable_bash=args.enable_bash,
        enable_text_editor=args.enable_text_editor,
    )
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
