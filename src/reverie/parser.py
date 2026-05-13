from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator

TOOL_PAYLOAD_CAP = 4096
TEXT_BEARING_BLOCK_TYPES = {"text", "thinking"}


@dataclass
class ToolIO:
    block_idx: int
    kind: str
    tool_name: str | None
    payload: str


@dataclass
class Message:
    id: str
    parent_id: str | None
    ord: int
    role: str
    ts: int
    text: str
    tool_io: list[ToolIO] = field(default_factory=list)

    @property
    def tool_names(self) -> str:
        names = sorted({io.tool_name for io in self.tool_io if io.tool_name})
        return ",".join(names)

    @property
    def has_tool_io(self) -> bool:
        return bool(self.tool_io)


@dataclass
class ParsedSession:
    id: str
    project_path: str
    file_path: str
    file_mtime: int
    file_size: int
    started_at: int
    ended_at: int
    git_branch: str | None
    cc_version: str | None
    first_user: str | None
    summary: str | None
    messages: list[Message]


def _ts_to_epoch(ts: str | None) -> int | None:
    if not ts:
        return None
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _truncate(s: str, cap: int = TOOL_PAYLOAD_CAP) -> str:
    if len(s) <= cap:
        return s
    return s[:cap] + f"\n…[truncated {len(s) - cap} chars]"


def _flatten_content(content) -> tuple[str, list[tuple[str, str | None, str]]]:
    """Return (concatenated_text, [(kind, tool_name, payload), ...])."""
    if content is None:
        return "", []
    if isinstance(content, str):
        return content, []
    if not isinstance(content, list):
        return "", []
    texts: list[str] = []
    blocks: list[tuple[str, str | None, str]] = []
    for b in content:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t in TEXT_BEARING_BLOCK_TYPES:
            v = b.get("text") or b.get("thinking") or ""
            if v:
                texts.append(v)
        elif t == "tool_use":
            name = b.get("name")
            payload = json.dumps(b.get("input"), ensure_ascii=False, default=str)
            blocks.append(("use", name, _truncate(payload)))
        elif t == "tool_result":
            inner = b.get("content")
            if isinstance(inner, list):
                inner_text = "\n".join(
                    x.get("text", "") for x in inner if isinstance(x, dict) and x.get("type") == "text"
                )
            elif isinstance(inner, str):
                inner_text = inner
            else:
                inner_text = json.dumps(inner, ensure_ascii=False, default=str) if inner else ""
            blocks.append(("result", None, _truncate(inner_text)))
    return "\n\n".join(texts).strip(), blocks


def parse_file(path: Path) -> ParsedSession | None:
    stat = path.stat()
    raw_lines: list[dict] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw_lines.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not raw_lines:
        return None

    session_id: str | None = None
    project_path: str | None = None
    git_branch: str | None = None
    cc_version: str | None = None
    summary: str | None = None
    first_user: str | None = None
    timestamps: list[int] = []
    messages: list[Message] = []
    tool_use_names: dict[str, str] = {}  # tool_use_id -> name

    for ord_idx, d in enumerate(raw_lines):
        if session_id is None:
            session_id = d.get("sessionId")
        project_path = project_path or d.get("cwd")
        git_branch = git_branch or d.get("gitBranch")
        cc_version = cc_version or d.get("version")
        if d.get("type") == "summary" and not summary:
            summary = d.get("summary") or d.get("text")

        ttype = d.get("type")
        if ttype not in ("user", "assistant"):
            continue
        msg = d.get("message")
        if not isinstance(msg, dict):
            continue
        ts = _ts_to_epoch(d.get("timestamp"))
        if ts is not None:
            timestamps.append(ts)

        text, blocks = _flatten_content(msg.get("content"))
        tool_io: list[ToolIO] = []
        for bi, (kind, name, payload) in enumerate(blocks):
            if kind == "use" and name:
                # remember name keyed by the tool_use id, if available
                # find the original block to grab its id
                pass
            tool_io.append(ToolIO(block_idx=bi, kind=kind, tool_name=name, payload=payload))

        # Second pass on raw content to map tool_use_id -> name and back-fill result names
        content = msg.get("content")
        if isinstance(content, list):
            result_idx_iter = iter(
                i for i, b in enumerate(content)
                if isinstance(b, dict) and b.get("type") == "tool_result"
            )
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tid, tname = b.get("id"), b.get("name")
                    if tid and tname:
                        tool_use_names[tid] = tname
            # back-fill result tool_names by tool_use_id
            io_results = [io for io in tool_io if io.kind == "result"]
            result_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
            for io, rb in zip(io_results, result_blocks):
                tid = rb.get("tool_use_id")
                if tid and tid in tool_use_names:
                    io.tool_name = tool_use_names[tid]

        if ttype == "user" and first_user is None and text:
            first_user = text[:280]

        if not text and not tool_io:
            continue

        messages.append(
            Message(
                id=d.get("uuid") or f"{session_id}:{ord_idx}",
                parent_id=d.get("parentUuid"),
                ord=ord_idx,
                role=ttype,
                ts=ts or 0,
                text=text,
                tool_io=tool_io,
            )
        )

    if not session_id or not messages:
        return None

    return ParsedSession(
        id=session_id,
        project_path=project_path or "",
        file_path=str(path.resolve()),
        file_mtime=int(stat.st_mtime),
        file_size=int(stat.st_size),
        started_at=min(timestamps) if timestamps else 0,
        ended_at=max(timestamps) if timestamps else 0,
        git_branch=git_branch,
        cc_version=cc_version,
        first_user=first_user,
        summary=summary,
        messages=messages,
    )


def iter_transcripts(root: Path) -> Iterator[Path]:
    yield from root.glob("*/*.jsonl")
