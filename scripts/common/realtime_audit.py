"""Realtime audit event writer and tail helper.

This module is intentionally small and dependency-light so site scripts can
record audit events without pulling in the server package.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ai_orchestrator.paths.runtime import data_dir  # noqa: E402
from ai_orchestrator.core.logging_utils import mask_sensitive  # noqa: E402 - sys.path 부트스트랩 뒤 import

LOG_DIR = data_dir() / "logs"
AUDIT_JSONL = LOG_DIR / "realtime_audit.jsonl"
AUDIT_TEXT = LOG_DIR / "realtime_audit.log"

_MAX_FIELD_LENGTH = 500


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _truncate(value: Any, max_len: int = _MAX_FIELD_LENGTH) -> Any:
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + f"...[+{len(value) - max_len}chars]"
    if isinstance(value, dict):
        return {str(k): _truncate(v, max_len) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate(v, max_len) for v in value]
    return value


def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    return _truncate(mask_sensitive(metadata or {}))


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        f.flush()


def _append_text(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = entry.get("metadata") or {}
    meta_text = " ".join(f"{k}={v}" for k, v in meta.items())
    line = (
        f"{entry['timestamp']} [{entry['status']}] {entry['event_type']} "
        f"site={entry.get('site') or '-'} workflow={entry.get('workflow') or '-'} "
        f"risk={entry.get('risk') or '-'} {entry.get('message') or ''} {meta_text}"
    ).strip()
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()


def emit_event(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수/CLI 인자 보존)
    event_type: str,
    *,
    site: str = "",
    workflow: str = "",
    status: str = "info",
    risk: str = "",
    message: str = "",
    actor: str = "system",
    artifact_path: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one realtime audit event to JSONL and text logs."""
    entry = {
        "timestamp": _now(),
        "event_type": str(event_type),
        "site": site,
        "workflow": workflow,
        "status": status,
        "risk": risk,
        "message": _truncate(message, 300),
        "actor": actor,
        "artifact_path": artifact_path,
        "metadata": _sanitize_metadata(metadata),
    }
    _append_jsonl(AUDIT_JSONL, entry)
    _append_text(AUDIT_TEXT, entry)
    return entry


def read_recent_events(
    limit: int = 50,
    *,
    event_type: str | None = None,
    site: str | None = None,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Read recent JSONL audit events, newest last."""
    src = path or AUDIT_JSONL
    if not src.exists():
        return []
    lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
    events: list[dict[str, Any]] = []
    for line in lines[-max(limit * 3, limit) :]:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event_type and event.get("event_type") != event_type:
            continue
        if site and event.get("site") != site:
            continue
        events.append(event)
    return events[-limit:]


def format_event(event: dict[str, Any]) -> str:
    """Return a compact one-line representation for terminal monitoring."""
    return (
        f"{event.get('timestamp')} [{event.get('status')}] "
        f"{event.get('event_type')} site={event.get('site') or '-'} "
        f"workflow={event.get('workflow') or '-'} {event.get('message') or ''}"
    ).strip()


def follow_file(path: Path, *, from_start: bool = False, interval: float = 0.3) -> Iterable[str]:
    """Yield appended lines from a file, waiting for it to be created if needed."""
    while not path.exists():
        time.sleep(interval)
    with path.open("r", encoding="utf-8", errors="replace") as f:
        if not from_start:
            f.seek(0, 2)
        while True:
            line = f.readline()
            if line:
                yield line.rstrip("\n")
            else:
                time.sleep(interval)


def _cmd_recent(args: argparse.Namespace) -> None:
    for event in read_recent_events(args.limit, event_type=args.event_type, site=args.site):
        print(format_event(event))


def _cmd_tail(args: argparse.Namespace) -> None:
    path = AUDIT_TEXT if args.text else AUDIT_JSONL
    print(f"watching: {path}")
    for line in follow_file(path, from_start=args.from_start):
        if args.text:
            print(line, flush=True)
            continue
        try:
            print(format_event(json.loads(line)), flush=True)
        except json.JSONDecodeError:
            print(line, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Realtime audit log helper")
    sub = parser.add_subparsers(dest="cmd")

    recent = sub.add_parser("recent", help="print recent audit events")
    recent.add_argument("--limit", type=int, default=30)
    recent.add_argument("--site")
    recent.add_argument("--event-type")
    recent.set_defaults(func=_cmd_recent)

    tail = sub.add_parser("tail", help="follow realtime audit events")
    tail.add_argument("--from-start", action="store_true")
    tail.add_argument("--text", action="store_true", help="tail text log instead of JSONL")
    tail.set_defaults(func=_cmd_tail)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
