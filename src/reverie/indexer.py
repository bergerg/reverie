from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from . import db, parser

CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"


def index_session(conn: sqlite3.Connection, file_path: Path, *, force: bool = False) -> tuple[str, bool]:
    """Index a single session file. Returns (session_id_or_path, was_indexed)."""
    if not file_path.exists():
        return (str(file_path), False)
    stat = file_path.stat()
    if not force and not db.session_needs_reindex(
        conn, str(file_path.resolve()), int(stat.st_mtime), int(stat.st_size)
    ):
        return (str(file_path), False)

    parsed = parser.parse_file(file_path)
    if parsed is None:
        return (str(file_path), False)

    conn.execute("BEGIN")
    try:
        db.purge_session(conn, parsed.id)
        conn.execute(
            """
            INSERT INTO sessions (
              id, project_path, file_path, file_mtime, file_size,
              started_at, ended_at, msg_count, git_branch, cc_version,
              first_user, summary, indexed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                parsed.id,
                parsed.project_path,
                parsed.file_path,
                parsed.file_mtime,
                parsed.file_size,
                parsed.started_at,
                parsed.ended_at,
                len(parsed.messages),
                parsed.git_branch,
                parsed.cc_version,
                parsed.first_user,
                parsed.summary,
                int(time.time()),
            ),
        )
        msg_rows = []
        fts_rows = []
        tool_rows = []
        tool_fts_rows = []
        for m in parsed.messages:
            msg_rows.append(
                (m.id, parsed.id, m.parent_id, m.ord, m.role, m.ts, m.text, m.tool_names, int(m.has_tool_io))
            )
            if m.text:
                fts_rows.append((m.text, m.role, parsed.id, m.id))
            for io in m.tool_io:
                tool_rows.append((m.id, io.block_idx, io.kind, io.tool_name, io.payload))
                if io.payload:
                    tool_fts_rows.append((io.tool_name or "", io.payload, m.id, parsed.id))

        conn.executemany(
            "INSERT INTO messages (id, session_id, parent_id, ord, role, ts, text, tool_names, has_tool_io) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            msg_rows,
        )
        conn.executemany(
            "INSERT INTO messages_fts (text, role, session_id, message_id) VALUES (?,?,?,?)",
            fts_rows,
        )
        conn.executemany(
            "INSERT INTO tool_io (message_id, block_idx, kind, tool_name, payload) VALUES (?,?,?,?,?)",
            tool_rows,
        )
        conn.executemany(
            "INSERT INTO tool_fts (tool_name, payload, message_id, session_id) VALUES (?,?,?,?)",
            tool_fts_rows,
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return (parsed.id, True)


def backfill(conn: sqlite3.Connection, root: Path = CLAUDE_PROJECTS_ROOT, *, force: bool = False) -> dict:
    indexed = skipped = errors = 0
    for f in parser.iter_transcripts(root):
        try:
            _, did = index_session(conn, f, force=force)
            if did:
                indexed += 1
            else:
                skipped += 1
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"[reverie] error indexing {f}: {exc}")
    return {"indexed": indexed, "skipped": skipped, "errors": errors}
