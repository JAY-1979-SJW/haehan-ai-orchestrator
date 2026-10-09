"""local_agent 사이트 게이트 테스트 — _site_allowed (P1-4).

L11. enabled_sites 비면 제한 없음(기존/owner 보존), 값 있으면 해당 사이트 tool만 허용.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("la_mod", _ROOT / "core" / "agent_runtime" / "runtime" / "local_agent.py")
assert _spec is not None and _spec.loader is not None, "모듈 spec 로드 실패: core/agent_runtime/runtime/local_agent.py"
la = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(la)


def test_no_restriction_when_empty():
    assert la._site_allowed("collect_products", None) is True
    assert la._site_allowed("collect_products", set()) is True


def test_enabled_site_allows_its_tools():
    assert la._site_allowed("collect_products", {"naver"}) is True
    assert la._site_allowed("open_seller_center", {"naver"}) is True


def test_disabled_site_blocks_tools():
    assert la._site_allowed("collect_products", {"gabia"}) is False
    assert la._site_allowed("collect_orders", {"google"}) is False


def test_unknown_tool_always_allowed():
    # 매핑에 없는 tool 은 제한 대상 아님(신규 tool 비차단)
    assert la._site_allowed("some_new_tool", {"naver"}) is True
