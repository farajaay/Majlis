#!/usr/bin/env python3
"""Tests for @seat routing and the invocation-hook drivers in
scripts/watch_majlis.py. Stdlib-only (unittest + mock); never touches the
live webapp — the room "read" is always a mocked `api` callable.

Run:
  python -m unittest tests/test_watch_majlis.py -v
"""
import importlib.util
import os
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(ROOT, "scripts", "watch_majlis.py")

_spec = importlib.util.spec_from_file_location("watch_majlis", SCRIPT_PATH)
watch_majlis = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(watch_majlis)


class MentionsSeatTests(unittest.TestCase):
    def test_at_mention_anywhere_in_message(self):
        self.assertTrue(watch_majlis.mentions_seat("hey @codex can you look at this", "codex"))

    def test_dash_prefix_at_start(self):
        self.assertTrue(watch_majlis.mentions_seat("codex — thoughts on the plan?", "codex"))

    def test_hyphen_prefix_at_start(self):
        self.assertTrue(watch_majlis.mentions_seat("codex - thoughts?", "codex"))

    def test_colon_prefix_at_start(self):
        self.assertTrue(watch_majlis.mentions_seat("codex: check this please", "codex"))

    def test_case_insensitive(self):
        self.assertTrue(watch_majlis.mentions_seat("@Codex please respond", "codex"))

    def test_no_match_for_other_seat(self):
        self.assertFalse(watch_majlis.mentions_seat("gemini, what do you think?", "codex"))

    def test_word_boundary_avoids_partial_match(self):
        self.assertFalse(watch_majlis.mentions_seat("@codexish is unrelated", "codex"))

    def test_alias_matches(self):
        self.assertTrue(watch_majlis.mentions_seat("@claude take a look", "claude-code", aliases=["claude"]))

    def test_prefix_form_only_at_message_start(self):
        self.assertFalse(watch_majlis.mentions_seat("ask codex - later maybe", "codex"))

    def test_empty_content_is_safe(self):
        self.assertFalse(watch_majlis.mentions_seat("", "codex"))


