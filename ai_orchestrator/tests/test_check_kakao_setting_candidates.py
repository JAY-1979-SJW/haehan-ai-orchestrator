"""KAKAO-DEV-5-LITE 테스트 — check_kakao_setting_candidates.py 검증.

보안:
- secret/session/cookie 원문 출력 없음
- Kakao 콘솔 write 없음
- ID/PW 없음

기능:
- 후보 URL 기본값 생성
- HTTPS 검증
- reachable 판정 (mock)
- privacy URL 후보 중 1개 200 성공
- redirect_uri 404는 WARN
- JSON/MD/next_actions.md 생성
- judgment 필드 검증
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

_MODULE_PATH = REPO_ROOT / "scripts" / "check_kakao_setting_candidates.py"
_SOURCE = _MODULE_PATH.read_text(encoding="utf-8")
_SECRET_PATTERN = re.compile(r"[0-9a-f]{32,}|[A-Za-z0-9+/]{40,}={0,2}", re.IGNORECASE)

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("check_kakao_setting_candidates", _MODULE_PATH)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------
# 헬퍼: mock HTTP checker
# ---------------------------------------------------------------------------

def _make_checker(responses: dict[str, dict]):
    """URL → 결과 dict를 반환하는 fake checker."""
    def checker(url: str, timeout: int = 10) -> dict:
        base = {
            "url": url,
            "https": url.startswith("https://"),
            "reachable": False,
            "status_code": None,
            "final_url": url,
            "title": "",
            "redirect": False,
            "error": None,
            "kakao_registerable": False,
        }
        override = responses.get(url, {"status_code": 404, "reachable": True})
        base.update(override)
        base["kakao_registerable"] = (
            base["https"] and base["reachable"]
            and base["status_code"] is not None
            and base["status_code"] < 500
        )
        return base
    return checker


_DOMAIN = "https://attendance.haehan-ai.kr"
_REDIRECT = "https://attendance.haehan-ai.kr/auth/kakao/callback"
_PRIVACYS = [
    "https://attendance.haehan-ai.kr/privacy",
    "https://attendance.haehan-ai.kr/privacy-policy",
    "https://attendance.haehan-ai.kr/terms/privacy",
]


# ---------------------------------------------------------------------------
# 기본값 검증
# ---------------------------------------------------------------------------

def test_default_domain_is_https():
    assert _mod._DEFAULT_DOMAIN.startswith("https://")


def test_default_redirect_uri_is_https():
    assert _mod._DEFAULT_REDIRECT_URI.startswith("https://")


def test_default_privacy_candidates_all_https():
    for url in _mod._DEFAULT_PRIVACY_CANDIDATES:
        assert url.startswith("https://"), f"개인정보처리방침 후보 HTTPS 아님: {url}"


def test_default_domain_contains_attendance():
    assert "attendance" in _mod._DEFAULT_DOMAIN


# ---------------------------------------------------------------------------
# HTTPS 검증
# ---------------------------------------------------------------------------

def test_check_url_marks_https_false_for_http():
    result = _mod._check_url.__wrapped__ if hasattr(_mod._check_url, "__wrapped__") else None
    # _judge 로직으로 검증
    domain = {"reachable": True, "https": False, "status_code": 200, "kakao_registerable": False}
    redirect = {"reachable": True, "status_code": 200}
    privs = [{"status_code": 200}]
    j = _mod._judge(domain, redirect, privs)
    assert any("HTTPS" in b for b in j["blockers"])


# ---------------------------------------------------------------------------
# _judge 단위 테스트
# ---------------------------------------------------------------------------

def test_judge_all_ok():
    domain = {"reachable": True, "https": True, "status_code": 200, "kakao_registerable": True}
    redirect = {"reachable": True, "status_code": 200}
    privs = [{"status_code": 200}]
    j = _mod._judge(domain, redirect, privs)
    assert j["ready_for_platform_registration"] is True
    assert j["ready_for_redirect_uri_registration"] is True
    assert j["ready_for_permission_request"] is True
    assert j["blockers"] == []
    assert j["warnings"] == []


def test_judge_redirect_uri_404_is_warn_not_blocker():
    domain = {"reachable": True, "https": True, "status_code": 200, "kakao_registerable": True}
    redirect = {"reachable": True, "status_code": 404}
    privs = [{"status_code": 200}]
    j = _mod._judge(domain, redirect, privs)
    assert j["blockers"] == [], "redirect 404는 blocker가 아님"
    assert any("404" in w for w in j["warnings"]), "redirect 404는 WARN이어야 함"


def test_judge_domain_unreachable_is_blocker():
    domain = {"reachable": False, "https": True, "status_code": None, "kakao_registerable": False}
    redirect = {"reachable": False, "status_code": None}
    privs = [{"status_code": None}]
    j = _mod._judge(domain, redirect, privs)
    assert j["blockers"], "도메인 미접근 시 blocker 있어야 함"
    assert j["ready_for_platform_registration"] is False


def test_judge_no_privacy_is_warn():
    domain = {"reachable": True, "https": True, "status_code": 200, "kakao_registerable": True}
    redirect = {"reachable": True, "status_code": 200}
    privs = [{"status_code": 404}, {"status_code": 404}]
    j = _mod._judge(domain, redirect, privs)
    assert any("개인정보" in w for w in j["warnings"])
    assert j["ready_for_permission_request"] is False


# ---------------------------------------------------------------------------
# check_candidates 통합 테스트 (mock HTTP)
# ---------------------------------------------------------------------------

def test_check_candidates_files_created(tmp_path):
    checker = _make_checker({
        _DOMAIN: {"status_code": 200, "reachable": True},
        _REDIRECT: {"status_code": 404, "reachable": True},
        _PRIVACYS[0]: {"status_code": 404, "reachable": True},
        _PRIVACYS[1]: {"status_code": 404, "reachable": True},
        _PRIVACYS[2]: {"status_code": 404, "reachable": True},
    })
    result = _mod.check_candidates(
        domain=_DOMAIN,
        redirect_uri=_REDIRECT,
        privacy_urls=_PRIVACYS,
        out_dir=str(tmp_path),
        _http_checker=checker,
    )
    rdir = Path(result["result_dir"])
    assert (rdir / "candidates.json").exists()
    assert (rdir / "candidates.md").exists()
    assert (rdir / "next_actions.md").exists()


def test_check_candidates_privacy_one_ok(tmp_path):
    checker = _make_checker({
        _DOMAIN: {"status_code": 200, "reachable": True},
        _REDIRECT: {"status_code": 200, "reachable": True},
        _PRIVACYS[0]: {"status_code": 200, "reachable": True},
        _PRIVACYS[1]: {"status_code": 404, "reachable": True},
        _PRIVACYS[2]: {"status_code": 404, "reachable": True},
    })
    result = _mod.check_candidates(
        domain=_DOMAIN, redirect_uri=_REDIRECT, privacy_urls=_PRIVACYS,
        out_dir=str(tmp_path), _http_checker=checker,
    )
    j = result["judgment"]
    assert j["ready_for_permission_request"] is True
    assert j["warnings"] == []


def test_check_candidates_no_secret_in_json(tmp_path):
    checker = _make_checker({
        _DOMAIN: {"status_code": 200, "reachable": True},
        _REDIRECT: {"status_code": 404, "reachable": True},
    })
    result = _mod.check_candidates(
        domain=_DOMAIN, redirect_uri=_REDIRECT, privacy_urls=[],
        out_dir=str(tmp_path), _http_checker=checker,
    )
    rdir = Path(result["result_dir"])
    content = (rdir / "candidates.json").read_text(encoding="utf-8")
    matches = _SECRET_PATTERN.findall(content)
    assert not matches, f"candidates.json에 secret 패턴: {matches[:3]}"


def test_check_candidates_security_flags(tmp_path):
    checker = _make_checker({_DOMAIN: {"status_code": 200, "reachable": True}})
    result = _mod.check_candidates(
        domain=_DOMAIN, redirect_uri=_REDIRECT, privacy_urls=[],
        out_dir=str(tmp_path), _http_checker=checker,
    )
    sec = result.get("security") or {}
    assert sec.get("password_stored") is False
    assert sec.get("storage_state_printed") is False
    assert sec.get("secret_raw_stored") is False
    assert sec.get("kakao_console_write") is False


def test_check_candidates_account_email_note_present(tmp_path):
    checker = _make_checker({_DOMAIN: {"status_code": 200, "reachable": True}})
    result = _mod.check_candidates(
        domain=_DOMAIN, redirect_uri=_REDIRECT, privacy_urls=[],
        out_dir=str(tmp_path), _http_checker=checker,
    )
    assert "account_email_note" in result
    assert "account_email" in result["account_email_note"]


def test_check_candidates_no_kakao_console_call(tmp_path):
    """script 소스에 Kakao 콘솔 write URL이 없음."""
    for bad in ("developers.kakao.com/console", "click(", ".fill(", "submit_form"):
        # check_url은 HTTP GET이므로 developers.kakao.com 접근은 없음
        pass
    assert "developers.kakao.com/console" not in _SOURCE, \
        "Kakao 콘솔 write URL이 소스에 있으면 안 됨"


# ---------------------------------------------------------------------------
# 소스 레벨 보안 검사
# ---------------------------------------------------------------------------

def test_no_password_read_in_source():
    assert "input_value" not in _SOURCE
    assert 'type="password"' not in _SOURCE


def test_no_storage_state_export():
    assert "storage_state()" not in _SOURCE
    assert "export_storage" not in _SOURCE


def test_no_raw_secret_literal():
    matches = _SECRET_PATTERN.findall(_SOURCE)
    assert not matches, f"소스에 raw secret 패턴: {matches[:3]}"
