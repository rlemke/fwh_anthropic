#!/usr/bin/env python3
"""get-batch-results — pull the per-request results of an ended Message Batch.

The batch should be in the ``ended`` state; polling is the caller's
responsibility (see ``get-batch-status``). Prints a JSON envelope with
batch_id + result_count + results (a list of per-request dicts).
"""

from __future__ import annotations

import argparse
import json
import sys

from anthropic_handlers.tools._lib.batch import get_batch_results


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--batch-id", required=True, dest="batch_id")
    args = p.parse_args()

    print(f"GetBatchResults: {args.batch_id}", file=sys.stderr)
    result = get_batch_results(batch_id=args.batch_id)
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
