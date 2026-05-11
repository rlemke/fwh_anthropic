#!/usr/bin/env bash
# Shell wrapper for create_message.py — see python file for argparse help.
exec python3 "$(dirname "$0")/create_message.py" "$@"
