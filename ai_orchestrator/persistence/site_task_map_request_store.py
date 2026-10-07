"""L7 Persistence — 사이트 탐색 요청(승인 카드) 저장소 (요청 하나당 JSON 한 개).

기준서: docs/specs/2026-10-03_site_task_map.md (M3)

- 위치: `data/site_task_map_requests/<id>.json` (gitignore 대상). 지도 파일(`site_task_map/`)과 폴더를 나눠 호스트 목록에 섞이지 않게 한다.
- 상태 전이는 서비스가 정한다(여기서는 읽기/쓰기만). 쓰기는 임시 파일 → 교체(원자적).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import data_dir

_DIR = data_dir() / "site_task_map_requests"
_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def new_id() -> str:
    return uuid.uuid4().hex


def _path(request_id: str) -> Path:
    if not _ID_RE.match(str(request_id or "")):
        raise ValueError("요청 id 가 올바르지 않습니다")
    return _DIR / f"{request_id}.json"


def save(request: dict[str, Any]) -> None:
    path = _path(request["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(request, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load(request_id: str) -> dict[str, Any] | None:
    path = _path(request_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"탐색 요청 파일을 읽을 수 없습니다: {path.name}") from e


def list_all(status: str | None = None) -> list[dict[str, Any]]:
    if not _DIR.exists():
        return []
    out = []
    for path in _DIR.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # 깨진 파일 하나가 목록 전체를 막지 않게 건너뛴다
        if status is None or item.get("status") == status:
            out.append(item)
    return sorted(out, key=lambda r: r.get("created_at", ""), reverse=True)
