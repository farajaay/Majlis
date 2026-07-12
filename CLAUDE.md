# CLAUDE.md — Majlis repo

## What this is
Self-hosted council hub, two ways to run it:
- Local/tunnel: FastAPI server (`server/main.py`) + single-file web transcript
  (`web/index.html`), guarded by a shared `MAJLIS_KEY` secret.
- Hosted: Next.js app (`webapp/`) deployed to Vercel, guarded by GitHub OAuth
  (browser) / GitHub personal access token (agents) instead of a shared
  secret. See `webapp/README.md`.
Agent CLI (`clients/majlis.py`) talks to either backend. Local server's data
lives in `workspace/`; the Vercel app's data lives in MongoDB Atlas + Blob
storage (see "Live deployment state" below).

## Conventions
- Python 3.9+ stdlib only in `clients/` (must run on restricted machines).
- No new dependencies without adding to `requirements.txt` and README.
- `workspace/` contents are data, not code — never refactor or delete.
- `web/index.html`: system fonts only; keep single-file, no build step.
- `webapp/`: normal Next.js/TypeScript conventions apply; it's a separate
  build with its own `package.json`, not subject to the stdlib-only rule.

## Skills
- `.claude/skills/scroll-world/` — how to modify the hosted webapp's landing
  (transcript) page, its Scroll-World world-map backdrop, and the PYTHIA
  oracle side console. Load it before editing `webapp/app/Transcript.tsx`,
  `ScrollWorld.tsx`, `PythiaPanel.tsx`, or their styles.

## Tooling notes
- **spec-kit** (github/spec-kit) — GitHub's spec-driven development toolkit.
  Not installed in this repo yet, but worth reaching for on any
  nontrivial new feature: write a spec first (`/speckit.specify`), clarify,
  plan (`/speckit.plan`), break into tasks (`/speckit.tasks`), then
  implement (`/speckit.implement`), instead of jumping straight to code.
  Install via `uv tool install specify-cli --from
  git+https://github.com/github/spec-kit.git` then `specify init . --integration
  claude` to drop the slash commands into this repo. Pairs well with the
  multi-agent council setup here (claude-code/codex/gemini all seated on
  the same repo) — a spec/plan doc gives them a shared reference instead
  of each agent improvising independently. Consider this before starting
  large features in `webapp/` or `server/`, not for one-line fixes.

## References (cached for reuse across dev/repos)
- `docs/references/kinetics-motion.md` — spring-physics UI-motion cheatsheet
  (Kinetics library: https://kinetics.colorion.co/,
  https://github.com/ckissi/kinetics). Reach for it when adding animation to
  the React `webapp/` (seat chips, claims panel, PYTHIA/Scroll-World): ready
  spring presets, the go-to `cubic-bezier(0.34, 1.56, 0.64, 1)` overshoot
  curve, and copy-ready CSS/React snippets. Self-contained — no need to hit
  the site.

## Who's who
- **Ahmad** — GitHub login `farajaay`, owns this repo and the Vercel account
  it's deployed under. The human directing this project; the one who opens
  rooms, seats agents, and chairs decisions.
- Agents seated so far: `claude-code` (this assistant, via Claude Code),
  with `codex` and `gemini` expected to join the same way.
- Any agent being pointed at this repo should read `docs/JOIN.md` — it's
  written to be self-contained, no prior conversation needed.

## Live deployment state
The hosted app is deployed: **https://majlis-webapp.vercel.app**
(Vercel project `majlis-webapp`, id `prj_HHIZRjyakVgya8OSINN0WjRB0ueV`,
under Ahmad's account/team `team_KnPr9jT0jU61Vp10ZrSs4nhA`). Linked to
`farajaay/Majlis`, root directory `webapp/`, production branch `main` —
**pushes to `main` auto-deploy**, no manual step needed.

Storage decisions, and why, in case they need revisiting:
- **MongoDB Atlas**, not Redis/KV. Vercel's Redis (Upstash) marketplace
  product was never installed on this account, and installing a *new*
  marketplace integration requires an interactive vendor consent screen —
  no API token can complete that headlessly. A MongoDB Atlas integration
  was already installed (with API-provisioning enabled, unlike the also-
  installed Supabase/Railway integrations, which are link-only). The app
  connects to that **same cluster as another project** (`hadeed-cctv-
  dashboard`) but uses its own `majlis` database within it — see
  `webapp/lib/kv.ts`. If Ahmad ever installs Redis/KV properly via the
  dashboard, swapping it back is a `lib/kv.ts` rewrite, not a redesign.
- **Vercel Blob** for uploaded files — provisioned cleanly via API, no
  caveats.
- Vercel's own Deployment Protection (the SSO/login wall) is deliberately
  **disabled** on this project — GitHub sign-in via the app itself is the
  only gate. Don't re-enable it without checking with Ahmad; it would sit
  in front of the app's own auth.
- `ALLOWED_GITHUB_LOGINS` currently contains just `farajaay`. Add logins
  there (Vercel project env vars) before anyone else can sign in or use a
  bearer token against the hosted app.

None of the above is guessable from the code alone — it's the result of
probing Vercel's API live and hitting real platform limits, not a design
choice visible in a diff.

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
