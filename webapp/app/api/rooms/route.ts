import { NextRequest, NextResponse } from "next/server";
import { resolveIdentity } from "@/lib/identity";
import { listRooms } from "@/lib/kv";

export async function GET(req: NextRequest) {
  const id = await resolveIdentity(req);
  if (!id) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  return NextResponse.json(await listRooms());
}
