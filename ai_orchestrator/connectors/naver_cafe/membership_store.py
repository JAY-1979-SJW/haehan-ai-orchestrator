"""L7 Persistence — 가입 카페 스냅샷 이력과 변동 기록 (파일 저장).

기준서: docs/specs/2026-10-05_cafe_membership_changes.md

- 스냅샷: `data/cafe/my_cafes_history/<UTC 시각>.json` — 카페 id·이름·clubid 만(쿠키·토큰·값 없음). 최근 HISTORY_MAX 개만 유지.
- 변동 기록: `data/cafe/my_cafes_changes.jsonl` — 신규·탈퇴·이름 변경이 있었던 수집만 한 줄씩. 최근 CHANGES_MAX 줄만 유지.
- 기존 `my_cafes.json`(현재 목록) 쓰기는 그대로 수집기(scripts)가 한다 — 여기서는 이력만 다룬다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_orchestrator.paths import repo_root
from ai_orchestrator.paths.runtime import data_dir

ROOT = repo_root()
_DIR = data_dir() / "cafe"
HISTORY_MAX = 90
CHANGES_MAX = 200


def _history_dir() -> Path:
    return _DIR / "my_cafes_history"


def _changes_path() -> Path:
    return _DIR / "my_cafes_changes.jsonl"


def _snapshot_files() -> list[Path]:
    d = _history_dir()
    return sorted(d.glob("*.json")) if d.exists() else []  # 파일 이름이 시각이라 사전순 = 시간순


def _stamp(now_iso: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in now_iso)[:32]


def latest_snapshot() -> list[dict[str, str]] | None:
    """가장 최근 스냅샷의 카페 목록. 이력이 없거나 읽을 수 없으면 None(= 기준선부터 시작)."""
    files = _snapshot_files()
    if not files:
        return None
    try:
        data = json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cafes = data.get("cafes") if isinstance(data, dict) else None
    return cafes if isinstance(cafes, list) else None


def save_snapshot(cafes: list[dict[str, str]], *, now_iso: str) -> Path:
    """스냅샷을 저장하고 오래된 것을 정리한다."""
    d = _history_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{_stamp(now_iso)}.json"
    path.write_text(
        json.dumps({"at": now_iso, "total": len(cafes), "cafes": cafes}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    for old in _snapshot_files()[:-HISTORY_MAX]:
        old.unlink(missing_ok=True)
    return path


def history_totals(limit: int = 30) -> list[dict[str, Any]]:
    """최근 스냅샷의 (시각, 총 가입 수) — 가입 수 추이용(최신이 마지막)."""
    out: list[dict[str, Any]] = []
    for f in _snapshot_files()[-max(1, limit) :]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append({"at": str(data.get("at", "")), "total": int(data.get("total", 0))})
        except (OSError, ValueError, TypeError):
            continue
    return out


def append_change(record: dict[str, Any]) -> None:
    """변동 기록 한 줄을 더하고 오래된 줄을 정리한다."""
    _DIR.mkdir(parents=True, exist_ok=True)
    path = _changes_path()
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines.append(json.dumps(record, ensure_ascii=False))
    path.write_text("\n".join(lines[-CHANGES_MAX:]) + "\n", encoding="utf-8")


def recent_changes(limit: int = 20) -> list[dict[str, Any]]:
    """최근 변동 기록(최신순). 깨진 줄은 건너뛴다."""
    path = _changes_path()
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
        if len(out) >= max(1, limit):
            break
    return out
