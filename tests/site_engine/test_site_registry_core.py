"""사이트 등록표(scripts/site_registry) — 동작 고정 테스트.

결함 #113: L4 범용 엔진(cdp_client·login_session·site_access)이 사이트별 지식이 가득한 등록표를 import 하는 구조를 바꾸기 위해
등록표를 "코어(조회·등록)"와 "L5 사이트 모듈(사이트별 로그인 래퍼)"로 나눈다. 이 파일의 앞부분은 **분리 전 현재 동작을 그대로 고정**하고
(분리 후에도 통과해야 한다), 뒷부분은 분리된 구조의 계약을 검증한다. 브라우저·네트워크·로그인을 실행하지 않는다(가짜 page).
"""

from __future__ import annotations

import inspect

import pytest

from scripts.site_engine import site_registry as reg

EXPECTED_ORDER = ["eum", "naver", "smartstore", "google", "hiworks", "gabia", "kakao"]

EXPECTED_FIELDS = {
    "eum": (
        "https://eum.cw.or.kr/main",
        ("eum.cw.or.kr/web/log/WEBLOG400M00", "eum.cw.or.kr/login", "eum.cw.or.kr/web/login"),
        "registered_only",
    ),
    "naver": ("https://www.naver.com", ("nid.naver.com", "/nidlogin"), "registered_only"),
    "smartstore": (
        "https://sell.smartstore.naver.com/#/home/dashboard",
        ("sell.smartstore.naver.com", "nid.naver.com", "/nidlogin"),
        "manual_only",
    ),
    "google": ("https://www.google.com", ("accounts.google.com",), "registered_only"),
    "hiworks": (
        "https://dashboard.office.hiworks.com/",
        ("login.office.hiworks.com", "office.hiworks.com"),
        "manual_only",
    ),
    "gabia": ("https://www.gabia.com", ("account.gabia.com",), "manual_only"),
    "kakao": ("https://www.kakao.com", ("accounts.kakao.com",), "manual_only"),
}


# ── 분리 전후 공통: 현재 동작 고정 ──────────────────────────────────────────


def test_list_sites_order_is_preserved():
    assert reg.list_sites() == EXPECTED_ORDER


@pytest.mark.parametrize("key", EXPECTED_ORDER)
def test_site_metadata_is_unchanged(key):
    spec = reg.get_site(key)
    base_url, hints, strategy = EXPECTED_FIELDS[key]
    assert spec is not None and spec.key == key
    assert (spec.base_url, spec.login_domain_hints, spec.login_strategy) == (base_url, hints, strategy)
    assert callable(spec.login) and callable(spec.is_logged_in)


def test_unknown_site_is_none():
    assert reg.get_site("없는사이트") is None and reg.get_site("") is None


def test_only_naver_login_accepts_force_login():
    """site_access.py:462 가 login(page, force_login=...) 를 먼저 시도하고 TypeError 면 login(page) 로 되돌아간다."""
    sig = inspect.signature(reg.get_site("naver").login)
    assert "force_login" in sig.parameters and sig.parameters["force_login"].kind is inspect.Parameter.KEYWORD_ONLY
    for key in EXPECTED_ORDER:
        if key != "naver":
            assert "force_login" not in inspect.signature(reg.get_site(key).login).parameters, key


class FakePage:
    def __init__(self, url="", text="", fail=False):
        self.url, self._text, self._fail = url, text, fail

    def locator(self, selector):
        return self

    def inner_text(self, timeout=0):
        if self._fail:
            raise RuntimeError("page closed")
        return self._text

    def evaluate(self, script):
        raise RuntimeError("page closed")


def test_hiworks_login_state_rules():
    check = reg.get_site("hiworks").is_logged_in
    assert check(FakePage(url="https://login.office.hiworks.com/x")) is False
    assert check(FakePage(url="https://example.com")) is False
    assert check(FakePage(url="https://dashboard.office.hiworks.com/", text="오피스 홈 메일 전자결재")) is True
    assert check(FakePage(url="https://dashboard.office.hiworks.com/", text="아무것도 없음")) is False
    assert check(FakePage(url="https://dashboard.office.hiworks.com/", fail=True)) is False  # 예외는 로그인 안 됨으로


def test_smartstore_state_check_fails_closed_on_errors():
    assert reg.get_site("smartstore").is_logged_in(FakePage(fail=True)) is False


def test_manual_only_logins_return_the_manual_schema():
    smart = reg.get_site("smartstore").login(object())
    assert smart == {"ok": False, "reason": "manual_smartstore_login_required", "user": "", "needs_manual": True}
    hiworks = reg.get_site("hiworks").login(object())
    assert hiworks["ok"] is False and hiworks["needs_manual"] is True and callable(hiworks["monitor"])


