#!/usr/bin/env python3
"""run-batch — submit a batch and block until it ends, then pull results.

Convenience that wraps submit + poll + retrieve in one CLI call.
Prints status lines to stderr while polling; emits the final
``{batch, poll_count, elapsed_seconds, results}`` dict as JSON on
stdout. Requires ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from anthropic_handlers.tools._lib.batch import run_batch


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--requests-json", default=None, dest="requests_json")
    p.add_argument("--requests-file", default=None, dest="requests_file")
    p.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=10.0,
        dest="poll_interval_seconds",
    )
    p.add_argument(
        "--timeout-seconds",
        type=float,
        default=600.0,
        dest="timeout_seconds",
    )
    args = p.parse_args()

    if not (args.requests_json or args.requests_file):
        raise SystemExit("provide --requests-json or --requests-file")
    if args.requests_json and args.requests_file:
        raise SystemExit("provide one of --requests-json / --requests-file, not both")

    if args.requests_file:
        requests = json.loads(Path(args.requests_file).read_text())
    else:
        requests = json.loads(args.requests_json)

    def _on_status(meta: dict) -> None:
        counts = meta.get("request_counts") or {}
        print(
            f"batch {meta.get('id', '?')} status={meta.get('processing_status', '?')} "
            f"succeeded={counts.get('succeeded', 0)} "
            f"errored={counts.get('errored', 0)} "
            f"processing={counts.get('processing', 0)}",
            file=sys.stderr,
        )

    print(
        f"RunBatch: {len(requests)} requests "
        f"poll={args.poll_interval_seconds}s timeout={args.timeout_seconds}s",
        file=sys.stderr,
    )
    result = run_batch(
        requests=requests,
        poll_interval_seconds=args.poll_interval_seconds,
        timeout_seconds=args.timeout_seconds,
        on_status=_on_status,
    )
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
