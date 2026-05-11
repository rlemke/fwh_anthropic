#!/usr/bin/env python3
"""count-tokens — count input tokens for a prepared Messages request.

Costs one accounting round-trip but no inference. Useful for budgeting
+ cache-eviction checks. Requires ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import argparse
import json
import sys

from anthropic_handlers.tools._lib.client import DEFAULT_MODEL, redact_prompt
from anthropic_handlers.tools._lib.messages import count_tokens


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--prompt", required=True)
    p.add_argument("--system", default="", help="Optional system prompt")
    p.add_argument(
        "--model",
        default=None,
        help=f"Override the default model (current default: {DEFAULT_MODEL})",
    )
    args = p.parse_args()

    print(
        f"CountTokens: model={args.model or DEFAULT_MODEL} "
        f"prompt={redact_prompt(args.prompt)}",
        file=sys.stderr,
    )
    result = count_tokens(prompt=args.prompt, system=args.system, model=args.model)
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
