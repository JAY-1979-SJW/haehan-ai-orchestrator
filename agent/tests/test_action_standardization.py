"""표준화 1단계 테스트.

검증:
1) 모든 action 이 {ok, action, data, error} 공통 응답 형식 반환
2) 주요 실패가 표준 error code 를 반환
3) action registry 메타데이터 존재/일관성
4) 로그 entry 가 공통 표준 필드(action/category/risk_level/timestamp/ok/duration_ms) 유지
5) 기존 차단 정책(host/path/profile/secret) 회귀 없음
6) 민감정보 미노출 (로그/응답)
"""
from __future__ import annotations

import json
import os
import sys
import types

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)


# ── Playwright 테스트 더블 (다른 테스트와 동일 수준의 최소본) ──────────
class _FakeTimeout(Exception):
    pass


class _FakeResponse:
    def __init__(self, status: int = 200):
        self.status = status


class _FakeLocator:
    def __init__(self, *, text: str = "", count: int = 0):
        self._text = text
        self._count = count

    def inner_text(self, timeout=None):  # noqa: ARG002
        return self._text

    def count(self):
        return self._count


class _FakePage:
    def __init__(self, resolved_url: str = "https://www.example.com/final"):
        self.url = resolved_url
        self._resolved = resolved_url

    def goto(self, *_a, **_kw):
        return _FakeResponse()

    def title(self):
        return "타이틀"

    def locator(self, selector: str):
        if selector == "body":
            return _FakeLocator(text="본문")
        return _FakeLocator(count=0)

    def close(self):
        pass


class _FakeContext:
    def __init__(self, page):
        self._page = page

    def new_page(self):
        return self._page

    def close(self):
        pass


class _FakeBrowser:
    def __init__(self, page):
        self._ctx = _FakeContext(page)

    def new_context(self, **_):
        return self._ctx

    def close(self):
        pass


class _FakeChromium:
    def __init__(self, page):
        self._page = page

    def launch(self, **_):
        return _FakeBrowser(self._page)


class _FakePlaywrightCtx:
    def __init__(self, page):
        self.chromium = _FakeChromium(page)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _install_fake_playwright(monkeypatch, *, page):
    fake_mod = types.ModuleType("playwright.sync_api")
    fake_mod.sync_playwright = lambda: _FakePlaywrightCtx(page)
    fake_mod.TimeoutError = _FakeTimeout
    fake_pkg = types.ModuleType("playwright")
    monkeypatch.setitem(sys.modules, "playwright", fake_pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_mod)


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    from agent import config as _cfg
    from agent import runner as _runner
    from agent import site_profiles as _sp

    monkeypatch.setenv("AGENT_SECRETS_DIR", str(tmp_path / "secrets"))
    monkeypatch.setattr(
        _cfg, "AGENT_LOG_PATH", tmp_path / "agent_actions.jsonl"
    )
    _sp._REGISTRY.clear()
    if _runner._browser_lock.locked():
        try:
            _runner._browser_lock.release()
        except RuntimeError:
            pass
    yield
    _sp._REGISTRY.clear()
    if _runner._browser_lock.locked():
        try:
            _runner._browser_lock.release()
        except RuntimeError:
            pass


def _read_log(tmp_path):
    p = tmp_path / "agent_actions.jsonl"
    if not p.exists():
        return []
    return [
        json.loads(ln)
        for ln in p.read_text(encoding="utf-8").strip().splitlines()
        if ln
    ]


# ══════════════════════════════════════════════════════════════════════
# 1) 모든 action 이 공통 응답 형식 반환
# ══════════════════════════════════════════════════════════════════════
_COMMON_KEYS = {"ok", "action", "data", "error"}


def test_ping_response_shape():
    from agent import app
    out = app.run("ping")
    assert set(out.keys()) == _COMMON_KEYS
    assert out["action"] == "ping"
    assert isinstance(out["data"], dict)


def test_get_system_info_response_shape():
    from agent import app
    out = app.run("get_system_info")
    assert set(out.keys()) == _COMMON_KEYS
    assert out["action"] == "get_system_info"


