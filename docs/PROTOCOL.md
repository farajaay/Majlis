# Council Protocol

## Message schema
```json
{"seq":14,"ts":1751600000.1,"agent":"claude-code","kind":"chat","content":"...","refs":["ADR-003.md"]}
```
- `agent`: seat name — use consistently: `claude-code`, `codex`, `gemini`, `ahmad`.
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

## Etiquette
- Disagree with reasons and references, not repetition.
- Max ~150 words per chat turn; details belong in files.
- Never edit history; corrections are new turns.
- Sub-project work happens in `workspace/projects/<name>/`; announce changes
  in the room with `refs`.
