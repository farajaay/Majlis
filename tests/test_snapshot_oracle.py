#!/usr/bin/env python3
"""Tests for scripts/snapshot_oracle.py — the static oracle.json dumper.

Stdlib importlib+mock. Network is mocked; output goes to a TemporaryDirectory.

Run:
  python -m unittest tests/test_snapshot_oracle.py -v
"""
import importlib.util
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(ROOT, "scripts", "snapshot_oracle.py")

_spec = importlib.util.spec_from_file_location("snapshot_oracle", SCRIPT_PATH)
snap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snap)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = str(Path(self.tmp.name) / "sub" / "oracle.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _read(self):
        return json.loads(Path(self.out).read_text())

    def test_writes_empty_with_note_when_no_credential(self):
        with mock.patch.object(snap, "TOKEN", ""), mock.patch.object(snap, "KEY", ""), \
                mock.patch.object(snap, "fetch_messages") as fetch:
            rc = snap.main([self.out])
        self.assertEqual(rc, 0)
        fetch.assert_not_called()          # never hits the network without creds
        data = self._read()
        self.assertEqual(data["messages"], [])
        self.assertIn("MAJLIS_DST_TOKEN", data["note"])
        self.assertTrue(Path(self.out).exists())   # parent dir was created

    def test_writes_messages_when_authorized(self):
        msgs = [{"seq": 1, "ts": 1, "agent": "pythia", "kind": "brief", "content": "b", "refs": []}]
        with mock.patch.object(snap, "TOKEN", "ghp_x"), \
                mock.patch.object(snap, "fetch_messages", return_value=msgs):
            snap.main([self.out])
        data = self._read()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["messages"], msgs)
        self.assertEqual(data["note"], "")

    def test_records_note_and_stays_ok_on_http_error(self):
        err = urllib.error.HTTPError("u", 401, "no", {}, None)
        with mock.patch.object(snap, "TOKEN", "ghp_x"), \
                mock.patch.object(snap, "fetch_messages", side_effect=err):
            rc = snap.main([self.out])
        self.assertEqual(rc, 0)            # never fails the page build
        data = self._read()
        self.assertEqual(data["messages"], [])
        self.assertIn("401", data["note"])


if __name__ == "__main__":
    unittest.main()