def test_open_page_readonly_response_shape(monkeypatch):
    from agent import app
    _install_fake_playwright(monkeypatch, page=_FakePage())
    out = app.run("open_page_readonly", url="https://www.example.com/")
    assert set(out.keys()) == _COMMON_KEYS
    assert out["action"] == "open_page_readonly"


def test_inspect_page_response_shape(monkeypatch):
    from agent import app
    _install_fake_playwright(monkeypatch, page=_FakePage())
    out = app.run("inspect_page", url="https://www.example.com/")
    assert set(out.keys()) == _COMMON_KEYS
    assert out["action"] == "inspect_page"


def test_login_with_secret_response_shape_on_missing_site():
    from agent import app
    out = app.run("login_with_secret", site_key="ghost_site")
    assert set(out.keys()) == _COMMON_KEYS
    assert out["action"] == "login_with_secret"
    assert out["ok"] is False


def test_inspect_after_login_response_shape_on_missing_target():
    from agent import app
    out = app.run("inspect_after_login", site_key="x", target_url="")
    assert set(out.keys()) == _COMMON_KEYS
    assert out["action"] == "inspect_after_login"
    assert out["ok"] is False


def test_unknown_action_response_shape():
    from agent import app
    out = app.run("signup")
    assert set(out.keys()) == _COMMON_KEYS
    assert out["ok"] is False


# ══════════════════════════════════════════════════════════════════════
# 2) 주요 실패가 표준 error code 반환
# ══════════════════════════════════════════════════════════════════════
def test_major_failures_use_standard_error_codes(monkeypatch):
    from agent import app, errors

    # action_not_allowed
    out = app.run("signup")
    assert out["error"] == errors.ACTION_NOT_ALLOWED
    assert errors.is_standard_code(out["error"])

    # url_not_allowed (prefix)
    out = app.run("open_page_readonly", url="")
    assert out["error"].startswith(errors.URL_NOT_ALLOWED)
    assert errors.is_standard_code(out["error"])

    # site_key_required
    out = app.run("login_with_secret", site_key="")
    assert out["error"] == errors.SITE_KEY_REQUIRED
    assert errors.is_standard_code(out["error"])

    # target_url_required
    out = app.run("inspect_after_login", site_key="x", target_url="")
    assert out["error"] == errors.TARGET_URL_REQUIRED
    assert errors.is_standard_code(out["error"])

    # site_profile_not_found
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    out = app.run("login_with_secret", site_key="does_not_exist")
    assert out["error"] == errors.SITE_PROFILE_NOT_FOUND
    assert errors.is_standard_code(out["error"])


def test_all_error_constants_exist():
    from agent import errors
    # 단일 코드
    for name in (
        "ACTION_NOT_ALLOWED", "CONCURRENT_BROWSER_LIMIT",
        "SITE_KEY_REQUIRED", "TARGET_URL_REQUIRED",
        "SITE_PROFILE_NOT_FOUND", "SECRET_NOT_FOUND",
        "HOST_NOT_ALLOWED", "LOGIN_HOST_NOT_ALLOWED",
        "TARGET_HOST_NOT_ALLOWED", "TARGET_PATH_NOT_ALLOWED",
        "LOGIN_FAILED", "INSPECT_CHECK_FAILED",
        "PLAYWRIGHT_TIMEOUT", "PLAYWRIGHT_NOT_INSTALLED",
    ):
        assert hasattr(errors, name), f"errors.{name} missing"
        assert getattr(errors, name) in errors.ALL_CODES, name

    # prefix 코드
    for name in (
        "URL_NOT_ALLOWED", "LOGIN_URL_NOT_ALLOWED",
        "TARGET_URL_NOT_ALLOWED", "PLAYWRIGHT_ERROR", "SECRET_STORE_ERROR",
    ):
        assert hasattr(errors, name), f"errors.{name} missing"
        assert getattr(errors, name) in errors.PREFIX_CODES, name


def test_is_standard_code_handles_prefix_and_plain():
    from agent import errors
    assert errors.is_standard_code("action_not_allowed")
    assert errors.is_standard_code("url_not_allowed:blocked_host:localhost")
    assert errors.is_standard_code("playwright_error:RuntimeError")
    assert not errors.is_standard_code("")
    assert not errors.is_standard_code(None)  # type: ignore[arg-type]
    assert not errors.is_standard_code("totally_not_a_code")


