#!/usr/bin/env python3
"""Invoke the codex seat from watch_majlis.py.

The watcher passes room/seat/seq as args and the fresh transcript on stdin.

If OPENAI_API_KEY is set, this script asks the OpenAI Responses API for a
short Majlis reply and posts it through the Majlis HTTP API. If no API key is
set, it writes a local prompt packet, copies it to the Windows clipboard when
available, and opens the Codex desktop app.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "gpt-4.1-mini"
CODEX_APP_ID = "OpenAI.Codex_2p2nqsd0c76g0!App"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def request_json(url, data=None, headers=None, method=None):
    body = None
    h = dict(headers or {})
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


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
    return request_json(
        base + path,
        {"agent": seat, "content": content, "kind": "chat"},
        headers=headers,
        method="POST",
    )


def extract_response_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"].strip()
    parts = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def build_prompt(room: str, seat: str, seq: str, transcript: str) -> str:
    return f"""You are the `{seat}` seat in a Majlis council room.

Room: {room}
Addressed/new turn seq: {seq}

Reply as `{seat}` with one focused Majlis chat turn.
Constraints:
- 150 words maximum.
- Cite relevant sequence numbers, e.g. `re #123`.
- Be direct and useful.
- Do not claim persistent autonomous presence. If watcher/invocation limits matter, say so plainly.
- Do not include markdown tables.

Transcript:
{transcript}
"""


def openai_reply(prompt: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return ""
    model = os.environ.get("MAJLIS_OPENAI_MODEL", os.environ.get("OPENAI_MODEL", DEFAULT_MODEL))
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": "You are Codex participating in a concise multi-agent engineering council.",
            },
            {"role": "user", "content": prompt},
        ],
        "max_output_tokens": 350,
    }
    headers = {"Authorization": "Bearer " + api_key}
    result = request_json("https://api.openai.com/v1/responses", payload, headers=headers, method="POST")
    return extract_response_text(result)


def write_prompt_packet(room: str, seat: str, seq: str, prompt: str) -> Path:
    out_dir = ROOT / ".majlis-invoke"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_room = "".join(c if c.isalnum() or c in "-_." else "_" for c in room)
    path = out_dir / f"{stamp}-{safe_room}-{seat}-{seq}.md"
    path.write_text(prompt, encoding="utf-8")
    return path


def copy_to_clipboard(text: str) -> bool:
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
            input=text,
            text=True,
            check=True,
            timeout=15,
            capture_output=True,
        )
        return True
    except Exception:
        return False


def open_codex_app() -> bool:
    try:
        subprocess.Popen(
            ["explorer.exe", f"shell:AppsFolder\\{CODEX_APP_ID}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("room", nargs="?")
    parser.add_argument("seat", nargs="?")
    parser.add_argument("seq", nargs="?")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")

    room = args.room or os.environ.get("MAJLIS_INVOKE_ROOM", "")
    seat = args.seat or os.environ.get("MAJLIS_INVOKE_SEAT", os.environ.get("MAJLIS_AGENT", "codex"))
    seq = args.seq or os.environ.get("MAJLIS_INVOKE_SEQ", "")
    transcript = sys.stdin.read()
    if not room or not seat or not seq:
        print("room, seat, and seq are required", file=sys.stderr)
        return 2

    prompt = build_prompt(room, seat, seq, transcript)
    if args.dry_run:
        print(prompt)
        return 0

    reply = openai_reply(prompt)
    if reply:
        record = post_majlis(room, seat, reply)
        print(f"posted {seat} reply seq {record.get('seq')}")
        return 0

    packet = write_prompt_packet(room, seat, seq, prompt)
    copied = copy_to_clipboard(prompt)
    opened = open_codex_app()
    print(f"prepared Codex prompt packet: {packet}")
    print(f"clipboard={'yes' if copied else 'no'} codex_app={'opened' if opened else 'not-opened'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
