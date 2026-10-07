"""도구 분리(smartstore 자동화) — 스마트스토어 자동화 5개 모듈을 도구 폴더로 옮긴 뒤에도 옛 경로·공개 이름·경로 값이 그대로인지 고정한다."""

from __future__ import annotations

import importlib

from ai_orchestrator.paths import repo_root

MODS = ("analytics_dashboard", "competitor_analysis", "csv_import", "inventory_monitor", "order_automation")
OLD = "scripts.naver.automation.smartstore."
NEW = "scripts.naver.smartstore.automation."


def test_old_paths_alias_new_modules():
    for m in MODS:
        assert importlib.import_module(OLD + m) is importlib.import_module(NEW + m)


def test_compat_reexports_still_work():
    csv_old = importlib.import_module("scripts.naver.automation.csv_import")
    csv_new = importlib.import_module(NEW + "csv_import")
    assert csv_old.CSVImporter is csv_new.CSVImporter


def test_root_constant_value_unchanged():
    """ROOT 는 이동 전부터 scripts 폴더(parents[3])였고, 같은 깊이로 옮겨 값이 같다."""
    scripts_dir = repo_root() / "scripts"
    for m in ("analytics_dashboard", "competitor_analysis"):
        assert importlib.import_module(NEW + m).ROOT == scripts_dir
