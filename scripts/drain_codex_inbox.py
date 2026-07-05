#!/usr/bin/env python3
"""Claim and display the next Codex pipe packet.

The pipe listener writes JSON/markdown pairs to .majlis-pipe-inbox/pending.
This script atomically moves the oldest packet to claimed and prints a compact
summary plus the prompt path so the active Codex session can read/respond.
"""
import argparse
import json
import os
import shutil
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INBOX = ROOT / ".majlis-pipe-inbox"


def ensure_dirs(inbox: Path) -> None:
    for name in ("pending", "claimed", "done"):
        (inbox / name).mkdir(parents=True, exist_ok=True)


def move_path(src: Path, dst: Path) -> bool:
    try:
        src.replace(dst)
        return True
    except PermissionError:
        try:
            shutil.copy2(src, dst)
            src.unlink()
            return True
        except OSError:
            return False
    except OSError:
        return False


def requeue_stale_claims(inbox: Path, stale_seconds: int) -> int:
    if stale_seconds <= 0:
        return 0
    now = time.time()
    moved = 0
    for json_path in sorted((inbox / "claimed").glob("*.json")):
        if now - json_path.stat().st_mtime < stale_seconds:
            continue
        stem = json_path.stem
        pending_json = inbox / "pending" / json_path.name
        if not move_path(json_path, pending_json):
            continue
        md_path = inbox / "claimed" / f"{stem}.md"
        if md_path.exists():
            move_path(md_path, inbox / "pending" / md_path.name)
        moved += 1
    return moved


def claim_next(inbox: Path, latest: bool = False):
    candidates = sorted(
        (inbox / "pending").glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=latest,
    )
    blocked = 0
    for json_path in candidates:
        claimed_json = inbox / "claimed" / json_path.name
        if not move_path(json_path, claimed_json):
            blocked += 1
            continue
        md_path = inbox / "pending" / f"{json_path.stem}.md"
        claimed_md = inbox / "claimed" / md_path.name
        if md_path.exists():
            move_path(md_path, claimed_md)
        return claimed_json, claimed_md if claimed_md.exists() else None, blocked, len(candidates)
    return None, None, blocked, len(candidates)


def mark_done(inbox: Path, stem: str) -> None:
    for suffix in (".json", ".md"):
        src = inbox / "claimed" / f"{stem}{suffix}"
        if src.exists():
            if not move_path(src, inbox / "done" / src.name):
                raise OSError(f"could not move {src} to done")


def load_packet(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inbox", default=str(DEFAULT_INBOX))
    parser.add_argument("--stale-seconds", type=int, default=900)
    parser.add_argument("--latest", action="store_true", help="Claim the newest pending packet instead of the oldest.")
    parser.add_argument("--done", help="Move claimed packet stem to done.")
    args = parser.parse_args()

    inbox = Path(args.inbox)
    ensure_dirs(inbox)
    if args.done:
        mark_done(inbox, args.done)
        print(f"done {args.done}")
        return 0

    requeued = requeue_stale_claims(inbox, args.stale_seconds)
    json_path, md_path, blocked, pending = claim_next(inbox, latest=args.latest)
    if not json_path:
        if pending:
            print(f"pending packets exist but could not be claimed; pending={pending} blocked={blocked} requeued_stale={requeued}")
        else:
            print(f"no pending packets; requeued_stale={requeued}")
        return 1

    packet = load_packet(json_path)
    content = str(packet.get("prompt", ""))
    preview = " ".join(content.split())[:500]
    print(f"claimed={json_path.stem}")
    print(f"json={json_path}")
    if md_path:
        print(f"prompt={md_path}")
    print(f"room={packet.get('room')} seat={packet.get('seat')} seq={packet.get('seq')}")
    print(f"preview={preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
