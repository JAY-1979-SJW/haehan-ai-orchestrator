"""사용자별 메뉴 설정 저장/로드.

settings/{user_id}.json 에 개인 메뉴 ON/OFF + 순서 저장.
역할(role)에 따라 접근 가능한 항목이 제한됨.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SETTINGS_DIR = Path(__file__).parent / "settings"

# 전체 메뉴 항목 정의
# (id, label, icon, min_role, default_visible)
# min_role: "any" = 모든 역할, "admin" = admin/owner만
ALL_MENU_ITEMS: list[dict[str, Any]] = [
    {"id": "chat",       "label": "대화",          "icon": "💬", "section": "AI 대화",   "min_role": "any",   "default": True},
    {"id": "task_queue", "label": "작업 큐",        "icon": "📋", "section": "AI 대화",   "min_role": "any",   "default": True},
    {"id": "approval",   "label": "승인 대기",      "icon": "✅", "section": "AI 대화",   "min_role": "any",   "default": True},
    {"id": "news",       "label": "뉴스",           "icon": "📰", "section": "업무 조회", "min_role": "any",   "default": True},
    {"id": "eum",             "label": "EUM 단말기",     "icon": "🏗️", "section": "업무 조회", "min_role": "admin", "default": True},
    {"id": "admin_dashboard", "label": "관리 대시보드",  "icon": "🖥️", "section": "관리 웹",   "min_role": "admin", "default": True},
    {"id": "admin_ops",       "label": "운영 현황",      "icon": "📊", "section": "관리 웹",   "min_role": "admin", "default": True},
    {"id": "admin_approvals", "label": "브라우저 승인",  "icon": "🔐", "section": "관리 웹",   "min_role": "admin", "default": True},
    {"id": "admin_agents",    "label": "로컬 에이전트",  "icon": "🤖", "section": "관리 웹",   "min_role": "admin", "default": True},
    {"id": "admin_filemap",   "label": "파일맵",         "icon": "🗂️", "section": "관리 웹",   "min_role": "admin", "default": False},
    {"id": "admin_cad",       "label": "CAD",            "icon": "📐", "section": "관리 웹",   "min_role": "admin", "default": False},
    {"id": "browser",         "label": "브라우저 상태",  "icon": "🌐", "section": "시스템",    "min_role": "admin", "default": True},
    {"id": "screenshot", "label": "최근 스크린샷",  "icon": "📸", "section": "시스템",    "min_role": "admin", "default": False},
    {"id": "logs",       "label": "로그",           "icon": "📊", "section": "시스템",    "min_role": "admin", "default": True},
]

_ADMIN_ROLES = {"admin", "owner"}


def _settings_path(user_id: str) -> Path:
    return _SETTINGS_DIR / f"{user_id}.json"


def _role_allowed(item_min_role: str, user_role: str) -> bool:
    if item_min_role == "any":
        return True
    return user_role in _ADMIN_ROLES


def load_menu(user_id: str, role: str) -> list[dict[str, Any]]:
    """사용자 메뉴 목록 반환.

    저장된 설정이 있으면 visible/order 적용,
    없으면 역할 기반 기본값 반환.
    """
    _SETTINGS_DIR.mkdir(exist_ok=True)
    path = _settings_path(user_id)

    saved: dict[str, Any] = {}
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("settings load error %s: %s", path, exc)

    saved_items: dict[str, dict] = {
        item["id"]: item for item in saved.get("items", [])
    }
    saved_order: list[str] = saved.get("order", [])

    # 역할 필터 적용
    allowed = [m for m in ALL_MENU_ITEMS if _role_allowed(m["min_role"], role)]

    # 저장된 순서 적용 (없는 항목은 뒤에 추가)
    order_map = {sid: i for i, sid in enumerate(saved_order)}
    allowed.sort(key=lambda m: order_map.get(m["id"], 9999))

    result = []
    for item in allowed:
        si = saved_items.get(item["id"], {})
        result.append({
            **item,
            "visible": si.get("visible", item["default"]),
        })
    return result


def save_menu(user_id: str, items: list[dict[str, Any]]) -> None:
    """사용자 메뉴 설정 저장 (visible + order)."""
    _SETTINGS_DIR.mkdir(exist_ok=True)
    data = {
        "order": [item["id"] for item in items],
        "items": [{"id": item["id"], "visible": item.get("visible", True)} for item in items],
    }
    path = _settings_path(user_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("menu settings saved: %s", path)
