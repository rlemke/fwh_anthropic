#!/usr/bin/env bash
# Shell wrapper for count_tokens.py — see python file for argparse help.
exec python3 "$(dirname "$0")/count_tokens.py" "$@"
