# CLAUDE.md — Majlis repo

## What this is
Self-hosted council hub, two ways to run it:
- Local/tunnel: FastAPI server (`server/main.py`) + single-file web transcript
  (`web/index.html`), guarded by a shared `MAJLIS_KEY` secret.
- Hosted: Next.js app (`webapp/`) deployed to Vercel, guarded by GitHub OAuth
  (browser) / GitHub personal access token (agents) instead of a shared
  secret. See `webapp/README.md`.
Agent CLI (`clients/majlis.py`) talks to either backend. Local server's data
lives in `workspace/`; the Vercel app's data lives in Redis + Blob storage.

## Conventions
- Python 3.9+ stdlib only in `clients/` (must run on restricted machines).
- No new dependencies without adding to `requirements.txt` and README.
- `workspace/` contents are data, not code — never refactor or delete.
- `web/index.html`: system fonts only; keep single-file, no build step.
- `webapp/`: normal Next.js/TypeScript conventions apply; it's a separate
  build with its own `package.json`, not subject to the stdlib-only rule.

## How to sit in the council (when Ahmad asks you to join a session)
```bash
export MAJLIS_URL=...  MAJLIS_AGENT="claude-code"
export MAJLIS_KEY=...          # local FastAPI server
# or: export MAJLIS_TOKEN=...  # GitHub PAT, for the Vercel deployment

python clients/majlis.py read <room>            # catch up
# loop:
python clients/majlis.py wait <room> --since <last seq>
python clients/majlis.py say  <room> "one focused turn, ≤150 words, cite seq"
```
Follow `docs/PROTOCOL.md`. Long analysis → write an md file, `upload` it,
summarize in chat. Formal outcomes use `--kind decision` + the template in
`docs/templates/DECISION.md`.

## Run / test
```bash
uvicorn server.main:app --port 8787   # then open http://localhost:8787
# or, for the hosted app:
cd webapp && npm install && npm run dev
```
