#!/usr/bin/env python3
"""Tests for scripts/pythia_bridge.py — the PYTHIA→Majlis feed.

Stdlib-only (unittest + mock); never touches a live server. We verify the two
things that were unconfirmed in the original draft and are easy to regress:
the message wire-shape (matches server/main.py's MsgIn) and the auth headers
(matches clients/majlis.py), plus the pure formatters.

Run:
  python -m unittest tests/test_pythia_bridge.py -v
"""
import importlib.util
import os
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(ROOT, "scripts", "pythia_bridge.py")

_spec = importlib.util.spec_from_file_location("pythia_bridge", SCRIPT_PATH)
pythia_bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pythia_bridge)


class MessagePayloadTests(unittest.TestCase):
    def test_payload_matches_msgin_schema(self):
        payload = pythia_bridge.build_message_payload("hello", kind="brief")
        # server/main.py MsgIn requires `agent` and `content`; `kind`/`refs`
        # have defaults. There is no sender/role/ts on the wire.
        self.assertEqual(set(payload), {"agent", "content", "kind", "refs"})
        self.assertEqual(payload["agent"], pythia_bridge.AGENT_NAME)
        self.assertEqual(payload["content"], "hello")
        self.assertEqual(payload["kind"], "brief")
        self.assertEqual(payload["refs"], [])
        self.assertNotIn("sender", payload)
        self.assertNotIn("role", payload)
        self.assertNotIn("ts", payload)

    def test_payload_carries_refs(self):
        payload = pythia_bridge.build_message_payload("x", kind="forecast", refs=["a.md"])
        self.assertEqual(payload["refs"], ["a.md"])
        self.assertEqual(payload["kind"], "forecast")


class MessageRouteAndPostTests(unittest.TestCase):
    def test_route_is_api_prefixed(self):
        self.assertEqual(
            pythia_bridge.MAJLIS_MESSAGE_PATH,
            f"/api/rooms/{pythia_bridge.MAJLIS_ROOM}/messages",
        )

    def test_post_hits_correct_url_with_payload(self):
        with mock.patch.object(pythia_bridge, "_http_json") as http:
            pythia_bridge.post_to_majlis("brief body", kind="brief")
        url = http.call_args.args[0]
        method = http.call_args.args[1]
        payload = http.call_args.args[2]
        self.assertTrue(url.endswith(f"/api/rooms/{pythia_bridge.MAJLIS_ROOM}/messages"))
        self.assertEqual(method, "POST")
        self.assertEqual(payload["agent"], pythia_bridge.AGENT_NAME)
        self.assertEqual(payload["content"], "brief body")


class AuthHeaderTests(unittest.TestCase):
    def test_shared_key_uses_x_majlis_key(self):
        with mock.patch.object(pythia_bridge, "MAJLIS_KEY", "s3cret"), \
                mock.patch.object(pythia_bridge, "MAJLIS_TOKEN", ""):
            headers = pythia_bridge.majlis_auth_headers()
        self.assertEqual(headers, {"X-Majlis-Key": "s3cret"})
        # never the Bearer form the original draft wrongly used for the key
        self.assertNotIn("Authorization", headers)

    def test_token_uses_bearer(self):
        with mock.patch.object(pythia_bridge, "MAJLIS_KEY", ""), \
                mock.patch.object(pythia_bridge, "MAJLIS_TOKEN", "ghp_x"):
            headers = pythia_bridge.majlis_auth_headers()
        self.assertEqual(headers, {"Authorization": "Bearer ghp_x"})

    def test_no_auth_env_yields_no_headers(self):
        with mock.patch.object(pythia_bridge, "MAJLIS_KEY", ""), \
                mock.patch.object(pythia_bridge, "MAJLIS_TOKEN", ""):
            self.assertEqual(pythia_bridge.majlis_auth_headers(), {})


class FormatterTests(unittest.TestCase):
    def test_world_brief_format(self):
        view = {"summary": "calm", "event_count": 3, "domains": ["geo", "mkt", "cyber"]}
        out = pythia_bridge.format_world_brief(view)
        self.assertIn("3 live events", out)
        self.assertIn("geo, mkt, cyber", out)
        self.assertIn("calm", out)

    def test_prediction_alert_format(self):
        pred = {"statement": "rate cut", "probability": 0.72,
                "horizon": "30d", "location": "US", "split": True}
        out = pythia_bridge.format_prediction_alert(pred)
        self.assertIn("[30d]", out)
        self.assertIn("rate cut", out)
        self.assertIn("72%", out)
        self.assertIn("US", out)
        self.assertIn("swarm split", out)


class HandleDeltaThresholdTests(unittest.TestCase):
    def test_only_above_threshold_predictions_posted(self):
        evt = {"predictions": [
            {"statement": "hi", "probability": 0.9, "horizon": "7d", "location": "X"},
            {"statement": "lo", "probability": 0.1, "horizon": "7d", "location": "Y"},
        ]}
        with mock.patch.object(pythia_bridge, "post_to_majlis") as post:
            pythia_bridge._handle_delta(evt)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs.get("kind"), "forecast")

    def test_only_above_threshold_events_posted(self):
        evt = {"events": [
            {"title": "big", "salience": 0.9, "category": "geo", "summary": "s"},
            {"title": "small", "salience": 0.1, "category": "geo", "summary": "s"},
        ]}
        with mock.patch.object(pythia_bridge, "post_to_majlis") as post:
            pythia_bridge._handle_delta(evt)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs.get("kind"), "alert")


if __name__ == "__main__":
    unittest.main()
