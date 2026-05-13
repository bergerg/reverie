from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(
    os.environ.get(
        "REVERIE_DB",
        str(Path.home() / ".claude" / "cache" / "reverie.db"),
    )
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id            TEXT PRIMARY KEY,
  project_path  TEXT NOT NULL,
  file_path     TEXT NOT NULL UNIQUE,
  file_mtime    INTEGER NOT NULL,
  file_size     INTEGER NOT NULL,
  started_at    INTEGER NOT NULL,
  ended_at      INTEGER NOT NULL,
  msg_count     INTEGER NOT NULL,
  git_branch    TEXT,
  cc_version    TEXT,
  first_user    TEXT,
  summary       TEXT,
  indexed_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_project ON sessions(project_path, started_at DESC);
CREATE INDEX IF NOT EXISTS sessions_started ON sessions(started_at DESC);

CREATE TABLE IF NOT EXISTS messages (
  id            TEXT PRIMARY KEY,
  session_id    TEXT NOT NULL,
  parent_id     TEXT,
  ord           INTEGER NOT NULL,
  role          TEXT NOT NULL,
  ts            INTEGER NOT NULL,
  text          TEXT,
  tool_names    TEXT,
  has_tool_io   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id, ord);
CREATE INDEX IF NOT EXISTS messages_ts ON messages(ts DESC);

CREATE TABLE IF NOT EXISTS tool_io (
  message_id    TEXT NOT NULL,
  block_idx     INTEGER NOT NULL,
  kind          TEXT NOT NULL,
  tool_name     TEXT,
  payload       TEXT,
  PRIMARY KEY (message_id, block_idx)
);
CREATE INDEX IF NOT EXISTS tool_io_msg ON tool_io(message_id);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
  text,
  role UNINDEXED,
  session_id UNINDEXED,
  message_id UNINDEXED,
  tokenize='porter unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS tool_fts USING fts5(
  tool_name,
  payload,
  message_id UNINDEXED,
  session_id UNINDEXED,
  tokenize='porter unicode61'
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path) if path else DEFAULT_DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def session_needs_reindex(conn: sqlite3.Connection, file_path: str, mtime: int, size: int) -> bool:
    row = conn.execute(
        "SELECT file_mtime, file_size FROM sessions WHERE file_path = ?",
        (file_path,),
    ).fetchone()
    if row is None:
        return True
    return row["file_mtime"] != mtime or row["file_size"] != size


def purge_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM messages_fts WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM tool_fts WHERE session_id = ?", (session_id,))
    conn.execute(
        "DELETE FROM tool_io WHERE message_id IN (SELECT id FROM messages WHERE session_id = ?)",
        (session_id,),
    )
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
