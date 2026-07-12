#!/usr/bin/env python3
"""
snapshot_oracle.py — dump a Majlis room's messages to a static JSON file.

Used by the PYTHIA public-page workflow (.github/workflows/pythia-pages.yml):
the Action fetches the oracle feed from the live app (the credential stays in
the Action via MAJLIS_TOKEN) and writes a static `oracle.json` that the public
GitHub Pages page reads client-side — so the page needs no token of its own.

Always writes a valid file, even unauthenticated or on error (empty feed + a
note), so the page still builds and simply shows "no data yet". Stdlib only.

Env:
  MAJLIS_BASE   council to read from (default the live Vercel app)
  MAJLIS_TOKEN  GitHub PAT for the hosted app  (or MAJLIS_KEY for a shared-secret server)
  MAJLIS_ROOM   room to snapshot               (default oracle)

Usage:
  python3 scripts/snapshot_oracle.py pages/pythia/oracle.json
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("MAJLIS_BASE", "https://majlis-webapp.vercel.app").rstrip("/")
TOKEN = os.environ.get("MAJLIS_TOKEN", "")
KEY = os.environ.get("MAJLIS_KEY", "")
ROOM = os.environ.get("MAJLIS_ROOM", "oracle")


def headers() -> dict:
    h = {}
    if KEY:
        h["X-Majlis-Key"] = KEY
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def fetch_messages() -> list:
    url = f"{BASE}/api/rooms/{ROOM}/messages"
    req = urllib.request.Request(url, headers=headers())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def build_payload() -> dict:
    note, messages = "", []
    if not (TOKEN or KEY):
        note = "no credential configured — set the MAJLIS_DST_TOKEN secret to publish the live feed"
    else:
        try:
            messages = fetch_messages()
        except urllib.error.HTTPError as e:
            note = f"feed fetch rejected ({e.code})"
        except Exception as e:  # network/DNS/etc — never fail the page build
            note = f"feed unavailable: {e}"
    return {"room": ROOM, "source": BASE, "updated": time.time(),
            "count": len(messages), "note": note, "messages": messages}


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    out = args[0] if args else "oracle.json"
    payload = build_payload()
    parent = os.path.dirname(os.path.abspath(out))
    os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tail = f" — {payload['note']}" if payload["note"] else ""
    print(f"[snapshot_oracle] wrote {out}: {payload['count']} message(s){tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
