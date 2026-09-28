"""GUI 로그 ring buffer — 1000 라인 + 자동 redact + JSON Lines export.

policy:
  - device_token / registration_code / Authorization 등 secret 패턴은
    저장 단계에서 즉시 [REDACTED] 치환
  - export 시 동일 redact 1차 확인 (2중 안전)
"""

from __future__ import annotations

import contextlib
import json
import re
import threading
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))

MAX_LINES = 1000

# secret 패턴 — 가능한 폭넓게 (key=value, key: value, "key": "value")
_REDACT_KEYS = (
    "device_token",
    "registration_code",
    "authorization",
    "cookie",
    "session",
    "password",
    "secret",
    "api_key",
    "bearer",
    "x-api-key",
    "token",
)

_REDACT_PATTERNS = [
    re.compile(
        rf'(?i)\b({k})\s*[:=]\s*["\']?([^\s"\',;]+)["\']?',
    )
    for k in _REDACT_KEYS
]
# JSON-style "key": "value"
_JSON_PATTERN = re.compile(
    r'(?i)"({})"\s*:\s*"([^"]{{8,}})"'.format("|".join(_REDACT_KEYS)),
)


_BEARER_PATTERN = re.compile(
    r"(?i)(Authorization\s*:\s*Bearer)\s+\S+",
)


def redact(text: str) -> str:
    if not text:
        return text
    out = text
    # Bearer 토큰 (Authorization: Bearer <value>)
    out = _BEARER_PATTERN.sub(r"\1 [REDACTED]", out)
    for p in _REDACT_PATTERNS:
        out = p.sub(lambda m: f"{m.group(1)}=[REDACTED]", out)
    out = _JSON_PATTERN.sub(r'"\1": "[REDACTED]"', out)
    return out


@dataclass
class LogEntry:
    ts: str  # ISO
    level: str  # INFO / WARN / ERR
    msg: str  # redacted
    source: str = "gui"

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class LogBuffer:
    """thread-safe ring buffer (deque maxlen=1000)."""

    def __init__(self, maxlen: int = MAX_LINES):
        self._lock = threading.Lock()
        self._buf: deque[LogEntry] = deque(maxlen=maxlen)
        self._subs: list = []

    def append(self, level: str, msg: str, *, source: str = "gui") -> LogEntry:
        ts = datetime.now(KST).strftime("%H:%M:%S")
        entry = LogEntry(ts=ts, level=level.upper(), msg=redact(msg or ""), source=source)
        with self._lock:
            self._buf.append(entry)
        for fn in list(self._subs):
            # 구독자 콜백 예외로 로깅 전체가 죽지 않도록 무시(메시지는 이미 redact됨)
            with contextlib.suppress(Exception):
                fn(entry)
        return entry

    def info(self, msg: str, **kw) -> LogEntry:
        return self.append("INFO", msg, **kw)

    def warn(self, msg: str, **kw) -> LogEntry:
        return self.append("WARN", msg, **kw)

    def err(self, msg: str, **kw) -> LogEntry:
        return self.append("ERR", msg, **kw)

    def tail(self, n: int = 100, level_filter: str | None = None) -> list[LogEntry]:
        with self._lock:
            items = list(self._buf)
        if level_filter and level_filter.upper() != "ALL":
            items = [e for e in items if e.level == level_filter.upper()]
        return items[-n:]

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    def subscribe(self, fn) -> None:
        self._subs.append(fn)

    def export_jsonl(self, path: Path) -> dict:
        """JSON Lines 로 export. 2차 redact 검증."""
        with self._lock:
            entries = list(self._buf)
        lines = []
        for e in entries:
            # 2차 redact 안전망
            safe = LogEntry(ts=e.ts, level=e.level, msg=redact(e.msg), source=e.source)
            lines.append(safe.to_jsonl())
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"path": str(path), "count": len(lines)}

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)
