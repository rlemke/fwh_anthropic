#!/usr/bin/env python3
"""stream-message — streaming single-turn Messages API call.

Prints each text delta to stdout as it arrives (no buffering) and
writes the final usage JSON to stderr after the stream completes.
That way the shell sees the model "type" in real time but a downstream
pipe still gets the assembled text.

Requires ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import argparse
import json
import sys

from anthropic_handlers.tools._lib.client import DEFAULT_MODEL, redact_prompt
from anthropic_handlers.tools._lib.messages import stream_message


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
    p.add_argument(
        "--cache-system",
        action="store_true",
        dest="cache_system",
        help="Mark the system prompt with cache_control=ephemeral",
    )
    p.add_argument(
        "--no-stream-stdout",
        action="store_true",
        dest="no_stream_stdout",
        help="Don't print deltas to stdout — only emit the final JSON",
    )
    args = p.parse_args()

    cache_marker = " [cached]" if args.cache_system else ""
    print(
        f"CreateMessageStream: model={args.model or DEFAULT_MODEL}{cache_marker} "
        f"prompt={redact_prompt(args.prompt)}",
        file=sys.stderr,
    )

    def _on_chunk(delta: str) -> None:
        if not args.no_stream_stdout:
            sys.stdout.write(delta)
            sys.stdout.flush()

    result = stream_message(
        prompt=args.prompt,
        system=args.system,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        cache_system=args.cache_system,
        on_chunk=_on_chunk,
    )

    if not args.no_stream_stdout:
        # Separate the streamed text from the JSON metadata.
        sys.stdout.write("\n")
        sys.stdout.flush()

    # Final metadata goes to stderr so callers piping stdout still get
    # just the model's text. (Pass --no-stream-stdout to get the JSON
    # on stdout instead, e.g. for machine-readable workflows.)
    target = sys.stderr if not args.no_stream_stdout else sys.stdout
    json.dump(result, target, indent=2, default=str)
    target.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
