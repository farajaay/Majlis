---
name: a11y-pass
description: >-
  Catch accessibility failures before shipping a webapp/ screen. Use after
  building or restyling any interactive component in webapp/app/.
when_to_use: forms, buttons, panels, modals, color/contrast choices, keyboard interaction
---

# Accessibility Pass

Adapted from LoopKit's `a11y-pass` skill (github.com/Archive228/loopkit,
MIT) for this repo. Run this over any screen in `webapp/app/` before
considering it done — the transcript floor, PYTHIA panel, composer,
sign-in, and guide pages all have real keyboard/mouse interaction and
deserve the same pass.

- **Keyboard** — every interactive element (send button, mode picker,
  PYTHIA's `◎ map` toggle, room switcher, sign-in button) reachable and
  operable via Tab/Enter/Esc, not just click.
- **Labels** — every input has a real `<label>` or `aria-label`; icon-only
  controls (copy-code button, map toggle) get `aria-label`, not just a
  visual glyph.
- **Images** — meaningful `alt` where images exist; decorative elements
  (Scroll-World's canvas backdrop) get `aria-hidden="true"` since it's
  ambient decoration, not content.
- **Contrast** — text ≥ 4.5:1 (3:1 for large text). This matters especially
  where `.council-floor` sits translucent over the Scroll-World backdrop —
  re-check contrast any time either layer's colors change (see the
  scroll-world skill's "readability first" rule).
- **Semantics** — real `<button>`/`<a>`, not a clickable `<div>`; heading
  levels in order.
- **Focus** — visible focus ring on every interactive element; never
  `outline: none` without a replacement indicator.
- **Motion** — anything that moves (message entrance, panel open/close,
  hover feedback) must respect `prefers-reduced-motion` per spec FR-009.

Output format: list each failure found as `element → fix`. Verify with
Tab-only navigation, no mouse, before calling a screen done.
