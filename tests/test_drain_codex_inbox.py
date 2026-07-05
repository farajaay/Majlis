#!/usr/bin/env python3
import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(ROOT, "scripts", "drain_codex_inbox.py")

_spec = importlib.util.spec_from_file_location("drain_codex_inbox", SCRIPT_PATH)
drain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drain)


class DrainCodexInboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inbox = Path(self.tmp.name)
        drain.ensure_dirs(self.inbox)

    def tearDown(self):
        self.tmp.cleanup()

    def write_packet(self, stem="packet-1", seq=1):
        packet = {"room": "Test", "seat": "codex", "seq": seq, "prompt": "reply please"}
        (self.inbox / "pending" / f"{stem}.json").write_text(json.dumps(packet), encoding="utf-8")
        (self.inbox / "pending" / f"{stem}.md").write_text(packet["prompt"], encoding="utf-8")
        return stem

    def test_claim_next_moves_pending_pair_to_claimed(self):
        self.write_packet()
        json_path, md_path, blocked, pending = drain.claim_next(self.inbox)
        self.assertTrue(json_path.exists())
        self.assertTrue(md_path.exists())
        self.assertFalse((self.inbox / "pending" / "packet-1.json").exists())
        self.assertEqual(json_path.parent.name, "claimed")
        self.assertEqual(blocked, 0)
        self.assertEqual(pending, 1)

    def test_mark_done_moves_claimed_pair_to_done(self):
        stem = self.write_packet()
        drain.claim_next(self.inbox)
        drain.mark_done(self.inbox, stem)
        self.assertTrue((self.inbox / "done" / f"{stem}.json").exists())
        self.assertTrue((self.inbox / "done" / f"{stem}.md").exists())

    def test_requeue_stale_claims_moves_claimed_to_pending(self):
        stem = self.write_packet()
        json_path, md_path, _blocked, _pending = drain.claim_next(self.inbox)
        old = time.time() - 3600
        os.utime(json_path, (old, old))
        os.utime(md_path, (old, old))
        moved = drain.requeue_stale_claims(self.inbox, stale_seconds=1)
        self.assertEqual(moved, 1)
        self.assertTrue((self.inbox / "pending" / f"{stem}.json").exists())
        self.assertTrue((self.inbox / "pending" / f"{stem}.md").exists())

    def test_claim_latest_moves_newest_packet(self):
        self.write_packet("old", seq=1)
        time.sleep(0.01)
        self.write_packet("new", seq=2)
        json_path, _md_path, _blocked, pending = drain.claim_next(self.inbox, latest=True)
        self.assertEqual(json_path.stem, "new")
        self.assertEqual(pending, 2)


if __name__ == "__main__":
    unittest.main()
