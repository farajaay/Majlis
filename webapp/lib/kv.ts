import { Redis } from "@upstash/redis";

// Vercel's "Redis" marketplace integration (Upstash under the hood) injects
// KV_REST_API_URL / KV_REST_API_TOKEN when connected to this project.
const kv = new Redis({
  url: process.env.KV_REST_API_URL || "",
  token: process.env.KV_REST_API_TOKEN || "",
});

const ROOM_RE = /^[a-zA-Z0-9_\-.]{1,64}$/;

export function assertSafeName(name: string): string {
  if (!ROOM_RE.test(name)) throw new Error("invalid name");
  return name;
}

export type Message = {
  seq: number;
  ts: number;
  agent: string;
  kind: "chat" | "decision" | "system" | "file";
  content: string;
  refs: string[];
};

export type FileMeta = { name: string; url: string; size: number; ts: number };

const roomsKey = () => "majlis:rooms";
const seqKey = (room: string) => `majlis:room:${room}:seq`;
const messagesKey = (room: string) => `majlis:room:${room}:messages`;
const filesKey = (room: string) => `majlis:room:${room}:files`;

export async function listRooms(): Promise<
  { room: string; messages: number; agents: string[]; last: number | null }[]
> {
  const rooms = ((await kv.smembers(roomsKey())) as string[]) ?? [];
  const out = [];
  for (const room of rooms.sort()) {
    const msgs = await readMessages(room);
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
  const raw = ((await kv.lrange(messagesKey(room), 0, -1)) as (string | Message)[]) ?? [];
  const all = raw.map((r) => (typeof r === "string" ? (JSON.parse(r) as Message) : r));
  return all.filter((m) => m.seq > since);
}

export async function postMessage(
  room: string,
  msg: { agent: string; content: string; kind?: Message["kind"]; refs?: string[] }
): Promise<Message> {
  assertSafeName(room);
  assertSafeName(msg.agent);
  await kv.sadd(roomsKey(), room);
  const seq = await kv.incr(seqKey(room));
  const record: Message = {
    seq,
    ts: Date.now() / 1000,
    agent: msg.agent,
    kind: msg.kind ?? "chat",
    content: msg.content,
    refs: msg.refs ?? [],
  };
  await kv.rpush(messagesKey(room), JSON.stringify(record));
  return record;
}

export async function listFiles(room: string): Promise<FileMeta[]> {
  assertSafeName(room);
  const map = ((await kv.hgetall(filesKey(room))) as Record<string, string | FileMeta>) ?? {};
  return Object.values(map)
    .map((v) => (typeof v === "string" ? (JSON.parse(v) as FileMeta) : v))
    .sort((a, b) => a.name.localeCompare(b.name));
}

export async function addFile(room: string, file: FileMeta): Promise<void> {
  assertSafeName(room);
  assertSafeName(file.name);
  await kv.hset(filesKey(room), { [file.name]: JSON.stringify(file) });
}

export async function getFile(room: string, name: string): Promise<FileMeta | null> {
  assertSafeName(room);
  const raw = (await kv.hget(filesKey(room), name)) as string | FileMeta | null;
  if (!raw) return null;
  return typeof raw === "string" ? (JSON.parse(raw) as FileMeta) : raw;
}
