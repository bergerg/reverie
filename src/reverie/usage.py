from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable

USAGE_LOG = Path(
    os.environ.get(
        "REVERIE_USAGE_LOG",
        str(Path.home() / ".claude" / "cache" / "reverie-usage.jsonl"),
    )
)

DISABLED = os.environ.get("REVERIE_USAGE_DISABLE") == "1"

# One UUID per server-process; in practice one Claude Code session == one
# reverie subprocess, so this is a usable session identifier without
# relying on CC-specific env vars.
INSTANCE_ID = os.environ.get("CLAUDE_SESSION_ID") or str(uuid.uuid4())


def _estimate_tokens(s: str) -> int:
    # ~4 chars/token, English-biased. Good enough for tracking trends;
    # swap in tiktoken or anthropic.count_tokens if you need accuracy.
    return (len(s) + 3) // 4


def _to_jsonable(x: Any) -> Any:
    try:
        json.dumps(x)
        return x
    except TypeError:
        return json.dumps(x, default=str, ensure_ascii=False)


def log_call(tool: str, args: dict, result: Any, *, elapsed_ms: float, error: str | None = None) -> None:
    if DISABLED:
        return
    try:
        in_str = json.dumps(args, default=str, ensure_ascii=False)
        out_str = "" if result is None else json.dumps(result, default=str, ensure_ascii=False)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session": INSTANCE_ID,
            "tool": tool,
            "in_tokens": _estimate_tokens(in_str),
            "out_tokens": _estimate_tokens(out_str),
            "in_chars": len(in_str),
            "out_chars": len(out_str),
            "elapsed_ms": round(elapsed_ms, 2),
        }
        if error is not None:
            record["error"] = error
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        # O_APPEND on POSIX guarantees atomic writes under PIPE_BUF for a
        # single write(); a one-line JSON record stays well under 4KB.
        with USAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Telemetry must never break a tool call.
        pass


def measured(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        all_args = {**kwargs}
        if args:
            all_args["_positional"] = list(args)
        t0 = time.perf_counter()
        err: str | None = None
        result: Any = None
        try:
            result = fn(*args, **kwargs)
            return result
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            raise
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            log_call(fn.__name__, all_args, result, elapsed_ms=elapsed_ms, error=err)

    return wrapper


def iter_records(path: Path | None = None):
    p = path or USAGE_LOG
    if not p.exists():
        return
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def summarize(path: Path | None = None, *, since: str | None = None, session: str | None = None) -> dict:
    since_ts = None
    if since:
        since_ts = datetime.fromisoformat(since).replace(tzinfo=timezone.utc).timestamp()
    totals = {"calls": 0, "in_tokens": 0, "out_tokens": 0, "errors": 0}
    per_tool: dict[str, dict[str, int]] = {}
    per_session: dict[str, dict[str, int]] = {}
    for r in iter_records(path):
        if session and r.get("session") != session:
            continue
        if since_ts is not None:
            try:
                rec_ts = datetime.fromisoformat(r["ts"]).timestamp()
            except (KeyError, ValueError):
                continue
            if rec_ts < since_ts:
                continue
        totals["calls"] += 1
        totals["in_tokens"] += r.get("in_tokens", 0)
        totals["out_tokens"] += r.get("out_tokens", 0)
        if r.get("error"):
            totals["errors"] += 1
        for bucket, key in ((per_tool, r.get("tool", "?")), (per_session, r.get("session", "?"))):
            b = bucket.setdefault(key, {"calls": 0, "in_tokens": 0, "out_tokens": 0})
            b["calls"] += 1
            b["in_tokens"] += r.get("in_tokens", 0)
            b["out_tokens"] += r.get("out_tokens", 0)
    return {
        "log_path": str(USAGE_LOG),
        "totals": totals,
        "by_tool": per_tool,
        "by_session": per_session,
    }
