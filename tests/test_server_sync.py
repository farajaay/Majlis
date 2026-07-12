#!/usr/bin/env python3
"""Tests for the on-demand "push to live" endpoint in server/main.py.

Stdlib-only (importlib + unittest.mock), matching the tests/ convention — no
TestClient/httpx. We load server.main, point its workspace + watermark at a
TemporaryDirectory, seed a room on disk, mock the outbound POST, and call the
endpoint function directly.

Run:
  python -m unittest tests/test_server_sync.py -v
"""
import importlib.util
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_PATH = os.path.join(ROOT, "server", "main.py")

_spec = importlib.util.spec_from_file_location("majlis_server_main", SERVER_PATH)
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)


def _dummy_request():
    # _check_key is a no-op while srv.KEY == "", so headers are never read
    return types.SimpleNamespace(headers={})


def _seed_room(ws: Path, room: str, records):
    d = ws / room
    (d / "files").mkdir(parents=True, exist_ok=True)
    with (d / "messages.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


class SyncEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name) / "rooms"
        self.ws.mkdir(parents=True)
        self.state = Path(self.tmp.name) / "state.json"
        self._patches = [
            mock.patch.object(srv, "WS", self.ws),
            mock.patch.object(srv, "SYNC_STATE", self.state),
            mock.patch.object(srv, "KEY", ""),
        ]
        for p in self._patches:
            p.start()
        _seed_room(self.ws, "oracle", [
            {"seq": 1, "ts": 1700000000.0, "agent": "pythia", "kind": "brief", "content": "b", "refs": []},
            {"seq": 2, "ts": 1700000600.0, "agent": "pythia", "kind": "alert", "content": "a", "refs": []},
            {"seq": 3, "ts": 1700001200.0, "agent": "pythia", "kind": "forecast", "content": "f", "refs": []},
        ])

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self.tmp.cleanup()

    def _env(self, **extra):
        base = {"MAJLIS_DST_URL": "https://live.example", "MAJLIS_DST_TOKEN": "ghp_x"}
        base.update(extra)
        return mock.patch.dict(os.environ, base, clear=False)

    def test_pushes_all_and_preserves_ts(self):
        with self._env(), mock.patch.object(srv, "_post_message_to", return_value={"seq": 9}) as post:
            out = srv.sync_room_to_dest("oracle", _dummy_request())
        self.assertEqual(out["pushed"], 3)
        self.assertEqual(out["through_seq"], 3)
        self.assertEqual(post.call_count, 3)
        # original timestamps carried in the outbound payload
        sent_ts = [c.args[1]["ts"] for c in post.call_args_list]
        self.assertEqual(sent_ts, [1700000000.0, 1700000600.0, 1700001200.0])
        # dest url + bearer header wired through
        first_url, first_payload, first_headers = post.call_args_list[0].args
        self.assertEqual(first_url, "https://live.example/api/rooms/oracle/messages")
        self.assertEqual(first_headers["Authorization"], "Bearer ghp_x")
        # watermark persisted under the dest+room key
        saved = json.loads(self.state.read_text())
        self.assertEqual(saved["https://live.example::oracle"], 3)

    def test_second_run_is_idempotent(self):
        with self._env(), mock.patch.object(srv, "_post_message_to", return_value={"seq": 9}) as post:
            srv.sync_room_to_dest("oracle", _dummy_request())
            out2 = srv.sync_room_to_dest("oracle", _dummy_request())
        self.assertEqual(post.call_count, 3)   # not 6
        self.assertEqual(out2["pushed"], 0)

    def test_not_configured_raises_400(self):
        from fastapi import HTTPException
        with mock.patch.dict(os.environ, {"MAJLIS_DST_URL": "", "MAJLIS_DST_TOKEN": "", "MAJLIS_DST_KEY": ""}):
            with self.assertRaises(HTTPException) as ctx:
                srv.sync_room_to_dest("oracle", _dummy_request())
        self.assertEqual(ctx.exception.status_code, 400)

    def test_partial_progress_saved_on_failure(self):
        import urllib.error
        from fastapi import HTTPException
        # succeed on seq 1, fail on seq 2
        calls = {"n": 0}

        def flaky(url, payload, headers):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise urllib.error.URLError("boom")
            return {"seq": 1}

        with self._env(), mock.patch.object(srv, "_post_message_to", side_effect=flaky):
            with self.assertRaises(HTTPException) as ctx:
                srv.sync_room_to_dest("oracle", _dummy_request())
        self.assertEqual(ctx.exception.status_code, 502)
        # watermark advanced only past the message that actually landed (seq 1)
        saved = json.loads(self.state.read_text())
        self.assertEqual(saved["https://live.example::oracle"], 1)


if __name__ == "__main__":
    unittest.main()
