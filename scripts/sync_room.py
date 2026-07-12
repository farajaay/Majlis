#!/usr/bin/env python3
"""
sync_room.py — copy a Majlis room's messages from one backend to another,
on demand. Built for the local-first PYTHIA workflow: run PYTHIA + the bridge
+ the local FastAPI server on your machine (the oracle room fills up locally),
then run this whenever you want to push those turns up to the live Vercel app.

One-way, incremental, idempotent:
  * reads the SOURCE room's messages after a locally-stored watermark
  * re-posts each new one to the DEST room (preserving agent/kind/content/refs
    and, thanks to the optional `ts` field, the ORIGINAL timestamp)
  * advances the watermark so re-runs only push what's new

The destination assigns its own seq numbers; we match on the source seq we
last synced (stored per dest+room in a small state file), so running it twice
never duplicates.

Zero third-party deps, same spirit as clients/majlis.py.

Env (all optional except a dest credential):
  MAJLIS_SRC_URL    source base   (default http://localhost:8787)
  MAJLIS_SRC_KEY    source X-Majlis-Key (local server shared secret)
  MAJLIS_SRC_TOKEN  source Bearer token (if the source is GitHub-gated)
  MAJLIS_DST_URL    dest base     (default https://majlis-webapp.vercel.app)
  MAJLIS_DST_TOKEN  dest Bearer   (GitHub PAT in ALLOWED_GITHUB_LOGINS)
  MAJLIS_DST_KEY    dest X-Majlis-Key (if the dest is a shared-secret server)
  MAJLIS_ROOM       room to sync  (default oracle)
  MAJLIS_SYNC_STATE watermark file (default ./.majlis_sync_state.json)

Usage:
  python3 scripts/sync_room.py                 # sync default oracle room
  python3 scripts/sync_room.py mes-design      # sync a specific room
  python3 scripts/sync_room.py --dry-run       # show what would be pushed
  python3 scripts/sync_room.py --since 0        # re-push from the start
  python3 scripts/sync_room.py --reset          # forget the watermark, then sync
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

SRC_URL = os.environ.get("MAJLIS_SRC_URL", "http://localhost:8787").rstrip("/")
SRC_KEY = os.environ.get("MAJLIS_SRC_KEY", "")
SRC_TOKEN = os.environ.get("MAJLIS_SRC_TOKEN", "")
DST_URL = os.environ.get("MAJLIS_DST_URL", "https://majlis-webapp.vercel.app").rstrip("/")
DST_KEY = os.environ.get("MAJLIS_DST_KEY", "")
DST_TOKEN = os.environ.get("MAJLIS_DST_TOKEN", "")
ROOM = os.environ.get("MAJLIS_ROOM", "oracle")
STATE_PATH = os.environ.get("MAJLIS_SYNC_STATE", ".majlis_sync_state.json")


def auth_headers(key: str, token: str) -> dict:
    """X-Majlis-Key and/or Authorization: Bearer, mirroring clients/majlis.py."""
    headers = {}
    if key:
        headers["X-Majlis-Key"] = key
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def http_json(url, method="GET", payload=None, headers=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def state_key(dst_url: str, room: str) -> str:
    return f"{dst_url}::{room}"


def load_state(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(path: str, state: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    os.replace(tmp, path)


def read_source(room: str, since: int) -> list:
    url = f"{SRC_URL}/api/rooms/{room}/messages?since={since}"
    return http_json(url, headers=auth_headers(SRC_KEY, SRC_TOKEN))


def post_dest(room: str, msg: dict) -> dict:
    payload = {
        "agent": msg["agent"],
        "content": msg["content"],
        "kind": msg.get("kind", "chat"),
        "refs": msg.get("refs", []),
        "ts": msg.get("ts"),  # preserve original time (dest accepts optional ts)
    }
    url = f"{DST_URL}/api/rooms/{room}/messages"
    return http_json(url, "POST", payload, auth_headers(DST_KEY, DST_TOKEN))


def sync(room: str, since: int, dry_run: bool, state_path: str) -> int:
    """Push messages with source seq > `since` from SRC to DST. Returns count."""
    try:
        msgs = read_source(room, since)
    except urllib.error.URLError as e:
        print(f"[sync_room] cannot read source {SRC_URL}: {e}", file=sys.stderr)
        return 0

    if not msgs:
        print(f"[sync_room] '{room}' already up to date (source seq > {since}: none).")
        return 0

    pushed = 0
    highest = since
    for m in msgs:
        label = f"#{m['seq']} <{m['agent']}> ({m.get('kind', 'chat')}) {m['content'][:60]}"
        if dry_run:
            print(f"[dry-run] would push {label}")
            highest = max(highest, m["seq"])
            pushed += 1
            continue
        try:
            post_dest(room, m)
        except urllib.error.URLError as e:
            print(f"[sync_room] push failed at source seq {m['seq']}: {e}", file=sys.stderr)
            break
        highest = max(highest, m["seq"])
        pushed += 1

    if pushed and not dry_run:
        state = load_state(state_path)
        state[state_key(DST_URL, room)] = highest
        save_state(state_path, state)

    verb = "would push" if dry_run else "pushed"
    print(f"[sync_room] {verb} {pushed} message(s) from {SRC_URL} → {DST_URL} "
          f"(room '{room}', through source seq {highest}).")
    return pushed


def main(argv=None):
    p = argparse.ArgumentParser(description="Copy a Majlis room to another backend on demand.")
    p.add_argument("room", nargs="?", default=ROOM, help=f"room to sync (default {ROOM})")
    p.add_argument("--since", type=int, default=None,
                   help="override watermark: only push source seq greater than this")
    p.add_argument("--reset", action="store_true", help="forget the stored watermark first")
    p.add_argument("--dry-run", action="store_true", help="show what would be pushed, post nothing")
    p.add_argument("--state", default=STATE_PATH, help=f"watermark file (default {STATE_PATH})")
    a = p.parse_args(argv)

    if not a.dry_run and not (DST_TOKEN or DST_KEY):
        print("[sync_room] refusing to push: set MAJLIS_DST_TOKEN (PAT) or MAJLIS_DST_KEY.",
              file=sys.stderr)
        return 2

    if a.since is not None:
        since = a.since
    elif a.reset:
        since = 0
    else:
        since = load_state(a.state).get(state_key(DST_URL, a.room), 0)

    sync(a.room, since, a.dry_run, a.state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
