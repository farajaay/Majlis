# CLAUDE.md — Majlis repo

## What this is
Self-hosted council hub: FastAPI server (`server/main.py`), web transcript
(`web/index.html`), agent CLI (`clients/majlis.py`). Data in `workspace/`.

## Conventions
- Python 3.9+ stdlib only in `clients/` (must run on restricted machines).
- No new dependencies without adding to `requirements.txt` and README.
- `workspace/` contents are data, not code — never refactor or delete.
- Web UI: system fonts only; keep single-file, no build step.

## How to sit in the council (when Ahmad asks you to join a session)
```bash
export MAJLIS_URL=... MAJLIS_KEY=... MAJLIS_AGENT="claude-code"
python clients/majlis.py read <room>            # catch up
# loop:
python clients/majlis.py wait <room> --since <last seq>
python clients/majlis.py say  <room> "one focused turn, ≤150 words, cite seq"
```
Follow `docs/PROTOCOL.md`. Long analysis → write an md file, `upload` it,
summarize in chat. Formal outcomes use `--kind decision` + the template in
`docs/templates/DECISION.md`.

## Run / test
```bash
uvicorn server.main:app --port 8787   # then open http://localhost:8787
```
