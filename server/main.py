"""Majlis — multi-agent council server.

Run:  uvicorn server.main:app --host 0.0.0.0 --port 8787
Auth: set MAJLIS_KEY env var to require X-Majlis-Key header on all /api routes.
Data: workspace/rooms/<room>/messages.jsonl  +  workspace/rooms/<room>/files/
"""
import asyncio, json, os, re, time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
WS = ROOT / "workspace" / "rooms"
WS.mkdir(parents=True, exist_ok=True)
KEY = os.environ.get("MAJLIS_KEY", "")

app = FastAPI(title="Majlis")
_subscribers: dict[str, list[asyncio.Queue]] = {}


def _safe(name: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_\-\.]{1,64}", name):
        raise HTTPException(400, "invalid name")
    return name


def _room_dir(room: str) -> Path:
    d = WS / _safe(room)
    (d / "files").mkdir(parents=True, exist_ok=True)
    return d


def _check_key(request: Request):
    if KEY and request.headers.get("x-majlis-key") != KEY:
        raise HTTPException(401, "bad or missing X-Majlis-Key")


def _check_key_query_ok(request: Request):
    """Like _check_key, but also accepts ?key= — EventSource can't set headers."""
    if KEY and request.headers.get("x-majlis-key") != KEY \
            and request.query_params.get("key") != KEY:
        raise HTTPException(401, "bad or missing key")


def _read_messages(room: str, since: int = 0) -> list[dict]:
    f = _room_dir(room) / "messages.jsonl"
    if not f.exists():
        return []
    out = []
    with f.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            m = json.loads(line)
            if m["seq"] > since:
                out.append(m)
    return out


class MsgIn(BaseModel):
    agent: str
    content: str
    kind: str = "chat"          # chat | decision | system | file
    refs: list[str] = []        # filenames or decision ids referenced
    ts: float | None = None     # optional original timestamp (for replication);
                                # server stamps now() when omitted


class PresenceIn(BaseModel):
    agent: str
    state: str = "watching"     # active | watching | away


def _read_presence(room: str) -> dict[str, dict]:
    f = _room_dir(room) / "presence.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8"))


def _write_presence(room: str, presence: dict[str, dict]):
    f = _room_dir(room) / "presence.json"
    f.write_text(json.dumps(presence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


CLAIM_STATUSES = {"claimed", "working", "posted", "failed", "stale", "superseded"}


class ClaimIn(BaseModel):
    seat: str
    trigger_seq: int
    status: str = "claimed"
    scope: str = "reply"
    expires_at: float | None = None
    last_error: str | None = None
    posted_seq: int | None = None
    owner: str | None = None


def _claim_key(seat: str, trigger_seq: int) -> str:
    return f"{seat}::{trigger_seq}"


def _claim_blocks(claim: dict, now: float) -> bool:
    """Whether an existing claim should block a *different* owner from taking
    it over: still-active work (claimed/working, lease unexpired) or resolved
    for good (posted/superseded). Mirrors claim_blocks_invocation in
    scripts/watch_majlis.py; failed/stale stay reclaimable on purpose."""
    status = claim.get("status")
    if status in {"posted", "superseded"}:
        return True
    if status in {"claimed", "working"}:
        expires_at = claim.get("expires_at")
        return expires_at is None or float(expires_at) > now
    return False


def _read_claims(room: str) -> dict[str, dict]:
    f = _room_dir(room) / "claims.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8"))


