# Install Script Design

**Date:** 2026-05-13  
**Status:** Approved

## Context

Reverie requires three manual setup steps after cloning: `uv sync`, patching `claude_desktop_config.json` with the MCP server entry, and patching `settings.json` with the `SessionEnd` hook. The goal is a single `curl | bash` command that performs all of this automatically.

## Invocation

```sh
curl -fsSL https://raw.githubusercontent.com/bergerg/reverie/main/install.sh | bash
```

## What the Script Does

1. **Preflight check** — verifies `uv` is on `$PATH`; exits with a clear install link if not
2. **Clone** — clones repo to `~/.local/share/reverie` (skips if already present)
3. **Sync deps** — runs `uv sync` in the install dir
4. **Backfill** — runs `uv run reverie backfill` to index existing transcripts
5. **Patch MCP config** — merges the `reverie` server entry into `~/.claude/claude_desktop_config.json` using inline Python
6. **Patch hook config** — merges the `SessionEnd` hook entry into `~/.claude/settings.json` using inline Python
7. **Print summary** — confirms what was done and instructs user to restart Claude Code

## Key Constraints

- **No `jq` dependency** — JSON patching uses inline Python 3 (always available on macOS)
- **Idempotent** — safe to run multiple times; existing entries are not duplicated
- **Non-destructive** — existing config keys are preserved; only the `reverie` entries are added/updated
- **Install dir** — `~/.local/share/reverie` (XDG base dir convention); overridable via `REVERIE_INSTALL_DIR` env var

## Files Modified by the Script

- `~/.local/share/reverie/` — cloned repo
- `~/.claude/claude_desktop_config.json` — MCP server entry added under `mcpServers.reverie`
- `~/.claude/settings.json` — SessionEnd hook added under `hooks.SessionEnd`

## MCP Entry Added

```json
{
  "mcpServers": {
    "reverie": {
      "command": "uv",
      "args": ["run", "--project", "~/.local/share/reverie", "reverie", "serve"]
    }
  }
}
```

## Hook Entry Added

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.local/share/reverie/bin/reverie-hook.sh"
          }
        ]
      }
    ]
  }
}
```

## Verification

After running the script:
```sh
uv run --project ~/.local/share/reverie reverie stats
```
Should return session/message counts. Restart Claude Code and confirm `search_sessions` appears as an available MCP tool.
