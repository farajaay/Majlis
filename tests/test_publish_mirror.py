#!/usr/bin/env python3
"""Tests for scripts/publish_mirror.py — the PC-side static-page mirror.

Stdlib importlib+mock. Network and the template are stubbed; output goes to a
TemporaryDirectory. Git push is never exercised (push=False).

Run:
  python -m unittest tests/test_publish_mirror.py -v
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
SCRIPT_PATH = os.path.join(ROOT, "scripts", "publish_mirror.py")

_spec = importlib.util.spec_from_file_location("publish_mirror", SCRIPT_PATH)
mirror = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mirror)

TEMPLATE = "<html><head><title>t</title><!--__ORACLE__--></head><body>x</body></html>"
MSGS = [{"seq": 1, "ts": 1, "agent": "pythia", "kind": "brief", "content": "hi", "refs": []}]


class RenderTests(unittest.TestCase):
    def test_inlines_data_at_marker(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(TEMPLATE)
            tpl = f.name
        try:
            with mock.patch.object(mirror, "TEMPLATE", tpl):
                out = mirror.render_html({"messages": MSGS, "count": 1})
        finally:
            os.unlink(tpl)
        self.assertNotIn("<!--__ORACLE__-->", out)          # marker consumed
        self.assertIn("window.__ORACLE__", out)
        self.assertIn('"content": "hi"', out) if False else self.assertIn("hi", out)
        # the payload round-trips as valid JSON inside the tag
        blob = out.split("window.__ORACLE__ = ", 1)[1].split(";</script>", 1)[0]
        self.assertEqual(json.loads(blob)["messages"], MSGS)

    def test_escapes_closing_script_in_content(self):
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(TEMPLATE)
            tpl = f.name
        try:
            with mock.patch.object(mirror, "TEMPLATE", tpl):
                out = mirror.render_html({"messages": [{"content": "</script><b>x"}]})
        finally:
            os.unlink(tpl)
        self.assertNotIn("</script><b>", out)   # the injected data can't break out
        self.assertIn("<\\/script>", out)


class OnceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = str(Path(self.tmp.name) / "sub" / "index.html")
        self.tpl = str(Path(self.tmp.name) / "tpl.html")
        Path(self.tpl).write_text(TEMPLATE)
        self._p = mock.patch.object(mirror, "TEMPLATE", self.tpl)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        self.tmp.cleanup()

    def test_writes_self_contained_page_from_local_feed(self):
        with mock.patch.object(mirror, "fetch_messages", return_value=MSGS):
            rc = mirror.once(self.out, push=False, empty=False)
        self.assertEqual(rc, 0)
        html = Path(self.out).read_text()
        self.assertIn("window.__ORACLE__", html)
        self.assertIn("hi", html)

    def test_empty_mode_skips_network(self):
        with mock.patch.object(mirror, "fetch_messages") as fetch:
            rc = mirror.once(self.out, push=False, empty=True)
        self.assertEqual(rc, 0)
        fetch.assert_not_called()
        blob = Path(self.out).read_text().split("window.__ORACLE__ = ", 1)[1].split(";</script>", 1)[0]
        self.assertEqual(json.loads(blob)["messages"], [])

    def test_unreachable_local_returns_1_and_writes_nothing(self):
        with mock.patch.object(mirror, "fetch_messages",
                               side_effect=urllib.error.URLError("refused")):
            rc = mirror.once(self.out, push=False, empty=False)
        self.assertEqual(rc, 1)
        self.assertFalse(Path(self.out).exists())   # last-good page preserved


if __name__ == "__main__":
    unittest.main()
