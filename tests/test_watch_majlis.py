#!/usr/bin/env python3
"""Tests for @seat routing and the invocation-hook drivers in
scripts/watch_majlis.py. Stdlib-only (unittest + mock); never touches the
live webapp — the room "read" is always a mocked `api` callable.

Run:
  python -m unittest tests/test_watch_majlis.py -v
"""
import importlib.util
import os
import time
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
        # Any path (including /claims) returns []: claims are supported but
        # empty, so the guard never blocks these tests unless they set up
        # their own api function to say otherwise.
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

    def test_active_claim_from_another_process_blocks_invocation(self):
        """The actual cross-process case: a second watch_majlis.py instance,
        its own invoked_state empty, must not invoke when another process's
        claim on this exact turn is still active."""
        found = [("Test", {"seq": 51, "agent": "farajaay", "kind": "chat", "content": "@codex ping"})]
        invoker = mock.Mock(spec=watch_majlis.Invoker)

        def api(path, data=None, method=None):
            if "/claims" in path:
                self.assertIsNone(method)  # only a GET should happen before the skip
                return [{"seat": "codex", "trigger_seq": 51, "status": "working",
                         "expires_at": time.time() + 300}]
            return []

        invoked_state = {}
        failed = watch_majlis.route_addressed(found, "codex", [], "codex", invoked_state, invoker, api)
        invoker.invoke.assert_not_called()
        self.assertEqual(invoked_state, {})
        self.assertEqual(failed, [])

    def test_expired_claim_does_not_block_invocation(self):
        found = [("Test", {"seq": 52, "agent": "farajaay", "kind": "chat", "content": "@codex ping"})]
        invoker = mock.Mock(spec=watch_majlis.Invoker)
        invoker.invoke.return_value = True

        def api(path, data=None, method=None):
            if "/claims" in path and method != "POST":
                return [{"seat": "codex", "trigger_seq": 52, "status": "working",
                         "expires_at": time.time() - 1}]
            if "/claims" in path:
                return dict(data)
            return []

        invoked_state = {}
        watch_majlis.route_addressed(found, "codex", [], "codex", invoked_state, invoker, api)
        invoker.invoke.assert_called_once()
        self.assertEqual(invoked_state["Test"], 52)

    def test_already_posted_claim_blocks_a_fresh_watchers_reinvocation(self):
        """Caught via live testing, not just reasoning: a brand-new watcher
        process (empty invoked_state, e.g. a replay or a lost state file)
        must not re-answer a turn another process already posted a reply
        for — 'posted' isn't 'active', but it must still block."""
        found = [("Test", {"seq": 56, "agent": "farajaay", "kind": "chat", "content": "@codex ping"})]
        invoker = mock.Mock(spec=watch_majlis.Invoker)

        def api(path, data=None, method=None):
            if "/claims" in path:
                self.assertIsNone(method)  # only a GET should happen before the skip
                return [{"seat": "codex", "trigger_seq": 56, "status": "posted", "expires_at": None}]
            return []

        invoked_state = {}  # fresh process — nothing local says this was ever handled
        failed = watch_majlis.route_addressed(found, "codex", [], "codex", invoked_state, invoker, api)
        invoker.invoke.assert_not_called()
        self.assertEqual(invoked_state, {})
        self.assertEqual(failed, [])

    def test_claim_lifecycle_on_success_is_claimed_working_posted(self):
        found = [("Test", {"seq": 53, "agent": "farajaay", "kind": "chat", "content": "@codex ping"})]
        invoker = mock.Mock(spec=watch_majlis.Invoker)
        invoker.invoke.return_value = watch_majlis.InvocationResult(True, posted_seq=321)
        posts = []

        def api(path, data=None, method=None):
            if "/claims" in path:
                if method == "POST":
                    posts.append(dict(data))
                    return dict(data)
                return []
            return []

        watch_majlis.route_addressed(found, "codex", [], "codex", {}, invoker, api)
        self.assertEqual([p["status"] for p in posts], ["claimed", "working", "posted"])
        self.assertIn("expires_at", posts[0])
        self.assertEqual(posts[-1]["posted_seq"], 321)

    def test_claim_lifecycle_records_failed_status_on_invoke_failure(self):
        found = [("Test", {"seq": 54, "agent": "farajaay", "kind": "chat", "content": "@codex ping"})]
        invoker = mock.Mock(spec=watch_majlis.Invoker)
        invoker.invoke.return_value = watch_majlis.InvocationResult(False, last_error="boom")
        posts = []

        def api(path, data=None, method=None):
            if "/claims" in path:
                if method == "POST":
                    posts.append(dict(data))
                    return dict(data)
                return []
            return []

        failed = watch_majlis.route_addressed(found, "codex", [], "codex", {}, invoker, api)
        self.assertEqual([p["status"] for p in posts], ["claimed", "working", "failed"])
        self.assertEqual(posts[-1]["last_error"], "boom")
        self.assertEqual(failed, [("Test", 54)])

    def test_claim_lifecycle_records_stale_on_timeout(self):
        found = [("Test", {"seq": 55, "agent": "farajaay", "kind": "chat", "content": "@codex ping"})]
        invoker = mock.Mock(spec=watch_majlis.Invoker)
        invoker.invoke.return_value = watch_majlis.InvocationResult(False, last_error="timed out", stale=True)
        posts = []

        def api(path, data=None, method=None):
            if "/claims" in path:
                if method == "POST":
                    posts.append(dict(data))
                    return dict(data)
                return []
            return []

        watch_majlis.route_addressed(found, "codex", [], "codex", {}, invoker, api)
        self.assertEqual(posts[-1]["status"], "stale")

    def test_newer_claim_supersedes_older_unresolved_claim(self):
        found = [("Test", {"seq": 60, "agent": "farajaay", "kind": "chat", "content": "@codex ping"})]
        invoker = mock.Mock(spec=watch_majlis.Invoker)
        invoker.invoke.return_value = True
        posts = []

        def api(path, data=None, method=None):
            if "/claims" in path:
                if method == "POST":
                    posts.append(dict(data))
                    return dict(data)
                # this seat has an older, never-resolved claim
                return [{"seat": "codex", "trigger_seq": 58, "status": "failed"}]
            return []

        watch_majlis.route_addressed(found, "codex", [], "codex", {}, invoker, api)
        superseded = [p for p in posts if p["trigger_seq"] == 58]
        self.assertEqual(len(superseded), 1)
        self.assertEqual(superseded[0]["status"], "superseded")

    def test_claims_endpoint_unavailable_falls_back_to_invoking(self):
        """Older deployments without /claims must not block invocation —
        same resilience contract as try_ping_presence."""
        found = [("Test", {"seq": 61, "agent": "farajaay", "kind": "chat", "content": "@codex ping"})]
        invoker = mock.Mock(spec=watch_majlis.Invoker)
        invoker.invoke.return_value = True

        def api(path, data=None, method=None):
            if "/claims" in path:
                raise RuntimeError("404")
            return []

        invoked_state = {}
        watch_majlis.route_addressed(found, "codex", [], "codex", invoked_state, invoker, api)
        invoker.invoke.assert_called_once()
        self.assertEqual(invoked_state["Test"], 61)


