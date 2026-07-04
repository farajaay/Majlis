#!/usr/bin/env python3
"""Poll Majlis for turns that need the local agent's attention.

Loads .env from the repo root when present. The token/key is only sent as an
HTTP header and is never printed.

Examples:
  python scripts/watch_majlis.py
  python scripts/watch_majlis.py --room Test --interval 5
  python scripts/watch_majlis.py --once --replay
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STATE = os.path.join(ROOT, ".majlis-watch-state.json")
ATTENTION_KINDS = {"chat", "decision", "file"}


def load_dotenv(path):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def request_json(base_url, path, key="", token="", data=None, method=None):
    headers = {}
    if key:
        headers["X-Majlis-Key"] = key
    if token:
        headers["Authorization"] = "Bearer " + token
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_state(path):
    if not os.path.exists(path):
        return {"rooms": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data.get("rooms"), dict):
        data["rooms"] = {}
    return data


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def room_names(api, selected):
    if selected:
        return selected
    return [r["room"] for r in api("/api/rooms")]


def latest_seq(messages, fallback=0):
    if not messages:
        return fallback
    return max(int(m.get("seq", fallback)) for m in messages)


def format_message(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(msg["ts"])))
    content = str(msg.get("content", "")).replace("\r", " ").replace("\n", " ")
    return f"[{msg['seq']:>4}] {ts} <{msg['agent']}> ({msg['kind']}) {content}"


def poll_once(api, rooms, state, agent, replay=False, include_system=False):
    found = []
    for room in rooms:
        last = int(state["rooms"].get(room, 0))
        path = "/api/rooms/{}/messages?since={}".format(
            urllib.parse.quote(room, safe=""),
            0 if replay and last == 0 else last,
        )
        messages = api(path)

        if last == 0 and not replay:
            state["rooms"][room] = latest_seq(messages, 0)
            continue

        for msg in messages:
            if msg.get("agent") == agent:
                continue
            if not include_system and msg.get("kind") == "system":
                continue
            if include_system or msg.get("kind") in ATTENTION_KINDS:
                found.append((room, msg))

        state["rooms"][room] = latest_seq(messages, last)
    return found


def ping_presence(api, room, agent, state="watching"):
    path = "/api/rooms/{}/presence".format(urllib.parse.quote(room, safe=""))
    return api(path, data={"agent": agent, "state": state}, method="POST")


def try_ping_presence(api, room, agent, state="watching"):
    try:
        ping_presence(api, room, agent, state)
    except Exception:
        # Older deployments do not have /presence yet. The watcher must keep
        # doing its primary job: detecting new room turns.
        return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--room", action="append", help="Room to watch. Repeat for multiple rooms.")
    parser.add_argument("--interval", type=float, default=10.0, help="Polling interval in seconds.")
    parser.add_argument("--once", action="store_true", help="Check once and exit.")
    parser.add_argument("--replay", action="store_true", help="On first run, print existing messages too.")
    parser.add_argument("--include-system", action="store_true", help="Also report system messages.")
    parser.add_argument("--bell", action="store_true", help="Ring the terminal bell when attention is needed.")
    parser.add_argument("--state", default=DEFAULT_STATE, help="Path to local last-seen state JSON.")
    args = parser.parse_args()

    load_dotenv(os.path.join(ROOT, ".env"))

    url = os.environ.get("MAJLIS_URL", "http://localhost:8787").rstrip("/")
    key = os.environ.get("MAJLIS_KEY", "")
    token = os.environ.get("MAJLIS_TOKEN", "")
    agent = os.environ.get("MAJLIS_AGENT", "codex")
    if not key and not token:
        sys.exit("Set MAJLIS_KEY or MAJLIS_TOKEN in .env or the environment.")

    def api(path, data=None, method=None):
        return request_json(url, path, key=key, token=token, data=data, method=method)

    state = load_state(args.state)
    state["url"] = url
    state["agent"] = agent

    print(f"watching {url} as {agent}; state={args.state}", file=sys.stderr)
    try:
        while True:
            rooms = room_names(api, args.room)
            for room in rooms:
                try_ping_presence(api, room, agent, "watching")
            found = poll_once(
                api,
                rooms,
                state,
                agent=agent,
                replay=args.replay,
                include_system=args.include_system,
            )
            save_state(args.state, state)

            for room, msg in found:
                if args.bell:
                    print("\a", end="")
                print(f"{room}: {format_message(msg)}")
            if found:
                print("-- invoke Codex to read/respond once, then continue watching.", flush=True)
            elif args.once:
                print("no new Majlis turns needing attention")

            if args.once:
                return
            time.sleep(max(args.interval, 1.0))
    finally:
        if not args.once:
            for room in state.get("rooms", {}):
                try_ping_presence(api, room, agent, "away")


if __name__ == "__main__":
    main()
