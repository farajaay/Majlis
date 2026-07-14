import { Collection, MongoClient } from "mongodb";

const ROOM_RE = /^[a-zA-Z0-9_\-.]{1,64}$/;

export function assertSafeName(name: string): string {
  if (!ROOM_RE.test(name)) throw new Error("invalid name");
  return name;
}

export type Message = {
  room: string;
  seq: number;
  ts: number;
  agent: string;
  kind: "chat" | "decision" | "system" | "file";
  content: string;
  refs: string[];
};

export type FileMeta = { room: string; name: string; url: string; size: number; ts: number };
export type Presence = {
  room: string;
  agent: string;
  state: "active" | "watching" | "away";
  last_seen: number;
};
type Counter = { _id: string; seq: number };

export type ClaimStatus = "claimed" | "working" | "posted" | "failed" | "stale" | "superseded";

const CLAIM_STATUSES: ClaimStatus[] = ["claimed", "working", "posted", "failed", "stale", "superseded"];

export type Claim = {
  room: string;
  seat: string;
  scope: string;
  trigger_seq: number;
  status: ClaimStatus;
  started_at: number;
  updated_at: number;
  expires_at: number | null;
  last_error: string | null;
  posted_seq: number | null;
  // Per-process nonce identifying who holds this claim. Optional for
  // backwards compatibility: legacy records (and callers that don't send an
  // owner) have `null` and get the old last-write-wins behaviour. When set,
  // it turns the upsert into a compare-and-swap so a second process can't
  // steal a claim another owner is actively holding — see upsertClaim.
  owner?: string | null;
};

// Raised by upsertClaim when a POST would overwrite a claim that a *different*
// owner is currently holding (active-unexpired or terminal). The route maps
// this to HTTP 409 so a racing watcher backs off instead of both invoking.
export class ClaimConflictError extends Error {
  constructor(message = "claim held by another owner") {
    super(message);
    this.name = "ClaimConflictError";
  }
}

// Whether an existing claim should block a different owner from grabbing it:
// still-active work (claimed/working with an unexpired lease) or resolved for
// good (posted/superseded). Mirrors claim_blocks_invocation in
// scripts/watch_majlis.py — failed/stale are deliberately reclaimable.
function claimBlocks(claim: Claim, now: number): boolean {
  if (claim.status === "posted" || claim.status === "superseded") return true;
  if (claim.status === "claimed" || claim.status === "working") {
    return claim.expires_at == null || claim.expires_at > now;
  }
  return false;
}

// This project shares a MongoDB Atlas cluster with another Vercel project
// (the only already-authorized, API-provisionable database on the account) —
// everything Majlis writes lives in its own `majlis` database within that
// cluster, isolated from whatever collections the other project uses.
let clientPromise: Promise<MongoClient> | null = null;
function getClient(): Promise<MongoClient> {
  if (!clientPromise) {
    const uri = process.env.MONGODB_URI;
    if (!uri) throw new Error("MONGODB_URI not set");
    clientPromise = new MongoClient(uri).connect();
  }
  return clientPromise;
}

async function db() {
  return (await getClient()).db("majlis");
}
async function messages(): Promise<Collection<Message>> {
  return (await db()).collection<Message>("messages");
}
async function files(): Promise<Collection<FileMeta>> {
  return (await db()).collection<FileMeta>("files");
}
async function presence(): Promise<Collection<Presence>> {
  return (await db()).collection<Presence>("presence");
}
async function counters(): Promise<Collection<Counter>> {
  return (await db()).collection<Counter>("counters");
}
async function claims(): Promise<Collection<Claim>> {
  return (await db()).collection<Claim>("claims");
}

// Hard ceiling on how many messages one read returns. A pathologically large
// room (e.g. a runaway sync flooding thousands of multi-KB briefs) must never
// force an unbounded, multi-megabyte response that trips the serverless
// payload/time limit — so reads return at most the most-recent MAX_MESSAGES.
export const DEFAULT_MESSAGE_LIMIT = 500;
export const MAX_MESSAGE_LIMIT = 1000;

// Ensure the compound index that keeps message reads (filtered by room, sorted
// by seq) off a collection scan — without it, a large `messages` collection
// makes even an empty-result query time out. Cached so it runs at most once per
// warm process; createIndex is idempotent.
let indexesPromise: Promise<void> | null = null;
function ensureIndexes(): Promise<void> {
  if (!indexesPromise) {
    indexesPromise = (async () => {
      await (await messages()).createIndex({ room: 1, seq: 1 });
    })().catch((e) => {
      indexesPromise = null; // let a later call retry after a transient failure
      throw e;
    });
  }
  return indexesPromise;
}

export async function listRooms(): Promise<
  { room: string; messages: number; agents: string[]; last: number | null }[]
> {
  await ensureIndexes();
  const col = await messages();
  const rooms = await col.distinct("room");
  const out = [];
  for (const room of rooms.sort()) {
    // Count and last-message lookups are server-side and index-friendly — never
    // load the whole room into memory (a huge room would blow the heap).
    const count = await col.countDocuments({ room });
    const lastDoc = await col
      .find({ room }, { projection: { _id: 0, ts: 1 } })
      .sort({ seq: -1 })
      .limit(1)
      .next();
    const agents = (await col.distinct("agent", { room })).sort();
    out.push({ room, messages: count, agents, last: lastDoc ? lastDoc.ts : null });
  }
  return out;
}

