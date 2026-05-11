#!/usr/bin/env python3
"""delete-file — delete a previously-uploaded Anthropic file by ID."""

from __future__ import annotations

import argparse
import json
import sys

from anthropic_handlers.tools._lib.files import delete_file


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--file-id", required=True, dest="file_id")
    args = p.parse_args()

    print(f"DeleteFile: {args.file_id}", file=sys.stderr)
    result = delete_file(file_id=args.file_id)
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
