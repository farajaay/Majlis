import { NextRequest, NextResponse } from "next/server";
import { resolveIdentity } from "@/lib/identity";
import { listClaims, upsertClaim, ClaimConflictError } from "@/lib/kv";

export async function GET(req: NextRequest, { params }: { params: { room: string } }) {
  const id = await resolveIdentity(req);
  if (!id) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const seat = req.nextUrl.searchParams.get("seat") || undefined;
  try {
    return NextResponse.json(await listClaims(params.room, seat));
  } catch {
    return NextResponse.json({ error: "invalid room" }, { status: 400 });
  }
}

export async function POST(req: NextRequest, { params }: { params: { room: string } }) {
  const id = await resolveIdentity(req);
  if (!id) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  const body = (await req.json()) as {
    seat?: string;
    trigger_seq?: number;
    status?: string;
    scope?: string;
    expires_at?: number | null;
    last_error?: string | null;
    posted_seq?: number | null;
    owner?: string | null;
  };
  if (typeof body.seat !== "string" || typeof body.trigger_seq !== "number") {
    return NextResponse.json({ error: "seat and trigger_seq are required" }, { status: 400 });
  }
  try {
    const record = await upsertClaim(params.room, {
      seat: body.seat,
      trigger_seq: body.trigger_seq,
      status: body.status,
      scope: body.scope,
      expires_at: body.expires_at,
      last_error: body.last_error,
      posted_seq: body.posted_seq,
      owner: body.owner,
    });
    return NextResponse.json(record);
  } catch (err) {
    if (err instanceof ClaimConflictError) {
      return NextResponse.json({ error: err.message }, { status: 409 });
    }
    return NextResponse.json({ error: "invalid room, seat, or status" }, { status: 400 });
  }
}
