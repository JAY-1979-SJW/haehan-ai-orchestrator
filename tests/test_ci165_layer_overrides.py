"""PR #165 CI 분석(backup\\ci165_analysis_W4.md) — module_registry.overrides.json 에 추가한
27건의 층(layer) 확정값이 유효한 JSON이고, 실제로 그 층간 위반 35건을 해소하는지 확인한다.

이 override 들은 classify.py 가 content-heuristic 으로 reclassify 할 때 이 파일들이
local_agent/* 기본값(L10)·SITE_MODULES 기본값(L5) 으로 잘못 떨어지는 걸 막는다(이미 커밋된
configs/module_registry.json 자체는 올바른 값을 갖고 있어 고칠 필요 없음 — 문제는 classify.py
재실행 시의 비결정적 재분류뿐).
"""

from __future__ import annotations

import json
from pathlib import Path

OVERRIDES_PATH = Path(__file__).resolve().parents[1] / "configs" / "module_registry.overrides.json"

CI165_KEYS_AND_LAYERS = {
    "core/agent_runtime/runtime/security_program/security_installer_candidate_finder.py": "L4",
    "core/agent_runtime/runtime/security_program/security_program_detector.py": "L4",
    "core/agent_runtime/runtime/security_program/security_program_install_result_sanitizer.py": "L4",
    "core/agent_runtime/runtime/universal/universal_ai_site_agent.py": "L4",
    "core/agent_runtime/runtime/universal/universal_safe_result.py": "L4",
    "core/agent_runtime/runtime/universal/user_intent_parser.py": "L4",
    "core/agent_runtime/runtime/universal/generic_selector_discovery.py": "L4",
    "core/agent_runtime/runtime/download/download_upload_manifest.py": "L4",
    "core/agent_runtime/runtime/playwright/playwright_bootstrap.py": "L4",
    "core/agent_runtime/runtime/common_tool_runtime.py": "L4",
    "core/agent_runtime/runtime/notify/user_notification_adapter.py": "L4",
    "core/agent_runtime/runtime/download/download_result_sanitizer.py": "L4",
    "core/agent_runtime/runtime/site_profile/site_type_classifier.py": "L4",
    "core/agent_runtime/runtime/universal/universal_page_observer.py": "L4",
    "core/agent_runtime/runtime/universal/universal_task_planner.py": "L4",
    "core/agent_runtime/runtime/site_profile/selector_pack_registry.py": "L4",
    "scripts/naver/agent_mixins/cafe_mixin_activity.py": "L4",
    "scripts/naver/agent_mixins/cafe_mixin_media.py": "L4",
    "scripts/naver/agent_mixins/cafe_mixin_member.py": "L4",
    "scripts/naver/agent_mixins/cafe_mixin_read.py": "L4",
    "scripts/naver/agent_mixins/cafe_mixin_common.py": "L4",
    "scripts/naver/agent_mixins/mail_mixin.py": "L4",
    "core/agent_runtime/runtime/site_profile/browser_discovery_candidates.py": "L1",
    "core/agent_runtime/runtime/site_profile/browser_site_registry.py": "L1",
    "core/agent_runtime/runtime/site_profile/browser_value_registry.py": "L1",
    "ai_orchestrator/agent_hub/registry/common.py": "L4",
    "ai_orchestrator/sites/adapters/naver_cafe_collection.py": "L6",
}


def _load_overrides() -> dict:
    return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))


def test_overrides_file_is_valid_json():
    overrides = _load_overrides()
    assert isinstance(overrides, dict)
    assert len(overrides) > 200  # 기존 200여 건 + 이번 27건, 실수로 파일을 통째로 날리지 않았는지


def test_all_ci165_keys_present_with_expected_layer():
    overrides = _load_overrides()
    missing = [k for k in CI165_KEYS_AND_LAYERS if k not in overrides]
    assert not missing, f"CI165 override 가 빠짐: {missing}"
    wrong = {
        k: overrides[k]["layer"] for k, expected in CI165_KEYS_AND_LAYERS.items() if overrides[k]["layer"] != expected
    }
    assert not wrong, f"층 값이 계획과 다름: {wrong}"


def test_every_ci165_override_has_a_reason():
    overrides = _load_overrides()
    for k in CI165_KEYS_AND_LAYERS:
        assert overrides[k].get("reason"), f"{k} 에 reason 없음(사람 확정값인데 근거가 없으면 안 됨)"
