"""하나팩스 상태·주소록 그룹 조회 실패 처리 시험.

2026-10-04 앱 실검증: Playwright 브라우저가 없는 PC 에서 /hanafax/status 가 500 Internal Server Error,
/hanafax/address-groups 가 "주소록 그룹을 읽지 못했습니다: Error" 로 원인을 알 수 없었다.
실제 하나팩스 사이트·브라우저는 쓰지 않는다 — 로그인 함수를 가짜로 바꾼다.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from ai_orchestrator.connectors.hanafax import router

MISSING = "BrowserType.launch: Executable doesn't exist at C:\\x\\chrome-headless-shell.exe"


def test_status_returns_ok_false_with_install_hint_when_browser_missing(monkeypatch):
    import scripts.hanafax.auth as auth

    def boom():
        raise RuntimeError(MISSING)

    monkeypatch.setattr(auth, "test_login", boom)
    res = router.get_status(_={})  # 500 으로 터지지 않는다
    assert res.ok is False
    assert "설치" in res.message and "Playwright" in res.message


def test_status_generic_failure_names_the_error_type(monkeypatch):
    import scripts.hanafax.auth as auth

    monkeypatch.setattr(auth, "test_login", lambda: (_ for _ in ()).throw(ConnectionError("x")))
    res = router.get_status(_={})
    assert res.ok is False
    assert "ConnectionError" in res.message


def test_status_login_failure_contract_unchanged(monkeypatch):
    import scripts.hanafax.auth as auth

    monkeypatch.setattr(auth, "test_login", lambda: {"ok": False, "message": "로그인 필요"})
    res = router.get_status(_={})
    assert res.ok is False and res.message == "로그인 필요"


def test_address_groups_explains_missing_browser(monkeypatch):
    class _Svc:
        def list_site_groups(self):
            raise RuntimeError(MISSING)

    monkeypatch.setattr(router, "_auth_service", lambda: _Svc())
    with pytest.raises(HTTPException) as exc_info:
        router.address_groups(_={})
    assert exc_info.value.status_code == 502
    assert "설치" in exc_info.value.detail and exc_info.value.detail != "주소록 그룹을 읽지 못했습니다: Error"
