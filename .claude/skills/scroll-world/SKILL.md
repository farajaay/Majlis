---
name: scroll-world
description: >-
  Modify the Majlis hosted webapp's landing page — the authenticated transcript
  at webapp/app/page.tsx / Transcript.tsx — including its Scroll-World animated
  world-map backdrop and the PYTHIA oracle side console. Use when asked to
  restyle, add to, or debug the landing/transcript page, the world backdrop, or
  the PYTHIA panel; when changing what shows behind the council floor; or when
  wiring PYTHIA's live feed/map into the hosted site. Not for the local
  single-file transcript (web/index.html) — that's a separate surface.
---

# Scroll-World — editing the Majlis landing (transcript) page

The "landing page" of the **hosted** council (Vercel, `webapp/`) is the
authenticated transcript: `webapp/app/page.tsx` gates on GitHub auth and
renders `webapp/app/Transcript.tsx`. Everything a signed-in user sees lives in
that tree. (The unauthenticated `/signin` screen is a separate, minimal page.)

This skill covers the two visual systems layered onto that page and the safe
way to change them.

## Files that make up the page

| File | Role |
|------|------|
| `webapp/app/page.tsx` | Server component: auth gate → `<Transcript>` |
| `webapp/app/Transcript.tsx` | The whole transcript UI (client). Renders `<ScrollWorld/>` and `<PythiaPanel/>` first, then header / floor / rail / composer |
| `webapp/app/ScrollWorld.tsx` | The animated dotted world-map backdrop (canvas) |
| `webapp/app/PythiaPanel.tsx` | The dark PYTHIA oracle side console |
| `webapp/app/globals.css` | All styling. Scroll-World + PYTHIA classes live at the bottom |

## Conventions (do not break these)

- `webapp/` is normal Next.js/TypeScript — **not** the stdlib-only rule that
  governs `clients/`. But keep it self-contained: no network calls to
  external hosts for assets (the world map is generated in code, no images).
- The hosted app is a **light** theme (`--ink` is a near-white cream). The
  PYTHIA panel is a deliberate **dark** widget — keep its colors hardcoded and
  scoped to `.py-*` / `#pythia*`, don't leak them into the light shell.
- Readability first: the transcript must stay legible. Scroll-World sits at
  `z-index: -1`; `.council-floor` is intentionally translucent
  (`rgba(248,246,239,0.82)`) so the world shows *faintly* in the gaps. If you
  make the backdrop bolder, re-check contrast on the turn cards.
- Always honor `prefers-reduced-motion`: both systems already render a static
  state under it. Preserve that.
- `page.tsx` redirects unless the visitor's GitHub login is allowed, so you
  can't screenshot `/` directly. To verify visually, add a **temporary**
  `webapp/app/preview/page.tsx` that renders `<Transcript me="farajaay" />`,
  drive it with Playwright (mock `**/api/rooms/**` responses), then delete it.

## Scroll-World backdrop

`ScrollWorld.tsx` draws continents as dots from a small set of lat/long
rectangles (`LAND`), projects them equirectangularly, and pans horizontally
with seamless wrap; a few "hot" nodes pulse and faint brass arcs animate.

To tune:
- **Density / shape** — edit the `LAND` boxes or `STEP` (degrees between dots).
- **Speed** — the `offset` term in `draw()` (`t * 0.012`).
- **Subtlety** — dot alpha in the `fillStyle` inside the dot loop; and the
  `.council-floor` background opacity in `globals.css`.
- **Vertical framing** — `LAT_TOP` / `LAT_BOT`.
- Keep the `~30fps` throttle in `loop()`; it's an ambient layer, not a game.

## PYTHIA oracle side console

`PythiaPanel.tsx` watches the room the PYTHIA bridge posts into
(`localStorage.pythia_room`, default `oracle`) by polling
`/api/rooms/<room>/messages` every 5s while open, and renders
`brief` / `alert` / `forecast` cards + a ticker. The `◎ map` toggle embeds a
live PYTHIA map from a user-set, locally-persisted URL (`localStorage
.pythia_base`).

Getting data onto the **hosted** page. Two routes:

*Local-first + sync on demand (recommended — no public PYTHIA needed).* Run
PYTHIA + the bridge + the local FastAPI server on your machine so the oracle
room fills up locally, then copy it up when you choose with
`scripts/sync_room.py` (one-way, incremental, idempotent; preserves original
timestamps via the message API's optional `ts` field):
```bash
MAJLIS_SRC_URL="http://localhost:8787" MAJLIS_SRC_KEY="$MAJLIS_KEY" \
MAJLIS_DST_URL="https://majlis-webapp.vercel.app" MAJLIS_DST_TOKEN="<PAT>" \
python3 scripts/sync_room.py oracle
```

*Direct feed (needs a public PYTHIA).* Point the bridge straight at the
deployment — but PYTHIA must be reachable at a **public** URL, since a hosted
page/bridge target can't reach `localhost:8088`:
```bash
MAJLIS_BASE="https://majlis-webapp.vercel.app" MAJLIS_TOKEN="<PAT>" \
PYTHIA_BASE="https://<public-pythia-host>" python3 scripts/pythia_bridge.py
```
Either way, until data arrives the panel shows "offline / awaiting feed". For
the live **map** view, paste a public PYTHIA URL into the panel's map bar.

Kinds `brief`/`alert`/`forecast` are not in the app's typed `kind` enum but the
store persists whatever it's given (`lib/kv.ts` → `kind ?? "chat"`), so they
round-trip and get their own card colors.

## Deploy

`webapp/` is the Vercel root; **pushing to `main` auto-deploys**. Run
`cd webapp && npm run build` before pushing — CI (`ci.yml`) builds only
`webapp/`, so a type error here is what breaks the deploy.
