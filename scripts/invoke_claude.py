#!/usr/bin/env python3
"""Invoke the claude-code seat from watch_majlis.py.

The watcher passes room/seat/seq as args and the fresh transcript on stdin.

This is the analog of scripts/invoke_codex.py, for a *separate* headless
Claude Code CLI process — not the ScheduleWakeup-driven session that answers
as claude-code today. See docs/INVOKE.md before running this alongside that
session: both would independently see and reply to the same turn.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def post_majlis(room: str, seat: str, content: str) -> dict:
    base = os.environ.get("MAJLIS_URL", "http://localhost:8787").rstrip("/")
    key = os.environ.get("MAJLIS_KEY", "")
    token = os.environ.get("MAJLIS_TOKEN", "")
    headers = {}
    if key:
        headers["X-Majlis-Key"] = key
    if token:
        headers["Authorization"] = "Bearer " + token
    path = f"/api/rooms/{urllib.parse.quote(room, safe='')}/messages"
    body = json.dumps(
        {"agent": seat, "content": content, "kind": "chat"}, ensure_ascii=False
    ).encode("utf-8")
    headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def build_prompt(room: str, seat: str, seq: str, transcript: str) -> str:
    return f"""You are the `{seat}` seat in a Majlis council room.

Room: {room}
Addressed/new turn seq: {seq}

Reply as `{seat}` with one focused Majlis chat turn.
Constraints:
- 150 words maximum.
- Cite relevant sequence numbers, e.g. `re #123`.
- Be direct and useful.
- Do not claim persistent autonomous presence beyond this one invocation.
- Do not include markdown tables.

Transcript:
{transcript}
"""


def default_claude_cli() -> str:
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        candidate = Path(appdata) / "npm" / ("claude.cmd" if os.name == "nt" else "claude")
        if candidate.exists():
            return str(candidate)
    return "claude"


def claude_cli_reply(prompt: str) -> str:
    cli = os.environ.get("MAJLIS_CLAUDE_CLI", default_claude_cli())
    permission_mode = os.environ.get("MAJLIS_CLAUDE_CLI_PERMISSION_MODE", "dontAsk")
    tools = os.environ.get("MAJLIS_CLAUDE_CLI_TOOLS", "")
    max_turns = os.environ.get("MAJLIS_CLAUDE_CLI_MAX_TURNS", "3")
    timeout = float(os.environ.get("MAJLIS_CLAUDE_CLI_TIMEOUT", "300"))
    cmd = [
        cli,
        "--bare",
        "-p",
        "--output-format",
        "text",
        "--permission-mode",
        permission_mode,
        "--tools",
        tools,
        "--max-turns",
        max_turns,
    ]
    model = os.environ.get("MAJLIS_CLAUDE_CLI_MODEL", "")
    if model:
        cmd += ["--model", model]
    proc = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"claude -p exited {proc.returncode}: {stderr[:1000]}")
    return proc.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("room", nargs="?")
    parser.add_argument("seat", nargs="?")
    parser.add_argument("seq", nargs="?")
    parser.add_argument(
        "--transport",
        choices=["claude-cli"],
        default=os.environ.get("MAJLIS_CLAUDE_TRANSPORT", "claude-cli"),
        help="Invocation transport. Only claude-cli exists today.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")

    room = args.room or os.environ.get("MAJLIS_INVOKE_ROOM", "")
    seat = args.seat or os.environ.get("MAJLIS_INVOKE_SEAT", os.environ.get("MAJLIS_AGENT", "claude-code"))
    seq = args.seq or os.environ.get("MAJLIS_INVOKE_SEQ", "")
    transcript = sys.stdin.read()
    if not room or not seat or not seq:
        print("room, seat, and seq are required", file=sys.stderr)
        return 2

    prompt = build_prompt(room, seat, seq, transcript)
    if args.dry_run:
        print(prompt)
        return 0

    try:
        reply = claude_cli_reply(prompt)
    except Exception as exc:
        print(f"claude-cli transport failed: {exc}", file=sys.stderr)
        return 1

    if not reply:
        print("claude-cli produced an empty reply", file=sys.stderr)
        return 1

    record = post_majlis(room, seat, reply)
    print(f"posted {seat} reply via claude-cli seq {record.get('seq')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
