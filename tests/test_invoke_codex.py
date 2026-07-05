#!/usr/bin/env python3
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(ROOT, "scripts", "invoke_codex.py")

_spec = importlib.util.spec_from_file_location("invoke_codex", SCRIPT_PATH)
invoke_codex = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(invoke_codex)


class CodexCliTransportTests(unittest.TestCase):
    def test_codex_cli_reply_reads_output_last_message_file(self):
        def fake_run(cmd, **kwargs):
            output_path = cmd[cmd.index("--output-last-message") + 1]
            Path(output_path).write_text("hello from cli\n", encoding="utf-8")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(invoke_codex.subprocess, "run", side_effect=fake_run) as run_mock:
            reply = invoke_codex.codex_cli_reply("prompt")

        self.assertEqual(reply, "hello from cli")
        cmd = run_mock.call_args.args[0]
        self.assertIn("exec", cmd)
        self.assertIn("--output-last-message", cmd)
        self.assertEqual(cmd[-1], "prompt")

    def test_codex_cli_reply_raises_on_nonzero(self):
        with mock.patch.object(
            invoke_codex.subprocess,
            "run",
            return_value=mock.Mock(returncode=2, stdout="", stderr="bad auth"),
        ):
            with self.assertRaises(RuntimeError):
                invoke_codex.codex_cli_reply("prompt")


if __name__ == "__main__":
    unittest.main()
