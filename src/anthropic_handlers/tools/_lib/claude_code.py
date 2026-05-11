"""Claude Code CLI orchestration.

Reference: https://github.com/anthropics/claude-code

Where the ``agent_sdk`` area drives the Agent SDK from Python, this
area drives the ``claude`` *CLI* via :mod:`subprocess`. That's useful
when you already have prompts crafted for Claude Code's interactive
session and want to fan them out across distributed runners (refactor
50 repos, audit 100 files, etc.) without rewriting them for the SDK.

Public surface:

- :func:`run_claude_code` — invoke ``claude -p <prompt>`` non-
  interactively, return stdout / stderr / exit code.

The ``claude`` binary must be on ``PATH``. If it isn't, the function
raises :class:`RuntimeError` with installation hints.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any


def run_claude_code(
    *,
    prompt: str,
    working_dir: str | None = None,
    allowed_tools: list[str] | None = None,
    model: str | None = None,
    permission_mode: str | None = None,
    timeout_seconds: float | None = 600.0,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """Run ``claude -p <prompt>`` and capture the result.

    Returns::

        {
            "stdout": "<the model's text output>",
            "stderr": "<warnings / progress logged by the CLI>",
            "exit_code": <int>,
            "success": <bool>,        # exit_code == 0
            "command": ["claude", "-p", "...", ...],
        }

    ``working_dir`` sets ``cwd`` for the subprocess — Claude Code's
    file-tool sandbox is rooted there. ``allowed_tools`` is passed via
    ``--allowed-tools`` (comma-joined as the CLI expects). Other
    Claude Code CLI flags can be threaded through ``extra_args``.

    Raises :class:`RuntimeError` if the ``claude`` binary isn't on PATH.
    Raises :class:`subprocess.TimeoutExpired` if ``timeout_seconds`` is
    exceeded (set to ``None`` to disable).
    """
    if not prompt:
        raise ValueError("prompt must not be empty")

    binary = shutil.which("claude")
    if not binary:
        raise RuntimeError(
            "`claude` binary not found on PATH. Install Claude Code from "
            "https://github.com/anthropics/claude-code "
            "(typically `npm install -g @anthropic-ai/claude-code`), "
            "then ensure your shell's PATH picks it up."
        )

    if working_dir is not None and not os.path.isdir(working_dir):
        raise FileNotFoundError(f"working_dir does not exist: {working_dir}")

    cmd: list[str] = [binary, "-p", prompt]
    if model:
        cmd.extend(["--model", model])
    if allowed_tools:
        cleaned = [t.strip() for t in allowed_tools if t and t.strip()]
        if cleaned:
            cmd.extend(["--allowed-tools", ",".join(cleaned)])
    if permission_mode:
        cmd.extend(["--permission-mode", permission_mode])
    if extra_args:
        cmd.extend(extra_args)

    completed = subprocess.run(  # noqa: S603 — args are validated above
        cmd,
        cwd=working_dir,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return {
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
        "exit_code": completed.returncode,
        "success": completed.returncode == 0,
        "command": list(cmd),
    }
