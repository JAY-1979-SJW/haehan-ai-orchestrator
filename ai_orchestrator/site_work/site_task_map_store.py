"""L7 Persistence — 사이트 업무 지도 저장소 (호스트별 JSON 한 개).

기준서: docs/specs/2026-10-03_site_task_map.md (M1)

- 위치: `data/site_task_map/<host>.json` (gitignore 대상 — 저장소가 PUBLIC 이므로 커밋하지 않는다).
- 쓰기는 임시 파일 → 교체(원자적)라 중간에 끊겨도 기존 지도가 깨지지 않는다.
- 읽기에서 형식이 틀리면 **오류를 낸다**(조용히 빈 지도로 덮어써 사라지지 않게).
- 이 모듈은 파일 입출력만 한다. 분류·병합 같은 규칙은 `domain/site_task_map` 이 한다.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import data_dir

from . import site_map_history as hist
from . import site_map_history_store as history_store
from . import site_task_map as tm

_DIR = data_dir() / "site_task_map"
_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")


def _path(host: str) -> Path:
    host = str(host or "").strip().lower()
    if not _HOST_RE.match(host) or ".." in host:
        raise ValueError("호스트 이름이 올바르지 않습니다")
    return _DIR / f"{host}.json"


def load(host: str, *, now: str = "") -> dict[str, Any]:
    """저장된 지도. 없으면 빈 지도. 파일이 깨졌거나 형식이 다르면 ValueError."""
    path = _path(host)
    if not path.exists():
        return tm.empty_map(host.strip().lower(), now=now)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"사이트 지도 파일을 읽을 수 없습니다: {path.name}") from e
    return tm.validate_map(data)


def _stamp_revision(site_map: dict[str, Any], path: Path) -> None:
    """구조(업무·메뉴·데이터 소스)가 바뀐 저장이면 지도 버전(`map_rev`)을 올리고 그 버전의 구조 요약을 이력에 남긴다.

    검증 상태·관찰 시각만 바뀐 저장은 버전을 올리지 않는다(구조 지문이 같으므로). 이전 파일이 없거나 버전이 없던 옛 지도는 1 부터.
    """
    prev: dict[str, Any] = {}
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prev = {}  # 깨진 이전 파일은 새 지도로 덮어쓰는 저장이므로 처음 저장처럼 다룬다
    struct = hist.structure(site_map)
    fp = hist.fingerprint(struct)
    rev, changed = hist.next_rev(int(prev.get("map_rev") or 0), str(prev.get("map_fingerprint") or ""), fp)
    site_map["map_rev"], site_map["map_fingerprint"] = rev, fp
    if changed:
        history_store.save(_DIR, site_map["host"], rev, struct, at=str(site_map.get("updated_at") or ""), fingerprint=fp)


def history_list(host: str) -> list[dict[str, Any]]:
    """보존 중인 지도 버전 목록(최신 순)."""
    return history_store.list_revs(_DIR, host)


def history_load(host: str, rev: int) -> dict[str, Any]:
    return history_store.load(_DIR, host, rev)


def save(site_map: dict[str, Any]) -> Path:
    tm.validate_map(site_map)
    path = _path(site_map["host"])
    _stamp_revision(site_map, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(site_map, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def list_hosts() -> list[str]:
    if not _DIR.exists():
        return []
    return sorted(p.stem for p in _DIR.glob("*.json"))
