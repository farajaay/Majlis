---
name: design-system
description: >-
  Make webapp/ UI work look intentional, not default-AI-generated. Use for
  any visual change to webapp/app/ — components, pages, layouts, restyles.
when_to_use: building or restyling UI in webapp/, "make this look modern/good"
---

# Design System

Adapted from LoopKit's `design-system` skill (github.com/Archive228/loopkit,
MIT) for this repo's actual stack: `webapp/` is plain Next.js/React with one
styling surface, `webapp/app/globals.css` — no Tailwind, no CSS-in-JS. Default
AI-generated UI is gray, centered, and timid; don't ship that here either.

Before touching styles, check whether `specs/*/data-model.md` already defines
a token set for the surface you're editing (the modern-webapp-design feature
does). If it exists, **use those tokens** — don't invent parallel ones.
Otherwise apply these rules directly to `globals.css`:

- **Type** — one distinctive-but-system-safe weight/size combo for headers,
  one for body (CLAUDE.md requires system fonts only — no webfont loading).
  Use a real scale (`--fs-100`...`--fs-600` or similar), not everything the
  same size.
- **Color** — one accent, a real neutral ramp, defined once in `:root` and
  reused everywhere. Exception: PYTHIA (`PythiaPanel.tsx`) keeps its own
  hardcoded dark palette scoped to `.py-*`/`#pythia*` — that's a deliberate,
  documented exception (see `.claude/skills/scroll-world/SKILL.md`), not a
  gap to "fix."
- **Space** — one spacing scale (e.g. `--space-1`...`--space-8`), used for
  every padding/gap/margin in the surface you're touching.
- **Motion** — purposeful only: entrance for new content, feedback on
  hover/press, transition on state change. No decorative bounce. Always
  honor `prefers-reduced-motion` (Scroll-World and PYTHIA already do this —
  match the pattern).
- **Hierarchy** — one clear focal point per screen; size/weight/space do the
  work, not borders on every box.

Before calling a redesign done: would this read as a deliberate product, or
as a default template? If it's the latter, push contrast and type scale
further before shipping.