def test_naver_login_wrapper_maps_the_result_to_the_common_schema(monkeypatch):
    seen = {}

    def fake_login_naver(page, **kwargs):
        seen.update(kwargs)
        return {"logged_in": True, "user": "skyjwsin", "captcha": False}

    monkeypatch.setattr("scripts.naver.common.auth.login_naver", fake_login_naver)
    result = reg.get_site("naver").login(object(), force_login=True)
    assert result == {"ok": True, "reason": "", "user": "skyjwsin", "needs_manual": False}
    assert seen == {"wait_for_user_s": 10, "force_relogin": True}


def test_naver_login_wrapper_flags_captcha_as_manual(monkeypatch):
    monkeypatch.setattr(
        "scripts.naver.common.auth.login_naver",
        lambda page, **kw: {"ok": False, "captcha_required": True, "reason": "captcha"},
    )
    result = reg.get_site("naver").login(object())
    assert result["ok"] is False and result["needs_manual"] is True and result["reason"] == "captcha"


def test_google_login_wrapper_maps_the_result(monkeypatch):
    monkeypatch.setattr(
        "scripts.google.auth.login_google", lambda page, **kw: {"ok": True, "user": "g", "challenge": True}
    )
    assert reg.get_site("google").login(object()) == {"ok": True, "reason": "", "user": "g", "needs_manual": True}


@pytest.mark.parametrize(
    ("key", "module"), [("eum", "scripts.eum.auth"), ("gabia", "scripts.gabia.auth"), ("kakao", "scripts.kakao.auth")]
)
def test_plain_wrappers_delegate_to_the_site_module(monkeypatch, key, module):
    monkeypatch.setattr(f"{module}.is_logged_in", lambda page: "STATE")
    monkeypatch.setattr(f"{module}.login", lambda page: {"ok": True, "via": key})
    spec = reg.get_site(key)
    assert spec.is_logged_in(object()) == "STATE" and spec.login(object()) == {"ok": True, "via": key}


@pytest.mark.parametrize("key", ["naver", "google"])
def test_detector_based_state_check_uses_the_logged_in_flag(monkeypatch, key):
    monkeypatch.setattr("scripts.auth.login_detector.detect_login_state", lambda page: {"logged_in": True})
    assert reg.get_site(key).is_logged_in(object()) is True
    monkeypatch.setattr("scripts.auth.login_detector.detect_login_state", lambda page: {})
    assert reg.get_site(key).is_logged_in(object()) is False


# ── 분리된 구조의 계약 (코어 ↔ L5 사이트 모듈) ──────────────────────────────


@pytest.fixture
def clean_registry(monkeypatch):
    """코어의 전역 상태(등록표·로드 플래그·공급자)를 격리하고 끝나면 원래대로 돌려놓는다. 공급자는 실제 사이트 목록으로 둔다."""
    from scripts.entry import site_login_registry as sites

    monkeypatch.setattr(reg, "_REGISTRY", {})
    monkeypatch.setattr(reg, "_loaded", False)
    monkeypatch.setattr(reg, "_loading", False)
    monkeypatch.setattr(reg, "_provider", sites.build_sites)


def _spec(key):
    return reg.SiteSpec(
        key=key, base_url="https://x", login_domain_hints=(), is_logged_in=lambda p: True, login=lambda p: {}
    )


