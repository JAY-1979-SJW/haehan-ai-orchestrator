"""F-4S-8d 정적 검사 + unit 테스트 — 실제 브라우저 실행 없음."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parent.parent.parent
_PREFLIGHT = _ROOT / "scripts" / "preflight_internal_recording_target.py"
_SMOKE = _ROOT / "scripts" / "smoke_web_recording_internal_url.py"

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.preflight_internal_recording_target import (
    _is_internal_host,
    _detect_login,
    _coerce_allow_hosts,
    check_url,
    run_preflight,
)


# ---------------------------------------------------------------------------
# preflight 정적 검사
# ---------------------------------------------------------------------------


def test_preflight_script_exists():
    assert _PREFLIGHT.exists()


def test_smoke_script_exists():
    assert _SMOKE.exists()


# ---------------------------------------------------------------------------
# preflight 단위 테스트
# ---------------------------------------------------------------------------


def test_default_allow_hosts_include_loopback():
    hosts = _coerce_allow_hosts(None)
    assert "127.0.0.1" in hosts
    assert "localhost" in hosts
    assert "::1" in hosts


def test_custom_allow_host_merged():
    hosts = _coerce_allow_hosts(["192.168.1.10"])
    assert "192.168.1.10" in hosts
    assert "127.0.0.1" in hosts


def test_internal_host_localhost_allowed():
    hosts = _coerce_allow_hosts(None)
    assert _is_internal_host("http://localhost:3000/", hosts) is True


def test_internal_host_127_allowed():
    hosts = _coerce_allow_hosts(None)
    assert _is_internal_host("http://127.0.0.1:8765/", hosts) is True


def test_internal_host_naver_blocked():
    hosts = _coerce_allow_hosts(None)
    assert _is_internal_host("https://naver.com", hosts) is False


def test_internal_host_youtube_blocked():
    hosts = _coerce_allow_hosts(None)
    assert _is_internal_host("https://youtube.com", hosts) is False


def test_internal_host_google_blocked():
    hosts = _coerce_allow_hosts(None)
    assert _is_internal_host("https://google.com", hosts) is False


def test_internal_host_unknown_external_blocked():
    hosts = _coerce_allow_hosts(None)
    assert _is_internal_host("http://example.com", hosts) is False


def test_detect_login_password_field():
    assert _detect_login('<input type="password" name="pw">') is True


def test_detect_login_password_name_attr():
    assert _detect_login("<input name='password'>") is True


def test_detect_login_login_form_action():
    assert _detect_login("<form action='/login'>") is True


def test_detect_login_plain_text_login_not_flagged():
    # "로그인 없음" 같은 단순 텍스트는 오탐 아님
    assert _detect_login("<li>로그인·입력폼 없음</li>") is False


def test_detect_login_clean_page():
    assert _detect_login("<h1>대시보드</h1><p>키워드 분석 결과</p>") is False


def test_check_url_external_blocked():
    hosts = _coerce_allow_hosts(None)
    result = check_url("https://naver.com", hosts)
    assert result["internal_host"] is False
    assert result["reachable"] is False
    assert result["skip_reason"] == "external_host_blocked"


def test_check_url_unreachable_internal():
    hosts = _coerce_allow_hosts(None)
    result = check_url("http://127.0.0.1:19999/", hosts, timeout=0.5)
    assert result["internal_host"] is True
    assert result["reachable"] is False


def test_run_preflight_external_blocked():
    result = run_preflight(["https://naver.com"], allow_hosts=None)
    assert result["recommended_url"] is None
    assert result["candidates"][0]["skip_reason"] == "external_host_blocked"


def test_run_preflight_no_reachable_returns_none():
    result = run_preflight(
        ["http://127.0.0.1:19999/", "http://127.0.0.1:19998/"],
        allow_hosts=None,
    )
    assert result["recommended_url"] is None


def test_run_preflight_login_page_not_recommended():
    hosts = _coerce_allow_hosts(None)
    with patch(
        "scripts.preflight_internal_recording_target.check_url",
        return_value={
            "url": "http://127.0.0.1:9000/",
            "internal_host": True,
            "reachable": True,
            "status_code": 200,
            "login_required": True,
            "skip_reason": None,
        },
    ):
        result = run_preflight(["http://127.0.0.1:9000/"])
        assert result["recommended_url"] is None


def test_run_preflight_selects_first_clean():
    with patch(
        "scripts.preflight_internal_recording_target.check_url",
        side_effect=[
            {"url": "http://127.0.0.1:9001/", "internal_host": True, "reachable": True,
             "status_code": 200, "login_required": False, "skip_reason": None},
            {"url": "http://127.0.0.1:9002/", "internal_host": True, "reachable": True,
             "status_code": 200, "login_required": False, "skip_reason": None},
        ],
    ):
        result = run_preflight(
            ["http://127.0.0.1:9001/", "http://127.0.0.1:9002/"]
        )
        assert result["recommended_url"] == "http://127.0.0.1:9001/"


# ---------------------------------------------------------------------------
# smoke 스크립트 정적 검사
# ---------------------------------------------------------------------------


def _smoke_src() -> str:
    return _SMOKE.read_text(encoding="utf-8")


def test_smoke_no_external_urls():
    src = _smoke_src()
    for pat in ["naver.com", "youtube.com", "google.com", "instagram.com"]:
        assert pat not in src.lower(), f"smoke must not reference: {pat}"


def test_smoke_no_click():
    assert "page.click(" not in _smoke_src()


def test_smoke_no_fill():
    assert "page.fill(" not in _smoke_src()


def test_smoke_no_type():
    assert "page.type(" not in _smoke_src()


def test_smoke_no_press():
    assert "page.press(" not in _smoke_src()


def test_smoke_no_evaluate():
    assert "page.evaluate(" not in _smoke_src()


def test_smoke_no_storage_state():
    # 실제 API 호출 패턴으로 검사 (docstring 언급은 허용)
    assert "storage_state=" not in _smoke_src()
    assert ".storage_state" not in _smoke_src()


def test_smoke_no_set_cookie():
    assert ".set_cookie(" not in _smoke_src().lower()


def test_smoke_no_oauth():
    assert "oauth2" not in _smoke_src().lower()
    assert "import oauth" not in _smoke_src().lower()


def test_smoke_no_ltx_api():
    assert "ltx_api" not in _smoke_src().lower()
    assert "import ltx" not in _smoke_src().lower()


def test_smoke_no_upload_call():
    assert ".upload(" not in _smoke_src().lower()


def test_smoke_recording_steps_no_forbidden():
    src = _smoke_src()
    forbidden = {"click", "fill", "type", "press", "submit", "login", "purchase"}
    step_types = re.findall(r'"type"\s*:\s*"([^"]+)"', src)
    for sv in step_types:
        assert sv not in forbidden, f"forbidden step type in smoke: {sv}"


def test_smoke_uses_preflight_before_execute():
    src = _smoke_src()
    assert "run_preflight" in src, "smoke must call preflight before execute"


def test_smoke_blocks_on_login_required():
    src = _smoke_src()
    assert "login_required" in src, "smoke must check login_required"


def test_smoke_blocks_on_external_host():
    src = _smoke_src()
    assert "external_host_blocked" in src or "internal_host" in src, \
        "smoke must guard against external hosts"
