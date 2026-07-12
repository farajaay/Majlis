# Quickstart: Validating the Modern Webapp Redesign

## Prerequisites

```bash
cd webapp
npm install
cp .env.example .env.local   # only needed for a real dev server; the preview
                              # route below works without real env vars filled in
```

## Run it

```bash
npm run dev
# open http://localhost:3000
```

`page.tsx` redirects signed-out/non-allowlisted visitors, so `/` alone won't show the redesigned transcript without a real GitHub OAuth session. Use the scroll-world skill's documented workaround to see it directly:

1. Temporarily add `webapp/app/preview/page.tsx` rendering `<Transcript me="farajaay" />` with mocked `fetch` responses for `**/api/rooms/**` (sample room + messages, a couple of seats, a couple of PYTHIA-kind messages).
2. Drive `http://localhost:3000/preview` with Playwright (pre-installed Chromium, `executablePath: '/opt/pw-browsers/chromium'`) at both a desktop width (e.g. 1280×800) and a mobile width (e.g. 390×844).
3. Delete `webapp/app/preview/page.tsx` once verification is done — it must not ship.

## Validation checklist (maps to spec.md's acceptance scenarios)

- **US1 (council floor)**: transcript with sample history renders with the new type/color/layout; messages, authors, timestamps all visible and in order; simulate a new message arriving (append to the mocked poll response) and confirm it animates in without breaking scroll position; confirm Scroll-World backdrop uses the new treatment without obscuring the floor.
- **US2 (PYTHIA)**: open the panel in the preview route; confirm it matches the shared token set (colors still dark/hardcoded per convention, but type/spacing/motion match the rest of the app); exercise its existing controls (ticker, `◎ map` toggle) and confirm no behavior change.
- **US3 (sign-in/guide)**: load `/signin` and `/guide` directly (no auth gate on these); confirm both use the new visual language; confirm the GitHub sign-in button still points at the same NextAuth flow; confirm guide content/navigation unchanged.
- **Reduced motion**: re-run the above with the OS/browser "reduce motion" preference enabled (Playwright: `page.emulateMedia({ reducedMotion: 'reduce' })`); confirm no non-essential animation plays (SC-004).
- **Responsive**: re-run at mobile width; confirm no horizontal scroll or clipped/overlapping content (SC-003).

## Build gate (this is what CI actually checks)

```bash
cd webapp && npm run build
```

CI (`ci.yml`) builds only `webapp/`; a type error here is what would break the real deploy. This must pass before considering any task in tasks.md done.

## Out of scope for this quickstart

- Real GitHub OAuth sign-in end-to-end (requires a live OAuth app + allowlisted login) — covered by existing project docs (`webapp/README.md`), not re-verified here since auth logic is unchanged (FR-010).
- Any MongoDB/Blob-backed data correctness — unchanged, not part of this feature.