class ClaimHelperTests(unittest.TestCase):
    def test_find_claim_matches_seat_and_trigger_seq(self):
        claims = [{"seat": "codex", "trigger_seq": 3}, {"seat": "codex", "trigger_seq": 5}]
        self.assertEqual(watch_majlis.find_claim(claims, "codex", 5)["trigger_seq"], 5)

    def test_find_claim_returns_none_when_missing(self):
        claims = [{"seat": "codex", "trigger_seq": 3}]
        self.assertIsNone(watch_majlis.find_claim(claims, "codex", 99))

    def test_claim_is_active_true_for_non_expired_active_status(self):
        claim = {"status": "working", "expires_at": time.time() + 100}
        self.assertTrue(watch_majlis.claim_is_active(claim))

    def test_claim_is_active_false_when_expired(self):
        claim = {"status": "working", "expires_at": time.time() - 1}
        self.assertFalse(watch_majlis.claim_is_active(claim))

    def test_claim_is_active_false_for_terminal_status(self):
        claim = {"status": "posted", "expires_at": time.time() + 100}
        self.assertFalse(watch_majlis.claim_is_active(claim))

    def test_claim_blocks_invocation_true_for_active_claim(self):
        claim = {"status": "working", "expires_at": time.time() + 100}
        self.assertTrue(watch_majlis.claim_blocks_invocation(claim))

    def test_claim_blocks_invocation_true_for_posted_even_though_not_active(self):
        """A posted claim isn't 'active' (claim_is_active is False), but it
        must still block re-invocation forever — it's resolved, not retryable."""
        claim = {"status": "posted", "expires_at": None}
        self.assertFalse(watch_majlis.claim_is_active(claim))
        self.assertTrue(watch_majlis.claim_blocks_invocation(claim))

    def test_claim_blocks_invocation_true_for_superseded(self):
        claim = {"status": "superseded"}
        self.assertTrue(watch_majlis.claim_blocks_invocation(claim))

    def test_claim_blocks_invocation_false_for_failed_or_stale(self):
        self.assertFalse(watch_majlis.claim_blocks_invocation({"status": "failed"}))
        self.assertFalse(watch_majlis.claim_blocks_invocation({"status": "stale"}))

    def test_claim_blocks_invocation_false_for_missing_claim(self):
        self.assertFalse(watch_majlis.claim_blocks_invocation(None))

    def test_claim_is_active_true_without_expiry(self):
        claim = {"status": "claimed", "expires_at": None}
        self.assertTrue(watch_majlis.claim_is_active(claim))

    def test_claim_is_active_false_for_missing_claim(self):
        self.assertFalse(watch_majlis.claim_is_active(None))