def _write_claims(room: str, claims: dict[str, dict]):
    f = _room_dir(room) / "claims.json"
    f.write_text(json.dumps(claims, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@app.get("/api/rooms")
def list_rooms(request: Request):
    _check_key(request)
    rooms = []
    for d in sorted(WS.iterdir()):
        if d.is_dir():
            msgs = _read_messages(d.name)
            agents = sorted({m["agent"] for m in msgs})
            last = msgs[-1]["ts"] if msgs else None
            rooms.append({"room": d.name, "messages": len(msgs),
                          "agents": agents, "last": last})
    return rooms


@app.get("/api/rooms/{room}/messages")
def get_messages(room: str, request: Request, since: int = 0):
    _check_key(request)
    return _read_messages(room, since)


@app.get("/api/rooms/{room}/presence")
def get_presence(room: str, request: Request):
    _check_key(request)
    return sorted(_read_presence(room).values(), key=lambda p: p["agent"])


@app.post("/api/rooms/{room}/presence")
def post_presence(room: str, msg: PresenceIn, request: Request):
    _check_key(request)
    agent = _safe(msg.agent)
    state = msg.state if msg.state in {"active", "watching", "away"} else "watching"
    presence = _read_presence(room)
    presence[agent] = {"agent": agent, "state": state, "last_seen": time.time()}
    _write_presence(room, presence)
    return presence[agent]


@app.get("/api/rooms/{room}/claims")
def get_claims(room: str, request: Request, seat: str | None = None):
    _check_key(request)
    claims = list(_read_claims(room).values())
    if seat:
        claims = [c for c in claims if c["seat"] == seat]
    return sorted(claims, key=lambda c: (c["seat"], c["trigger_seq"]))


@app.post("/api/rooms/{room}/claims")
def post_claim(room: str, msg: ClaimIn, request: Request):
    _check_key(request)
    if msg.status not in CLAIM_STATUSES:
        raise HTTPException(400, "invalid status")
    seat = _safe(msg.seat)
    claims = _read_claims(room)
    key = _claim_key(seat, msg.trigger_seq)
    existing = claims.get(key)
    now = time.time()
    # Compare-and-swap: reject a write from anyone but the current owner while
    # that owner's claim is still blocking, so a second racing watcher gets 409
    # and backs off instead of both invoking. A null incoming owner can't match
    # a held claim; legacy ownerless records keep last-write-wins.
    if existing and existing.get("owner") and existing["owner"] != msg.owner \
            and _claim_blocks(existing, now):
        raise HTTPException(409, "claim held by another owner")
    record = {
        "room": room,
        "seat": seat,
        "scope": msg.scope,
        "trigger_seq": msg.trigger_seq,
        "status": msg.status,
        "started_at": existing["started_at"] if existing else now,
        "updated_at": now,
        "expires_at": msg.expires_at if msg.expires_at is not None else (existing or {}).get("expires_at"),
        "last_error": msg.last_error if msg.last_error is not None else (existing or {}).get("last_error"),
        "posted_seq": msg.posted_seq if msg.posted_seq is not None else (existing or {}).get("posted_seq"),
        "owner": msg.owner if msg.owner is not None else (existing or {}).get("owner"),
    }
    claims[key] = record
    _write_claims(room, claims)
    return record


@app.post("/api/rooms/{room}/messages")
async def post_message(room: str, msg: MsgIn, request: Request):
    _check_key(request)
    d = _room_dir(room)
    f = d / "messages.jsonl"
    seq = sum(1 for _ in f.open(encoding="utf-8")) if f.exists() else 0
    record = {"seq": seq + 1, "ts": msg.ts if msg.ts is not None else time.time(),
              "agent": _safe(msg.agent), "kind": msg.kind,
              "content": msg.content, "refs": msg.refs}
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    for q in _subscribers.get(room, []):
        q.put_nowait(record)
    return record


@app.get("/api/rooms/{room}/stream")
async def stream(room: str, request: Request):
    _check_key_query_ok(request)
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.setdefault(room, []).append(q)

    async def gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    rec = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {json.dumps(rec, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            _subscribers.get(room, []).remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/rooms/{room}/files")
def list_files(room: str, request: Request):
    _check_key(request)
    fdir = _room_dir(room) / "files"
    return [{"name": p.name, "size": p.stat().st_size, "ts": p.stat().st_mtime}
            for p in sorted(fdir.iterdir()) if p.is_file()]


@app.post("/api/rooms/{room}/files")
async def upload_file(room: str, request: Request,
                      agent: str = "unknown", file: UploadFile = File(...)):
    _check_key(request)
    name = _safe(Path(file.filename).name)
    dest = _room_dir(room) / "files" / name
    dest.write_bytes(await file.read())
    await post_message(room, MsgIn(agent=agent, kind="file",
                                   content=f"shared file: {name}",
                                   refs=[name]), request)
    return {"name": name, "size": dest.stat().st_size}


@app.get("/api/rooms/{room}/files/{name}")
def get_file(room: str, name: str, request: Request):
    _check_key(request)
    p = _room_dir(room) / "files" / _safe(name)
    if not p.exists():
        raise HTTPException(404, "no such file")
    return FileResponse(p)


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
