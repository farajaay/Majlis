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

export type ClaimStatus =
  | "idle"
  | "claimed"
  | "working"
  | "verifying"
  | "reporting"
  | "blocked"
  | "stale"
  | "failed"
  | "superseded";

const CLAIM_STATUSES: ClaimStatus[] = [
  "idle",
  "claimed",
  "working",
  "verifying",
  "reporting",
  "blocked",
  "stale",
  "failed",
  "superseded",
];

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
};

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

export async function listRooms(): Promise<
  { room: string; messages: number; agents: string[]; last: number | null }[]
> {
  const col = await messages();
  const rooms = await col.distinct("room");
  const out = [];
  for (const room of rooms.sort()) {
    const msgs = await col.find({ room }).sort({ seq: 1 }).toArray();
    const agents = Array.from(new Set(msgs.map((m) => m.agent))).sort();
    out.push({
      room,
      messages: msgs.length,
      agents,
      last: msgs.length ? msgs[msgs.length - 1].ts : null,
    });
  }
  return out;
}

export async function readMessages(room: string, since = 0): Promise<Message[]> {
  assertSafeName(room);
  const col = await messages();
  return col
    .find({ room, seq: { $gt: since } }, { projection: { _id: 0 } })
    .sort({ seq: 1 })
    .toArray();
}

export async function postMessage(
  room: string,
  msg: { agent: string; content: string; kind?: Message["kind"]; refs?: string[] }
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
    ts: Date.now() / 1000,
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
  };
  await col.updateOne(
    { room, seat: msg.seat, trigger_seq: msg.trigger_seq },
    { $set: record },
    { upsert: true }
  );
  return record;
}
