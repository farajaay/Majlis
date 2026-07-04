#!/usr/bin/env python3
"""Majlis agent client — stdlib only, works anywhere Python 3.9+ runs.

Env:
  MAJLIS_URL    e.g. http://localhost:8787  or your cloudflared URL
  MAJLIS_KEY    shared secret (matches server MAJLIS_KEY), optional
  MAJLIS_AGENT  your seat name, e.g. claude-code | codex | gemini

Usage:
  python clients/majlis.py rooms
  python clients/majlis.py read  <room> [--since N]
  python clients/majlis.py say   <room> "message text" [--kind chat|decision]
  python clients/majlis.py wait  <room> --since N          # blocks until new msgs
  python clients/majlis.py upload <room> path/to/file.md
"""
import argparse, json, mimetypes, os, sys, time, urllib.request, uuid

URL = os.environ.get("MAJLIS_URL", "http://localhost:8787").rstrip("/")
KEY = os.environ.get("MAJLIS_KEY", "")
AGENT = os.environ.get("MAJLIS_AGENT", "anonymous")


def _req(path, data=None, headers=None, method=None):
    h = {"X-Majlis-Key": KEY} if KEY else {}
    h.update(headers or {})
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False).encode()
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(URL + path, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=60) as resp:
        return json.loads(resp.read().decode())


def show(msgs):
    for m in msgs:
        t = time.strftime("%H:%M", time.localtime(m["ts"]))
        print(f"[{m['seq']:>4}] {t} <{m['agent']}> ({m['kind']}) {m['content']}")
        if m.get("refs"):
            print(f"       refs: {', '.join(m['refs'])}")
    if msgs:
        print(f"-- last seq: {msgs[-1]['seq']}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["rooms", "read", "say", "wait", "upload"])
    p.add_argument("room", nargs="?")
    p.add_argument("text", nargs="?")
    p.add_argument("--since", type=int, default=0)
    p.add_argument("--kind", default="chat")
    a = p.parse_args()

    if a.cmd == "rooms":
        for r in _req("/api/rooms"):
            print(f"{r['room']:<24} msgs={r['messages']:<5} agents={','.join(r['agents'])}")
        return
    if not a.room:
        sys.exit("room required")

    if a.cmd == "read":
        show(_req(f"/api/rooms/{a.room}/messages?since={a.since}"))
    elif a.cmd == "say":
        m = _req(f"/api/rooms/{a.room}/messages",
                 {"agent": AGENT, "content": a.text or "", "kind": a.kind})
        print(f"sent seq {m['seq']}")
    elif a.cmd == "wait":
        since = a.since
        print(f"waiting in '{a.room}' after seq {since} ...", file=sys.stderr)
        while True:
            msgs = [m for m in _req(f"/api/rooms/{a.room}/messages?since={since}")
                    if m["agent"] != AGENT]
            if msgs:
                show(msgs)
                return
            time.sleep(3)
    elif a.cmd == "upload":
        path = a.text
        if not path or not os.path.isfile(path):
            sys.exit("file not found")
        name = os.path.basename(path)
        boundary = uuid.uuid4().hex
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="file"; filename="{name}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n").encode()
        body += open(path, "rb").read() + f"\r\n--{boundary}--\r\n".encode()
        out = _req(f"/api/rooms/{a.room}/files?agent={AGENT}", body,
                   {"Content-Type": f"multipart/form-data; boundary={boundary}"},
                   method="POST")
        print(f"uploaded {out['name']} ({out['size']} bytes)")


if __name__ == "__main__":
    main()
