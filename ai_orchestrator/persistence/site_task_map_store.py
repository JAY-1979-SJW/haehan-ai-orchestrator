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

from ..domain import site_task_map as tm

_DIR = Path(__file__).resolve().parents[2] / "data" / "site_task_map"
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


def save(site_map: dict[str, Any]) -> Path:
    tm.validate_map(site_map)
    path = _path(site_map["host"])
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
