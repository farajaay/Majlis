# Research: Modern Redesign of the Majlis Webapp

## Decision: No new npm dependencies

**Decision**: Implement the entire redesign with plain CSS (custom properties, transitions, keyframes) and existing React — no animation library, no CSS framework.

**Rationale**: `webapp/package.json` has no CSS framework and no animation library today (only `next`, `next-auth`, `react`, `react-dom`, `mongodb`, `@vercel/blob`, markdown/syntax-highlighting). The spec (FR-010) and CLAUDE.md's dependency-discipline convention both push against adding one without clear justification. The Kinetics reference itself recommends: "Prefer CSS transitions and native browser APIs for simple UI motion... use Framer Motion, GSAP, Three.js, or canvas only when the project already uses them or the interaction needs them." Scroll-World already renders motion via `<canvas>`; that pattern is reused, not replaced.

**Alternatives considered**: Framer Motion (rejected — new dependency for spring easing that CSS `cubic-bezier`/`transition` can approximate closely enough for this UI's needs); Tailwind (rejected — would mean rewriting all existing class-based styling for no functional gain, and `globals.css` is explicitly the project's one styling surface per the scroll-world skill).

## Decision: Motion vocabulary — spring-like CSS easing, not literal physics

**Decision**: Use a small set of shared CSS custom properties for easing/duration (e.g. `--ease-spring: cubic-bezier(0.22, 1, 0.36, 1)`, `--ease-out: cubic-bezier(0.16, 1, 0.3, 1)`, plus `--dur-fast`/`--dur-med`/`--dur-slow`), applied via `transition` and small `@keyframes` for entrances (message arrival, panel open/close, hover/press feedback). No scroll-jacking, no parallax beyond what Scroll-World's canvas already does.

**Rationale**: Kinetics' guidance is to use it for "motion direction... timing, transitions, and kinetic UI feel," not to copy its code or add a dependency. A shared set of duration/easing tokens gives every component (transcript, PYTHIA, sign-in, guide) the same kinetic signature cheaply, satisfies spec FR-006 (one shared motion vocabulary), and composes with `prefers-reduced-motion` (FR-009) by having exactly one place to zero out.

**Alternatives considered**: Per-component bespoke transition values (rejected — produces the inconsistency FR-006 explicitly rules out); JS-driven spring physics via `requestAnimationFrame` (rejected — unnecessary complexity/perf cost for hover/entrance-level motion; reserved for Scroll-World's canvas loop, which already does this).

## Decision: Design tokens live in `globals.css` as CSS custom properties

**Decision**: Replace/expand the existing `:root` custom-property block in `globals.css` with a fuller token set (color roles, type scale, spacing scale, radii, shadows, motion tokens) and have every component (`Transcript.tsx`, `ScrollWorld.tsx`, `PythiaPanel.tsx`, sign-in, guide) consume only those tokens rather than hardcoded values, except where a file already intentionally hardcodes (PYTHIA's dark palette — see below).

**Rationale**: `globals.css` is already the single styling surface for the whole webapp (no CSS-in-JS, no modules) per the scroll-world skill; extending its existing `:root` pattern is the lowest-friction way to satisfy FR-006 without introducing new tooling (PostCSS plugins, Tailwind config, etc.).

**Alternatives considered**: CSS Modules per component (rejected — bigger structural change than a visual redesign needs, and fragments the single-source-of-truth token file); inline styles (rejected — already avoided in the codebase except a few dynamic style-object exceptions in `Transcript.tsx`).

## Decision: PYTHIA panel keeps its own hardcoded dark palette

**Decision**: Preserve the scroll-world skill's explicit rule — PYTHIA's dark colors stay hardcoded and scoped to `.py-*`/`#pythia*` — but re-derive its type scale, spacing, and motion tokens from the same shared scale as the rest of the app so it doesn't look like a foreign component, just a deliberately dark one.

**Rationale**: This is documented, intentional behavior in `.claude/skills/scroll-world/SKILL.md` ("keep its colors hardcoded... don't leak them into the light shell"). Overriding it would fight an existing, working design decision instead of modernizing it.

**Alternatives considered**: Fully unify PYTHIA onto the light shell's color tokens (rejected — explicitly against existing project convention and would remove PYTHIA's intentional "oracle console" visual identity).

## Decision: Verification approach — temporary preview route + Playwright, no new test framework

**Decision**: Reuse the scroll-world skill's documented technique — a temporary `webapp/app/preview/page.tsx` rendering `<Transcript me="farajaay" />` with mocked `**/api/rooms/**` responses, driven by the pre-installed Chromium via Playwright — to visually verify each user story, then delete the temporary route before finishing. `npm run build` (already CI's gate per `ci.yml`) is the correctness check; no new automated visual-regression tooling is introduced.

**Rationale**: `page.tsx` redirects unless the visitor's GitHub login is allowed, so `/` can't be screenshotted directly in this environment (no real OAuth session). The skill file already documents exactly this workaround. Introducing a full visual-regression suite is out of proportion for a presentation-only redesign with no new dependencies mandate.

**Alternatives considered**: Storybook or a dedicated component test harness (rejected — new dependency, disproportionate for this feature's scope); skipping visual verification entirely (rejected — CLAUDE.md requires testing UI changes in a browser before reporting complete).

## Constitution check

`.specify/memory/constitution.md` is still the unfilled template scaffold (no project-specific principles have been ratified for this repo). No gates apply; nothing to check against beyond the conventions already captured in `CLAUDE.md` and the `scroll-world` skill, both of which are reflected in the decisions above.
