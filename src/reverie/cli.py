from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import db, indexer, usage


def cmd_backfill(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    root = Path(args.root).expanduser()
    res = indexer.backfill(conn, root, force=args.force)
    print(json.dumps(res, indent=2))
    return 0


def cmd_session(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    sid, did = indexer.index_session(conn, Path(args.path).expanduser(), force=args.force)
    print(json.dumps({"session_id": sid, "indexed": did}))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    from . import server  # lazy: only needs DB

    server._conn = db.connect(args.db)
    results = server.search_sessions(
        args.query,
        limit=args.limit,
        project=args.project,
        role=args.role,
        include_tools=args.include_tools,
    )
    print(json.dumps(results, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from . import server

    server._conn = db.connect(args.db)
    server.run()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    from . import server

    server._conn = db.connect(args.db)
    print(json.dumps(server.stats(), indent=2))
    return 0


def cmd_usage(args: argparse.Namespace) -> int:
    summary = usage.summarize(since=args.since, session=args.session)
    print(json.dumps(summary, indent=2))
    return 0


def cmd_usage_tail(args: argparse.Namespace) -> int:
    records = list(usage.iter_records())
    for r in records[-args.n :]:
        print(json.dumps(r, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reverie")
    p.add_argument("--db", default=None, help="path to sqlite db (default: $REVERIE_DB or ~/.claude/cache/reverie.db)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("backfill", help="index all transcripts under root")
    s.add_argument("--root", default=str(indexer.CLAUDE_PROJECTS_ROOT))
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_backfill)

    s = sub.add_parser("session", help="index a single transcript file")
    s.add_argument("path")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_session)

    s = sub.add_parser("search", help="search transcripts (FTS5 syntax)")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--project")
    s.add_argument("--role", choices=["user", "assistant"])
    s.add_argument("--include-tools", action="store_true")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("serve", help="run the MCP stdio server")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("stats", help="print index stats")
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("usage", help="summarize MCP tool usage from the append-only log")
    s.add_argument("--since", help="ISO timestamp (e.g. 2026-05-13)")
    s.add_argument("--session", help="filter to a specific server-instance session id")
    s.set_defaults(func=cmd_usage)

    s = sub.add_parser("usage-tail", help="print the last N usage records")
    s.add_argument("-n", type=int, default=10)
    s.set_defaults(func=cmd_usage_tail)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
