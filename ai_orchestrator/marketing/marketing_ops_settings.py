"""마케팅 운영실(marketing_ops) 기능 스위치 — 저장: data/marketing_ops/settings.json.

기본값은 꺼짐(enabled=False). 대표님 결정(2026-10-07, ROOT_FIX_ORDERS.md
"추가 배정 → W2 — 마케팅 운영 연결"): marketing_ops_router를 include하되
사용자가 설정에서 켜야 동작.

쓰기는 임시 파일 → os.replace(원자적) — ai_orchestrator/persistence/
site_registry_store.py 와 같은 패턴. licenses.json 비원자적 쓰기로 파일이
깨져 앱이 멈춘 사고가 있어(이 저장소 교훈) community_router의
notify_toggle save_config(직접 write_text, 비원자적) 패턴은 그대로 쓰지
않음. 파일이 깨졌을 때는 꺼짐(False)으로 처리한다.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from ai_orchestrator.paths.runtime import data_dir

_FILE = data_dir() / "marketing_ops" / "settings.json"
_lock = threading.Lock()

_DEFAULT: dict[str, Any] = {"enabled": False}


def load_settings() -> dict[str, Any]:
    if not _FILE.exists():
        return dict(_DEFAULT)
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(_DEFAULT)  # 파일이 깨졌을 때는 꺼짐으로 처리
    if not isinstance(data, dict) or not isinstance(data.get("enabled"), bool):
        return dict(_DEFAULT)
    return {"enabled": data["enabled"]}


def is_enabled() -> bool:
    return load_settings()["enabled"]


def save_settings(enabled: bool) -> dict[str, Any]:
    settings = {"enabled": bool(enabled)}
    with _lock:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=_FILE.parent, prefix=".settings.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                json.dump(settings, fp, ensure_ascii=False, indent=2)
            os.replace(tmp, _FILE)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    return settings
