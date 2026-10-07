"""L7 Persistence — 등록 사이트 저장소 (JSON 한 개).

기준서: docs/specs/2026-10-05_site_task_map_m7_onboarding_auto_prepare.md (F1)

- 위치: `data/site_registry/sites.json` (gitignore 대상 — 저장소가 PUBLIC). 지도 폴더(`data/site_task_map/`)와 분리한다:
  지도 저장소는 그 폴더의 `*.json` 전부를 호스트로 취급하므로 같은 폴더에 두면 호스트 목록이 오염된다.
- 쓰기는 임시 파일 → 교체(원자적). 읽기에서 형식이 틀리면 오류(조용히 빈 목록으로 덮어쓰지 않는다).
- 구조만 저장한다(호스트·상태·정책·시각). 이 모듈은 파일 입출력만 한다 — 규칙은 `domain/site_registry`.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import data_dir

from . import site_registry as sr

_FILE = data_dir() / "site_registry" / "sites.json"
_lock = threading.Lock()


def _read() -> dict[str, dict[str, Any]]:
    if not _FILE.exists():
        return {}
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError("등록 사이트 파일을 읽을 수 없습니다(sites.json)") from e
    if not isinstance(data, dict) or data.get("version") != sr.VERSION or not isinstance(data.get("sites"), dict):
        raise ValueError("등록 사이트 파일 형식이 올바르지 않습니다(sites.json)")
    return {host: sr.validate_record(rec) for host, rec in data["sites"].items()}


def _write(sites: dict[str, dict[str, Any]]) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=_FILE.parent, prefix=".sites.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump({"version": sr.VERSION, "sites": sites}, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, _FILE)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_all() -> list[dict[str, Any]]:
    with _lock:
        return sorted(_read().values(), key=lambda r: r["host"])


def get(host: str) -> dict[str, Any] | None:
    with _lock:
        return _read().get(host)


def put(record: dict[str, Any]) -> dict[str, Any]:
    sr.validate_record(record)
    with _lock:
        sites = _read()
        sites[record["host"]] = record
        _write(sites)
    return record