# ══════════════════════════════════════════════════════════════════════
# 3) action registry 메타데이터
# ══════════════════════════════════════════════════════════════════════
def test_action_registry_contents():
    from agent import action_registry as reg

    from agent.cad_api_spec import action_names as _cad_api_names
    expected = {
        "ping", "get_system_info", "open_page_readonly",
        "inspect_page", "login_with_secret", "inspect_after_login",
        # Excel 1단계
        "excel_read_sheet", "excel_write_report_copy",
        # Excel 2단계
        "excel_describe_workbook", "excel_read_table",
        # Excel COM (B안 4단계)
        "excel.run_poc", "excel.read_cell",
        "excel.write_cell", "excel.save_as",
        # CAD COM (2단계 편입)
        "cad.health", "cad.open_info", "cad.add_text_save_as",
        # local_agent 전용 visible 브라우저 기동 (E단계)
        "open_local_browser",
        # local_agent 전용 Playwright dedicated 프로필 visible probe (E-2)
        "open_local_browser_probe",
        # local_agent 전용 공개 페이지 read-only observer (F-4B)
        "observe_public_browser_page",
    } | set(_cad_api_names())
    assert set(reg.list_actions()) == expected

    # CAD API 3단계 편입 — 스펙 테이블의 모든 action 이 등록·category=cad
    for name in _cad_api_names():
        m = reg.get_meta(name)
        assert m is not None, f"{name} not registered"
        assert m.category == reg.CATEGORY_CAD
        assert m.requires_secret is False
        assert m.requires_browser is False
        # 서버 리소스 조작이라 로컬 파일/경로 요구 없음 — upload 는 예외
        if name != "cad.upload_drawing":
            assert m.requires_file_path is False, name
        assert m.requires_save_as is False, name
    # write 와 read 분포 확인 (GET = read / 그 외 = write)
    from agent import cad_api_spec as _sp
    for spec in _sp.CAD_API_ACTIONS:
        m = reg.get_meta(spec.action)
        if spec.method == "GET":
            assert m.read_only is True, spec.action
            assert m.risk_level == reg.RISK_LOW, spec.action
        else:
            assert m.read_only is False, spec.action
            assert m.risk_level == reg.RISK_MEDIUM, spec.action

    # CAD 메타데이터
    for a in ("cad.health", "cad.open_info", "cad.add_text_save_as"):
        m = reg.get_meta(a)
        assert m.category == reg.CATEGORY_CAD
        assert m.requires_secret is False
        assert m.requires_browser is False
    # health / open_info 는 read-only, add_text_save_as 만 write
    assert reg.get_meta("cad.health").read_only is True
    assert reg.get_meta("cad.open_info").read_only is True
    assert reg.get_meta("cad.add_text_save_as").read_only is False
    # risk_level: health/open_info=low, add_text_save_as=medium (Excel write 와 동급)
    assert reg.get_meta("cad.health").risk_level == reg.RISK_LOW
    assert reg.get_meta("cad.open_info").risk_level == reg.RISK_LOW
    assert reg.get_meta("cad.add_text_save_as").risk_level == reg.RISK_MEDIUM
    # cad.health 만 file_path 면제 플래그가 False
    assert reg.get_meta("cad.health").requires_file_path is False
    assert reg.get_meta("cad.open_info").requires_file_path is True
    assert reg.get_meta("cad.add_text_save_as").requires_file_path is True

    # Excel COM 메타데이터
    for a in ("excel.run_poc", "excel.read_cell",
              "excel.write_cell", "excel.save_as"):
        m = reg.get_meta(a)
        assert m.category == reg.CATEGORY_EXCEL_COM
        assert m.requires_secret is False
        assert m.requires_browser is False

    # read_cell 만 read_only=true, 나머지 3개는 false
    assert reg.get_meta("excel.read_cell").read_only is True
    assert reg.get_meta("excel.run_poc").read_only is False
    assert reg.get_meta("excel.write_cell").read_only is False
    assert reg.get_meta("excel.save_as").read_only is False

    # risk_level: read_cell / run_poc = low, write_cell / save_as = medium
    assert reg.get_meta("excel.read_cell").risk_level == reg.RISK_LOW
    assert reg.get_meta("excel.run_poc").risk_level == reg.RISK_LOW
    assert reg.get_meta("excel.write_cell").risk_level == reg.RISK_MEDIUM
    assert reg.get_meta("excel.save_as").risk_level == reg.RISK_MEDIUM

    # Excel 메타데이터
    m = reg.get_meta("excel_read_sheet")
    assert m.category == reg.CATEGORY_EXCEL
    assert m.risk_level == reg.RISK_LOW
    assert m.requires_secret is False
    assert m.requires_browser is False
    assert m.read_only is True

    m = reg.get_meta("excel_write_report_copy")
    assert m.category == reg.CATEGORY_EXCEL
    assert m.risk_level in (reg.RISK_LOW, reg.RISK_MEDIUM)
    assert m.requires_secret is False
    assert m.requires_browser is False
    assert m.read_only is False

    # Excel 2단계 — 둘 다 read-only / low / 브라우저 없음
    for a in ("excel_describe_workbook", "excel_read_table"):
        m = reg.get_meta(a)
        assert m.category == reg.CATEGORY_EXCEL
        assert m.risk_level == reg.RISK_LOW
        assert m.requires_secret is False
        assert m.requires_browser is False
        assert m.read_only is True

    assert reg.category_of("ping") == reg.CATEGORY_SYSTEM
    assert reg.category_of("get_system_info") == reg.CATEGORY_SYSTEM
    assert reg.category_of("open_page_readonly") == reg.CATEGORY_WEB
    assert reg.category_of("inspect_page") == reg.CATEGORY_WEB
    assert reg.category_of("login_with_secret") == reg.CATEGORY_SECRET
    assert reg.category_of("inspect_after_login") == reg.CATEGORY_SECRET

    # 시크릿 action 은 secret/browser 둘 다 요구
    for a in ("login_with_secret", "inspect_after_login"):
        m = reg.get_meta(a)
        assert m.requires_secret is True
        assert m.requires_browser is True
        assert m.risk_level == reg.RISK_HIGH

    # 웹 action 은 secret 불필요, 브라우저 필요
    for a in ("open_page_readonly", "inspect_page"):
        m = reg.get_meta(a)
        assert m.requires_secret is False
        assert m.requires_browser is True
        assert m.read_only is True
        assert m.risk_level == reg.RISK_LOW

    # 시스템 action 은 둘 다 불필요
    for a in ("ping", "get_system_info"):
        m = reg.get_meta(a)
        assert m.requires_secret is False
        assert m.requires_browser is False
        assert m.read_only is True
        assert m.risk_level == reg.RISK_LOW

    # 미등록 action
    assert reg.get_meta("nope") is None
    assert reg.is_known_action("ping") is True
    assert reg.is_known_action("nope") is False
    assert reg.category_of("nope") == reg.CATEGORY_UNKNOWN
    assert reg.risk_of("nope") == reg.RISK_UNKNOWN


