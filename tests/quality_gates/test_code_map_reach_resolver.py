"""코드맵 import 해석기(scripts/ops/code_map/reach.Resolver) — 이름이 겹치는 모듈/패키지의 해석 우선순위.

결함 #114: `from local_agent import site_entry_policy` 가 루트 `local_agent/` 패키지가 아니라 같은 이름의 `core/agent_runtime/runtime/local_agent.py` 로
해석돼 가짜 층간 위반을 만들었다. `from X import Y` 의 `Y` 가 서브모듈로 풀리는 위치를 먼저 쓰도록 고쳤다.
합성 파일 목록만 사용한다(저장소 지도·파일시스템 불필요).
"""

from __future__ import annotations

from tools.code_map.reach import Resolver

# 이 저장소의 실제 충돌 배치를 그대로 본뜬 파일 목록
FILES = [
    "local_agent/__init__.py",
    "local_agent/agent.py",
    "core/agent_runtime/__init__.py",
    "core/agent_runtime/agent.py",
    "core/agent_runtime/runtime/local_agent.py",
    "scripts/local_agent.py",
    "scripts/core/agent_runtime/__init__.py",
    "scripts/local_agent/router.py",
    "scripts/site_engine/login_session.py",
    "scripts/google/auth.py",
    "scripts/common/logger.py",
    "logger.py",
    "ai_orchestrator/core/agent_runtime/__init__.py",
    "ai_orchestrator/local_agent/actions.py",
    "ai_orchestrator/tests/test_x.py",
    "ai_orchestrator/agent_hub/registry/facade.py",
]


def resolve(rel, module, names=(), level=0):
    return Resolver(FILES).resolve_import(rel, module, level, tuple(names))


def test_from_import_prefers_the_location_where_the_name_is_a_submodule():
    targets, status = resolve("scripts/site_engine/login_session.py", "local_agent", ["agent"])
    assert status == "internal"
    assert "local_agent/agent.py" in targets  # 루트 패키지의 서브모듈
    assert "scripts/local_agent.py" not in targets  # 같은 이름의 scripts 모듈이 아니다
    assert "core/agent_runtime/runtime/local_agent.py" not in targets  # 같은 이름의 core 모듈도 아니다


def test_the_same_holds_for_other_submodules_of_the_root_package():
    targets, _ = resolve("scripts/google/auth.py", "local_agent", ["agent"])
    assert "local_agent/agent.py" in targets
    assert "scripts/local_agent.py" not in targets
    assert "core/agent_runtime/runtime/local_agent.py" not in targets


def test_without_a_matching_submodule_the_nearest_base_still_wins():
    """이름이 서브모듈이 아니면(예: 클래스·함수) 기존 순서(가까운 폴더 먼저)를 유지한다."""
    targets, status = resolve("scripts/site_engine/login_session.py", "local_agent", ["SomeClass"])
    assert status == "internal" and "scripts/local_agent.py" in targets
    assert "local_agent/agent.py" not in targets


def test_plain_import_statement_is_unchanged():
    targets, _ = resolve("scripts/site_engine/login_session.py", "local_agent")
    assert "scripts/local_agent.py" in targets  # 하위 이름이 없는 `import local_agent` 는 기존대로


def test_sub_roots_keep_resolving_to_their_own_package():
    """ai_orchestrator 안의 파일은 가까운 ai_orchestrator/local_agent 를 계속 쓴다(루트 우선으로 바꾸면 깨진다)."""
    targets, _ = resolve("ai_orchestrator/tests/test_x.py", "local_agent", ["actions"])
    assert "ai_orchestrator/local_agent/actions.py" in targets
    assert "core/agent_runtime/agent.py" not in targets


def test_relative_imports_are_not_affected():
    targets, status = resolve("scripts/local_agent/router.py", "", ["router"], level=1)
    assert status == "internal" and "scripts/local_agent/router.py" in targets


def test_absolute_module_without_submodule_names_keeps_nearest_first_for_logger():
    targets, _ = resolve("scripts/common/op_log.py", "logger", ["get_logger"])
    assert targets == ["scripts/common/logger.py"]


def test_standard_library_and_third_party_stay_external():
    assert resolve("scripts/site_engine/login_session.py", "json", ["loads"])[1] == "external"
    assert resolve("scripts/google/auth.py", "google.oauth2.credentials", ["Credentials"])[1] == "external"
