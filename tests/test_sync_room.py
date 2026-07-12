#!/usr/bin/env python3
"""Tests for scripts/sync_room.py — on-demand room replication.

Stdlib unittest+mock, matching the tests/ convention. Network is always mocked
(source read + dest post are patched), so nothing touches a live server. The
watermark file is written to a TemporaryDirectory.

Run:
  python -m unittest tests/test_sync_room.py -v
"""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(ROOT, "scripts", "sync_room.py")

_spec = importlib.util.spec_from_file_location("sync_room", SCRIPT_PATH)
sync_room = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync_room)


def _msg(seq, kind="brief", content="x", agent="pythia", ts=None):
    return {"seq": seq, "ts": 1000.0 + seq if ts is None else ts,
            "agent": agent, "kind": kind, "content": content, "refs": []}


class AuthHeaderTests(unittest.TestCase):
    def test_key_uses_x_majlis_key(self):
        self.assertEqual(sync_room.auth_headers("s3cret", ""), {"X-Majlis-Key": "s3cret"})

    def test_token_uses_bearer(self):
        self.assertEqual(sync_room.auth_headers("", "ghp_x"), {"Authorization": "Bearer ghp_x"})

    def test_both_present(self):
        self.assertEqual(
            sync_room.auth_headers("k", "t"),
            {"X-Majlis-Key": "k", "Authorization": "Bearer t"},
        )


class PostDestTests(unittest.TestCase):
    def test_payload_preserves_ts_and_fields(self):
        with mock.patch.object(sync_room, "http_json", return_value={"seq": 5}) as hj:
            sync_room.post_dest("oracle", _msg(3, kind="alert", content="hi", ts=1234.5))
        url, method, payload = hj.call_args.args[0], hj.call_args.args[1], hj.call_args.args[2]
        self.assertTrue(url.endswith("/api/rooms/oracle/messages"))
        self.assertEqual(method, "POST")
        self.assertEqual(payload["agent"], "pythia")
        self.assertEqual(payload["kind"], "alert")
        self.assertEqual(payload["content"], "hi")
        self.assertEqual(payload["ts"], 1234.5)  # original timestamp carried over


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = str(Path(self.tmp.name) / "state.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_pushes_new_messages_and_advances_watermark(self):
        with mock.patch.object(sync_room, "read_source", return_value=[_msg(1), _msg(2), _msg(3)]), \
                mock.patch.object(sync_room, "post_dest", return_value={"seq": 1}) as post:
            n = sync_room.sync("oracle", since=0, dry_run=False, state_path=self.state)
        self.assertEqual(n, 3)
        self.assertEqual(post.call_count, 3)
        saved = json.loads(Path(self.state).read_text())
        self.assertEqual(saved[sync_room.state_key(sync_room.DST_URL, "oracle")], 3)

    def test_dry_run_posts_nothing_and_no_state_written(self):
        with mock.patch.object(sync_room, "read_source", return_value=[_msg(1), _msg(2)]), \
                mock.patch.object(sync_room, "post_dest") as post:
            n = sync_room.sync("oracle", since=0, dry_run=True, state_path=self.state)
        self.assertEqual(n, 2)
        post.assert_not_called()
        self.assertFalse(Path(self.state).exists())

    def test_nothing_new_is_noop(self):
        with mock.patch.object(sync_room, "read_source", return_value=[]), \
                mock.patch.object(sync_room, "post_dest") as post:
            n = sync_room.sync("oracle", since=7, dry_run=False, state_path=self.state)
        self.assertEqual(n, 0)
        post.assert_not_called()

    def test_watermark_makes_rerun_incremental(self):
        # first run pushes 1..2, second run (same watermark file) only sees 3
        with mock.patch.object(sync_room, "post_dest", return_value={"seq": 1}) as post:
            with mock.patch.object(sync_room, "read_source", return_value=[_msg(1), _msg(2)]):
                sync_room.sync("oracle", since=0, dry_run=False, state_path=self.state)
            saved = json.loads(Path(self.state).read_text())
            wm = saved[sync_room.state_key(sync_room.DST_URL, "oracle")]
            self.assertEqual(wm, 2)
            with mock.patch.object(sync_room, "read_source", return_value=[_msg(3)]) as rs:
                sync_room.sync("oracle", since=wm, dry_run=False, state_path=self.state)
                rs.assert_called_once_with("oracle", 2)
        self.assertEqual(post.call_count, 3)


class MainGuardTests(unittest.TestCase):
    def test_refuses_push_without_dest_credential(self):
        with mock.patch.object(sync_room, "DST_TOKEN", ""), \
                mock.patch.object(sync_room, "DST_KEY", ""):
            rc = sync_room.main(["oracle"])
        self.assertEqual(rc, 2)

    def test_dry_run_allowed_without_credential(self):
        with mock.patch.object(sync_room, "DST_TOKEN", ""), \
                mock.patch.object(sync_room, "DST_KEY", ""), \
                mock.patch.object(sync_room, "sync", return_value=0) as s:
            rc = sync_room.main(["oracle", "--dry-run"])
        self.assertEqual(rc, 0)
        s.assert_called_once()


if __name__ == "__main__":
    unittest.main()
