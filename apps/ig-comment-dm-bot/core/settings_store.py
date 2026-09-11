"""토큰(민감정보, keyring에 별도 저장)을 제외한 나머지 설정 — 계정 ID, 키워드 규칙,
DM 메시지, 폴링 간격/게시물 수 — 를 JSON 파일로 영속 저장한다.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from core.app_paths import get_data_dir
from core.keyword_matcher import KeywordRule

_SETTINGS_PATH = get_data_dir() / "settings.json"


def load_settings() -> dict[str, Any]:
    if not _SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(
    *,
    ig_user_id: str,
    rules: list[KeywordRule],
    dm_message: str,
    interval_minutes: int,
    media_limit: int,
) -> None:
    data = {
        "ig_user_id": ig_user_id,
        "rules": [asdict(r) for r in rules],
        "dm_message": dm_message,
        "interval_minutes": interval_minutes,
        "media_limit": media_limit,
    }
    _SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_rules() -> list[KeywordRule]:
    raw = load_settings().get("rules", [])
    return [KeywordRule(keyword=r["keyword"], match_type=r["match_type"]) for r in raw]
