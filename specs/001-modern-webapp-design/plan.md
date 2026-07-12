# Implementation Plan: Modern Redesign of the Majlis Webapp

**Branch**: `001-modern-webapp-design` | **Date**: 2026-07-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-modern-webapp-design/spec.md`

## Summary

Redesign the visual language of the hosted Majlis webapp (`webapp/`) — the transcript/council-floor page, Scroll-World backdrop, PYTHIA console, sign-in page, and guide page — using one shared set of CSS design tokens (color, type, spacing, motion) added to `globals.css`, with no new dependencies and no changes to any backend/auth/API behavior. Motion direction is informed by the Kinetics-by-Colorion reference but implemented with plain CSS transitions/keyframes, matching the stack the project already uses.

## Technical Context

**Language/Version**: TypeScript 5.5 / React 18, Next.js 14 (App Router)

**Primary Dependencies**: `next`, `react`, `react-dom`, `next-auth` (auth, unchanged), `react-markdown` + `react-syntax-highlighter` (transcript rendering, unchanged). No new dependencies added by this feature (see research.md).

**Storage**: N/A for this feature — MongoDB Atlas + Vercel Blob remain exactly as-is (`lib/kv.ts` untouched).

**Testing**: No automated test framework exists in `webapp/` today (`npm run build` via `next build` is the CI gate, per `ci.yml`). This feature adds no test framework; verification is manual/visual per `quickstart.md` (temporary preview route + Playwright, pre-installed Chromium).

**Target Platform**: Vercel serverless (Next.js), evergreen desktop and mobile browsers.

**Project Type**: Web application — single Next.js app under `webapp/`, no separate frontend/backend split (the "backend" is Next.js API routes + NextAuth within the same app).

**Performance Goals**: No regression to current page weight/interactivity; Scroll-World keeps its existing ~30fps canvas throttle. No specific new performance target introduced.

**Constraints**: Presentation-layer only (FR-010) — no changes to `webapp/app/api/`, `lib/auth.ts`, `lib/allowlist.ts`, `lib/kv.ts`, or the message/room data model. System fonts only (CLAUDE.md convention, unchanged). Must honor `prefers-reduced-motion` (FR-009). Must remain a single-file styling surface (`globals.css`), no CSS-in-JS/CSS Modules introduced.

**Scale/Scope**: 5 screens/components — `Transcript.tsx` (+ its header/floor/rail/composer regions), `ScrollWorld.tsx`, `PythiaPanel.tsx`, `signin/page.tsx`, `guide/page.tsx` + `guide.css` — plus the shared `globals.css` token layer and `layout.tsx` shell.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled template scaffold — no project-specific principles have been ratified, so there are no constitution gates to evaluate. The applicable guardrails for this feature instead come from `CLAUDE.md` (webapp is normal Next.js/TS, no stdlib-only rule; no new dependencies without updating `requirements.txt`/README — N/A here since this is `webapp/`, which has its own `package.json`; system fonts only for `web/index.html`, not directly binding on `webapp/` but followed anyway for consistency) and `.claude/skills/scroll-world/SKILL.md` (PYTHIA's hardcoded dark palette, Scroll-World's `z-index:-1` + translucency contract, `prefers-reduced-motion` static-state requirement, no external asset network calls). All of these are satisfied by the approach in research.md. **PASS** — no violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/001-modern-webapp-design/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output (design-token inventory; no app data entities)
├── quickstart.md        # Phase 1 output (manual/visual validation guide)
├── checklists/
│   └── requirements.md  # Spec quality checklist (from /speckit-specify)
└── tasks.md             # Phase 2 output (/speckit-tasks command — not created by this plan)
```

No `contracts/` directory: this feature changes no external interface. FR-010 requires all API route contracts in `webapp/app/api/` to stay exactly as they are, so there is nothing to contract-document for this feature.

### Source Code (repository root)

```text
webapp/
├── app/
│   ├── page.tsx            # Auth gate → <Transcript> (unchanged logic, may restyle shell)
│   ├── layout.tsx           # Root layout/shell — token-level styling changes
│   ├── globals.css          # Design tokens (color/type/spacing/radii/motion) + all component styles
│   ├── Transcript.tsx        # Council-floor UI: header, floor, rail, composer (restyle only)
│   ├── ScrollWorld.tsx        # Canvas world-map backdrop (restyle: palette/motion, same data wiring)
│   ├── PythiaPanel.tsx         # Oracle console (restyle: shared type/spacing/motion, own dark colors kept)
│   ├── signin/page.tsx          # Sign-in screen (restyle only, same NextAuth flow)
│   └── guide/
│       ├── page.tsx              # Guide content (restyle only, same content/nav)
│       ├── GuideScripts.tsx
│       └── guide.css              # Folded into / aligned with globals.css tokens
├── lib/                      # auth.ts, allowlist.ts, identity.ts, kv.ts — NOT touched by this feature
└── app/api/                  # NOT touched by this feature (FR-010)
```

**Structure Decision**: Single existing Next.js app (`webapp/`), no new top-level directories. All work happens inside `webapp/app/` (styling + component markup/classnames) and is centered on expanding `globals.css`'s token layer; `webapp/lib/` and `webapp/app/api/` are out of scope and untouched, matching FR-010.

## Complexity Tracking

*No constitution violations — this section is not applicable.*
