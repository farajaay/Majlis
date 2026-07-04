#!/usr/bin/env bash
# Quick tunnel for the work PC. Requires cloudflared installed.
exec cloudflared tunnel --url "http://localhost:${PORT:-8787}"