export async function readMessages(
  room: string,
  since = 0,
  limit?: number
): Promise<Message[]> {
  assertSafeName(room);
  await ensureIndexes();
  const col = await messages();
  const cap = Math.min(
    limit && limit > 0 ? limit : DEFAULT_MESSAGE_LIMIT,
    MAX_MESSAGE_LIMIT
  );
  // Return the most-recent `cap` messages in the range: sort descending, take
  // `cap` (index-covered, bounded), then reverse to the ascending order clients
  // expect. Incremental pollers (since=lastSeq) see small deltas as before; an
  // initial since=0 load on a huge room gets a bounded tail instead of timing
  // out or returning tens of MB.
  const docs = await col
    .find({ room, seq: { $gt: since } }, { projection: { _id: 0 } })
    .sort({ seq: -1 })
    .limit(cap)
    .toArray();
  return docs.reverse();
}

export async function postMessage(
  room: string,
  msg: { agent: string; content: string; kind?: Message["kind"]; refs?: string[]; ts?: number }
): Promise<Message> {
  assertSafeName(room);
  assertSafeName(msg.agent);
  const counterDoc = await (
    await counters()
  ).findOneAndUpdate(
    { _id: room },
    { $inc: { seq: 1 } },
    { upsert: true, returnDocument: "after" }
  );
  const seq = counterDoc!.seq;
  const record: Message = {
    room,
    seq,
    ts: typeof msg.ts === "number" ? msg.ts : Date.now() / 1000,
    agent: msg.agent,
    kind: msg.kind ?? "chat",
    content: msg.content,
    refs: msg.refs ?? [],
  };
  await (await messages()).insertOne({ ...record });
  // Auto-update presence to active when an agent speaks
  await updatePresence(room, { agent: msg.agent, state: "active" });
  return record;
}

export async function listFiles(room: string): Promise<FileMeta[]> {
  assertSafeName(room);
  return (await files())
    .find({ room }, { projection: { _id: 0 } })
    .sort({ name: 1 })
    .toArray();
}

export async function addFile(room: string, file: Omit<FileMeta, "room">): Promise<void> {
  assertSafeName(room);
  assertSafeName(file.name);
  await (
    await files()
  ).updateOne({ room, name: file.name }, { $set: { room, ...file } }, { upsert: true });
}

export async function getFile(room: string, name: string): Promise<FileMeta | null> {
  assertSafeName(room);
  return (await files()).findOne({ room, name }, { projection: { _id: 0 } });
}

export async function listPresence(room: string): Promise<Presence[]> {
  assertSafeName(room);
  return (await presence())
    .find({ room }, { projection: { _id: 0 } })
    .sort({ agent: 1 })
    .toArray();
}

export async function updatePresence(
  room: string,
  msg: { agent: string; state?: Presence["state"] }
): Promise<Presence> {
  assertSafeName(room);
  assertSafeName(msg.agent);
  const state = msg.state && ["active", "watching", "away"].includes(msg.state)
    ? msg.state
    : "watching";
  const record: Presence = { room, agent: msg.agent, state, last_seen: Date.now() / 1000 };
  await (
    await presence()
  ).updateOne({ room, agent: msg.agent }, { $set: record }, { upsert: true });
  return record;
}

export async function listClaims(room: string, seat?: string): Promise<Claim[]> {
  assertSafeName(room);
  const query: { room: string; seat?: string } = { room };
  if (seat) query.seat = seat;
  return (await claims())
    .find(query, { projection: { _id: 0 } })
    .sort({ seat: 1, trigger_seq: 1 })
    .toArray();
}

export async function upsertClaim(
  room: string,
  msg: {
    seat: string;
    trigger_seq: number;
    status?: string;
    scope?: string;
    expires_at?: number | null;
    last_error?: string | null;
    posted_seq?: number | null;
    owner?: string | null;
  }
): Promise<Claim> {
  assertSafeName(room);
  assertSafeName(msg.seat);
  if (msg.status && !CLAIM_STATUSES.includes(msg.status as ClaimStatus)) {
    throw new Error("invalid status");
  }
  const status = (msg.status as ClaimStatus) || "claimed";
  const col = await claims();
  const existing = await col.findOne({ room, seat: msg.seat, trigger_seq: msg.trigger_seq });
  const now = Date.now() / 1000;
  // Compare-and-swap: reject a write from anyone other than the current owner
  // while that owner's claim is still blocking. This closes the client's
  // GET-then-POST race (scripts/watch_majlis.py claim_and_invoke) — the loser
  // gets 409 and skips instead of both processes invoking. A null incoming
  // owner never matches a held claim, so it can't steal one either; legacy
  // records without an owner keep last-write-wins.
  const incomingOwner = msg.owner ?? null;
  if (existing && existing.owner && existing.owner !== incomingOwner && claimBlocks(existing, now)) {
    throw new ClaimConflictError();
  }
  const record: Claim = {
    room,
    seat: msg.seat,
    scope: msg.scope ?? existing?.scope ?? "reply",
    trigger_seq: msg.trigger_seq,
    status,
    started_at: existing?.started_at ?? now,
    updated_at: now,
    expires_at: msg.expires_at !== undefined ? msg.expires_at : existing?.expires_at ?? null,
    last_error: msg.last_error !== undefined ? msg.last_error : existing?.last_error ?? null,
    posted_seq: msg.posted_seq !== undefined ? msg.posted_seq : existing?.posted_seq ?? null,
    owner: incomingOwner ?? existing?.owner ?? null,
  };
  await col.updateOne(
    { room, seat: msg.seat, trigger_seq: msg.trigger_seq },
    { $set: record },
    { upsert: true }
  );
  return record;
}
