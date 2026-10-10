"""도구 분리(smartstore 자동화) — 스마트스토어 자동화 5개 모듈을 도구 폴더로 옮긴 뒤에도 공개 이름·경로 값이 그대로인지 고정한다.

옛 경로(scripts.naver.automation.*) 재수출 shim 은 b7d96230(W9, 호출처 없음 확인)으로
의도적으로 삭제됐다 — 그 shim 을 대상으로 하던 test_compat_reexports_still_work 도 함께 뺐다.
"""

from __future__ import annotations

import importlib

from ai_orchestrator.paths import repo_root

MODS = ("analytics_dashboard", "competitor_analysis", "csv_import", "inventory_monitor", "order_automation")
NEW = "scripts.naver.smartstore.automation."


def test_root_constant_value_unchanged():
    """ROOT 는 이동 전부터 scripts 폴더(parents[3])였고, 같은 깊이로 옮겨 값이 같다."""
    scripts_dir = repo_root() / "scripts"
    for m in ("analytics_dashboard", "competitor_analysis"):
        assert importlib.import_module(NEW + m).ROOT == scripts_dir
