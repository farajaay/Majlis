#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
[ -z "$MAJLIS_KEY" ] && echo "WARNING: MAJLIS_KEY not set — server is open."
exec uvicorn server.main:app --host 0.0.0.0 --port "${PORT:-8787}"
