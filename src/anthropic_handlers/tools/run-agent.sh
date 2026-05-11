#!/usr/bin/env bash
# Shell wrapper for run_agent.py — see python file for argparse help.
exec python3 "$(dirname "$0")/run_agent.py" "$@"
