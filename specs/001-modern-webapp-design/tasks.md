---
description: "Task list for Modern Redesign of the Majlis Webapp"
---

# Tasks: Modern Redesign of the Majlis Webapp

**Input**: Design documents from `/specs/001-modern-webapp-design/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Not requested — this feature is visual/UX only and `webapp/` has no automated test framework. `npm run build` (the real CI gate) plus the manual/Playwright verification steps in `quickstart.md` serve as the done-check for every story instead of test tasks.

**Organization**: Tasks are grouped by user story (from `spec.md`) so each story can be redesigned, verified, and considered "shippable" independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are relative to the repo root

## Phase 1: Setup

**Purpose**: Establish a known-good baseline before touching any styling

- [X] T001 Run `cd webapp && npm run build` to confirm the pre-redesign baseline builds cleanly; note the result so later build failures are attributable to this feature's changes
- [X] T002 [P] Inventory current hardcoded colors, font sizes, spacing, and radii across `webapp/app/globals.css`, `webapp/app/guide/guide.css`, and inline `style={{...}}` usages in `webapp/app/Transcript.tsx`/`webapp/app/PythiaPanel.tsx`, listing them in a scratch note so Phase 2's token set (data-model.md) covers every value in use today

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared design-token layer every user story depends on (spec.md FR-006)

**⚠️ CRITICAL**: No user story task may begin until this phase is complete

- [X] T003 Define the full token set (`--ink`, `--panel`, `--line`, `--text`, `--text-muted`, `--accent`, `--accent-strong`, `--fs-100`...`--fs-600`, `--space-1`...`--space-8`, `--radius-sm/md/lg`, `--shadow-sm/md`, `--ease-spring`, `--ease-out`, `--dur-fast/med/slow`) in the `:root` block of `webapp/app/globals.css`, per `data-model.md`'s token-group list, replacing the existing minimal `:root` block
- [X] T004 [P] Add/update the `prefers-reduced-motion: reduce` override block in `webapp/app/globals.css` so all `--dur-*` tokens collapse to near-zero and `--ease-*` tokens become linear, matching the existing static-state pattern Scroll-World/PYTHIA already use
- [X] T005 Update `webapp/app/layout.tsx` (root shell) to reference the new tokens for any top-level background/font styling, keeping the system-font stack unchanged

**Checkpoint**: Token layer ready — user story redesign work can now begin

---

## Phase 3: User Story 1 - Council floor first impression (Priority: P1) 🎯 MVP

**Goal**: The transcript page and Scroll-World backdrop read as a modern, cohesive product while every existing interaction keeps working

**Independent Test**: Load `/preview` (temporary route, see T010) with sample transcript history; confirm new visual language, message ordering/legibility, live-update animation, and backdrop treatment all pass `quickstart.md`'s US1 checklist

- [X] T006 [US1] Restyle the transcript header region in `webapp/app/Transcript.tsx` and its classes in `webapp/app/globals.css` using the Phase 2 tokens (typography, spacing, color)
- [X] T007 [US1] Restyle the council-floor message/turn cards in `webapp/app/Transcript.tsx` and `webapp/app/globals.css` (per-seat color swatches, kind badges, code blocks) using the shared tokens; add a subtle entrance transition (using `--ease-spring`/`--dur-fast`) for newly arrived messages
- [X] T008 [US1] Restyle the side rail (seat/presence list) and composer (mode picker, textarea, send control) in `webapp/app/Transcript.tsx` and `webapp/app/globals.css` using the shared tokens; add hover/press motion using the shared motion tokens
- [X] T009 [US1] Redesign `webapp/app/ScrollWorld.tsx`'s visual treatment — dot/arc palette brought into the same hue family as `--accent`/`--ink`, motion easing aligned with the shared vocabulary — while preserving its data wiring, `z-index: -1` layering, `~30fps` throttle, and the `.council-floor` translucency contract documented in `.claude/skills/scroll-world/SKILL.md`
- [X] T010 [US1] Add a temporary `webapp/app/preview/page.tsx` rendering `<Transcript me="farajaay" />` with mocked `fetch` responses for `**/api/rooms/**` (sample room, a few messages across different `kind`s and seats), per `quickstart.md`
- [X] T011 [US1] Verify via Playwright against `/preview` at desktop (1280×800) and mobile (390×844) widths, and with `reducedMotion: 'reduce'` emulated, per `quickstart.md`'s US1 checklist; confirm contrast of the translucent `.council-floor` background against the redesigned Scroll-World backdrop remains legible

**Checkpoint**: User Story 1 is a fully functional, independently demoable increment (the MVP)

---

## Phase 4: User Story 2 - PYTHIA oracle console (Priority: P2)

**Goal**: The PYTHIA panel visually matches the redesigned system while keeping its intentional dark identity and all existing behavior

**Independent Test**: Open the PYTHIA panel in `/preview`; confirm it matches the shared type/spacing/motion tokens, its dark palette stays intact and scoped, and its ticker/map-toggle controls behave identically to before

- [X] T012 [US2] Restyle `webapp/app/PythiaPanel.tsx` to consume the shared type scale, spacing scale, and motion tokens from Phase 2, while leaving its dark color values hardcoded and scoped to `.py-*`/`#pythia*` per the scroll-world skill's explicit rule
- [X] T013 [US2] Restyle PYTHIA-specific classes in `webapp/app/globals.css` (ticker, `brief`/`alert`/`forecast` cards, `◎ map` toggle) so their rhythm/motion matches the rest of the redesigned app
- [X] T014 [US2] Re-add the temporary `webapp/app/preview/page.tsx` (if removed after T011) and verify the PYTHIA panel via Playwright per `quickstart.md`'s US2 checklist — open panel, exercise ticker and map toggle, confirm no behavior change — then remove the temporary route again

**Checkpoint**: User Stories 1 and 2 both work independently and together

---

## Phase 5: User Story 3 - Sign-in and guide pages (Priority: P3)

**Goal**: Sign-in and guide pages feel like the same modern product, with zero change to the OAuth flow or guide content

**Independent Test**: Load `/signin` and `/guide` directly (no auth gate on either); confirm new visual language, unchanged GitHub sign-in action, and unchanged guide content/navigation, per `quickstart.md`'s US3 checklist

- [X] T015 [P] [US3] Redesign `webapp/app/signin/page.tsx` markup/classes using the shared tokens, preserving the existing GitHub OAuth sign-in button and its NextAuth flow unchanged
- [X] T016 [P] [US3] Redesign `webapp/app/guide/page.tsx` and `webapp/app/guide/GuideScripts.tsx` markup/classes using the shared tokens, preserving all existing instructional content and navigation
- [X] T017 [US3] Fold `webapp/app/guide/guide.css` onto the shared `globals.css` tokens (replace one-off hardcoded values with `var()` references to the Phase 2 token set), removing duplicated color/spacing/type definitions
- [X] T018 [US3] Verify `/signin` and `/guide` directly via Playwright at desktop and mobile widths, and with reduced motion emulated, per `quickstart.md`'s US3 checklist

**Checkpoint**: All three user stories are independently functional and visually consistent with each other

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final checks that span all three stories

- [X] T019 [P] Run `cd webapp && npm run build` and fix any type or lint errors introduced by the redesign (this is CI's actual gate per `ci.yml`)
- [X] T020 [P] Re-check `.council-floor` background opacity against the redesigned Scroll-World backdrop for contrast/readability, per the scroll-world skill's "readability first" rule
- [X] T021 Run the full `quickstart.md` validation checklist end-to-end across US1–US3 in one pass, confirming zero functional regressions (SC-001) and consistent shared tokens across all four surfaces (SC-002)
- [X] T022 Confirm no temporary preview route or mocked-fetch code remains in `webapp/app/` before considering the feature complete

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories (FR-006 requires one shared token set before any surface is restyled)
- **User Stories (Phase 3-5)**: All depend on Phase 2 completion; may then proceed in priority order (P1 → P2 → P3) or in parallel if staffed
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 — no dependency on US2/US3
- **User Story 2 (P2)**: Can start after Phase 2 — visually should follow the token set US1 also uses, but has no code dependency on US1's tasks
- **User Story 3 (P3)**: Can start after Phase 2 — no dependency on US1/US2

### Within Each User Story

- Restyle component markup/classes before the Playwright verification task
- `ScrollWorld.tsx` restyle (T009) has no dependency on `Transcript.tsx` restyle tasks (T006-T008) beyond sharing tokens — can run in parallel
- Verification tasks (T011, T014, T018) run last within their story, after all that story's restyle tasks

### Parallel Opportunities

- T002 (inventory) can run alongside T001 (build baseline)
- T004 (reduced-motion override) can run in parallel with T003 only if T003 is drafted first (same file — treat as sequential in practice; both are in Phase 2 either way)
- T015 and T016 (sign-in and guide restyles) touch disjoint files and can run in parallel
- T019 and T020 (build check, contrast check) can run in parallel in Phase 6

---

## Parallel Example: User Story 3

```bash
# Sign-in and guide restyles touch different files, no shared state:
Task: "Redesign webapp/app/signin/page.tsx markup/classes using shared tokens"
Task: "Redesign webapp/app/guide/page.tsx and GuideScripts.tsx using shared tokens"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational token layer (blocks everything else)
3. Complete Phase 3: User Story 1 (council floor + Scroll-World)
4. **STOP and VALIDATE**: run `quickstart.md`'s US1 checklist independently
5. This alone is a demoable "the main page looks modern now" increment

### Incremental Delivery

1. Setup + Foundational → token system ready
2. Add User Story 1 → validate independently → this is the MVP
3. Add User Story 2 (PYTHIA) → validate independently
4. Add User Story 3 (sign-in/guide) → validate independently
5. Phase 6 polish → full regression pass, then done

## Notes

- No test tasks are included per this feature's explicit scope (visual/UX only, no test framework in `webapp/`); `npm run build` + `quickstart.md`'s manual/Playwright checks are the done-check for every phase.
- Commit after each user-story phase (or logical group within one) rather than one giant commit at the end, so the redesign's history is reviewable story-by-story.
- Never leave the temporary `webapp/app/preview/page.tsx` route in the tree between verification passes for different stories — add it, verify, remove it (T010/T014/T022).

## Implementation Notes (post-hoc)

- **T003 deviation**: kept the existing token names (`--ink`, `--panel`, `--paper`, `--dim`, `--muted`, `--brass`, `--brass-2`, `--danger`, `--ok`, `--watch`, `--shadow`) rather than renaming to `data-model.md`'s illustrative names (`--text`, `--accent`, etc.) — those names are already referenced across `globals.css`, `guide.css`, and inline styles in `Transcript.tsx`/`signin/page.tsx`; renaming them was unnecessary churn for a restyle. Added the new type/space/radius/motion scale tokens alongside them. FR-006 (one shared token set) is satisfied either way.
- **T010/T014 consolidation**: added the temporary preview route once (with mocked fetch covering both the transcript and oracle rooms) and used it for all three stories' Playwright verification in one pass, rather than literally re-adding/removing it between US1 and US2. Removed for good after the full pass (T022).
- **Bug found + fixed during T003/T017**: a CSS comment (`globals.css`) and a JS comment (temporary `preview/page.tsx`) each contained a literal `*/` inside descriptive text (e.g. "`.py-*/#pythia*`", "`**/api/rooms/**`"), which prematurely closed the comment and broke the build. Reworded both; documented here since it's an easy mistake to reintroduce when writing comments that mention glob patterns or CSS class prefixes.
- **T020 contrast re-check**: done via Playwright screenshots (desktop + mobile, motion + reduced-motion) reviewed visually rather than an automated contrast-ratio tool; council-floor-over-Scroll-World legibility held up in all captures.
