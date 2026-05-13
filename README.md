# reverie

Local-first index and MCP server for Claude Code session transcripts.

Reverie parses the JSONL transcript files that Claude Code writes to `~/.claude/projects/`, indexes them into a SQLite full-text-search database, and exposes them as MCP tools — so Claude can search its own conversation history across sessions.

## What it does

- **Indexes** past Claude Code sessions (messages, tool use/results, timestamps, project paths, git branch) into `~/.claude/cache/reverie.db`
- **Searches** transcripts via SQLite FTS5 with BM25 ranking
- **Serves** an MCP stdio server with tools for searching, browsing, and retrieving sessions
- **Tracks** MCP tool usage in an append-only log

## Installation

### One-liner

```sh
curl -fsSL https://raw.githubusercontent.com/bergerg/reverie/main/install.sh | bash
```

Installs to `~/.local/share/reverie`, configures the MCP server and `SessionEnd` hook automatically. Restart Claude Code when done.

### Manual

Requires Python ≥ 3.11 and [uv](https://github.com/astral-sh/uv).

```sh
git clone https://github.com/bergerg/reverie
cd reverie
uv sync
```

## Usage

### Index transcripts

```sh
# Index all past sessions
uv run reverie backfill

# Index a single transcript file
uv run reverie session ~/.claude/projects/my-project/abc123.jsonl
```

### Search

```sh
uv run reverie search "cache invalidation"
uv run reverie search '"exact phrase"' --project my-project --role assistant
uv run reverie search "token bucket" --include-tools --limit 5
```

### Run the MCP server

```sh
uv run reverie serve
```

### Stats and usage

```sh
uv run reverie stats
uv run reverie usage --since 2026-01-01
uv run reverie usage-tail -n 20
```

## MCP tools

| Tool | Description |
|---|---|
| `search_sessions` | Full-text search across all indexed transcripts |
| `get_session` | Fetch a session's metadata and messages |
| `get_message` | Fetch one message with surrounding context |
| `list_recent` | List recent sessions, newest first |
| `stats` | Index statistics |

## Hook integration

`bin/reverie-hook.sh` is a Claude Code `SessionEnd` hook that auto-indexes each session as it closes. Add it to your Claude Code settings:

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/reverie/bin/reverie-hook.sh"
          }
        ]
      }
    ]
  }
}
```

## Configuration

| Env var | Default | Description |
|---|---|---|
| `REVERIE_DB` | `~/.claude/cache/reverie.db` | SQLite database path |
| `REVERIE_USAGE_LOG` | `~/.claude/cache/reverie-usage.jsonl` | Usage log path |
| `REVERIE_USAGE_DISABLE` | — | Set to `1` to disable usage logging |
