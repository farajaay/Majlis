# Design System "Data Model": Modern Redesign of the Majlis Webapp

This feature introduces no application data entities (spec.md's Key Entities section is explicitly N/A). What it does introduce is a small, shared set of **design tokens** that every redesigned surface consumes. They're documented here in lieu of a data model because they are the one new "shape" this feature adds to the codebase, and downstream tasks (tasks.md) reference them by name.

## Token groups (CSS custom properties in `webapp/app/globals.css` `:root`)

- **Color roles**: `--ink` (background), `--panel`, `--line`, `--text`, `--text-muted`, `--accent`, `--accent-strong`, plus the existing per-seat `SEAT_COLORS` array in `Transcript.tsx` (unchanged — seat colors are data-driven, not part of the redesign's token set).
- **Type scale**: `--font-sans` (system font stack, per CLAUDE.md's "system fonts only" rule — unchanged), a small numeric scale (`--fs-100` ... `--fs-600`) covering body copy, message metadata, section headers, and page titles.
- **Spacing scale**: `--space-1` ... `--space-8`, a consistent step used for padding/gaps across the transcript, PYTHIA panel, sign-in, and guide pages.
- **Radii & elevation**: `--radius-sm`/`--radius-md`/`--radius-lg`, `--shadow-sm`/`--shadow-md` for cards, panels, and the composer.
- **Motion tokens**: `--ease-spring`, `--ease-out`, `--dur-fast`, `--dur-med`, `--dur-slow` (see research.md) — all zeroed out or shortened to `0.01ms` under `prefers-reduced-motion: reduce`, matching the existing pattern already used by Scroll-World and PYTHIA.

## Relationships / scoping rules

- All light-shell surfaces (`Transcript.tsx`'s header/floor/rail/composer, sign-in page, guide page) consume the color roles directly.
- PYTHIA (`PythiaPanel.tsx`) keeps its own hardcoded dark color values (existing, intentional — see research.md) but consumes the shared type scale, spacing scale, and motion tokens so its rhythm matches the rest of the app.
- Scroll-World (`ScrollWorld.tsx`) is canvas-drawn, so it doesn't consume CSS tokens directly, but its palette (dot color, arc color, alpha values) is manually kept in the same hue family as `--accent`/`--ink` so the backdrop and foreground read as one system (FR-002, FR-006).

## State / transitions

Not applicable — tokens are static design values, not stateful entities. The only "transition" of note is the reduced-motion media query switching the motion token values, which is a CSS-level override, not application state.
