"""tests/test_local_agent_public_external_readonly_live_smoke_20260508.py

live smoke 스크립트의 정책/구조 검증 (외부 사이트 실제 접속 없음).
"""

import importlib
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# 스크립트 모듈 import (모듈로 로드 가능해야 함)
import importlib.util  # noqa: E402

_SCRIPT_PATH = Path(_REPO_ROOT) / "tools" / "smoke" / "local_agent_public_external_readonly_live_smoke.py"
_spec = importlib.util.spec_from_file_location("_lp_smoke", str(_SCRIPT_PATH))
assert _spec is not None and _spec.loader is not None, "모듈 spec 로드 실패: local_agent_public_external_readonly_live_smoke.py"
_smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_smoke)

_SAFE_FIELDS = [
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
]


# ── allowlist ──────────────────────────────────────────────────────────────


def test_allowlist_contains_three_sites():
    assert "https://example.com" in _smoke._ALLOWLIST
    assert "https://www.wikipedia.org" in _smoke._ALLOWLIST
    assert "https://www.python.org" in _smoke._ALLOWLIST


def test_allowlist_size_exactly_three():
    assert len(_smoke._ALLOWLIST) == 3


def test_is_allowlisted_example():
    assert _smoke._is_allowlisted("https://example.com") is True
    assert _smoke._is_allowlisted("https://example.com/") is True


def test_is_allowlisted_wikipedia():
    assert _smoke._is_allowlisted("https://www.wikipedia.org") is True


def test_is_allowlisted_python():
    assert _smoke._is_allowlisted("https://www.python.org") is True


def test_naver_not_allowlisted():
    assert _smoke._is_allowlisted("https://naver.com") is False


def test_g2b_not_allowlisted():
    assert _smoke._is_allowlisted("https://www.g2b.go.kr") is False


def test_kbstar_not_allowlisted():
    assert _smoke._is_allowlisted("https://obank.kbstar.com") is False


def test_localhost_not_allowlisted():
    """allowlist는 외부 공개 사이트만 — localhost는 별도 정책."""
    assert _smoke._is_allowlisted("http://localhost") is False


# ── allowlist 외 URL은 BLOCKED 반환 (실제 외부 접속 없음) ────────────────


def test_smoke_blocks_non_allowlisted_url():
    r = _smoke.smoke_one("https://malicious.example.com/")
    assert r["verdict"] == "BLOCKED_NOT_ALLOWLISTED"
    assert r["reachable"] is False
    for f in _SAFE_FIELDS:
        assert r.get(f) is False


def test_smoke_blocks_naver():
    r = _smoke.smoke_one("https://naver.com")
    assert r["verdict"] == "BLOCKED_NOT_ALLOWLISTED"


# ── 차단 액션 frozenset ────────────────────────────────────────────────────


def test_blocked_actions_login():
    assert "login" in _smoke._BLOCKED_LIVE_ACTIONS


def test_blocked_actions_password():
    assert "type_password" in _smoke._BLOCKED_LIVE_ACTIONS


def test_blocked_actions_submit():
    assert "submit_form" in _smoke._BLOCKED_LIVE_ACTIONS


def test_blocked_actions_cookie_export():
    assert "cookie_export" in _smoke._BLOCKED_LIVE_ACTIONS


def test_blocked_actions_session_export():
    assert "session_export" in _smoke._BLOCKED_LIVE_ACTIONS


def test_blocked_actions_storage_state_export():
    assert "storage_state_export" in _smoke._BLOCKED_LIVE_ACTIONS


def test_blocked_actions_token_export():
    assert "token_export" in _smoke._BLOCKED_LIVE_ACTIONS


def test_blocked_actions_payment():
    assert "payment" in _smoke._BLOCKED_LIVE_ACTIONS


def test_blocked_actions_bid():
    assert "bid_submit" in _smoke._BLOCKED_LIVE_ACTIONS


def test_blocked_actions_signature():
    assert "electronic_signature" in _smoke._BLOCKED_LIVE_ACTIONS


