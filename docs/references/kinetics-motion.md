# Kinetics — spring-physics motion reference

Cached reference for a UI-motion library we want on hand for future work
(this repo's `webapp/`, and new repos). Distilled so it's usable without the
live site.

- **Live gallery:** https://kinetics.colorion.co/
- **Source:** https://github.com/ckissi/kinetics
- **License:** none stated on the site as of caching (2026-07-12). The
  *physics parameters and cubic-bezier values below are just numbers — free to
  reuse.* Before copy-pasting whole component code from the repo, check the
  repo's license first.

## What it is

An interactive gallery + library of **99 spring-driven interface animations**.
The premise: drive motion with **spring physics** (stiffness / damping / mass)
instead of fixed-duration easing, so interactions feel physical (overshoot,
settle, momentum) rather than mechanically timed. Every effect ships in three
forms: **pure CSS**, **React (hooks)**, and a **natural-language "AI prompt"**
you can paste into a model to regenerate/vary it.

Three categories, 33 effects each:
- **Interaction & Input** — card resize, magnetic button, number counter,
  toast, tab pills, accordion, drag-to-dismiss, ripple, hold-to-confirm,
  slider, like button, cursor trail, push button, star rating, floating label,
  copy button, stepper, chips, PIN input, password meter, tooltip,
  swipe-to-reveal, rotary knob, reorderable list, expanding search, squish
  button, toggle pills, value scrubber, speed dial, swatch picker,
  slide-to-unlock, tag input, keycap press.
- **Feedback & State** — scramble reveal, marquee, stagger entrance, icon
  morph, underline draw, elastic progress, delayed tooltip, switch, checkbox,
  typewriter, counter, odometer, status pill, pulse badge, success check,
  segment loader, spinner, progress ring, notification slide-in, step
  progress, undo snackbar, submit states, countdown, skeleton, toast stack,
  indeterminate bar, shimmer skeleton, typing dots, heartbeat, battery charge,
  signal bars, badge counter, bookmark toggle.
- **Surface & Motion** — error shake, confetti burst, parallax tilt, blur
  transition, flip card, gradient drift, color pulse, focus ring, smooth
  scroll, zoom-pan.

## Reusable primitives

### Baseline spring
`stiffness 320 · damping 24 · mass 1.0` — the gallery's default tuning knobs.
Higher stiffness = snappier; higher damping = less overshoot/oscillation;
higher mass = heavier/slower.

### Spring presets (stiffness, damping) seen in the gallery
| Preset          | Feel                                   |
| --------------- | -------------------------------------- |
| spring(360, 22) | very snappy, small overshoot           |
| spring(340, 22) | snappy                                 |
| spring(320, 24) | **baseline** — brisk, gentle settle    |
| spring(300, 24) | balanced                               |
| spring(300, 20) | balanced, a touch more bounce          |
| spring(280, 18) | softer, more overshoot                 |
| spring(260, 28) | slow, well-damped (little bounce)      |
| spring(200, 20) | slow, loose, pronounced overshoot      |

### CSS cubic-bezier curves (springs approximated as fixed curves)
For plain CSS transitions you can't run a real solver, so these curves stand in
for spring feel. The first is the workhorse.
```css
/* spring settlement — overshoot then settle (GO-TO for most UI) */
--ease-spring:   cubic-bezier(0.34, 1.56, 0.64, 1);
/* glide / strong ease-out — long, smooth deceleration */
--ease-glide:    cubic-bezier(0.16, 1, 0.3, 1);
/* custom glide — symmetric-ish in/out */
--ease-glide-2:  cubic-bezier(0.65, 0, 0.35, 1);
/* gentle overshoot — subtler than --ease-spring */
--ease-overshoot: cubic-bezier(0.18, 1.25, 0.4, 1);
/* shake decay — for error/attention shakes */
--ease-shake:    cubic-bezier(0.36, 0.07, 0.19, 0.97);
```
Note: any bezier whose 2nd control-point y > 1 (e.g. `1.56`, `1.25`)
**overshoots** past the target before settling — that's what reads as "spring."

## Copy-ready patterns

CSS — spring-settling size/position change (e.g. the "card resize" effect):
```css
.card {
  height: 64px;
  overflow: hidden;
  transition: height 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.card[data-open="true"] { height: 120px; }
```

React — same idea with a hook and inline transition:
```jsx
function SpringCard() {
  const [open, setOpen] = useState(false);
  return (
    <div
      onClick={() => setOpen(!open)}
      style={{
        height: open ? 120 : 64,
        overflow: "hidden",
        transition: "height 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)",
      }}
    />
  );
}
```

"AI prompt" export style (paste into a model to generate a variant), e.g.:
> Build a card that expands and collapses its height when clicked. Animate only
> the height with a single spring-like cubic-bezier(...) over ~0.5s...

## When to reach for this here

The hosted `webapp/` is React/Next — the presets and curves apply directly to
seat chips, the claims/right-rail panel, PYTHIA console, and Scroll-World
transitions (see `.claude/skills/scroll-world`). Prefer `--ease-spring` for
opens/toggles/entrances; `--ease-glide` for scroll/parallax; `--ease-shake` for
error states. For real (not approximated) springs in React, a physics lib
(Framer Motion / react-spring) using the stiffness/damping presets above gets
you the true feel — but mind the stdlib/no-build constraints of each surface
before adding a dependency (see root `CLAUDE.md` conventions).
