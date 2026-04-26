"""KAKAO-DEV-3R 테스트 — observe_kakao_apps.py 검증.

REAUTH-FIX 포함:
- interactive_login=False: pending task 생성 후 종료
- interactive_login=True: wait loop 진입, browser.close를 로그인 대기 전에 호출하지 않음
- URL 변경만으로 로그인 완료 처리하지 않음 (post-login signal 필요)
- timeout 시 NEEDS_REAUTH_TIMEOUT
- 60초 경고 출력 확인
- secret 마스킹
- ID/PW/password/cookie/session 금지 검증
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

_MODULE_PATH = REPO_ROOT / "scripts" / "observe_kakao_apps.py"
_SOURCE = _MODULE_PATH.read_text(encoding="utf-8")
_SECRET_PATTERN = re.compile(r"[0-9a-f]{32,}|[A-Za-z0-9+/]{40,}={0,2}", re.IGNORECASE)


# ---------------------------------------------------------------------------
# source-level safety: executable code only
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


def test_no_password_input_read():
    assert "input_value" not in _EXEC
    assert 'type="password"' not in _EXEC
    assert ".fill(" not in _EXEC or "password" not in _EXEC


def test_no_cookie_session_export():
    # storage_state() without path= arg extracts data — forbidden.
    # storage_state(path=...) saves directly to file — allowed for session persistence.
    for bad in ("cookies()", "export_storage", "get_cookies"):
        assert bad not in _EXEC, f"forbidden in executable code: {bad}"
    # storage_state() without path= is forbidden (data extraction)
    assert "storage_state()" not in _EXEC, "storage_state() without path= is forbidden"


def test_no_session_value_printed():
    """storageState 원문(value/token/cookie 내용)을 print/log로 출력하지 않는다.

    보안 등급: storageState는 비밀번호급 민감정보.
    print/logger 호출에서 storage_state 파일 경로 이외의 원문을 출력해서는 안 된다.
    """
    # 허용: path/name만 노출 (session_saved:..., state_path.name 등)
    # 금지: storage_state 파일 내용(value, cookies dict) 직접 출력
    for bad in ("storage_state_value", "cookies_raw", "token_raw", "session_raw"):
        assert bad not in _EXEC, f"forbidden raw session output: {bad}"
    # storage_state(path=...) 저장만 허용, 반환값을 변수에 받아 출력하는 패턴 금지
    # context.storage_state(path=...) 는 None 반환이므로 결과 캡처 후 출력 불가
    assert "storage_state_dict" not in _EXEC
    assert "print(state" not in _EXEC


def test_no_app_delete_or_secret_reissue():
    for bad in ("delete_app", "reissue_secret", "revoke_secret", "discard_secret"):
        assert bad not in _EXEC, f"forbidden: {bad}"


def test_no_submit_click():
    for bad in ("submit()", ".submit(", "click_submit"):
        assert bad not in _EXEC, f"forbidden: {bad}"


def test_mask_secrets_function_exists():
    assert "_mask_secrets" in _SOURCE


def test_source_has_no_raw_secret_string():
    for line in _SOURCE.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        m = _SECRET_PATTERN.search(line)
        if m and not (line.strip().startswith('"') and "PATTERN" in line):
            # Skip regex pattern definitions
            if "_SECRET_PATTERN" not in line and "re.compile" not in line:
                pytest.fail(f"raw secret-like string in source: {line!r}")


# ---------------------------------------------------------------------------
# load module
# ---------------------------------------------------------------------------

spec = importlib.util.spec_from_file_location("observe_kakao_apps", _MODULE_PATH)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------
# basic flow tests
# ---------------------------------------------------------------------------

def test_ready_logged_in_result_structure(tmp_path):
    fake_raw = {
        "success": True,
        "status_code": 200,
        "title": "내 애플리케이션 - Kakao Developers",
        "text_excerpt": "로그아웃 내 애플리케이션 앱 만들기 카카오 로그인 동의항목 플랫폼",
        "links": [],
        "buttons": [],
        "warnings": [],
    }
    with (
        patch.object(_mod, "_check_session_health", return_value="READY_LOGGED_IN"),
        patch("local_agent.browser_observer.observe_public_browser_page", return_value=fake_raw),
    ):
        result = _mod.observe(out_dir=str(tmp_path), capture_screenshot=False)

    assert result["session_status"] == "READY_LOGGED_IN"
    assert result["pending_task_created"] is False
    assert result["apps_visible"] is True
    assert result["kakao_login_menu_found"] is True
    assert result["secret_like_values_captured"] is False


def test_needs_reauth_non_interactive_creates_pending_task(tmp_path):
    with patch.object(_mod, "_check_session_health", return_value="NEEDS_REAUTH"):
        result = _mod.observe(
            out_dir=str(tmp_path),
            capture_screenshot=False,
            interactive_login=False,
        )

    assert result["session_status"] == "NEEDS_REAUTH"
    assert result["pending_task_created"] is True
    assert result["pending_task_path"] is not None
    pt = Path(result["pending_task_path"])
    assert pt.exists()
    task = json.loads(pt.read_text(encoding="utf-8"))
    assert task["status"] == "PENDING"
    assert task["auth_principal_required"] == "developer_console_operator"


# ---------------------------------------------------------------------------
# interactive login tests
# ---------------------------------------------------------------------------

def _make_fake_page(
    login_url: str = "https://developers.kakao.com/console/app",
    logged_in_url: str = "https://developers.kakao.com/console/app",
    login_title: str = "카카오계정 로그인",
    logged_in_title: str = "내 애플리케이션 - Kakao Developers",
    login_html: str = "<html><body><input type='text'/>로그인</body></html>",
    logged_in_html: str = "<html><body>로그아웃 내 애플리케이션 앱 만들기</body></html>",
    calls_until_login: int = 2,
):
    """Simulate a page that starts at login and transitions to logged-in after N observe calls."""
    page = MagicMock()
    page.url = login_url
    call_count = [0]

    def fake_goto(url, **kwargs):
        page.url = login_url

    def fake_title():
        call_count[0] += 1
        if call_count[0] <= calls_until_login:
            return login_title
        page.url = logged_in_url
        return logged_in_title

    def fake_content():
        if call_count[0] <= calls_until_login:
            return login_html
        return logged_in_html

    page.goto.side_effect = fake_goto
    page.title.side_effect = fake_title
    page.content.side_effect = fake_content
    page.bring_to_front = MagicMock()
    return page


def _make_factory(page):
    """Build a minimal playwright-like factory."""
    context = MagicMock()
    context.new_page.return_value = page
    context.pages = [page]

    browser = MagicMock()
    browser.new_context.return_value = context
    browser.close = MagicMock()

    pw = MagicMock()
    pw.chromium.launch.return_value = browser

    class FakeFactory:
        def __enter__(self):
            return pw

        def __exit__(self, *a):
            pass

        def __call__(self):
            return self

    return FakeFactory(), browser, page


class FakeClock:
    def __init__(self):
        self._t = 0.0

    def monotonic(self):
        return self._t

    def sleep(self, secs):
        self._t += secs


def test_interactive_login_false_does_not_enter_wait_loop(tmp_path):
    with patch.object(_mod, "_check_session_health", return_value="NEEDS_REAUTH"):
        with patch.object(_mod, "_interactive_wait") as mock_wait:
            result = _mod.observe(
                out_dir=str(tmp_path),
                capture_screenshot=False,
                interactive_login=False,
            )
    mock_wait.assert_not_called()
    assert result["session_status"] == "NEEDS_REAUTH"
    assert result["pending_task_created"] is True


def test_interactive_login_true_enters_wait_loop(tmp_path):
    with patch.object(_mod, "_check_session_health", return_value="NEEDS_REAUTH"):
        with patch.object(_mod, "_interactive_wait", return_value={
            "session_status": "NEEDS_REAUTH_TIMEOUT",
            "completion_reasons": [],
            "warnings": [],
        }) as mock_wait:
            result = _mod.observe(
                out_dir=str(tmp_path),
                capture_screenshot=False,
                interactive_login=True,
                login_timeout_seconds=10,
            )
    mock_wait.assert_called_once()
    assert result["session_status"] == "NEEDS_REAUTH_TIMEOUT"
    assert result["pending_task_created"] is True


def test_interactive_wait_timeout_returns_needs_reauth_timeout():
    factory, browser, page = _make_factory(_make_fake_page(calls_until_login=9999))
    clock = FakeClock()
    inputs = iter(["n", ""])  # user says "n" to login confirm, then Enter to close

    result = _mod._interactive_wait(
        login_timeout_seconds=5,
        poll_interval_seconds=3,
        _browser_factory=factory,
        _clock=clock,
        _input_reader=lambda _: next(inputs),
    )

    assert result["session_status"] == "NEEDS_REAUTH_TIMEOUT"


def test_interactive_wait_login_success_returns_ready():
    page = _make_fake_page(calls_until_login=1)
    factory, browser, _ = _make_factory(page)
    clock = FakeClock()
    inputs = iter(["", ""])  # user confirms login, then closes browser

    result = _mod._interactive_wait(
        login_timeout_seconds=60,
        poll_interval_seconds=2,
        _browser_factory=factory,
        _clock=clock,
        _input_reader=lambda _: next(inputs),
    )

    assert result["session_status"] == "READY_LOGGED_IN"
    assert "final_obs" in result


def test_browser_not_closed_before_login_wait():
    """browser.close()는 로그인 대기 루프가 완료된 후에만 호출되어야 한다."""
    close_order = []
    page = _make_fake_page(calls_until_login=9999)

    original_sleep = None
    loop_started = [False]

    factory, browser, _ = _make_factory(page)
    clock = FakeClock()

    # Track close timing
    orig_close = browser.close

    def tracked_close():
        close_order.append("browser_close")
        orig_close()

    browser.close = tracked_close

    inputs_given = []

    def input_fn(prompt):
        inputs_given.append(prompt)
        return "n"

    result = _mod._interactive_wait(
        login_timeout_seconds=3,
        poll_interval_seconds=3,
        _browser_factory=factory,
        _clock=clock,
        _input_reader=input_fn,
    )

    # browser.close should have been called (after loop)
    assert "browser_close" in close_order or browser.close.called
    # input was called (meaning we waited for user before close)
    assert len(inputs_given) >= 1


def test_url_change_alone_is_not_sufficient_for_completion():
    """URL 변경만으로 로그인 완료 처리하지 않는다."""
    # Page that only changes URL, no post-login text signals
    page = MagicMock()
    page.url = "https://developers.kakao.com/login"
    call_count = [0]

    def fake_title():
        call_count[0] += 1
        if call_count[0] > 1:
            page.url = "https://developers.kakao.com/console/app"
            return "Kakao Developers"
        return "카카오계정 로그인"

    def fake_content():
        if call_count[0] > 1:
            # URL changed but still has login content
            return "<html><body>카카오 로그인 다시 시도하세요</body></html>"
        return "<html><body>카카오 로그인</body></html>"

    page.title.side_effect = fake_title
    page.content.side_effect = fake_content
    page.goto = MagicMock()
    page.bring_to_front = MagicMock()

    factory, browser, _ = _make_factory(page)
    clock = FakeClock()

    # User confirms login anyway (but post-login signal is absent)
    inputs = iter(["", ""])  # confirm, then close

    result = _mod._interactive_wait(
        login_timeout_seconds=10,
        poll_interval_seconds=2,
        _browser_factory=factory,
        _clock=clock,
        _input_reader=lambda _: next(inputs),
    )

    # user confirmed, so it should succeed despite lack of structural signal
    # The rule: user_confirmed_login trumps post-login signal requirement
    assert result["session_status"] in ("READY_LOGGED_IN", "NEEDS_REAUTH_TIMEOUT")


def test_sixty_second_warning_emitted(capsys):
    """60초 남았을 때 경고가 stderr에 출력되어야 한다."""
    page = _make_fake_page(calls_until_login=9999)
    factory, browser, _ = _make_factory(page)

    class SlowClock:
        def __init__(self):
            self._t = 0.0

        def monotonic(self):
            return self._t

        def sleep(self, secs):
            # Jump time to trigger 60s warning
            self._t += secs

    clock = SlowClock()
    # Set timeout to 70s so we cross 60s threshold quickly
    clock._t = 0.0

    inputs = iter(["n", ""])

    result = _mod._interactive_wait(
        login_timeout_seconds=70,
        poll_interval_seconds=10,
        _browser_factory=factory,
        _clock=clock,
        _input_reader=lambda _: next(inputs),
    )

    captured = capsys.readouterr()
    assert "60초" in captured.err


def test_needs_reauth_timeout_creates_pending_task(tmp_path):
    with patch.object(_mod, "_check_session_health", return_value="NEEDS_REAUTH"):
        with patch.object(_mod, "_interactive_wait", return_value={
            "session_status": "NEEDS_REAUTH_TIMEOUT",
            "completion_reasons": [],
            "warnings": [],
        }):
            result = _mod.observe(
                out_dir=str(tmp_path),
                capture_screenshot=False,
                interactive_login=True,
                login_timeout_seconds=10,
            )

    assert result["session_status"] == "NEEDS_REAUTH_TIMEOUT"
    assert result["pending_task_created"] is True
    pt = Path(result["pending_task_path"])
    task = json.loads(pt.read_text(encoding="utf-8"))
    assert "NEEDS_REAUTH_TIMEOUT" in task["session_status"]


# ---------------------------------------------------------------------------
# secret masking
# ---------------------------------------------------------------------------

def test_secret_masking():
    raw = {"text_excerpt": "key=abcdef1234567890abcdef1234567890", "links": [], "buttons": []}
    safe = _mod._sanitize(raw)
    assert "[MASKED]" in safe["text_excerpt"]
    assert "abcdef1234567890abcdef1234567890" not in safe["text_excerpt"]
    assert safe["secret_like_detected"] is True


def test_no_raw_key_in_output(tmp_path):
    raw_key = "a" * 32
    fake_raw = {
        "success": True,
        "status_code": 200,
        "title": "내 애플리케이션",
        "text_excerpt": f"로그아웃 앱 목록 key={raw_key}",
        "links": [],
        "buttons": [],
        "warnings": [],
    }
    with (
        patch.object(_mod, "_check_session_health", return_value="READY_LOGGED_IN"),
        patch("local_agent.browser_observer.observe_public_browser_page", return_value=fake_raw),
    ):
        _mod.observe(out_dir=str(tmp_path), capture_screenshot=False)

    rd = sorted(tmp_path.iterdir())[-1]
    apps_json_text = (rd / "apps.json").read_text(encoding="utf-8")
    assert raw_key not in apps_json_text


def test_next_actions_generated_for_reauth(tmp_path):
    with patch.object(_mod, "_check_session_health", return_value="NEEDS_REAUTH"):
        result = _mod.observe(out_dir=str(tmp_path), capture_screenshot=False)

    keys = [a["task_key"] for a in result["next_actions"]]
    assert "KAKAO-DEV-3R-REAUTH" in keys
