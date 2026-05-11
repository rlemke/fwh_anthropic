#!/usr/bin/env bash
# Shell wrapper for list_areas.py — see python file for argparse help.
exec python3 "$(dirname "$0")/list_areas.py" "$@"
