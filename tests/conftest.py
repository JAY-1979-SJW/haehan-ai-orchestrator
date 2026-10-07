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