class RouteAddressedTests(unittest.TestCase):
    def setUp(self):
        self.api = mock.Mock(return_value=[])

    def test_fires_on_addressed_turn(self):
        invoker = mock.Mock(spec=watch_majlis.Invoker)
        found = [("Test", {"seq": 10, "agent": "farajaay", "kind": "chat", "content": "@codex please look"})]
        invoked_state = {}
        failed = watch_majlis.route_addressed(found, "codex", [], "codex", invoked_state, invoker, self.api)
        invoker.invoke.assert_called_once()
        self.assertEqual(invoked_state["Test"], 10)
        self.assertEqual(failed, [])

    def test_skips_seats_own_messages(self):
        invoker = mock.Mock(spec=watch_majlis.Invoker)
        found = [("Test", {"seq": 11, "agent": "codex", "kind": "chat", "content": "@codex talking to myself"})]
        invoked_state = {}
        watch_majlis.route_addressed(found, "codex", [], "codex", invoked_state, invoker, self.api)
        invoker.invoke.assert_not_called()
        self.assertEqual(invoked_state, {})

    def test_skips_unaddressed_messages(self):
        invoker = mock.Mock(spec=watch_majlis.Invoker)
        found = [("Test", {"seq": 12, "agent": "gemini", "kind": "chat", "content": "no mention here"})]
        invoked_state = {}
        watch_majlis.route_addressed(found, "codex", [], "codex", invoked_state, invoker, self.api)
        invoker.invoke.assert_not_called()

    def test_invoke_on_all_fires_on_unaddressed_messages(self):
        invoker = mock.Mock(spec=watch_majlis.Invoker)
        found = [("Test", {"seq": 13, "agent": "gemini", "kind": "chat", "content": "no mention here"})]
        invoked_state = {}
        watch_majlis.route_addressed(
            found, "codex", [], "codex", invoked_state, invoker, self.api, invoke_on="all"
        )
        invoker.invoke.assert_called_once()
        self.assertEqual(invoked_state["Test"], 13)

    def test_idempotent_across_simulated_restart(self):
        msg = {"seq": 20, "agent": "farajaay", "kind": "chat", "content": "@codex go"}
        found = [("Test", msg)]
        invoked_state = {}

        invoker_run1 = mock.Mock(spec=watch_majlis.Invoker)
        watch_majlis.route_addressed(found, "codex", [], "codex", invoked_state, invoker_run1, self.api)
        self.assertEqual(invoker_run1.invoke.call_count, 1)

        # A restart loads the persisted invoked_state but re-delivers the same
        # turn (e.g. re-polled with the same since= cursor) — must not re-fire.
        invoker_run2 = mock.Mock(spec=watch_majlis.Invoker)
        watch_majlis.route_addressed(found, "codex", [], "codex", invoked_state, invoker_run2, self.api)
        invoker_run2.invoke.assert_not_called()

    def test_one_invocation_per_distinct_turn(self):
        invoker = mock.Mock(spec=watch_majlis.Invoker)
        found = [
            ("Test", {"seq": 30, "agent": "farajaay", "kind": "chat", "content": "@codex one"}),
            ("Test", {"seq": 31, "agent": "farajaay", "kind": "chat", "content": "@codex two"}),
        ]
        invoked_state = {}
        watch_majlis.route_addressed(found, "codex", [], "codex", invoked_state, invoker, self.api)
        self.assertEqual(invoker.invoke.call_count, 2)
        self.assertEqual(invoked_state["Test"], 31)

    def test_failed_invocation_does_not_advance_invoked_state(self):
        invoker = mock.Mock(spec=watch_majlis.Invoker)
        invoker.invoke.return_value = False
        found = [("Test", {"seq": 32, "agent": "farajaay", "kind": "chat", "content": "@codex one"})]
        invoked_state = {}
        failed = watch_majlis.route_addressed(found, "codex", [], "codex", invoked_state, invoker, self.api)
        invoker.invoke.assert_called_once()
        self.assertEqual(invoked_state, {})
        self.assertEqual(failed, [("Test", 32)])

    def test_failed_invocation_can_rewind_room_cursor(self):
        state = {"rooms": {"Test": 40}, "invoked": {}}
        failed = [("Test", 32)]
        for room, seq in failed:
            state["rooms"][room] = min(int(state["rooms"].get(room, seq)), seq - 1)
        self.assertEqual(state["rooms"]["Test"], 31)


class CommandInvokerTests(unittest.TestCase):
    def test_runs_command_with_transcript_on_stdin_and_env(self):
        fake_result = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(watch_majlis.subprocess, "run", return_value=fake_result) as run_mock:
            invoker = watch_majlis.CommandInvoker("echo hi")
            ok = invoker.invoke("Test", "codex", {"seq": 5}, "transcript text\n")
        self.assertTrue(ok)
        run_mock.assert_called_once()
        _, kwargs = run_mock.call_args
        self.assertEqual(kwargs["input"], "transcript text\n")
        self.assertEqual(kwargs["env"]["MAJLIS_INVOKE_ROOM"], "Test")
        self.assertEqual(kwargs["env"]["MAJLIS_INVOKE_SEAT"], "codex")
        self.assertEqual(kwargs["env"]["MAJLIS_INVOKE_SEQ"], "5")

    def test_returns_false_on_nonzero_exit(self):
        fake_result = mock.Mock(returncode=1, stdout="", stderr="boom")
        with mock.patch.object(watch_majlis.subprocess, "run", return_value=fake_result):
            invoker = watch_majlis.CommandInvoker("false")
            ok = invoker.invoke("Test", "codex", {"seq": 6}, "t")
        self.assertFalse(ok)

    def test_fires_once_per_addressed_turn_not_on_own_posts(self):
        fake_result = mock.Mock(returncode=0, stdout="", stderr="")
        api = mock.Mock(return_value=[])
        with mock.patch.object(watch_majlis.subprocess, "run", return_value=fake_result) as run_mock:
            invoker = watch_majlis.CommandInvoker("noop")
            found = [
                ("Test", {"seq": 40, "agent": "farajaay", "kind": "chat", "content": "@codex please respond"}),
                ("Test", {"seq": 41, "agent": "codex", "kind": "chat", "content": "@codex talking to self"}),
            ]
            invoked_state = {}
            watch_majlis.route_addressed(found, "codex", [], "codex", invoked_state, invoker, api)
        run_mock.assert_called_once()
        self.assertEqual(invoked_state["Test"], 40)


