#!/usr/bin/env bash
# Shell wrapper for create_message_with_images.py — see python file for argparse help.
exec python3 "$(dirname "$0")/create_message_with_images.py" "$@"
