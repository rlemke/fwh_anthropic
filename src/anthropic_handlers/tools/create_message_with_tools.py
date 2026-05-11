#!/usr/bin/env python3
"""create-message-with-tools — single round of an Anthropic tool-use conversation.

Sends ``--prompt`` (or an existing conversation passed via
``--messages-file``) along with the tool definitions in
``--tools-file``, and prints the model's text + any ``tool_use``
blocks it requested. The caller is responsible for executing tools
and threading results back into a future round (see
``anthropic_handlers.tools._lib.messages.run_tool_use_loop`` for a
turnkey Python helper that does the loop for you).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from anthropic_handlers.tools._lib.client import DEFAULT_MODEL, redact_prompt
from anthropic_handlers.tools._lib.messages import create_message_with_tools


def _load_json_arg(*, inline: str | None, path: str | None, name: str):
    """Resolve one of ``--<name>-json`` (inline JSON) or ``--<name>-file`` (path)."""
    if inline and path:
        raise SystemExit(f"specify either --{name}-json or --{name}-file, not both")
    if path:
        return json.loads(Path(path).read_text())
    if inline:
        return json.loads(inline)
    return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--prompt", default="", help="User prompt (omit if --messages-file carries one)")
    p.add_argument("--tools-json", default=None, help="Tool definitions as inline JSON")
    p.add_argument("--tools-file", default=None, help="Path to a JSON file with tool definitions")
    p.add_argument(
        "--messages-json",
        default=None,
        help="Existing conversation history as inline JSON (list of {role, content})",
    )
    p.add_argument("--messages-file", default=None, help="Path to a JSON file with conversation history")
    p.add_argument("--system", default="", help="Optional system prompt")
    p.add_argument(
        "--model",
        default=None,
        help=f"Override the default model (current default: {DEFAULT_MODEL})",
    )
    p.add_argument("--max-tokens", type=int, default=1024, dest="max_tokens")
    p.add_argument("--temperature", type=float, default=1.0)
    args = p.parse_args()

    tools = _load_json_arg(inline=args.tools_json, path=args.tools_file, name="tools")
    if not tools:
        raise SystemExit("provide tool definitions via --tools-json or --tools-file")

    messages = _load_json_arg(inline=args.messages_json, path=args.messages_file, name="messages")
    if messages:
        request: object = messages
        preview = "<history>"
    elif args.prompt:
        request = args.prompt
        preview = args.prompt
    else:
        raise SystemExit("provide either --prompt or a --messages-json/--messages-file")

    print(
        f"CreateMessageWithTools: model={args.model or DEFAULT_MODEL} "
        f"tools={len(tools)} prompt={redact_prompt(preview)}",
        file=sys.stderr,
    )
    result = create_message_with_tools(
        prompt=request,
        tools=tools,
        system=args.system,
        model=args.model,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
