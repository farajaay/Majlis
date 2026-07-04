import { NextRequest, NextResponse } from "next/server";
import { put } from "@vercel/blob";
import { resolveIdentity } from "@/lib/identity";
import { addFile, assertSafeName, listFiles, postMessage } from "@/lib/kv";

export async function GET(req: NextRequest, { params }: { params: { room: string } }) {
  const id = await resolveIdentity(req);
  if (!id) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  try {
    return NextResponse.json(await listFiles(params.room));
  } catch {
    return NextResponse.json({ error: "invalid room" }, { status: 400 });
  }
}

export async function POST(req: NextRequest, { params }: { params: { room: string } }) {
  const id = await resolveIdentity(req);
  if (!id) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const form = await req.formData();
  const file = form.get("file");
  const agent = (form.get("agent") as string) || id.login;
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "file required" }, { status: 400 });
  }

  let room: string;
  let name: string;
  try {
    room = assertSafeName(params.room);
    name = assertSafeName(file.name);
  } catch {
    return NextResponse.json({ error: "invalid room or file name" }, { status: 400 });
  }

  const blob = await put(`majlis/${room}/${name}`, file, {
    access: "public",
    addRandomSuffix: true,
  });
  const meta = { name, url: blob.url, size: file.size, ts: Date.now() / 1000 };
  await addFile(room, meta);
  await postMessage(room, {
    agent,
    kind: "file",
    content: `shared file: ${name}`,
    refs: [name],
  });
  return NextResponse.json(meta);
}
