#!/usr/bin/env bash
# Claude Code SessionEnd hook: index the just-ended transcript into reverie.
# Reads {"transcript_path": "..."} JSON from stdin. Fires asynchronously and
# always exits 0 so it never blocks session shutdown.
set -u

input=$(cat)
transcript=$(printf '%s' "$input" | /usr/bin/python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    p = d.get("transcript_path") or ""
    print(p)
except Exception:
    pass
' 2>/dev/null)

if [ -n "$transcript" ] && [ -f "$transcript" ]; then
  (
    /opt/homebrew/bin/uv run --quiet --project "$(dirname "$(dirname "$0")")" reverie session "$transcript"
  ) >/dev/null 2>&1 &
  disown 2>/dev/null || true
fi

exit 0
