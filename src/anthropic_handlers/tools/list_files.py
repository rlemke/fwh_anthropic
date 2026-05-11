#!/usr/bin/env python3
"""list-files — list files uploaded to Anthropic's Files API (most-recent-first)."""

from __future__ import annotations

import argparse
import json
import sys

from anthropic_handlers.tools._lib.files import list_files


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--limit", type=int, default=50)
    args = p.parse_args()

    print(f"ListFiles: limit={args.limit}", file=sys.stderr)
    result = list_files(limit=args.limit)
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
