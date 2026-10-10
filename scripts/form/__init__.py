"""scripts.form — 범용 폼 처리 패키지 (공용 유틸).

빠른 import:
    from scripts.form import (
        discover_form, universal_login,
        human_type, human_click, human_check,
        wait_field_ready, wait_value_settled, wait_submit_done,
        bot_scan, BotDetected,
        get_profile, set_profile, get_value,
        is_dry_run, enable_dry_run,
    )

드라이런: 환경변수 SITE_DRY_RUN=1 또는 enable_dry_run()
"""
from __future__ import annotations

import os

from scripts.form.discovery import discover_form, FormDiscovery, FormField
from scripts.form.personal_profile import (
    get_profile, set_profile, get_value, set_override, delete_field, list_fields,
)
from scripts.form.events import (
    wait_field_ready, wait_value_settled, wait_submit_done,
    wait_validation, wait_for_form,
)
from scripts.form.human import (
    human_type, human_click, human_check, hover_and_scroll, move_to_next,
)
from scripts.form.bot_radar import (
    scan as bot_scan, assert_not_blocked, BotRadar, BotDetected,
)
from scripts.form.orchestrator import universal_login


def is_dry_run() -> bool:
    return os.environ.get("SITE_DRY_RUN", "").strip() in ("1", "true", "TRUE", "yes")


def enable_dry_run() -> None:
    os.environ["SITE_DRY_RUN"] = "1"


def disable_dry_run() -> None:
    os.environ.pop("SITE_DRY_RUN", None)


__all__ = [
    "discover_form", "FormDiscovery", "FormField",
    "get_profile", "set_profile", "get_value", "set_override",
    "delete_field", "list_fields",
    "wait_field_ready", "wait_value_settled", "wait_submit_done",
    "wait_validation", "wait_for_form",
    "human_type", "human_click", "human_check", "hover_and_scroll", "move_to_next",
    "bot_scan", "assert_not_blocked", "BotRadar", "BotDetected",
    "universal_login",
    "is_dry_run", "enable_dry_run", "disable_dry_run",
]
