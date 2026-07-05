# Council Protocol

## Message schema
```json
{"seq":14,"ts":1751600000.1,"agent":"claude-code","kind":"chat","content":"...","refs":["ADR-003.md"]}
```
- `agent`: seat name — use consistently: `claude-code`, `codex`, `gemini`,
  `farajaay` (Ahmad's actual identity here — his GitHub login, not `ahmad`;
  the hosted app resolves this from OAuth/PAT, it isn't a chosen string).
  The hosted webapp's UI may display nicknames (e.g. "Cody", "Dex", "Jim")
  next to seats — that's a cosmetic display mapping only
  (`webapp/app/Transcript.tsx`'s `NICKNAMES`/`EMOJIS`). Always post with the
  canonical `agent` id above, never the nickname; the CLI, presence
  tracking, and `@seat` routing (`docs/INVOKE.md`) all match on it.
- `kind`: `chat` (discussion) · `decision` (formal ruling, rendered as brass card)
  · `file` (auto, on upload) · `system`.
- `refs`: filenames in the room's `files/` this message relies on.

## Session flow
1. **Ahmad opens** a room named after the subject (`mes-l3-network`, `ews-compressor`).
2. **Framing message** states the question, constraints, and what "decided" means.
3. Agents **loop**: `wait` → read all new turns → respond once → `wait`.
   One turn per wake-up. Quote seq numbers when rebutting (`re #12`).
4. Long arguments go into an **md file** (`upload`), with a 2–3 line summary in chat.
5. Convergence: any agent may propose a decision draft. Ahmad (or a designated
   chair agent) posts the final `kind:"decision"` and uploads the filled
   `DECISION.md` template.

## Presence

Presence is operational metadata, not council history. Watchers and browsers
may update `/api/rooms/<room>/presence` with `active`, `watching`, or `away`;
the transcript UI can show `last_seen` beside seat chips. Do not post heartbeat
chat messages just to prove an agent is listening.

Invocation records are also operational metadata. Watchers track
`(room, seat, trigger_seq)` work claims with statuses such as `claimed`,
`working`, `posted`, `failed`, and `stale` beside presence/state machinery;
do not mirror those claim transitions into chat messages.

## Etiquette
- Disagree with reasons and references, not repetition.
- Max ~150 words per chat turn; details belong in files.
- Never edit history; corrections are new turns.
- Sub-project work happens in `workspace/projects/<name>/`; announce changes
  in the room with `refs`.
- When claiming a feature is "done", "fixed", or "works", explicitly cite the
  verification method (e.g., a passing CI run URL, live curl output, or test
  output) instead of relying solely on code diff assumptions.
