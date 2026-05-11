#!/usr/bin/env python3
"""submit-batch — submit a Message Batches request.

Accepts either ``--requests-json`` (inline JSON list) or
``--requests-file`` (path to a JSON file). Each request element must
have ``custom_id`` and ``params`` keys per the Anthropic SDK shape.

Requires ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from anthropic_handlers.tools._lib.batch import submit_batch


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--requests-json", default=None, dest="requests_json", help="Inline JSON list")
    p.add_argument("--requests-file", default=None, dest="requests_file", help="Path to JSON file")
    args = p.parse_args()

    if not (args.requests_json or args.requests_file):
        raise SystemExit("provide --requests-json or --requests-file")
    if args.requests_json and args.requests_file:
        raise SystemExit("provide one of --requests-json / --requests-file, not both")

    if args.requests_file:
        requests = json.loads(Path(args.requests_file).read_text())
    else:
        requests = json.loads(args.requests_json)

    print(f"SubmitBatch: {len(requests)} requests", file=sys.stderr)
    result = submit_batch(requests=requests)
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