class RetryFailedInvocationsClaimTests(unittest.TestCase):
    def test_retry_skips_invocation_when_claim_active(self):
        def api(path, data=None, method=None):
            if "/claims" in path:
                return [{"seat": "codex", "trigger_seq": 9, "status": "working",
                         "expires_at": time.time() + 300}]
            if "messages" in path:
                return [{"seq": 9, "ts": 0, "agent": "farajaay", "kind": "chat", "content": "@codex retry me"}]
            return []

        invoker = mock.Mock(spec=watch_majlis.Invoker)
        state = {"invoked": {}, "failed_invocations": {"Test": {"9": {"seq": 9, "next_retry": 0}}}}
        watch_majlis.retry_failed_invocations(state, ["Test"], "codex", "codex", invoker, api)
        invoker.invoke.assert_not_called()

    def test_retry_invokes_and_claims_when_no_active_claim(self):
        posts = []

        def api(path, data=None, method=None):
            if "/claims" in path:
                if method == "POST":
                    posts.append(dict(data))
                    return dict(data)
                return []
            if "messages" in path:
                return [{"seq": 9, "ts": 0, "agent": "farajaay", "kind": "chat", "content": "@codex retry me"}]
            return []

        invoker = mock.Mock(spec=watch_majlis.Invoker)
        invoker.invoke.return_value = True
        state = {"invoked": {}, "failed_invocations": {"Test": {"9": {"seq": 9, "next_retry": 0}}}}
        watch_majlis.retry_failed_invocations(state, ["Test"], "codex", "codex", invoker, api)
        invoker.invoke.assert_called_once()
        self.assertEqual([p["status"] for p in posts], ["claimed", "working", "posted"])
        self.assertEqual(state["invoked"]["Test"], 9)


class CommandInvokerTests(unittest.TestCase):
    def test_runs_command_with_transcript_on_stdin_and_env(self):
        fake_result = mock.Mock(returncode=0, stdout="posted codex reply seq 42\n", stderr="")
        with mock.patch.object(watch_majlis.subprocess, "run", return_value=fake_result) as run_mock:
            invoker = watch_majlis.CommandInvoker("echo hi")
            ok = invoker.invoke("Test", "codex", {"seq": 5}, "transcript text\n")
        self.assertTrue(ok)
        self.assertEqual(ok.posted_seq, 42)
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
        self.assertEqual(ok.last_error, "boom")

    def test_marks_timeout_as_stale(self):
        with mock.patch.object(
            watch_majlis.subprocess, "run",
            side_effect=watch_majlis.subprocess.TimeoutExpired(cmd="slow", timeout=1),
        ):
            invoker = watch_majlis.CommandInvoker("slow", timeout=1)
            ok = invoker.invoke("Test", "codex", {"seq": 7}, "t")
        self.assertFalse(ok)
        self.assertTrue(ok.stale)

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

    def test_prune_handled_failed_invocations(self):
        state = {
            "invoked": {"Test": 12},
            "failed_invocations": {
                "Test": {
                    "11": {"seq": 11},
                    "12": {"seq": 12},
                    "13": {"seq": 13},
                }
            },
        }
        watch_majlis.prune_handled_failed_invocations(state)
        self.assertEqual(list(state["failed_invocations"]["Test"].keys()), ["13"])


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
