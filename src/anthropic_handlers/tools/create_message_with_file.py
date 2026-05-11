#!/usr/bin/env python3
"""create-message-with-file — Messages call referencing uploaded files.

Sends ``--prompt`` along with one or more files (already uploaded via
``upload-file``). Each file ID is passed as a document or image
content block. Requires ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import argparse
import json
import sys

from anthropic_handlers.tools._lib.client import DEFAULT_MODEL, redact_prompt
from anthropic_handlers.tools._lib.messages import create_message_with_file


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--prompt", required=True)
    p.add_argument(
        "--file-ids",
        required=True,
        dest="file_ids",
        help="Comma-separated list of Anthropic file IDs",
    )
    p.add_argument(
        "--file-type",
        default="document",
        dest="file_type",
        choices=["document", "image"],
        help="Block type for the supplied files (default: document)",
    )
    p.add_argument("--system", default="")
    p.add_argument(
        "--model",
        default=None,
        help=f"Override the default model (current default: {DEFAULT_MODEL})",
    )
    p.add_argument("--max-tokens", type=int, default=1024, dest="max_tokens")
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--cache-system", action="store_true", dest="cache_system")
    args = p.parse_args()

    file_ids = [f.strip() for f in args.file_ids.split(",") if f.strip()]
    if not file_ids:
        raise SystemExit("--file-ids must contain at least one id")

    cache_marker = " [cached]" if args.cache_system else ""
    print(
        f"CreateMessageWithFile: model={args.model or DEFAULT_MODEL}{cache_marker} "
        f"files={len(file_ids)} type={args.file_type} prompt={redact_prompt(args.prompt)}",
        file=sys.stderr,
    )
    result = create_message_with_file(
        prompt=args.prompt,
        file_ids=file_ids,
        file_type=args.file_type,
        system=args.system,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        cache_system=args.cache_system,
    )
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
