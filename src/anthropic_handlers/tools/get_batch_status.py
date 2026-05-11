#!/usr/bin/env python3
"""get-batch-status — retrieve the current status of a Message Batch."""

from __future__ import annotations

import argparse
import json
import sys

from anthropic_handlers.tools._lib.batch import get_batch_status


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--batch-id", required=True, dest="batch_id")
    args = p.parse_args()

    print(f"GetBatchStatus: {args.batch_id}", file=sys.stderr)
    result = get_batch_status(batch_id=args.batch_id)
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
