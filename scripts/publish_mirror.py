#!/usr/bin/env python3
"""
publish_mirror.py — mirror the LOCAL council's oracle feed to a public static page.

Runs on your machine, where PYTHIA + the local Majlis server live. It reads the
local oracle feed, bakes it into a single self-contained HTML file (data inlined
as window.__ORACLE__ — no fetch, no sidecar json), writes docs/index.html, and
can git-commit+push it. Point GitHub Pages at "Deploy from a branch → main →
/docs" and the pushed file is served publicly at
https://<owner>.github.io/<repo>/ — no public PYTHIA, no Actions secret needed.

Schedule it every 4 hours (cron / Task Scheduler), or use --loop.

Env:
  MAJLIS_URL    local council (default http://localhost:8787)
  MAJLIS_KEY    shared secret for the local server
  MAJLIS_TOKEN  bearer token (if the local council is token-gated instead)
  MAJLIS_ROOM   room to mirror (default oracle)

Usage:
  python3 scripts/publish_mirror.py --push                 # one refresh + push
  python3 scripts/publish_mirror.py --loop --push          # every 4h, forever
  python3 scripts/publish_mirror.py --empty --out docs/index.html   # seed a page
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "pages", "pythia", "index.html")
INJECT = "<!--__ORACLE__-->"

URL = os.environ.get("MAJLIS_URL", "http://localhost:8787").rstrip("/")
KEY = os.environ.get("MAJLIS_KEY", "")
TOKEN = os.environ.get("MAJLIS_TOKEN", "")
ROOM = os.environ.get("MAJLIS_ROOM", "oracle")


def headers() -> dict:
    h = {}
    if KEY:
        h["X-Majlis-Key"] = KEY
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def fetch_messages() -> list:
    req = urllib.request.Request(f"{URL}/api/rooms/{ROOM}/messages", headers=headers())
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def build_payload(empty: bool = False) -> dict:
    msgs, note = [], ""
    if empty:
        note = "seed — run scripts/publish_mirror.py on your machine to fill this"
    else:
        msgs = fetch_messages()
    return {"room": ROOM, "source": URL, "updated": time.time(),
            "count": len(msgs), "note": note, "messages": msgs}


def render_html(payload: dict) -> str:
    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()
    # escape </ so message content can't break out of the inline <script>
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    tag = f"<script>window.__ORACLE__ = {blob};</script>"
    if INJECT in html:
        return html.replace(INJECT, tag)
    return html.replace("</head>", tag + "\n</head>", 1)


def git_push(out: str, count: int):
    def git(*a):
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)

    git("add", out)
    if git("diff", "--cached", "--quiet").returncode == 0:
        print("[publish_mirror] no change; nothing to push.")
        return
    c = git("commit", "-m", f"chore: refresh PYTHIA mirror ({count} signals)")
    if c.returncode != 0:
        print(f"[publish_mirror] commit failed: {c.stderr.strip()}", file=sys.stderr)
        return
    p = git("push")
    if p.returncode != 0:
        print(f"[publish_mirror] push failed: {p.stderr.strip()}", file=sys.stderr)
        return
    print(f"[publish_mirror] pushed {out} ({count} signals).")


def once(out: str, push: bool, empty: bool) -> int:
    try:
        payload = build_payload(empty=empty)
    except urllib.error.URLError as e:
        # never overwrite the last good page with a broken one
        print(f"[publish_mirror] cannot reach local council {URL}: {e}", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render_html(payload))
    print(f"[publish_mirror] wrote {out}: {payload['count']} signal(s).")
    if push:
        git_push(out, payload["count"])
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Mirror the local oracle feed to a static HTML page.")
    p.add_argument("--out", default=os.path.join("docs", "index.html"),
                   help="output HTML (default docs/index.html, relative to the repo)")
    p.add_argument("--push", action="store_true", help="git add/commit/push the file")
    p.add_argument("--empty", action="store_true",
                   help="write a seed page without contacting the local council")
    p.add_argument("--loop", action="store_true", help="repeat forever")
    p.add_argument("--interval", type=int, default=14400,
                   help="seconds between --loop runs (default 14400 = 4h)")
    a = p.parse_args(argv)

    out = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)

    if not a.loop:
        return once(out, a.push, a.empty)
    while True:
        try:
            once(out, a.push, a.empty)
        except Exception as e:  # keep the loop alive across transient errors
            print(f"[publish_mirror] error: {e}", file=sys.stderr)
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
