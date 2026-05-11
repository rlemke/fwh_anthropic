#!/usr/bin/env bash
# Shell wrapper for stream_message.py — see python file for argparse help.
exec python3 "$(dirname "$0")/stream_message.py" "$@"
