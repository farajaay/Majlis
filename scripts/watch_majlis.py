#!/usr/bin/env python3
"""Poll Majlis for turns that need the local agent's attention.

Loads .env from the repo root when present. The token/key is only sent as an
HTTP header and is never printed.

This watcher owns one seat (MAJLIS_AGENT, or --owned-seat). When a new turn
addresses that seat (`@seat` anywhere, or `seat:`/`seat -`/`seat —` at the
start of a message), it fires an invocation hook — see docs/INVOKE.md for
the driver model (manual/notify by default, or a configurable local command).

Examples:
  python scripts/watch_majlis.py
  python scripts/watch_majlis.py --room Test --interval 5
  python scripts/watch_majlis.py --once --replay
  python scripts/watch_majlis.py --invoke-driver command --invoke-cmd "./invoke_codex.sh"
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.parse
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STATE = os.path.join(ROOT, ".majlis-watch-state.json")
ATTENTION_KINDS = {"chat", "decision", "file"}
MENTION_RE_CACHE = {}


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
        return {"rooms": {}, "invoked": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data.get("rooms"), dict):
        data["rooms"] = {}
    if not isinstance(data.get("invoked"), dict):
        data["invoked"] = {}
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


def github_dispatch(repo, token, workflow, inputs):
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"
    data = json.dumps({
        "ref": "main",
        "inputs": inputs
    }).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "watch_majlis"
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 204
    except Exception as e:
        print(f"Error dispatching workflow: {e}", file=sys.stderr)
        return False


def _mention_pattern(name):
    pat = MENTION_RE_CACHE.get(name)
    if pat is None:
        escaped = re.escape(name.lower())
        pat = re.compile(r"@" + escaped + r"\b|^\s*" + escaped + r"\s*[:—-]")
        MENTION_RE_CACHE[name] = pat
    return pat


def mentions_seat(content, seat, aliases=None):
    """True if a message addresses `seat`: `@seat` anywhere, or `seat:`/`seat -`/
    `seat —` at the start of the message. Also checks any configured aliases
    (e.g. "claude" for a seat named "claude-code")."""
    text = (content or "").lower()
    for name in [seat] + list(aliases or []):
        if not name:
            continue
        if _mention_pattern(name).search(text):
            return True
    return False


class Invoker:
    """Fires a reasoning step for an addressed seat. Never posts to Majlis
    itself — that stays majlis.py's `say`, the only post path. The invoker's
    job ends at kicking off whatever will eventually call `say`."""

    def invoke(self, room, seat, message, transcript):
        raise NotImplementedError


class ManualNotifyInvoker(Invoker):
    """Default, safe driver: just alerts/logs. Nothing about how the seat
    actually responds changes unless a real driver is configured."""

    def invoke(self, room, seat, message, transcript):
        print(
            f"-- @{seat} addressed in '{room}' (seq {message.get('seq')}): "
            f"invoke {seat} to read and respond once.",
            flush=True,
        )
        return True


class CommandInvoker(Invoker):
    """Runs a configurable local shell command as the invocation hook. The
    room, seat, and addressed seq are passed both as env vars and as
    appended (shell-escaped) args; the fresh transcript is piped on stdin.

    This is the seam for driving a real reasoning step — e.g. desktop
    automation that brings a seat's app forward and prompts it, or any
    other local mechanism the user wires up. It does not itself make a
    desktop app reason; it only runs whatever command the user configured.
    """

    def __init__(self, command, timeout=120):
        self.command = command
        self.timeout = timeout

    def invoke(self, room, seat, message, transcript):
        env = os.environ.copy()
        env["MAJLIS_INVOKE_ROOM"] = room
        env["MAJLIS_INVOKE_SEAT"] = seat
        env["MAJLIS_INVOKE_SEQ"] = str(message.get("seq", ""))
        full_cmd = self.command + " " + " ".join(
            shlex.quote(x) for x in (room, seat, str(message.get("seq", "")))
        )
        try:
            proc = subprocess.run(
                full_cmd,
                shell=True,
                input=transcript,
                text=True,
                env=env,
                timeout=self.timeout,
                capture_output=True,
            )
        except Exception as exc:
            print(f"-- invoke command failed for @{seat} in '{room}': {exc}", file=sys.stderr, flush=True)
            return False
        if proc.stdout:
            print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
        if proc.stderr:
            print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", file=sys.stderr)
        if proc.returncode != 0:
            print(
                f"-- invoke command exited {proc.returncode} for @{seat} in '{room}'",
                file=sys.stderr,
                flush=True,
            )
            return False
        return True


def build_invoker(driver, command):
    if driver == "command":
        if not command:
            sys.exit("--invoke-driver command requires --invoke-cmd (or MAJLIS_INVOKE_CMD)")
        return CommandInvoker(command)
    return ManualNotifyInvoker()


def fetch_transcript(api, room):
    messages = api(f"/api/rooms/{urllib.parse.quote(room, safe='')}/messages?since=0")
    lines = [format_message(m) for m in messages]
    return "\n".join(lines) + ("\n" if lines else "")


def route_addressed(found, owned_seat, aliases, agent, invoked_state, invoker, api):
    """For each newly-seen message that addresses `owned_seat`, fire the
    invoker at most once (persisted in invoked_state[room] by seq, so a
    restart never re-fires a turn already handled). Never fires on the
    owned seat's own messages."""
    for room, msg in found:
        if msg.get("agent") == agent:
            continue
        if not mentions_seat(msg.get("content", ""), owned_seat, aliases):
            continue
        seq = int(msg.get("seq", 0))
        last_invoked = int(invoked_state.get(room, 0))
        if seq <= last_invoked:
            continue
        transcript = fetch_transcript(api, room)
        invoker.invoke(room, owned_seat, msg, transcript)
        invoked_state[room] = max(last_invoked, seq)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--room", action="append", help="Room to watch. Repeat for multiple rooms.")
    parser.add_argument("--interval", type=float, default=10.0, help="Polling interval in seconds.")
    parser.add_argument("--once", action="store_true", help="Check once and exit.")
    parser.add_argument("--replay", action="store_true", help="On first run, print existing messages too.")
    parser.add_argument("--include-system", action="store_true", help="Also report system messages.")
    parser.add_argument("--bell", action="store_true", help="Ring the terminal bell when attention is needed.")
    parser.add_argument("--state", default=DEFAULT_STATE, help="Path to local last-seen state JSON.")
    parser.add_argument("--auto-dispatch", help="GitHub repo for workflow_dispatch (e.g. farajaay/Majlis).")
    parser.add_argument("--workflow", default="agent-runner.yml", help="Workflow filename to dispatch.")
    parser.add_argument(
        "--owned-seat",
        default=os.environ.get("MAJLIS_OWNED_SEAT", ""),
        help="Seat this watcher instance owns for @seat routing (default: MAJLIS_AGENT).",
    )
    parser.add_argument(
        "--seat-alias",
        action="append",
        default=None,
        help="Extra name that also addresses the owned seat (repeatable). "
        "Defaults to comma-separated MAJLIS_SEAT_ALIASES if set.",
    )
    parser.add_argument(
        "--invoke-driver",
        choices=["manual", "command"],
        default=os.environ.get("MAJLIS_INVOKE_DRIVER", "manual"),
        help="How to fire the invocation hook when the owned seat is addressed. "
        "'manual' (default) just logs; 'command' runs --invoke-cmd.",
    )
    parser.add_argument(
        "--invoke-cmd",
        default=os.environ.get("MAJLIS_INVOKE_CMD", ""),
        help="Shell command to run for --invoke-driver command. Receives room/seat/seq "
        "as env vars (MAJLIS_INVOKE_ROOM/SEAT/SEQ) and appended args, transcript on stdin.",
    )
    args = parser.parse_args()

    load_dotenv(os.path.join(ROOT, ".env"))

    url = os.environ.get("MAJLIS_URL", "http://localhost:8787").rstrip("/")
    key = os.environ.get("MAJLIS_KEY", "")
    token = os.environ.get("MAJLIS_TOKEN", "")
    agent = os.environ.get("MAJLIS_AGENT", "codex")
    if not key and not token:
        sys.exit("Set MAJLIS_KEY or MAJLIS_TOKEN in .env or the environment.")

    owned_seat = args.owned_seat or agent
    aliases = args.seat_alias
    if aliases is None:
        env_aliases = os.environ.get("MAJLIS_SEAT_ALIASES", "")
        aliases = [a.strip() for a in env_aliases.split(",") if a.strip()]
    invoker = build_invoker(args.invoke_driver, args.invoke_cmd)

    def api(path, data=None, method=None):
        return request_json(url, path, key=key, token=token, data=data, method=method)

    state = load_state(args.state)
    state["url"] = url
    state["agent"] = agent

    print(
        f"watching {url} as {agent}; owned seat={owned_seat}; "
        f"invoke-driver={args.invoke_driver}; state={args.state}",
        file=sys.stderr,
    )
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
            route_addressed(found, owned_seat, aliases, agent, state["invoked"], invoker, api)
            save_state(args.state, state)

            for room, msg in found:
                if args.bell:
                    print("\a", end="")
                print(f"{room}: {format_message(msg)}")
            if found:
                if args.auto_dispatch and token:
                    unique_rooms = set(r for r, m in found)
                    for r in unique_rooms:
                        print(f"-- auto-dispatching {agent} in '{r}' to {args.auto_dispatch} via {args.workflow}...", flush=True)
                        success = github_dispatch(args.auto_dispatch, token, args.workflow, {"agent": agent, "room": r})
                        if success:
                            print("   dispatch successful.")
                        else:
                            print("   dispatch failed.")
                else:
                    print(f"-- invoke {agent} to read/respond once, then continue watching.", flush=True)
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
