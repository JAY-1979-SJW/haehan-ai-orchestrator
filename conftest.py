"""Pytest runtime defaults for local and deployment gates."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.common.runtime_temp import usable_temp_base

_SESSION_MP = None


def _pytest_base(kind: str = "pytest_runtime") -> Path:
    return usable_temp_base(kind, "HAEHAN_PYTEST_TEMP")


def _isolate_dotenv_override() -> None:
    """`.env` 가 시험이 지정한 환경변수를 덮어쓰지 못하게 `load_dotenv` 의 override 를 항상 끈다.

    `ai_orchestrator.core.config` 는 import(=시험의 importlib.reload)마다 `load_dotenv(override=True)` 를 불러 상위 폴더의
    `.env` 로 환경변수를 덮어쓴다. 개발 PC 의 `.env` 에 `HTTP_USERS_PATH=` 처럼 빈 값이 있으면, 시험이 방금 지정한
    사용자 파일 경로가 빈 값으로 돌아가 인증 시험이 401 로 실패하고, `.env` 가 없는 CI·깨끗한 복사본에서는 통과했다
    (2026-10-04 실측: 같은 시험이 폴더 위치에 따라 실패/통과, 단독 실행 기준 32건). `.env` 로 빈 값을 채우는 동작은 그대로 둔다.
    """
    import dotenv

    if getattr(dotenv.load_dotenv, "_haehan_no_override", False):
        return
    original = dotenv.load_dotenv

    def load_dotenv_without_override(*args, **kwargs):
        kwargs["override"] = False
        return original(*args, **kwargs)

    load_dotenv_without_override._haehan_no_override = True  # type: ignore[attr-defined]
    dotenv.load_dotenv = load_dotenv_without_override


def pytest_configure(config):
    """Force Python tempfile users under a verified runtime temp base."""
    base = _pytest_base()
    for key in ("TMP", "TEMP", "TMPDIR"):
        os.environ[key] = str(base)
    tempfile.tempdir = str(base)
    _isolate_dotenv_override()
    # 시험 프로세스도 하나의 진입점이다 — 사이트 로그인 등록표를 설치한다(진입점이 install 을 빠뜨리면 get_site 가 RuntimeError).
    from scripts.entry import site_login_registry

    site_login_registry.install()
    # 수집(import) 시점에 브라우저에 접속하는 모듈 최상위 코드(tests/integration/manual/test_context.py 등)도 막도록 세션 전체에 설치한다.
    global _SESSION_MP
    from tests.cdp_port_guard import install_guard

    _SESSION_MP = pytest.MonkeyPatch()
    install_guard(_SESSION_MP)


def pytest_unconfigure(config):
    if _SESSION_MP is not None:
        _SESSION_MP.undo()


@pytest.fixture(autouse=True)
def _block_local_cdp_port(monkeypatch):
    """사용자의 로그인된 Chrome(127.0.0.1:9222)에 시험이 접속하지 못하게 막는다(우회: HAEHAN_ALLOW_REAL_CDP=1)."""
    from tests.cdp_port_guard import install_guard

    install_guard(monkeypatch)


def pytest_collection_modifyitems(config, items):
    """실제 9222 Chrome 에 접속하는 시험은 기본 skip(HAEHAN_ALLOW_REAL_CDP=1 일 때만 실행)."""
    from tests.cdp_port_guard import SKIP_REASON, apply_real_cdp_skips

    apply_real_cdp_skips(items, pytest.mark.skip(reason=SKIP_REASON))


@pytest.fixture
def tmp_path(request) -> Path:
    """Replacement tmp_path that avoids pytest basetemp cleanup on Windows."""
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in request.node.name)[:80]
    path = _pytest_base("pytest_tmp_path") / f"{safe_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolate_runtime_state(monkeypatch, tmp_path):
    """테스트가 실제 사용자 상태 파일을 지우거나 덮어쓰지 못하게 임시 경로로 돌린다.

    local_agent_registry_common.clear() 는 data/local_agent_registry_state.json(실제로 등록된
    로컬 에이전트)을 unlink 하는데, test_local_agent*.py 등 일부 테스트가 경로를 돌리지 않고
    clear() 를 불러 개발 PC 의 에이전트 등록이 테스트를 돌릴 때마다 사라졌다(2026-09-30 실측:
    서버 재기동 후 에이전트가 4401 BAD_CREDENTIALS 로 거부). 개별 테스트가 같은 값을 다시
    monkeypatch 하면 그쪽이 우선한다.
    """
    targets = (
        ("ai_orchestrator.agent_hub.registry.common", "_REGISTRY_STATE_PATH", "local_agent_registry_state.json"),
        ("ai_orchestrator.tasks.chat_sessions", "_STORE_PATH", "chat_sessions.json"),
    )
    # 마스터 키는 기본이 OS 자격 증명 관리자(keyring)다. 테스트가 이 PC 의 진짜 키를 만들거나 건드리지
    # 않도록 파일 방식으로 강제한다(키 보관 자체를 시험하는 테스트는 이 값을 스스로 바꾼다).
    monkeypatch.setenv("HAEHAN_CRED_KEY_BACKEND", "file")
    # 저장소가 첫 로드 때 흡수하는 평문 레거시 파일(data/.env_naver)도 실제 위치를 읽지 못하게 한다.
    try:
        from scripts.auth import credentials as _cred

        monkeypatch.setattr(_cred, "_LEGACY_ENV_FILES", {"naver": tmp_path / ".env_naver_legacy"})
    except Exception:  # noqa: BLE001, S110 - scripts.auth.credentials 를 import 못 하는 환경은 격리 대상 아님
        pass
    for module_name, attr, filename in targets:
        try:
            module = __import__(module_name, fromlist=[attr])
        except Exception:  # noqa: BLE001, S112 - 해당 모듈을 import 못 하는 환경(일부 CI/스크립트 테스트)은 격리 대상 아님
            continue
        monkeypatch.setattr(module, attr, tmp_path / filename)