def test_core_never_imports_the_site_module_or_the_composition():
    """L4 코어가 사이트 모듈·조합 모듈을 import 하지 않고, 문자열 로더(importlib)도 쓰지 않는다."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path(reg.__file__).read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any(m.startswith(("scripts.entry", "scripts.eum", "scripts.naver", "importlib")) for m in imported), imported
    assert not hasattr(reg, "_LOADER")


def test_composition_module_does_not_import_site_modules_at_top_level():
    """조합 모듈은 코어(configure)만 정적으로 import 한다 — 사이트 auth 모듈은 로그인 호출 때에 불러온다."""
    import ast
    import pathlib

    from scripts.entry import site_login_registry as sites

    tree = ast.parse(pathlib.Path(sites.__file__).read_text(encoding="utf-8"))
    top = [n.module or "" for n in tree.body if isinstance(n, ast.ImportFrom)]
    assert top == ["__future__", "scripts.site_engine"], top


def test_unconfigured_lookup_fails_loudly_instead_of_returning_nothing(monkeypatch):
    """진입점이 install 을 빠뜨리면 조용히 빈 목록/None 이 아니라 RuntimeError 로 알린다(자동 로그인이 말없이 꺼지지 않게)."""
    monkeypatch.setattr(reg, "_REGISTRY", {})
    monkeypatch.setattr(reg, "_loaded", False)
    monkeypatch.setattr(reg, "_loading", False)
    monkeypatch.setattr(reg, "_provider", None)
    for call in (lambda: reg.get_site("eum"), reg.list_sites):
        with pytest.raises(RuntimeError, match="install"):
            call()
    assert reg._REGISTRY == {} and reg.is_configured() is False


def test_install_configures_the_core_and_is_idempotent(monkeypatch):
    from scripts.entry import site_login_registry as sites

    monkeypatch.setattr(reg, "_REGISTRY", {})
    monkeypatch.setattr(reg, "_loaded", False)
    monkeypatch.setattr(reg, "_loading", False)
    monkeypatch.setattr(reg, "_provider", None)
    sites.install()
    first = reg.get_site("eum")
    sites.install()  # 다시 불러도 이미 로드된 등록표를 지우지 않는다
    assert reg.is_configured() and reg.get_site("eum") is first and reg.list_sites() == EXPECTED_ORDER


def test_configure_with_a_different_provider_resets_the_registry(clean_registry):
    assert reg.list_sites() == EXPECTED_ORDER
    reg.configure(lambda spec_cls: [spec_cls(key="only", base_url="x", login_domain_hints=(), is_logged_in=bool, login=dict)])
    assert reg.list_sites() == ["only"]


def test_first_lookup_loads_the_sites_once_and_in_order(clean_registry):
    assert reg._REGISTRY == {}  # 조회 전에는 비어 있다
    assert reg.list_sites() == EXPECTED_ORDER
    first = reg.get_site("eum")
    assert reg.list_sites() == EXPECTED_ORDER and reg.get_site("eum") is first  # 두 번째 조회가 다시 등록하지 않는다


def test_ensure_loaded_is_idempotent(clean_registry):
    reg._ensure_loaded()
    reg._ensure_loaded()
    assert reg.list_sites() == EXPECTED_ORDER


def test_register_site_rejects_duplicates_instead_of_overwriting(clean_registry):
    reg.register_site(_spec("custom"))
    with pytest.raises(ValueError, match="custom"):
        reg.register_site(_spec("custom"))


def test_extra_sites_can_be_registered_and_appear_after_the_built_in_ones(clean_registry):
    reg.register_site(_spec("custom"))
    assert reg.list_sites() == ["custom", *EXPECTED_ORDER]  # 직접 등록은 로드 전에도 가능하고, 조회가 나머지를 채운다


def test_provider_failure_is_not_swallowed_and_leaves_nothing_half_registered(clean_registry):
    from scripts.entry import site_login_registry as sites

    def broken(spec_cls):
        raise ImportError("no such site module for test")

    reg.configure(broken)
    with pytest.raises(ImportError):
        reg.get_site("eum")
    assert reg._REGISTRY == {} and reg._loaded is False
    reg.configure(sites.build_sites)  # 고치면 다음 호출에서 정상 로드된다
    assert reg.list_sites() == EXPECTED_ORDER


def test_a_failure_after_some_sites_were_registered_rolls_them_back(clean_registry):
    """공급자가 일부를 만든 뒤 실패하면(예: 항목이 None) 이미 등록된 것도 지워 반쪽 상태를 남기지 않는다."""

    def build(spec_cls):
        return [
            spec_cls(key="a", base_url="x", login_domain_hints=(), is_logged_in=bool, login=dict),
            None,
        ]  # 두 번째 항목에서 실패

    reg.configure(build)
    with pytest.raises(AttributeError):
        reg.list_sites()
    assert reg._REGISTRY == {} and reg._loaded is False


def test_a_conflicting_site_loaded_from_the_provider_rolls_everything_back(clean_registry):
    reg.register_site(_spec("naver"))  # 공급자가 등록하려는 키와 충돌
    with pytest.raises(ValueError, match="naver"):
        reg.list_sites()
    assert reg._loaded is False  # 불완전한 상태로 '로드됨' 표시를 남기지 않는다


def test_build_sites_uses_the_class_it_is_given():
    from scripts.entry import site_login_registry as sites

    built = sites.build_sites(lambda **kw: kw)
    assert [b["key"] for b in built] == EXPECTED_ORDER and all("login_strategy" in b for b in built)


# ── 미구성(install 누락)이 자동 로그인 경로에서 조용히 삼켜지지 않는다 ─────────────────────────


@pytest.fixture
def unconfigured(monkeypatch):
    monkeypatch.setattr(reg, "_REGISTRY", {})
    monkeypatch.setattr(reg, "_loaded", False)
    monkeypatch.setattr(reg, "_loading", False)
    monkeypatch.setattr(reg, "_provider", None)


def test_auto_login_does_not_swallow_the_unconfigured_error(unconfigured):
    """_auto_login 이 '등록표 없음' 을 '자동 로그인 실패 → 사용자 대기' 로 바꿔 버리면 install 누락이 로그인 대기로 숨는다."""
    from scripts.site_engine import login_session

    with pytest.raises(RuntimeError, match="install"):
        login_session._auto_login(object(), "naver")


def test_ensure_login_propagates_the_unconfigured_error(unconfigured, monkeypatch):
    from scripts.site_engine import login_session

    monkeypatch.setattr(login_session, "is_logged_in", lambda page, site: False)
    with pytest.raises(RuntimeError, match="install"):
        login_session.ensure_login(object(), "naver", wait_seconds=1)


def test_open_site_propagates_the_unconfigured_error(unconfigured):
    from scripts.site_engine import site_access

    with pytest.raises(RuntimeError, match="install"):
        site_access.open_site("eum")
