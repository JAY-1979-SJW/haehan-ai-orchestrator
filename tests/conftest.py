"""tests/ 공용 픽스처 — 격리된 헤드리스 Chrome(외부 접속·사용자 9222 브라우저 없음).

`browser` 는 모듈 범위이며 이 픽스처를 쓰는 시험만 Chrome 을 띄운다. 못 띄우는 환경에서는 그 시험만 건너뛴다.
(각 시험 파일이 같은 픽스처를 복사해 두던 것을 한곳으로 모았다 — audit-kit DUP-02.)
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    pw = sync_api.sync_playwright().start()
    try:
        instance = pw.chromium.launch(channel="chrome", headless=True)
    except Exception as exc:  # noqa: BLE001 - Chrome 을 못 띄우는 환경은 이 시험만 건너뛴다
        pw.stop()
        pytest.skip(f"헤드리스 Chrome 을 띄울 수 없음: {type(exc).__name__}")
    yield instance
    instance.close()
    pw.stop()


@pytest.fixture(autouse=True)
def _no_real_preflight():
    """사이트 등록의 사전 조사(robots.txt 조회) 실행기는 운영에서만 연결한다 — 시험은 기본으로 끄고, 필요한 시험이 직접 가짜를 넣는다."""
    from ai_orchestrator.site_work import site_preflight_service

    site_preflight_service.configure_fetcher(None)
    yield
    site_preflight_service.configure_fetcher(None)


def _is_cdp_launch(args) -> bool:
    """파이썬으로 cdp_daemon.py 를 실행하거나, 원격 디버깅 포트 옵션으로 브라우저를 띄우는 호출만 잡는다(git show <경로> 같은 파일명 언급은 통과)."""
    parts = [str(a).replace("\\", "/") for a in (args if isinstance(args, (list, tuple)) else str(args).split())]
    if not parts:
        return False
    runs_python = parts[0].rsplit("/", 1)[-1].lower().startswith(("python", "pythonw", "py."))
    return (runs_python and any(p.rsplit("/", 1)[-1] == "cdp_daemon.py" for p in parts[1:])) or any(
        p.startswith("--remote-debugging-port") for p in parts
    )


@pytest.fixture(autouse=True)
def _no_real_cdp_daemon(monkeypatch):
    """시험이 실제 CDP 데몬·Chrome(원격 디버깅 포트)을 띄우지 못하게 막는다.

    2026-10-08 사고: naver/cafe 시험이 connection 의 자동 기동 경로(_ensure_cdp_daemon)로 pythonw cdp_daemon 을 띄워
    대표님이 Chrome 을 닫아도 계속 다시 떴다. 필요한 시험은 Popen 을 직접 가짜로 바꾸면 이 보호보다 우선한다.
    """
    import subprocess

    real_popen = subprocess.Popen

    class _GuardedPopen(real_popen):  # type: ignore[valid-type, misc]
        def __init__(self, args, *a, **kw):
            if _is_cdp_launch(args):
                raise RuntimeError(f"시험에서 실제 CDP 데몬/Chrome 기동 금지(Popen 을 가짜로 바꾸세요): {args!r}"[:300])
            super().__init__(args, *a, **kw)

    monkeypatch.setattr(subprocess, "Popen", _GuardedPopen)
def apply_basic_auth_users(mp, users_path) -> None:
    """AUTH_ENABLED=true + HTTP_USERS_PATH 를 환경변수로 설정한다.

    **호출 뒤 `ai_orchestrator.core.config` 를 `importlib.reload()` 해야 반영된다** — config 가 import
    시점에 환경변수를 읽어 모듈 상수로 고정하기 때문이다. 환경변수 방식을 쓰는 이유: 같은 파일의 다른
    fixture(예: 함수 범위 `_isolated_logdir`)가 독립적으로 `config` 를 reload 해도 그 reload 역시 같은
    환경변수를 다시 읽으므로 값이 유지된다 — `monkeypatch.setattr(config, "AUTH_ENABLED", ...)` 처럼
    속성만 바꾸면 그런 독립적인 reload 한 번에 값이 날아간다(2026-10-08 B11 이동 중 실제로 겪음).

    **`tools.gates.auth` 자체는 절대 reload 하지 않는다** — `gates.auth` 는
    `config.AUTH_ENABLED`·`config.HTTP_USERS_PATH` 를 호출마다 모듈 참조로 live 읽으므로 reload 가 필요
    없다. `importlib.reload(tools.gates.auth)` 로 켜고 끄던 옛 방식은 두 가지를 깨뜨렸다:
    ① reload 가 `get_current_user` 를 새 함수 객체로 만들어, 이미 import 돼 있는 라우터는 옛 객체에
    묶인 채 남는다 — 그 뒤 시험이 새 객체로 건 `dependency_overrides` 가 라우터에 안 닿아
    `AUTH_ENABLED=False` 의 고정 owner 로 통과한 것처럼 보였다. ② reload 가 `register_bearer_resolver`
    로 등록된 Bearer 토큰 검증기(`_bearer_resolver`)를 `None` 으로 되돌리는데, 등록을 다시 실행하는
    `ai_orchestrator.auth.user_auth_router` 는 보통 같이 reload 되지 않아 등록이 복구되지 않았다 —
    이후 세션의 모든 Bearer JWT 인증이 401 로 깨졌다(한 세션에서 재현: 새 시험 하나 +
    `test_console_api_contract_*.py` 조합으로 57건 무더기 실패).

    `mp` 는 함수 범위 `monkeypatch` fixture 또는 모듈 범위 fixture 안에서 직접 만든
    `pytest.MonkeyPatch()` 인스턴스(끝에 `.undo()` 로 직접 해제) 둘 다 받는다.
    """
    mp.setenv("AUTH_ENABLED", "true")
    mp.setenv("HTTP_USERS_PATH", str(users_path))
