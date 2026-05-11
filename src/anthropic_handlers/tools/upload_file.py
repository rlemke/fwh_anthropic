#!/usr/bin/env python3
"""upload-file — upload a local file to Anthropic's Files API."""

from __future__ import annotations

import argparse
import json
import sys

from anthropic_handlers.tools._lib.files import upload_file


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--path", required=True, help="Path to the local file")
    p.add_argument(
        "--mime-type",
        default=None,
        dest="mime_type",
        help="Override autodetected MIME type",
    )
    args = p.parse_args()

    print(f"UploadFile: {args.path}", file=sys.stderr)
    result = upload_file(path=args.path, mime_type=args.mime_type)
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
