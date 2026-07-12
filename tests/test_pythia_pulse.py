#!/usr/bin/env python3
"""Tests for scripts/pythia_pulse.py — the one-shot scheduled PYTHIA post.

Stdlib importlib+mock, matching the tests/ convention. The pulse module loads
scripts/pythia_bridge.py as `pulse.bridge`; we patch attributes on that loaded
bridge module (its network helpers) so nothing touches a real server.

Run:
  python -m unittest tests/test_pythia_pulse.py -v
"""
import importlib.util
import os
import unittest
import urllib.error
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(ROOT, "scripts", "pythia_pulse.py")

_spec = importlib.util.spec_from_file_location("pythia_pulse", SCRIPT_PATH)
pulse = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pulse)
bridge = pulse.bridge


class PulseTests(unittest.TestCase):
    def test_refuses_without_credential(self):
        with mock.patch.object(bridge, "MAJLIS_TOKEN", ""), \
                mock.patch.object(bridge, "MAJLIS_KEY", ""):
            self.assertEqual(pulse.main(), 2)

    def test_noop_when_pythia_unreachable(self):
        with mock.patch.object(bridge, "MAJLIS_TOKEN", "ghp_x"), \
                mock.patch.object(bridge, "MAJLIS_KEY", ""), \
                mock.patch.object(bridge, "check_pythia_ready", return_value=False), \
                mock.patch.object(pulse, "_post") as post:
            rc = pulse.main()
        self.assertEqual(rc, 0)
        post.assert_not_called()   # never fabricates data

    def test_fails_loudly_on_rejected_credential(self):
        with mock.patch.object(bridge, "MAJLIS_TOKEN", "ghp_x"), \
                mock.patch.object(bridge, "MAJLIS_KEY", ""), \
                mock.patch.object(bridge, "check_pythia_ready", return_value=True), \
                mock.patch.object(bridge, "_http_json",
                                  side_effect=urllib.error.HTTPError("u", 401, "no", {}, None)), \
                mock.patch.object(pulse, "_post") as post:
            rc = pulse.main()
        self.assertEqual(rc, 1)
        post.assert_not_called()

    def test_posts_brief_and_salient_items(self):
        view = {
            "summary": "calm", "event_count": 3, "domains": ["geo", "mkt"],
            "predictions": [
                {"statement": "hi", "probability": 0.9, "horizon": "7d", "location": "X"},
                {"statement": "lo", "probability": 0.1, "horizon": "7d", "location": "Y"},
            ],
            "events": [
                {"title": "big", "salience": 0.9, "category": "geo", "summary": "s"},
                {"title": "small", "salience": 0.1, "category": "geo", "summary": "s"},
            ],
        }

        def fake_http(url, *a, **k):
            # preflight GET (…/messages?since=0) returns [], the PYTHIA view returns `view`
            return view if url.endswith("/agent/view") else []

        with mock.patch.object(bridge, "MAJLIS_TOKEN", "ghp_x"), \
                mock.patch.object(bridge, "MAJLIS_KEY", ""), \
                mock.patch.object(bridge, "check_pythia_ready", return_value=True), \
                mock.patch.object(bridge, "_http_json", side_effect=fake_http), \
                mock.patch.object(pulse, "_post") as post:
            rc = pulse.main()
        self.assertEqual(rc, 0)
        kinds = [c.args[1] for c in post.call_args_list]
        # one brief + one above-threshold forecast + one above-threshold alert
        self.assertEqual(kinds, ["brief", "forecast", "alert"])


if __name__ == "__main__":
    unittest.main()
