#!/usr/bin/env python3
"""list-areas — show every integration area this package covers + wiring status.

For each area, prints:

- the FFL namespace it claims
- the upstream github.com/anthropics surface it wraps
- the number of facets currently wired in its handler module (0 during scaffolding)

Use this to see at a glance which areas have been filled in.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from textwrap import shorten

from anthropic_handlers.tools._lib.areas import AREAS


def _count_facets(module_path: str) -> int:
    try:
        mod = importlib.import_module(module_path)
    except Exception:
        return -1
    dispatch = getattr(mod, "_DISPATCH", {})
    return len(dispatch) if isinstance(dispatch, dict) else -1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON list instead of a human-readable table",
    )
    args = p.parse_args()

    rows = [
        {
            "area": a.name,
            "ffl_namespace": a.ffl_namespace,
            "surface": a.surface,
            "upstream": a.upstream,
            "facets_wired": _count_facets(a.handler_module),
        }
        for a in AREAS
    ]

    if args.json:
        import json
        json.dump(rows, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    total = sum(r["facets_wired"] for r in rows if r["facets_wired"] >= 0)
    print(f"fwh_anthropic — {len(rows)} areas, {total} facets wired\n")
    print(f"  {'AREA':14} {'NAMESPACE':22} {'WIRED':6}  SURFACE")
    print(f"  {'-' * 14} {'-' * 22} {'-' * 6}  {'-' * 60}")
    for r in rows:
        wired = (
            "—" if r["facets_wired"] < 0 else str(r["facets_wired"])
        )
        print(
            f"  {r['area']:14} {r['ffl_namespace']:22} {wired:6}  "
            f"{shorten(r['surface'], 60, placeholder='…')}"
        )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