class ManualNotifyInvokerTests(unittest.TestCase):
    def test_returns_true_without_shelling_out(self):
        invoker = watch_majlis.ManualNotifyInvoker()
        self.assertTrue(invoker.invoke("Test", "codex", {"seq": 1}, "transcript"))


class BuildInvokerTests(unittest.TestCase):
    def test_manual_is_default(self):
        self.assertIsInstance(watch_majlis.build_invoker("manual", ""), watch_majlis.ManualNotifyInvoker)

    def test_command_requires_cmd(self):
        with self.assertRaises(SystemExit):
            watch_majlis.build_invoker("command", "")

    def test_command_builds_command_invoker(self):
        invoker = watch_majlis.build_invoker("command", "echo hi")
        self.assertIsInstance(invoker, watch_majlis.CommandInvoker)


class LoadStateTests(unittest.TestCase):
    def test_missing_file_has_invoked_key(self):
        state = watch_majlis.load_state(os.path.join(ROOT, "no-such-state-file.json"))
        self.assertEqual(state, {"rooms": {}, "invoked": {}, "failed_invocations": {}})

    def test_existing_state_gets_failed_invocations_key(self):
        with mock.patch.object(watch_majlis.os.path, "exists", return_value=True), \
             mock.patch("builtins.open", mock.mock_open(read_data='{"rooms":{},"invoked":{}}')):
            state = watch_majlis.load_state("state.json")
        self.assertEqual(state["failed_invocations"], {})


class FailedInvocationBackoffTests(unittest.TestCase):
    def test_remember_failed_invocation_with_backoff(self):
        state = {"failed_invocations": {}}
        watch_majlis.remember_failed_invocations(state, [("Test", 12)], now=100)
        item = state["failed_invocations"]["Test"]["12"]
        self.assertEqual(item["attempts"], 1)
        self.assertEqual(item["next_retry"], 115)

    def test_due_failed_invocations_respects_limit_and_time(self):
        state = {"failed_invocations": {"Test": {"12": {"seq": 12, "next_retry": 90}, "13": {"seq": 13, "next_retry": 200}}}}
        self.assertEqual(watch_majlis.due_failed_invocations(state, ["Test"], now=100), [("Test", 12)])

    def test_clear_failed_invocation_removes_empty_room(self):
        state = {"failed_invocations": {"Test": {"12": {"seq": 12}}}}
        watch_majlis.clear_failed_invocation(state, "Test", 12)
        self.assertEqual(state["failed_invocations"], {})


class PollOnceRoutingIntegrationTests(unittest.TestCase):
    def test_own_messages_never_reach_routing_but_others_do(self):
        api = mock.Mock(return_value=[
            {"seq": 1, "ts": 0, "agent": "codex", "kind": "chat", "content": "@codex loop test"},
            {"seq": 2, "ts": 0, "agent": "farajaay", "kind": "chat", "content": "@codex please help"},
        ])
        state = {"rooms": {"Test": 0}, "invoked": {}}
        found = watch_majlis.poll_once(api, ["Test"], state, agent="codex", replay=True)

        invoker = mock.Mock(spec=watch_majlis.Invoker)
        watch_majlis.route_addressed(found, "codex", [], "codex", state["invoked"], invoker, api)

        invoker.invoke.assert_called_once()
        self.assertEqual(state["invoked"]["Test"], 2)


if __name__ == "__main__":
    unittest.main()
