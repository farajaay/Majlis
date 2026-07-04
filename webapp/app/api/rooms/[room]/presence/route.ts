import { NextRequest, NextResponse } from "next/server";
import { resolveIdentity } from "@/lib/identity";
import { listPresence, updatePresence } from "@/lib/kv";

export async function GET(req: NextRequest, { params }: { params: { room: string } }) {
  const id = await resolveIdentity(req);
  if (!id) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  try {
    return NextResponse.json(await listPresence(params.room));
  } catch {
    return NextResponse.json({ error: "invalid room" }, { status: 400 });
  }
}

export async function POST(req: NextRequest, { params }: { params: { room: string } }) {
  const id = await resolveIdentity(req);
  if (!id) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const body = (await req.json()) as {
    agent?: string;
    state?: "active" | "watching" | "away";
  };
  try {
    const record = await updatePresence(params.room, {
      agent: body.agent || id.login,
      state: body.state,
    });
    return NextResponse.json(record);
  } catch {
    return NextResponse.json({ error: "invalid room or agent name" }, { status: 400 });
  }
}
