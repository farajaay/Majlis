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

The PYTHIA-side endpoints and payload shapes (/links, /agent/view with its
`domains` {category: count} + `events_by_domain`, and /state/stream's
{kind, payload} frames) are confirmed against PYTHIA's engine/server.py,
engine/state.py, and engine/models.py.

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


def _top_domains(domains, events_by_domain) -> list:
    """PYTHIA's WorldBrief.domains is {category: count}; fall back to the
    categories present in events_by_domain when a brief hasn't set them yet."""
    if isinstance(domains, dict) and domains:
        return sorted(domains, key=lambda k: domains.get(k, 0), reverse=True)[:6]
    if isinstance(domains, list) and domains:      # defensive
        return list(domains)[:6]
    ebd = events_by_domain or {}
    return sorted(ebd, key=lambda k: len(ebd.get(k) or []), reverse=True)[:6]


def _brief_line(text: str, top: list, n_events) -> str:
    across = ", ".join(top) if top else "—"
    head = f"World brief — {n_events} live events across {across}."
    text = (text or "").strip()
    return f"{head}\n{text}" if text else head


def format_world_brief(view: dict) -> str:
    """Brief from GET /agent/view (keys: summary, event_count, domains dict,
    events_by_domain)."""
    top = _top_domains(view.get("domains"), view.get("events_by_domain"))
    return _brief_line(view.get("summary"), top, view.get("event_count", 0))


def format_brief_delta(brief: dict) -> str:
    """Brief from an SSE `world` payload (a WorldBrief.model_dump(): text +
    domains {category: count})."""
    domains = brief.get("domains") or {}
    n_events = sum(domains.values()) if isinstance(domains, dict) else 0
    return _brief_line(brief.get("text"), _top_domains(domains, None), n_events)


def format_prediction_alert(pred: dict) -> str:
    stmt = pred.get("statement", "")
    prob = pred.get("probability", 0)
    horizon = pred.get("horizon", "")
    loc = pred.get("location", "")
    split = " (swarm split)" if pred.get("split") else ""
    tail = f", {loc}" if loc else ""
    return f"[{horizon}] {stmt} — {prob:.0%} probability{tail}{split}"


def format_event_alert(e: dict) -> str:
    cat = (e.get("category") or "event").upper()
    line = f"{cat}: {e.get('title', '')}"
    summary = (e.get("summary") or "").strip()
    return f"{line} — {summary}" if summary else line


def iter_view_events(view: dict):
    """Flatten /agent/view's events_by_domain into individual event dicts,
    tagging each with its category."""
    for cat, events in (view.get("events_by_domain") or {}).items():
        for e in (events or []):
            e = dict(e)
            e.setdefault("category", cat)
            yield e


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
    # PYTHIA's SSE frames are {"kind", "ts", "payload"} (engine/state.py:publish).
    # Relevant kinds: "world" (payload = WorldBrief), "predictions" (payload =
    # list[Prediction]), "snapshot" (payload has world + predictions). Events are
    # NOT streamed — they only live in /agent/view, so the heartbeat/pulse carry
    # alerts; the stream carries the brief and forecasts.
    kind = evt.get("kind")
    payload = evt.get("payload")

    if kind == "world" and payload:
        post_to_majlis(format_brief_delta(payload), kind="brief")
        return

    if kind == "predictions":
        preds = payload or []
    elif kind == "snapshot":
        preds = (payload or {}).get("predictions") or []
    else:
        return

    for pred in preds:
        if pred.get("probability", 0) >= PROBABILITY_THRESHOLD:
            post_to_majlis(format_prediction_alert(pred), kind="forecast")


def main():
    if not (MAJLIS_KEY or MAJLIS_TOKEN):
        print("[pythia_bridge] warning: neither MAJLIS_KEY nor MAJLIS_TOKEN set — "
              "posts will be rejected if the backend requires auth.", file=sys.stderr)
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    stream_loop()  # blocks; run this whole script under your existing process manager


if __name__ == "__main__":
    main()
