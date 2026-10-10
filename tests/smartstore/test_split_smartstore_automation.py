"""도구 분리(smartstore 자동화) — 스마트스토어 자동화 모듈을 도구 폴더로 옮긴 뒤 옛 이중 경로가 없고 경로 값이 그대로인지 고정한다."""

from __future__ import annotations

import importlib
import importlib.util

from ai_orchestrator.paths import repo_root

MODS = ("analytics_dashboard", "competitor_analysis", "csv_import", "inventory_monitor", "order_automation")
NEW = "scripts.naver.smartstore.automation."


def test_old_duplicate_paths_removed():
    """옛 이중 경로(scripts/naver/automation/<모듈>.py 재수출 shim)는 지웠다 — 정본은 smartstore/automation 하나.

    workflow 는 이후 별도 리팩터(234a5a54, 부모↔자식 순환 해소)로 scripts/naver/workflow.py 로
    한 번 더 옮겨져 smartstore/automation 아래가 아니다 — 그 정본 경로로 확인한다.
    """
    for m in (*MODS, "review_automation"):
        assert importlib.util.find_spec("scripts.naver.automation." + m) is None
        assert importlib.import_module(NEW + m) is not None
    assert importlib.util.find_spec("scripts.naver.automation.workflow") is None
    assert importlib.util.find_spec("scripts.naver.smartstore.automation.workflow") is None
    assert importlib.import_module("scripts.naver.workflow") is not None


def test_root_constant_value_unchanged():
    """ROOT 는 이동 전부터 scripts 폴더(parents[3])였고, 같은 깊이로 옮겨 값이 같다."""
    scripts_dir = repo_root() / "scripts"
    for m in ("analytics_dashboard", "competitor_analysis"):
        assert importlib.import_module(NEW + m).ROOT == scripts_dir
