// Who may use this council: a comma-separated list of GitHub logins.
// Same list gates both the browser (OAuth session) and agent (PAT) paths.
export function isAllowedLogin(login: string | undefined | null): boolean {
  if (!login) return false;
  const raw = process.env.ALLOWED_GITHUB_LOGINS || "";
  const allowed = raw
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
  if (allowed.length === 0) return false; // fail closed: must be configured
  return allowed.includes(login.toLowerCase());
}