def test_blocked_actions_cert_password():
    assert "cert_password_input" in _smoke._BLOCKED_LIVE_ACTIONS


def test_blocked_actions_otp():
    assert "otp_input" in _smoke._BLOCKED_LIVE_ACTIONS


# ── 결과 sanitize ──────────────────────────────────────────────────────────


def test_sanitize_strips_unallowed_field():
    raw = {
        "url": "https://example.com",
        "title": "Example",
        "cookie_value": "secret",  # 허용 필드 아님
        "password_value": "p",  # 허용 필드 아님
        "raw_html": "<html>...</html>",
    }
    safe = _smoke._sanitize_result(raw)
    assert "cookie_value" not in safe
    assert "password_value" not in safe
    assert "raw_html" not in safe


def test_sanitize_safe_fields_always_false():
    raw = {"url": "https://example.com"}
    safe = _smoke._sanitize_result(raw)
    for f in _SAFE_FIELDS:
        assert safe.get(f) is False


def test_sanitize_redaction_applied_flag():
    raw = {"url": "https://example.com"}
    safe = _smoke._sanitize_result(raw)
    assert safe.get("redaction_applied") is True


def test_sanitize_keeps_allowed_fields():
    raw = {
        "url": "https://example.com",
        "title": "Example",
        "links_count": 5,
        "table_count": 0,
        "verdict": "OK_READONLY",
    }
    safe = _smoke._sanitize_result(raw)
    assert safe["url"] == "https://example.com"
    assert safe["title"] == "Example"
    assert safe["links_count"] == 5


# ── 차단 정책 분류기 ──────────────────────────────────────────────────────


def test_blocked_action_payloads_all_blocked_or_user_direct():
    payloads = _smoke._classify_blocked_action_payloads()
    for p in payloads:
        assert p["blocked_or_user_direct"] is True, f"FAIL: {p}"


# ── 서버 환경 감지 ────────────────────────────────────────────────────────


def test_is_local_execution_function_exists():
    assert callable(_smoke._is_local_execution)


# ── 스크립트 내 실제 외부 fetch 호출 부재 (정적 검사) ────────────────────


def test_script_no_requests_get():
    """스크립트에 requests.get/post/httpx 등 외부 fetch 직접 호출이 없어야 함."""
    with _SCRIPT_PATH.open(encoding="utf-8") as f:
        src = f.read()
    forbidden = ["requests.get", "requests.post", "httpx.get", "httpx.post", "urllib.request.urlopen"]
    for pat in forbidden:
        assert pat not in src, f"외부 fetch 직접 호출 발견: {pat}"


def test_script_uses_playwright():
    """live smoke는 playwright 사용 (LOCAL_PLAYWRIGHT 경로)."""
    with _SCRIPT_PATH.open(encoding="utf-8") as f:
        src = f.read()
    assert "from playwright.sync_api import sync_playwright" in src


def test_script_no_cookie_extraction():
    """쿠키/storage_state 추출 코드 없음."""
    with _SCRIPT_PATH.open(encoding="utf-8") as f:
        src = f.read()
    forbidden = ["context.cookies()", "page.cookies()", "context.storage_state()", ".storage_state()"]
    for pat in forbidden:
        assert pat not in src, f"쿠키/storage_state 추출 코드 발견: {pat}"


def test_script_no_screenshot_save():
    """screenshot 저장 코드 없음."""
    with _SCRIPT_PATH.open(encoding="utf-8") as f:
        src = f.read()
    assert ".screenshot(" not in src


def test_script_no_login_or_type_password():
    """로그인/패스워드 입력 코드 없음."""
    with _SCRIPT_PATH.open(encoding="utf-8") as f:
        src = f.read()
    forbidden = ["page.fill(", "page.type(", "page.locator(", "page.click("]
    # 단, 차단 정책의 _BLOCKED_LIVE_ACTIONS 정의 라인은 제외 — 액션 이름 문자열만
    for pat in forbidden:
        # query_selector_all은 read-only이므로 허용
        assert pat not in src, f"실행성 입력 코드 발견: {pat}"
