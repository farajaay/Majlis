#!/usr/bin/env python3
"""
pythia_bridge.py — feeds PYTHIA's world-state/forecasts into a Majlis room.

Treats PYTHIA as a silent seat at the majlis: it never calls /wait (it doesn't
converse), it only posts world-briefs and high-salience alerts through the
same POST-message endpoint your other agents use to `say`. Zero third-party
deps, same spirit as clients/majlis.py.

The Majlis side is confirmed against server/main.py + docs/PROTOCOL.md:
  * route  — POST /api/rooms/<room>/messages (note the /api prefix)
  * schema — MsgIn = {agent, content, kind, refs}; the server stamps `seq`
             and `ts` itself, so we never send them. There is no `sender`,
             `role`, or client `ts` field.
  * auth   — the local FastAPI server wants the shared secret in an
             X-Majlis-Key header; the hosted Vercel app wants a GitHub PAT
             as `Authorization: Bearer <token>`. We send whichever env var is
             set (MAJLIS_KEY / MAJLIS_TOKEN), matching clients/majlis.py.

The PYTHIA-side endpoints (/links, /agent/view, /state/stream) are confirmed
against PYTHIA's own API; only the two delta keys in _handle_delta are worth a
one-time `curl -N $PYTHIA_BASE/state/stream` sanity check (noted inline).

Run alongside run.sh / tunnel.sh (e.g. `python3 scripts/pythia_bridge.py &` or
under your process manager of choice). Requires PYTHIA's own stack already
running on :8088 (./run-all.sh in the Pythia repo).
"""

import os
import sys
import json
import time
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ---- Config (env-first, sensible defaults) ----
PYTHIA_BASE = os.environ.get("PYTHIA_BASE", "http://localhost:8088")
MAJLIS_BASE = os.environ.get("MAJLIS_BASE", "http://localhost:8787").rstrip("/")
MAJLIS_KEY = os.environ.get("MAJLIS_KEY", "")     # local FastAPI shared secret
MAJLIS_TOKEN = os.environ.get("MAJLIS_TOKEN", "")  # GitHub PAT for the Vercel app
MAJLIS_ROOM = os.environ.get("MAJLIS_ROOM", "oracle")  # room PYTHIA posts into
AGENT_NAME = os.environ.get("PYTHIA_AGENT_NAME", "pythia")

# Confirmed against server/main.py: routes are mounted under /api, and the room
# is a path segment (validated server-side against [a-zA-Z0-9_\-\.]{1,64}).
MAJLIS_MESSAGE_PATH = f"/api/rooms/{MAJLIS_ROOM}/messages"

# Only surface things worth the majlis's attention — tune freely.
SALIENCE_THRESHOLD = float(os.environ.get("PYTHIA_SALIENCE_THRESHOLD", "0.75"))
PROBABILITY_THRESHOLD = float(os.environ.get("PYTHIA_PROBABILITY_THRESHOLD", "0.65"))
HEARTBEAT_SECONDS = int(os.environ.get("PYTHIA_HEARTBEAT_SECONDS", "1800"))  # world-brief cadence


def majlis_auth_headers() -> dict:
    """Auth headers for the Majlis backend, mirroring clients/majlis.py.

    Send the shared secret as X-Majlis-Key (local server) and/or a GitHub PAT
    as Authorization: Bearer (hosted Vercel app). Whichever env var is set.
    """
    headers = {}
    if MAJLIS_KEY:
        headers["X-Majlis-Key"] = MAJLIS_KEY
    if MAJLIS_TOKEN:
        headers["Authorization"] = f"Bearer {MAJLIS_TOKEN}"
    return headers


def _http_json(url, method="GET", payload=None, headers=None, timeout=10):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def build_message_payload(content: str, kind: str = "brief", refs=None) -> dict:
    """Shape a message exactly as server/main.py's MsgIn expects.

    The server owns `seq` and `ts`; we only supply agent/content/kind/refs.
    `kind` is free-form server-side — the web transcript styles `decision`,
    `system`, and `file` specially and renders everything else (including our
    brief/alert/forecast) as an ordinary body, so these tags survive round-trip.
    """
    return {
        "agent": AGENT_NAME,
        "content": content,
        "kind": kind,           # "brief" | "alert" | "forecast"
        "refs": refs or [],
    }


def post_to_majlis(content: str, kind: str = "brief"):
    """Speak into the majlis the same way an agent's `say` does."""
    payload = build_message_payload(content, kind)
    try:
        _http_json(MAJLIS_BASE + MAJLIS_MESSAGE_PATH, "POST", payload, majlis_auth_headers())
    except urllib.error.URLError as e:
        print(f"[pythia_bridge] majlis post failed: {e}", file=sys.stderr)


def check_pythia_ready() -> bool:
    try:
        links = _http_json(PYTHIA_BASE + "/links")
        return all(links.get(k) for k in ("engine", "osiris", "oracle"))
    except Exception:
        return False


def format_world_brief(view: dict) -> str:
    summary = view.get("summary", "").strip()
    n_events = view.get("event_count", 0)
    domains = ", ".join(view.get("domains", [])[:6])
    return f"World brief — {n_events} live events across {domains}.\n{summary}"


def format_prediction_alert(pred: dict) -> str:
    stmt = pred.get("statement", "")
    prob = pred.get("probability", 0)
    horizon = pred.get("horizon", "")
    loc = pred.get("location", "")
    split = " (swarm split)" if pred.get("split") else ""
    return f"[{horizon}] {stmt} — {prob:.0%} probability, {loc}{split}"


def heartbeat_loop():
    """Periodic world-brief regardless of SSE activity — the calm pulse."""
    while True:
        if check_pythia_ready():
            try:
                view = _http_json(PYTHIA_BASE + "/agent/view")
                post_to_majlis(format_world_brief(view), kind="brief")
            except Exception as e:
                print(f"[pythia_bridge] heartbeat error: {e}", file=sys.stderr)
        time.sleep(HEARTBEAT_SECONDS)


def stream_loop():
    """Consume PYTHIA's SSE and forward only what crosses the thresholds."""
    url = PYTHIA_BASE + "/state/stream"
    while True:
        try:
            req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=None) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line.startswith("data:"):
                        continue
                    buf = line[len("data:"):].strip()
                    try:
                        evt = json.loads(buf)
                    except json.JSONDecodeError:
                        continue
                    _handle_delta(evt)
        except Exception as e:
            print(f"[pythia_bridge] stream error, retrying in 10s: {e}", file=sys.stderr)
            time.sleep(10)


def _handle_delta(evt: dict):
    # PYTHIA's docs describe /state as "predictions + world + runs + flags" but
    # don't pin the exact delta keys — run `curl -N $PYTHIA_BASE/state/stream`
    # once and adjust the two .get() keys below if they differ.
    for pred in evt.get("predictions", []) or []:
        if pred.get("probability", 0) >= PROBABILITY_THRESHOLD:
            post_to_majlis(format_prediction_alert(pred), kind="forecast")

    for e in evt.get("events", []) or []:
        if e.get("salience", 0) >= SALIENCE_THRESHOLD:
            title = e.get("title", "")
            cat = e.get("category", "event").upper()
            post_to_majlis(f"{cat}: {title} — {e.get('summary', '')}", kind="alert")


def main():
    if not (MAJLIS_KEY or MAJLIS_TOKEN):
        print("[pythia_bridge] warning: neither MAJLIS_KEY nor MAJLIS_TOKEN set — "
              "posts will be rejected if the backend requires auth.", file=sys.stderr)
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    stream_loop()  # blocks; run this whole script under your existing process manager


if __name__ == "__main__":
    main()
