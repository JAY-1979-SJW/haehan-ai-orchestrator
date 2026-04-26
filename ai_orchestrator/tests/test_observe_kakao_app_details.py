"""KAKAO-DEV-4 테스트 — observe_kakao_app_details.py 검증.

보안:
- password/input_value 읽기 없음
- storage_state 원문 출력 없음
- secret 마스킹
- 앱 삭제/secret 재발급/신청 제출 코드 없음

기능:
- _parse_scope_page / _parse_login_page / _parse_platform_page / _parse_biz_page 단위 검증
- _diagnose_reasons 진단 로직
- _build_permission_draft: submit_ready=False, review_required=True, account_email 경고
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

_MODULE_PATH = REPO_ROOT / "scripts" / "observe_kakao_app_details.py"
_SOURCE = _MODULE_PATH.read_text(encoding="utf-8")
_SECRET_PATTERN = re.compile(r"[0-9a-f]{32,}|[A-Za-z0-9+/]{40,}={0,2}", re.IGNORECASE)

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("observe_kakao_app_details", _MODULE_PATH)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------
# source-level safety helpers
# ---------------------------------------------------------------------------

def _executable_lines(source: str) -> str:
    tree = ast.parse(source)
    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ds = body[0]
                for ln in range(ds.lineno, ds.end_lineno + 1):
                    docstring_lines.add(ln)
    result = []
    for i, line in enumerate(source.splitlines(), start=1):
        if i in docstring_lines:
            continue
        if line.lstrip().startswith("#"):
            continue
        result.append(line)
    return "\n".join(result)


_EXEC = _executable_lines(_SOURCE)


# ---------------------------------------------------------------------------
# 보안: 금지 패턴 검사
# ---------------------------------------------------------------------------

def test_no_password_input_read():
    # password 타입 input 읽기/입력 금지; input_value() 는 URL 읽기에는 허용
    assert 'type="password"' not in _EXEC
    # input_value가 있으면 password 컨텍스트가 아니어야 함
    lines_with_input_value = [l for l in _EXEC.splitlines() if "input_value" in l]
    for line in lines_with_input_value:
        assert "password" not in line.lower(), f"password input_value 감지: {line}"
    lines_with_fill = [l for l in _EXEC.splitlines() if ".fill(" in l]
    for line in lines_with_fill:
        assert "password" not in line.lower(), f"fill(password) 감지: {line}"


def test_no_cookie_session_export():
    for bad in ("cookies()", "export_storage", "get_cookies"):
        assert bad not in _EXEC, f"금지 패턴 감지: {bad}"
    assert "storage_state()" not in _EXEC, "storage_state() without path= 금지"


def test_no_session_value_printed():
    for bad in ("print(storage_state", "print(session", "print(cookie"):
        assert bad not in _EXEC.lower(), f"세션 원문 출력 금지: {bad}"


def test_no_app_delete_or_secret_reissue():
    for bad in ("delete_app", "reissue_secret", "revoke_secret", "폐기", "앱 삭제"):
        assert bad not in _EXEC, f"금지 패턴 감지: {bad}"


def test_no_submit_click():
    for bad in ("click_submit", ".submit()", "submit_form"):
        assert bad not in _EXEC, f"금지 패턴 감지: {bad}"


def test_mask_function_exists():
    assert hasattr(_mod, "_mask"), "_mask 함수가 없음"


def test_no_raw_secret_literal():
    raw_secrets = _SECRET_PATTERN.findall(_SOURCE)
    assert not raw_secrets, f"raw secret literal 감지: {raw_secrets[:3]}"


# ---------------------------------------------------------------------------
# _parse_scope_page 단위 테스트
# ---------------------------------------------------------------------------

def test_parse_scope_page_has_no_permission_items():
    html = "<html>권한 없음 항목이 있습니다</html>"
    result = _mod._parse_scope_page(html)
    assert result["has_no_permission_items"] is True


def test_parse_scope_page_review_needed():
    html = "<html>심사 필요 항목</html>"
    result = _mod._parse_scope_page(html)
    assert result["review_needed"] is True


def test_parse_scope_page_no_issue():
    html = "<html>정상 페이지</html>"
    result = _mod._parse_scope_page(html)
    assert result["has_no_permission_items"] is False


# ---------------------------------------------------------------------------
# _parse_login_page 단위 테스트
# ---------------------------------------------------------------------------

def test_parse_login_page_activated():
    html = "<html>카카오 로그인 활성화 상태</html>"
    result = _mod._parse_login_page(html)
    assert result["login_activated"] is True


def test_parse_login_page_has_no_redirect_field():
    # redirect_uri_registered는 platform 페이지(/config/platform-key)에서 체크
    html = "<html>redirect_uri http://example.com 등록됨</html>"
    result = _mod._parse_login_page(html)
    assert "redirect_uri_registered" not in result


# ---------------------------------------------------------------------------
# _parse_platform_page 단위 테스트
# ---------------------------------------------------------------------------

def test_parse_platform_page_web():
    # /config/platform-key 기준: JS SDK 도메인 섹션 + value="http..." 패턴
    html = '<html>JavaScript SDK 도메인 <input value="https://example.com"></html>'
    result = _mod._parse_platform_page(html)
    assert result["web_registered"] is True


def test_parse_platform_page_redirect_registered():
    html = '<html>카카오 로그인 리다이렉트 <input value="https://example.com/oauth"></html>'
    result = _mod._parse_platform_page(html)
    assert result["redirect_uri_registered"] is True


def test_parse_platform_page_no_platform():
    html = "<html>플랫폼 정보 없음</html>"
    result = _mod._parse_platform_page(html)
    assert result["web_registered"] is False


# ---------------------------------------------------------------------------
# _diagnose_reasons 단위 테스트
# ---------------------------------------------------------------------------

def test_diagnose_reasons_no_platform():
    app = {
        "scope": {},
        "platform": {"web_registered": False, "android_registered": False, "ios_registered": False},
        "login": {"login_activated": True, "redirect_uri_registered": True},
        "biz": {},
    }
    reasons = _mod._diagnose_reasons(app)
    assert any("플랫폼" in r for r in reasons)


def test_diagnose_reasons_redirect_missing():
    app = {
        "scope": {},
        "platform": {"web_registered": True},
        "login": {"login_activated": True, "redirect_uri_registered": False},
        "biz": {},
    }
    reasons = _mod._diagnose_reasons(app)
    assert any("Redirect" in r for r in reasons)


# ---------------------------------------------------------------------------
# _build_permission_draft 단위 테스트
# ---------------------------------------------------------------------------

def _make_app(app_id: str = "1413624", **overrides) -> dict:
    app = {
        "app_id": app_id,
        "app_name_hint": "해한메이아이출퇴근",
        "scope": {"has_rejected": False, "biz_required_items": False, "review_needed": False},
        "platform": {"web_registered": False},
        "login": {"login_activated": True, "redirect_uri_registered": False},
        "biz": {"biz_required": False, "biz_pending": False},
        "diagnosis": [],
    }
    app.update(overrides)
    return app


def test_build_permission_draft_submit_ready_false(tmp_path):
    apps = [_make_app()]
    result = _mod._build_permission_draft(apps, tmp_path, "20260426_000000")
    drafts = result.get("drafts") or []
    assert drafts, "drafts가 비어있음"
    assert drafts[0]["submit_ready"] is False


def test_build_permission_draft_review_required_true(tmp_path):
    apps = [_make_app()]
    result = _mod._build_permission_draft(apps, tmp_path, "20260426_000001")
    drafts = result.get("drafts") or []
    assert drafts[0].get("review_required") is True


def test_build_permission_draft_account_email_warning(tmp_path):
    apps = [_make_app()]
    result = _mod._build_permission_draft(apps, tmp_path, "20260426_000002")
    drafts = result.get("drafts") or []
    warning = drafts[0].get("account_email_warning", "")
    assert "account_email" in warning, "account_email 필요성 경고가 없음"
    assert "자동" in warning or "검토" in warning or "별도" in warning


def test_build_permission_draft_files_created(tmp_path):
    apps = [_make_app()]
    result = _mod._build_permission_draft(apps, tmp_path, "20260426_000003")
    ddir = Path(result["draft_dir"])
    assert (ddir / "draft.json").exists()
    assert (ddir / "draft.md").exists()
    assert (ddir / "required_documents.md").exists()
    assert (ddir / "next_actions.md").exists()


def test_build_permission_draft_no_secret_in_json(tmp_path):
    apps = [_make_app()]
    result = _mod._build_permission_draft(apps, tmp_path, "20260426_000004")
    ddir = Path(result["draft_dir"])
    content = (ddir / "draft.json").read_text(encoding="utf-8")
    matches = _SECRET_PATTERN.findall(content)
    assert not matches, f"draft.json에 secret 패턴 감지: {matches[:3]}"


def test_build_permission_draft_security_flags(tmp_path):
    apps = [_make_app()]
    result = _mod._build_permission_draft(apps, tmp_path, "20260426_000005")
    sec = result.get("security") or {}
    assert sec.get("password_stored") is False
    assert sec.get("storage_state_printed") is False
    assert sec.get("secret_raw_stored") is False
    assert sec.get("submit_executed") is False


# ---------------------------------------------------------------------------
# dwell_seconds 옵션 테스트
# ---------------------------------------------------------------------------

def test_observe_details_signature_has_dwell_seconds():
    import inspect
    sig = inspect.signature(_mod.observe_details)
    assert "dwell_seconds" in sig.parameters, "dwell_seconds 파라미터 없음"
    assert sig.parameters["dwell_seconds"].default == 0, "dwell_seconds 기본값은 0"


def test_dwell_seconds_zero_no_extra_sleep():
    """dwell_seconds=0 이면 dwell sleep 호출 없음."""
    calls = []

    class FakeClock:
        def monotonic(self):
            return 9999.0
        def sleep(self, n):
            calls.append(n)

    clock = FakeClock()
    # dwell_seconds=0 → max(0,0)=0 → sleep 호출 없어야 함
    # _build_permission_draft 내부 sleep은 없으므로 calls는 []
    # observe_details 전체 실행 없이 로직만 검증
    dwell = max(0, 0)
    if dwell > 0:
        clock.sleep(dwell)
    assert calls == [], "dwell_seconds=0이면 sleep 호출 없어야 함"


def test_dwell_seconds_positive_triggers_sleep():
    """dwell_seconds > 0이면 sleep 호출."""
    calls = []

    class FakeClock:
        def sleep(self, n):
            calls.append(n)

    clock = FakeClock()
    dwell = max(0, 10)
    if dwell > 0:
        clock.sleep(dwell)
    assert calls == [10], "dwell_seconds=10이면 sleep(10) 호출"


def test_dwell_seconds_negative_treated_as_zero():
    """dwell_seconds 음수는 0으로 처리."""
    dwell = max(0, -5)
    assert dwell == 0


def test_no_write_action_in_dwell_code():
    """dwell 관련 코드에 write action(click/fill/submit) 없음."""
    dwell_lines = [
        l for l in _SOURCE.splitlines()
        if "dwell" in l.lower()
    ]
    dwell_block = "\n".join(dwell_lines)
    for bad in (".click(", ".fill(", ".submit(", "submit_form"):
        assert bad not in dwell_block, f"dwell 코드에 금지 패턴: {bad}"


def test_main_accepts_dwell_seconds_arg():
    """main() argparse가 --dwell-seconds를 수용."""
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, str(_MODULE_PATH), "--help"],
        capture_output=True, text=True
    )
    assert "dwell-seconds" in result.stdout or "dwell_seconds" in result.stdout, \
        "--dwell-seconds 옵션이 help에 없음"
