#!/usr/bin/env python3
"""create-message — single-turn Anthropic Messages API call.

Sends ``--prompt`` as one user turn (optionally with ``--system``) and
prints the assistant's text + usage as JSON. Requires
``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import argparse
import json
import sys

from anthropic_handlers.tools._lib.client import DEFAULT_MODEL, redact_prompt
from anthropic_handlers.tools._lib.messages import create_message


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--prompt", required=True)
    p.add_argument("--system", default="", help="Optional system prompt")
    p.add_argument(
        "--model",
        default=None,
        help=f"Override the default model (current default: {DEFAULT_MODEL})",
    )
    p.add_argument("--max-tokens", type=int, default=1024, dest="max_tokens")
    p.add_argument("--temperature", type=float, default=1.0)
    args = p.parse_args()

    print(
        f"CreateMessage: model={args.model or DEFAULT_MODEL} "
        f"prompt={redact_prompt(args.prompt)}",
        file=sys.stderr,
    )
    result = create_message(
        prompt=args.prompt,
        system=args.system,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