def test_policy_allowed_actions_match_registry():
    from agent import action_registry as reg
    from agent import policy
    assert set(policy.ALLOWED_ACTIONS) == set(reg.list_actions())


# ══════════════════════════════════════════════════════════════════════
# 4) 로그 entry 공통 필드
# ══════════════════════════════════════════════════════════════════════
_LOG_COMMON_KEYS = {
    "action", "category", "risk_level",
    "site_key", "target_url",
    "ok", "duration_ms", "timestamp",
}


def test_log_entry_common_fields_for_ping(tmp_path):
    from agent import app
    app.run("ping")
    entries = _read_log(tmp_path)
    assert entries, "no log entry emitted"
    last = entries[-1]
    assert _LOG_COMMON_KEYS.issubset(last.keys()), (
        f"missing keys: {_LOG_COMMON_KEYS - set(last.keys())}"
    )
    assert last["action"] == "ping"
    assert last["category"] == "system"
    assert last["risk_level"] == "low"
    assert last["ok"] is True
    assert isinstance(last["duration_ms"], int)


def test_log_entry_common_fields_for_web_action(monkeypatch, tmp_path):
    from agent import app
    _install_fake_playwright(monkeypatch, page=_FakePage())
    app.run("inspect_page", url="https://www.example.com/")
    entries = _read_log(tmp_path)
    last = entries[-1]
    assert _LOG_COMMON_KEYS.issubset(last.keys())
    assert last["action"] == "inspect_page"
    assert last["category"] == "web"
    assert last["risk_level"] == "low"
    assert last["ok"] is True


