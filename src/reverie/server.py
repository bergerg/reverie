from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import db
from .usage import measured

mcp = FastMCP("reverie")

_conn: sqlite3.Connection | None = None


def _c() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = db.connect()
    return _conn


def _epoch_to_iso(ts: int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {k: r[k] for k in r.keys()}


@mcp.tool()
@measured
def search_sessions(
    query: str,
    limit: int = 20,
    since: str | None = None,
    until: str | None = None,
    project: str | None = None,
    role: str | None = None,
    include_tools: bool = False,
) -> list[dict]:
    """Search past Claude Code session transcripts (the user's prior-work memory).

    CALL THIS FIRST when the user asks about past work, prior decisions, what
    "we" did, what was tried, what was discussed, or references a previous
    session — e.g. "what did we change in X", "last time we touched Y",
    "what did we decide about Z", "remember when we...". Prefer this over
    `git log` for those questions: git shows merged code, transcripts capture
    the reasoning, dead ends, and conversations behind the code. Use `git log`
    only when the user explicitly wants commit history or current code state.

    query: FTS5 query (e.g. 'cache invalidation', '"exact phrase"', 'token AND bucket').
    since/until: ISO8601 timestamps (inclusive) to filter messages.
    project: substring match on the project path (e.g. 'adr-embedder').
    role: 'user' or 'assistant'.
    include_tools: if true, also searches tool_use inputs and tool_result payloads.
    """
    conn = _c()
    params: list[Any] = [query]
    sql = [
        "SELECT m.id AS message_id, m.session_id, m.role, m.ts, s.project_path,",
        "       snippet(messages_fts, 0, '<<', '>>', '…', 12) AS snippet,",
        "       bm25(messages_fts) AS score",
        "FROM messages_fts JOIN messages m ON m.id = messages_fts.message_id",
        "JOIN sessions s ON s.id = m.session_id",
        "WHERE messages_fts MATCH ?",
    ]
    if since:
        sql.append("AND m.ts >= ?")
        params.append(int(datetime.fromisoformat(since).timestamp()))
    if until:
        sql.append("AND m.ts <= ?")
        params.append(int(datetime.fromisoformat(until).timestamp()))
    if project:
        sql.append("AND s.project_path LIKE ?")
        params.append(f"%{project}%")
    if role:
        sql.append("AND m.role = ?")
        params.append(role)
    sql.append("ORDER BY score LIMIT ?")
    params.append(limit)
    rows = conn.execute("\n".join(sql), params).fetchall()
    results = [
        {
            "message_id": r["message_id"],
            "session_id": r["session_id"],
            "role": r["role"],
            "ts": _epoch_to_iso(r["ts"]),
            "project_path": r["project_path"],
            "snippet": r["snippet"],
            "score": r["score"],
            "source": "messages",
        }
        for r in rows
    ]
    if include_tools:
        tool_params: list[Any] = [query]
        tool_sql = [
            "SELECT t.message_id, m.session_id, m.role, m.ts, s.project_path,",
            "       snippet(tool_fts, 1, '<<', '>>', '…', 12) AS snippet,",
            "       bm25(tool_fts) AS score, t.tool_name",
            "FROM tool_fts t JOIN messages m ON m.id = t.message_id",
            "JOIN sessions s ON s.id = m.session_id",
            "WHERE tool_fts MATCH ?",
        ]
        if since:
            tool_sql.append("AND m.ts >= ?")
            tool_params.append(int(datetime.fromisoformat(since).timestamp()))
        if until:
            tool_sql.append("AND m.ts <= ?")
            tool_params.append(int(datetime.fromisoformat(until).timestamp()))
        if project:
            tool_sql.append("AND s.project_path LIKE ?")
            tool_params.append(f"%{project}%")
        tool_sql.append("ORDER BY score LIMIT ?")
        tool_params.append(limit)
        rows = conn.execute("\n".join(tool_sql), tool_params).fetchall()
        results.extend(
            {
                "message_id": r["message_id"],
                "session_id": r["session_id"],
                "role": r["role"],
                "ts": _epoch_to_iso(r["ts"]),
                "project_path": r["project_path"],
                "snippet": r["snippet"],
                "score": r["score"],
                "tool_name": r["tool_name"],
                "source": "tool_io",
            }
            for r in rows
        )
        results.sort(key=lambda x: x["score"])
        results = results[:limit]
    return results


def _get_session_impl(
    session_id: str,
    from_ord: int | None = None,
    to_ord: int | None = None,
    include_tools: bool = False,
) -> dict:
    conn = _c()
    s = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if s is None:
        return {"error": f"session not found: {session_id}"}
    q = ["SELECT * FROM messages WHERE session_id = ?"]
    params: list[Any] = [session_id]
    if from_ord is not None:
        q.append("AND ord >= ?")
        params.append(from_ord)
    if to_ord is not None:
        q.append("AND ord <= ?")
        params.append(to_ord)
    q.append("ORDER BY ord")
    msgs = conn.execute("\n".join(q), params).fetchall()
    out_msgs = []
    for m in msgs:
        item = {
            "id": m["id"],
            "ord": m["ord"],
            "role": m["role"],
            "ts": _epoch_to_iso(m["ts"]),
            "text": m["text"],
            "tool_names": m["tool_names"],
        }
        if include_tools and m["has_tool_io"]:
            io = conn.execute(
                "SELECT block_idx, kind, tool_name, payload FROM tool_io WHERE message_id = ? ORDER BY block_idx",
                (m["id"],),
            ).fetchall()
            item["tool_io"] = [dict(x) for x in io]
        out_msgs.append(item)
    return {
        "session": {
            **{k: s[k] for k in s.keys() if k not in ("file_mtime", "file_size", "indexed_at")},
            "started_at": _epoch_to_iso(s["started_at"]),
            "ended_at": _epoch_to_iso(s["ended_at"]),
        },
        "messages": out_msgs,
    }


@mcp.tool()
@measured
def get_session(
    session_id: str,
    from_ord: int | None = None,
    to_ord: int | None = None,
    include_tools: bool = False,
) -> dict:
    """Fetch a session's metadata and a slice of its messages."""
    return _get_session_impl(session_id, from_ord, to_ord, include_tools)


@mcp.tool()
@measured
def get_message(message_id: str, context: int = 3, include_tools: bool = False) -> dict:
    """Fetch one message with N messages of surrounding context."""
    conn = _c()
    m = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    if m is None:
        return {"error": f"message not found: {message_id}"}
    lo, hi = m["ord"] - context, m["ord"] + context
    return _get_session_impl(m["session_id"], from_ord=lo, to_ord=hi, include_tools=include_tools)


@mcp.tool()
@measured
def list_recent(project: str | None = None, limit: int = 20) -> list[dict]:
    """List recent sessions, newest first."""
    conn = _c()
    q = ["SELECT id, project_path, started_at, ended_at, msg_count, first_user, git_branch FROM sessions"]
    params: list[Any] = []
    if project:
        q.append("WHERE project_path LIKE ?")
        params.append(f"%{project}%")
    q.append("ORDER BY started_at DESC LIMIT ?")
    params.append(limit)
    rows = conn.execute("\n".join(q), params).fetchall()
    return [
        {
            "session_id": r["id"],
            "project_path": r["project_path"],
            "started_at": _epoch_to_iso(r["started_at"]),
            "ended_at": _epoch_to_iso(r["ended_at"]),
            "msg_count": r["msg_count"],
            "git_branch": r["git_branch"],
            "first_user": r["first_user"],
        }
        for r in rows
    ]


@mcp.tool()
@measured
def stats() -> dict:
    """Index statistics."""
    conn = _c()
    sess = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
    msgs = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
    last = conn.execute("SELECT MAX(indexed_at) AS t FROM sessions").fetchone()["t"]
    projects = conn.execute("SELECT COUNT(DISTINCT project_path) AS n FROM sessions").fetchone()["n"]
    return {
        "sessions": sess,
        "messages": msgs,
        "projects": projects,
        "last_indexed_at": _epoch_to_iso(last),
        "db_path": str(db.DEFAULT_DB_PATH),
    }


def run() -> None:
    mcp.run()
