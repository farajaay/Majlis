#!/usr/bin/env python3
"""
pythia_pulse.py — a ONE-SHOT PYTHIA→Majlis post, for scheduled runs.

Where scripts/pythia_bridge.py is a long-running daemon (heartbeat + SSE
stream), this posts a single world-brief per invocation and exits — the right
shape for a cron / GitHub Actions schedule. It reuses the bridge's verified
helpers so there's one implementation of the PYTHIA + Majlis wiring.

Honest by design:
  * if no Majlis credential is set, it refuses (exit 2)
  * if PYTHIA isn't reachable, it posts NOTHING and exits 0 — never fabricates
  * if the Majlis credential is rejected, it fails loudly (exit 1)

Env (same names as pythia_bridge.py):
  MAJLIS_BASE     the destination council (e.g. the live Vercel app)
  MAJLIS_TOKEN    GitHub PAT for the hosted app   (or MAJLIS_KEY for a shared-secret server)
  MAJLIS_ROOM     room to post into               (default oracle)
  PYTHIA_BASE     a *reachable* PYTHIA base URL    (public, for CI)
  PYTHIA_PROBABILITY_THRESHOLD / PYTHIA_SALIENCE_THRESHOLD  (optional)
"""
import importlib.util
import os
import sys
import urllib.error

# Reuse the verified bridge helpers (same directory) — one source of truth for
# the PYTHIA reads, the Majlis auth headers, and the message formatting.
_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("pythia_bridge", os.path.join(_HERE, "pythia_bridge.py"))
bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge)


def _post(content: str, kind: str):
    """Post to Majlis and RAISE on failure (unlike bridge.post_to_majlis, which
    swallows errors — a scheduled run should surface a bad token / outage)."""
    payload = bridge.build_message_payload(content, kind)
    bridge._http_json(bridge.MAJLIS_BASE + bridge.MAJLIS_MESSAGE_PATH,
                      "POST", payload, bridge.majlis_auth_headers())


def main() -> int:
    if not (bridge.MAJLIS_KEY or bridge.MAJLIS_TOKEN):
        print("[pythia_pulse] no Majlis credential (MAJLIS_TOKEN / MAJLIS_KEY) — refusing.",
              file=sys.stderr)
        return 2

    if not bridge.check_pythia_ready():
        print(f"[pythia_pulse] PYTHIA not reachable at {bridge.PYTHIA_BASE}; nothing posted.")
        return 0

    # Pre-flight: confirm the credential is accepted before posting, so a bad
    # token shows up as a failed run rather than a silent no-op.
    try:
        bridge._http_json(bridge.MAJLIS_BASE + f"/api/rooms/{bridge.MAJLIS_ROOM}/messages?since=0",
                          headers=bridge.majlis_auth_headers())
    except urllib.error.HTTPError as e:
        print(f"[pythia_pulse] Majlis rejected the credential ({e.code}) at {bridge.MAJLIS_BASE}.",
              file=sys.stderr)
        return 1

    view = bridge._http_json(bridge.PYTHIA_BASE + "/agent/view")
    _post(bridge.format_world_brief(view), "brief")
    posted = 1

    # Forward the salient predictions and events the agent view carries
    # (guarded — absent keys simply post nothing).
    for pred in (view.get("predictions") or []):
        if pred.get("probability", 0) >= bridge.PROBABILITY_THRESHOLD:
            _post(bridge.format_prediction_alert(pred), "forecast")
            posted += 1
    for e in bridge.iter_view_events(view):     # flattens events_by_domain
        if e.get("salience", 0) >= bridge.SALIENCE_THRESHOLD:
            _post(bridge.format_event_alert(e), "alert")
            posted += 1

    print(f"[pythia_pulse] posted {posted} item(s) to {bridge.MAJLIS_BASE} "
          f"room '{bridge.MAJLIS_ROOM}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
