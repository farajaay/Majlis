import { NextRequest } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "./auth";
import { isAllowedLogin } from "./allowlist";

export type Identity = { login: string; via: "session" | "token" };

// Cache token→login lookups briefly; agents poll/say frequently and GitHub
// rate-limits unauthenticated-adjacent calls to /user.
const tokenCache = new Map<string, { login: string; exp: number }>();
const TOKEN_TTL_MS = 60_000;

async function loginFromGithubToken(token: string): Promise<string | null> {
  const cached = tokenCache.get(token);
  if (cached && cached.exp > Date.now()) return cached.login;
  const res = await fetch("https://api.github.com/user", {
    headers: { Authorization: `Bearer ${token}`, "User-Agent": "majlis-webapp" },
    cache: "no-store",
  });
  if (!res.ok) return null;
  const body = (await res.json()) as { login?: string };
  if (!body.login) return null;
  tokenCache.set(token, { login: body.login, exp: Date.now() + TOKEN_TTL_MS });
  return body.login;
}

// Two ways in, one identity model:
//  - a human browsing the transcript carries a NextAuth session cookie
//  - a headless agent (Claude Code, Codex, ...) sends `Authorization: Bearer <github PAT>`
// Both are ultimately GitHub logins, checked against the same allowlist.
export async function resolveIdentity(req: NextRequest): Promise<Identity | null> {
  const auth = req.headers.get("authorization");
  if (auth?.startsWith("Bearer ")) {
    const login = await loginFromGithubToken(auth.slice(7).trim());
    if (login && isAllowedLogin(login)) return { login, via: "token" };
    return null;
  }
  const session = await getServerSession(authOptions);
  const login = (session?.user as { login?: string } | undefined)?.login;
  if (login && isAllowedLogin(login)) return { login, via: "session" };
  return null;
}
