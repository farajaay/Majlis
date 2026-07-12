import { NextRequest, NextResponse } from "next/server";
import { resolveIdentity } from "@/lib/identity";
import { postMessage, readMessages } from "@/lib/kv";

export async function GET(req: NextRequest, { params }: { params: { room: string } }) {
  const id = await resolveIdentity(req);
  if (!id) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const since = Number(req.nextUrl.searchParams.get("since") ?? "0") || 0;
  try {
    return NextResponse.json(await readMessages(params.room, since));
  } catch {
    return NextResponse.json({ error: "invalid room" }, { status: 400 });
  }
}

export async function POST(req: NextRequest, { params }: { params: { room: string } }) {
  const id = await resolveIdentity(req);
  if (!id) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const body = (await req.json()) as {
    agent?: string;
    content?: string;
    kind?: "chat" | "decision" | "system" | "file";
    refs?: string[];
    ts?: number;
  };
  if (!body.content) return NextResponse.json({ error: "content required" }, { status: 400 });
  // GitHub identity gates *who may post at all*; the `agent` field is still
  // the seat label (one allowed human runs several agent CLIs — claude-code,
  // codex, gemini — all under their own PAT/session, same as MAJLIS_KEY did).
  try {
    const record = await postMessage(params.room, {
      agent: body.agent || id.login,
      content: body.content,
      kind: body.kind,
      refs: body.refs,
      ts: typeof body.ts === "number" ? body.ts : undefined,
    });
    return NextResponse.json(record);
  } catch {
    return NextResponse.json({ error: "invalid room or agent name" }, { status: 400 });
  }
}
