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
type Counter = { _id: string; seq: number };

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
async function counters(): Promise<Collection<Counter>> {
  return (await db()).collection<Counter>("counters");
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
