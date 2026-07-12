---
name: loading-empty-error-states
description: >-
  Design the loading/empty/error/partial states for any async view in
  webapp/, not just the happy path. Use for the transcript, PYTHIA panel,
  or any component that fetches or polls data.
when_to_use: a fetch, a poll loop, a list, a room with no data yet
---

# Loading / Empty / Error States

Adapted from LoopKit's `loading-empty-error-states` skill
(github.com/Archive228/loopkit, MIT) for this repo's async surfaces —
`Transcript.tsx` (3s room/message polling), `PythiaPanel.tsx` (5s message
polling + the map iframe), and `signin`/`guide`. AI-built UIs tend to handle
only the happy path; check all four states for each fetch/poll in the diff:

- **Loading** — a skeleton/placeholder that matches the final layout, not a
  centered spinner that shifts everything else once data arrives.
- **Empty** — a real first-run state. A room with no transcript history yet,
  or PYTHIA with no room configured, needs to say what it is and the one
  action to fill it — not a blank floor. PYTHIA already has a documented
  empty state ("offline / awaiting feed" — see `.claude/skills/scroll-
  world/SKILL.md`); match that pattern's tone for any new empty state rather
  than inventing a different one.
- **Error** — what failed, in plain language, plus a retry where one makes
  sense (e.g. a failed poll, GitHub OAuth denial on `/signin` for a
  non-allowlisted login). Never a raw stack trace or a silently frozen UI.
- **Partial** — the polling model here means data arrives incrementally;
  make sure a message that's mid-arrival or a stale/failed claim (see
  `Claim`/`derivedState` in `Transcript.tsx`) reads clearly rather than as a
  glitch.

For every `fetch`/polling call touched in the redesign, confirm all four
states exist and are styled with the same token set as the happy path —
the empty and error states are where a redesign most often looks unfinished.
