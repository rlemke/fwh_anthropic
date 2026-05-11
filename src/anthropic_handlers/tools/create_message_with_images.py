#!/usr/bin/env python3
"""create-message-with-images — single-turn vision call (Messages API).

Sends ``--prompt`` together with one or more images supplied via
``--image-url`` (URLs, repeatable) and/or ``--image-path`` (local
files, repeatable, base64-encoded with MIME type auto-detected). At
least one image must be provided. Prints the assistant's text + usage
as JSON. Requires ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import argparse
import json
import sys

from anthropic_handlers.tools._lib.client import DEFAULT_MODEL, redact_prompt
from anthropic_handlers.tools._lib.messages import create_message_with_images


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--prompt", required=True)
    p.add_argument(
        "--image-url",
        action="append",
        default=[],
        dest="image_urls",
        help="Image URL (repeatable). Sent as a URL block.",
    )
    p.add_argument(
        "--image-path",
        action="append",
        default=[],
        dest="image_paths",
        help="Local image file (repeatable). Read + base64-encoded.",
    )
    p.add_argument("--system", default="", help="Optional system prompt")
    p.add_argument(
        "--model",
        default=None,
        help=f"Override the default model (current default: {DEFAULT_MODEL})",
    )
    p.add_argument("--max-tokens", type=int, default=1024, dest="max_tokens")
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument(
        "--cache-system",
        action="store_true",
        dest="cache_system",
        help="Mark the system prompt with cache_control=ephemeral",
    )
    args = p.parse_args()

    if not args.image_urls and not args.image_paths:
        raise SystemExit("provide at least one --image-url or --image-path")

    cache_marker = " [cached]" if args.cache_system else ""
    print(
        f"CreateMessageWithImages: model={args.model or DEFAULT_MODEL}{cache_marker} "
        f"images={len(args.image_urls) + len(args.image_paths)} "
        f"prompt={redact_prompt(args.prompt)}",
        file=sys.stderr,
    )
    result = create_message_with_images(
        prompt=args.prompt,
        image_urls=args.image_urls or None,
        image_paths=args.image_paths or None,
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
