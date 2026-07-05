#!/usr/bin/env python3
import importlib.util
import os
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(ROOT, "scripts", "invoke_claude.py")

_spec = importlib.util.spec_from_file_location("invoke_claude", SCRIPT_PATH)
invoke_claude = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(invoke_claude)


class ClaudeCliTransportTests(unittest.TestCase):
    def test_claude_cli_reply_reads_stdout(self):
        with mock.patch.object(
            invoke_claude.subprocess,
            "run",
            return_value=mock.Mock(returncode=0, stdout="hello from claude\n", stderr=""),
        ) as run_mock:
            reply = invoke_claude.claude_cli_reply("prompt")

        self.assertEqual(reply, "hello from claude")
        cmd = run_mock.call_args.args[0]
        kwargs = run_mock.call_args.kwargs
        self.assertIn("-p", cmd)
        self.assertIn("--bare", cmd)
        self.assertIn("--output-format", cmd)
        self.assertIn("text", cmd)
        self.assertIn("--permission-mode", cmd)
        self.assertIn("dontAsk", cmd)
        self.assertIn("--tools", cmd)
        self.assertEqual(kwargs["input"], "prompt")

    def test_claude_cli_reply_raises_on_nonzero(self):
        with mock.patch.object(
            invoke_claude.subprocess,
            "run",
            return_value=mock.Mock(returncode=1, stdout="", stderr="not authenticated"),
        ):
            with self.assertRaises(RuntimeError):
                invoke_claude.claude_cli_reply("prompt")

    def test_claude_cli_reply_honors_env_overrides(self):
        env = {
            "MAJLIS_CLAUDE_CLI": "custom-claude",
            "MAJLIS_CLAUDE_CLI_PERMISSION_MODE": "plan",
            "MAJLIS_CLAUDE_CLI_TOOLS": "Read",
            "MAJLIS_CLAUDE_CLI_MAX_TURNS": "1",
            "MAJLIS_CLAUDE_CLI_MODEL": "sonnet",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch.object(
                invoke_claude.subprocess,
                "run",
                return_value=mock.Mock(returncode=0, stdout="ok", stderr=""),
            ) as run_mock:
                invoke_claude.claude_cli_reply("prompt")

        cmd = run_mock.call_args.args[0]
        self.assertEqual(cmd[0], "custom-claude")
        self.assertIn("plan", cmd)
        self.assertIn("Read", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("sonnet", cmd)


class MainArgParsingTests(unittest.TestCase):
    def test_dry_run_prints_prompt_without_invoking_cli(self):
        argv = ["invoke_claude.py", "Test", "claude-code", "42", "--dry-run"]
        with mock.patch.object(invoke_claude.sys, "argv", argv), \
             mock.patch.object(invoke_claude.sys, "stdin", mock.Mock(read=lambda: "transcript\n")), \
             mock.patch.object(invoke_claude.subprocess, "run") as run_mock:
            code = invoke_claude.main()

        self.assertEqual(code, 0)
        run_mock.assert_not_called()

    def test_missing_required_args_returns_2(self):
        argv = ["invoke_claude.py"]
        with mock.patch.object(invoke_claude.sys, "argv", argv), \
             mock.patch.object(invoke_claude.sys, "stdin", mock.Mock(read=lambda: "")), \
             mock.patch.dict(os.environ, {}, clear=True):
            code = invoke_claude.main()

        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
