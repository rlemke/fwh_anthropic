"""Tests for the claude_code integration area.

Mocks :mod:`subprocess` and :func:`shutil.which` so no real
``claude`` binary is required to run the suite.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(stdout="", stderr="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


# ---------------------------------------------------------------------------
# _lib.claude_code.run_claude_code
# ---------------------------------------------------------------------------


class TestRunClaudeCode:
    def test_success_path(self):
        from anthropic_handlers.tools._lib import claude_code as cc

        completed = _completed(stdout="Hello.\n", stderr="", returncode=0)
        with patch.object(cc, "shutil") as mock_shutil, \
             patch.object(cc, "subprocess") as mock_subprocess:
            mock_shutil.which.return_value = "/usr/local/bin/claude"
            mock_subprocess.run.return_value = completed
            out = cc.run_claude_code(prompt="say hi")

        assert out["stdout"] == "Hello.\n"
        assert out["exit_code"] == 0
        assert out["success"] is True
        # The subprocess command begins with the resolved claude path + -p + prompt.
        cmd = mock_subprocess.run.call_args.args[0]
        assert cmd[0].endswith("claude")
        assert cmd[1] == "-p"
        assert cmd[2] == "say hi"

    def test_failure_exit_code_surfaces_success_false(self):
        from anthropic_handlers.tools._lib import claude_code as cc

        with patch.object(cc, "shutil") as mock_shutil, \
             patch.object(cc, "subprocess") as mock_subprocess:
            mock_shutil.which.return_value = "/usr/local/bin/claude"
            mock_subprocess.run.return_value = _completed(returncode=2, stderr="boom")
            out = cc.run_claude_code(prompt="hi")

        assert out["exit_code"] == 2
        assert out["success"] is False
        assert out["stderr"] == "boom"

    def test_threads_optional_kwargs_into_command(self):
        from anthropic_handlers.tools._lib import claude_code as cc

        with patch.object(cc, "shutil") as mock_shutil, \
             patch.object(cc, "subprocess") as mock_subprocess, \
             patch.object(cc.os.path, "isdir", return_value=True):
            mock_shutil.which.return_value = "/usr/local/bin/claude"
            mock_subprocess.run.return_value = _completed()
            cc.run_claude_code(
                prompt="do the thing",
                working_dir="/tmp/wd",
                allowed_tools=["Read", " Bash ", "", "Edit"],
                model="claude-opus-4-7",
                permission_mode="acceptEdits",
            )
        kw = mock_subprocess.run.call_args.kwargs
        cmd = mock_subprocess.run.call_args.args[0]
        assert kw["cwd"] == "/tmp/wd"
        # --allowed-tools is comma-joined with empties stripped.
        idx = cmd.index("--allowed-tools")
        assert cmd[idx + 1] == "Read,Bash,Edit"
        # --model + --permission-mode threaded through.
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "claude-opus-4-7"
        assert "--permission-mode" in cmd
        assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"

    def test_missing_binary_raises_helpful_error(self):
        from anthropic_handlers.tools._lib import claude_code as cc

        with patch.object(cc, "shutil") as mock_shutil:
            mock_shutil.which.return_value = None
            with pytest.raises(RuntimeError, match=r"claude.*PATH"):
                cc.run_claude_code(prompt="hi")

    def test_missing_working_dir_raises(self):
        from anthropic_handlers.tools._lib import claude_code as cc

        with patch.object(cc, "shutil") as mock_shutil:
            mock_shutil.which.return_value = "/usr/local/bin/claude"
            with pytest.raises(FileNotFoundError, match="working_dir"):
                cc.run_claude_code(prompt="hi", working_dir="/does/not/exist")

    def test_empty_prompt_raises(self):
        from anthropic_handlers.tools._lib import claude_code as cc

        with pytest.raises(ValueError, match="prompt"):
            cc.run_claude_code(prompt="")


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class TestClaudeCodeHandler:
    def test_handler_passes_through(self):
        from anthropic_handlers.handlers.claude_code import claude_code_handlers as ch
        from anthropic_handlers.tools._lib import claude_code as cc

        with patch.object(cc, "shutil") as mock_shutil, \
             patch.object(cc, "subprocess") as mock_subprocess:
            mock_shutil.which.return_value = "/usr/local/bin/claude"
            mock_subprocess.run.return_value = _completed(stdout="done")
            out = ch._run_claude_code_handler({"prompt": "go"})
        assert out["result"]["stdout"] == "done"
        assert out["result"]["success"] is True

    def test_handler_parses_comma_separated_tools(self):
        from anthropic_handlers.handlers.claude_code import claude_code_handlers as ch
        from anthropic_handlers.tools._lib import claude_code as cc

        with patch.object(cc, "shutil") as mock_shutil, \
             patch.object(cc, "subprocess") as mock_subprocess:
            mock_shutil.which.return_value = "/usr/local/bin/claude"
            mock_subprocess.run.return_value = _completed()
            ch._run_claude_code_handler({
                "prompt": "go",
                "allowed_tools": "Read, Bash , Edit",
            })
        cmd = mock_subprocess.run.call_args.args[0]
        assert "Read,Bash,Edit" in cmd

    def test_dispatch_has_run_claude_code(self):
        from anthropic_handlers.handlers.claude_code import claude_code_handlers as ch

        assert set(ch._DISPATCH.keys()) == {"anthropic.code.RunClaudeCode"}
