import { NextRequest, NextResponse } from "next/server";
import { resolveIdentity } from "@/lib/identity";
import { getFile } from "@/lib/kv";

export async function GET(
  req: NextRequest,
  { params }: { params: { room: string; name: string } }
) {
  const id = await resolveIdentity(req);
  if (!id) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  try {
    const meta = await getFile(params.room, params.name);
    if (!meta) return NextResponse.json({ error: "no such file" }, { status: 404 });
    return NextResponse.redirect(meta.url);
  } catch {
    return NextResponse.json({ error: "invalid room or file name" }, { status: 400 });
  }
}