def test_log_entry_common_fields_for_blocked_action(tmp_path):
    from agent import app
    app.run("signup")
    entries = _read_log(tmp_path)
    last = entries[-1]
    assert _LOG_COMMON_KEYS.issubset(last.keys())
    assert last["action"] == "signup"
    # 알 수 없는 action 이어도 category/risk_level 필드는 존재한다
    assert last["category"] == "unknown"
    assert last["risk_level"] == "unknown"
    assert last["ok"] is False
    assert last["blocked_reason"] == app.ERR_ACTION_NOT_ALLOWED


# ══════════════════════════════════════════════════════════════════════
# 5) 기존 차단 정책 회귀 — 표준화 후에도 동일하게 차단되어야 한다
# ══════════════════════════════════════════════════════════════════════
def test_regression_host_path_profile_secret(monkeypatch):
    from agent import app, errors, site_profiles as sp
    from agent.secrets import store as secret_store

    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

    # (a) profile 없음 → site_profile_not_found
    out = app.run("login_with_secret", site_key="ghost")
    assert out["error"] == errors.SITE_PROFILE_NOT_FOUND

    # (b) host 미허용 → host_not_allowed
    sp.register_profile(sp.SiteProfile(
        site_key="s1",
        login_url="https://evil.example.com/login",
        username_selector="#u",
        password_selector="#p",
        submit_selector="#btn",
        success_check=sp.SuccessCheck(kind="url", value="/home"),
        allowed_hosts=("whitelisted.example.com",),
    ))
    secret_store.save_secret("s1", "alice", "PW-XYZ-UNIQUE")
    out = app.run("login_with_secret", site_key="s1")
    assert out["error"] == errors.HOST_NOT_ALLOWED

    # (c) secret 없음 → secret_not_found
    sp.register_profile(sp.SiteProfile(
        site_key="s2",
        login_url="https://example.com/login",
        username_selector="#u",
        password_selector="#p",
        submit_selector="#btn",
        success_check=sp.SuccessCheck(kind="url", value="/home"),
        allowed_hosts=("example.com",),
    ))
    out = app.run("login_with_secret", site_key="s2")
    assert out["error"] == errors.SECRET_NOT_FOUND

    # (d) inspect_after_login target path 미허용
    sp.register_profile(sp.SiteProfile(
        site_key="s3",
        login_url="https://example.com/login",
        username_selector="#u",
        password_selector="#p",
        submit_selector="#btn",
        success_check=sp.SuccessCheck(kind="url", value="/home"),
        allowed_hosts=("example.com",),
        post_login_allowed_paths=("/mypage",),
    ))
    secret_store.save_secret("s3", "alice", "PW-XYZ-UNIQUE-2")
    out = app.run(
        "inspect_after_login",
        site_key="s3",
        target_url="https://example.com/admin",
    )
    assert out["error"] == errors.TARGET_PATH_NOT_ALLOWED


# ══════════════════════════════════════════════════════════════════════
# 6) 민감정보 미노출 — category="secret" 가 들어가도 banned 키 누출 없음
# ══════════════════════════════════════════════════════════════════════
def test_logs_do_not_leak_sensitive_words_even_with_category_field(
    tmp_path, monkeypatch
):
    from agent import app
    # ping/get_system_info/signup/login_with_secret(실패) 모두 기록
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    app.run("ping")
    app.run("get_system_info")
    app.run("signup", url="http://user:pw@example.com/")
    app.run("login_with_secret", site_key="ghost")

    raw = (tmp_path / "agent_actions.jsonl").read_text(encoding="utf-8")
    for banned in ("password", "token", "cookie", "authorization", "session"):
        assert banned not in raw.lower(), f"banned '{banned}' leaked in log"
    # userinfo 가 URL 에 섞여 들어와도 로그에서 제거되어야 한다
    assert "pw@" not in raw
    assert "user:pw" not in raw


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
