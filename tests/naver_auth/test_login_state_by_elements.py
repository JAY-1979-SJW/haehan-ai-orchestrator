"""로그인 상태를 '눈에 보이는 요소 + 세션 쿠키 이름'으로 판정 + 사이트맵 경고 게이트.

기준서: docs/specs/2026-09-30_login_state_by_element_and_sitemap_gate.md (v3)
회귀 fixture 는 2026-09-30 실제 로그아웃 화면을 축소한 것 — 숨은 로그아웃 요소와 본문의 "○○○ 님" 이
로그인/다른 사용자로 오판되던 결함을 잠근다.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_orchestrator.connectors.naver_auth import login_pipeline as pipeline
from scripts.auth import login_detector as ld
from scripts.explorer import page_analysis, page_snapshot
from tools.write_gates import sitemap_gate

FIXTURE = Path(__file__).parent.parent / "fixtures" / "login_state" / "naver_logged_out_blog_home.json"
NAVER_URL = "https://section.blog.naver.com/BlogHome.naver"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _snapshot(*, links=(), buttons=()) -> dict:
    return {
        "url": NAVER_URL,
        "title": "t",
        "frames": [{"idx": 0, "links": list(links), "buttons": list(buttons), "inputs": []}],
    }


class _LoginProbePage:
    """login_detector 가 만지는 부분만 흉내 — 쿠키 이름 목록과 evaluate."""

    frames: list = []
    main_frame = None

    def __init__(self, url: str = NAVER_URL, cookies: tuple[str, ...] = ()):
        self.url = url
        self.context = SimpleNamespace(cookies=lambda: [{"name": n, "value": "SECRET"} for n in cookies])

    def evaluate(self, *_a, **_k):
        return {"logged_in": False, "score": 0, "url": self.url, "on_login_page": False}


@pytest.fixture
def use_snapshot(monkeypatch):
    def _apply(snapshot: dict) -> None:
        monkeypatch.setattr(page_snapshot, "collect", lambda _page: snapshot)

    return _apply


# ── 판정 규칙 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("login_visible", "in_visible", "cookie", "expected"),
    [
        (True, False, False, "out"),
        (True, False, None, "out"),
        (False, True, True, "in"),
        (False, True, None, "in"),
        (True, False, True, "unknown"),  # 로그인 버튼이 보이는데 세션 쿠키가 있음 → 충돌
        (False, True, False, "unknown"),  # 로그아웃이 보이는데 쿠키가 없음 → 충돌
        (True, True, None, "unknown"),
        (False, False, True, "unknown"),  # 화면 근거 없음
        (False, False, False, "unknown"),  # 빈 화면/로딩 중 — 추측 금지
    ],
)
def test_decide_login_state(login_visible, in_visible, cookie, expected):
    assert ld.decide_login_state(login_visible, in_visible, cookie) == expected


# ── 실제 화면 회귀 ───────────────────────────────────────────────────────


def test_fixture_hidden_logout_elements_are_not_counted():
    sig = page_analysis.element_login_signals(page_analysis.analyze_snapshot(_fixture()))
    assert sig["login_visible"] >= 1
    assert sig["in_visible"] == 0
    assert sig["in_hidden"] >= 1  # 숨은 로그아웃/계정 요소는 있지만 근거로 세지 않는다


def test_logged_out_screen_is_out_and_user_is_none(use_snapshot):
    use_snapshot(_fixture())  # 본문에 "가상이름 님" 링크가 들어 있다
    result = ld.detect_login_state(_LoginProbePage())
    assert (result["state"], result["logged_in"], result["user"], result["method"]) == ("out", False, None, "element")


LOGGED_IN_FIXTURE = Path(__file__).parent.parent / "fixtures" / "login_state" / "naver_logged_in_home.json"


def _logged_in_fixture() -> dict:
    return json.loads(LOGGED_IN_FIXTURE.read_text(encoding="utf-8"))


def test_real_logged_in_screen_is_in(use_snapshot):
    """2026-09-30 실제 로그인 화면: 보이는 로그아웃 + 세션 쿠키. 화면에만 있는 "로그인 보호 설정" 링크는 로그인 버튼이 아니다."""
    use_snapshot(_logged_in_fixture())
    result = ld.detect_login_state(_LoginProbePage(cookies=("NID_AUT", "NID_SES")))
    assert (result["state"], result["logged_in"], result["user"]) == ("in", True, None)
    assert result["evidence"]["login_button_visible"] == 0
    assert result["evidence"]["logout_or_account_visible"] == 1


def test_real_logged_in_screen_without_cookies_is_a_conflict(use_snapshot):
    use_snapshot(_logged_in_fixture())
    assert ld.detect_login_state(_LoginProbePage())["state"] == "unknown"


@pytest.mark.parametrize(
    "label", ["로그인 보호 설정", "로그인 도움말", "로그인 상태 유지", "로그인 기록", "로그인 방법 안내"]
)
def test_links_that_only_mention_login_are_not_login_buttons(label):
    snap = _snapshot(links=[{"text": label, "href": "/x", "visible": True}])
    assert page_analysis.element_login_signals(page_analysis.analyze_snapshot(snap))["login_visible"] == 0


@pytest.mark.parametrize("label", ["로그인", "로그인하기", "NAVER 로그인", "패스키 로그인", "Log in"])
def test_real_login_buttons_still_count(label):
    snap = _snapshot(buttons=[{"text": label, "visible": True}])
    assert page_analysis.element_login_signals(page_analysis.analyze_snapshot(snap))["login_visible"] == 1


def test_session_cookie_conflict_is_unknown_not_logged_in(use_snapshot):
    use_snapshot(_fixture())
    result = ld.detect_login_state(_LoginProbePage(cookies=("NID_AUT", "NID_SES")))
    assert result["state"] == "unknown"
    assert result["logged_in"] is False
    assert result["evidence"]["session_cookie"] is True


def test_visible_logout_with_session_cookies_is_in(use_snapshot):
    use_snapshot(_snapshot(buttons=[{"text": "로그아웃", "visible": True}]))
    result = ld.detect_login_state(_LoginProbePage(cookies=("NID_AUT", "NID_SES")))
    assert result["state"] == "in"
    assert result["logged_in"] is True
    assert result["user"] is None  # 계정 표시 영역 셀렉터가 없으면 이름은 읽지 않는다


def test_long_sentence_link_is_not_a_login_button():
    long_link = {
        "text": "2026년 9월 캘린더 - 이번 달 로그인하기 전에 확인할 수 있는 날짜 안내",
        "href": "/x",
        "visible": True,
    }
    sig = page_analysis.element_login_signals(page_analysis.analyze_snapshot(_snapshot(links=[long_link])))
    assert sig["login_visible"] == 0


def test_only_hidden_logout_is_not_in(use_snapshot):
    use_snapshot(_snapshot(buttons=[{"text": "로그아웃", "visible": False}]))
    assert ld.detect_login_state(_LoginProbePage())["state"] == "unknown"


def test_one_session_cookie_is_not_enough(use_snapshot):
    use_snapshot(_snapshot(buttons=[{"text": "로그아웃", "visible": True}]))
    result = ld.detect_login_state(_LoginProbePage(cookies=("NID_AUT",)))  # NID_SES 없음 → cookie False → 충돌
    assert result["state"] == "unknown"


def test_cookie_values_never_appear_in_result(use_snapshot):
    use_snapshot(_snapshot(buttons=[{"text": "로그아웃", "visible": True}]))
    result = ld.detect_login_state(_LoginProbePage(cookies=("NID_AUT", "NID_SES")))
    assert "SECRET" not in json.dumps(result, ensure_ascii=False)


def test_detect_login_on_current_tab_ignores_body_text_for_profile_sites(use_snapshot):
    use_snapshot(_fixture())
    page = _LoginProbePage()
    page.evaluate = lambda *_a, **_k: "로그아웃 상태입니다 로그아웃"  # 본문 문구 — 예전엔 이것만으로 True
    assert ld.detect_login_on_current_tab(page) == (False, None)


# ── 프로필 없는 사이트는 종전 동작 ────────────────────────────────────────


def test_site_without_profile_keeps_legacy_path(monkeypatch):
    called = []
    monkeypatch.setattr(page_snapshot, "collect", lambda _p: called.append(1) or {})
    page = _LoginProbePage(url="https://accounts.google.com/")
    page.evaluate = lambda *_a, **_k: {"logged_in": True, "score": 5, "url": page.url, "user_block": "Kim"}
    result = ld.detect_login_state(page)
    assert (result["logged_in"], result["user"], result["method"]) == (True, "Kim", "heuristic")
    assert called == []


# ── 프로필·수집 계약 ─────────────────────────────────────────────────────


def test_profiles_are_well_formed_and_never_store_secrets():
    sites = ld._load_probes()
    assert "naver" in sites
    for name, profile in sites.items():
        assert profile["hosts"], name
        assert all(isinstance(c, str) for c in profile.get("session_cookies", [])), name
        assert profile.get("account_selector") is None or isinstance(profile["account_selector"], str), name


def test_snapshot_collects_visibility_for_links():
    assert "visible: a.offsetParent" in page_snapshot._EXTRACT_FRAME_JS


@pytest.mark.parametrize(("label", "role"), [("로그아웃", "logout"), ("내 블로그", "account"), ("로그인", "login")])
def test_new_roles(label, role):
    assert page_analysis.classify_role("button", label) == role


# ── 파이프라인: 판정 불가일 때 새로 로그인하지 않는다 ─────────────────────


@pytest.fixture
def pipeline_env(monkeypatch):
    monkeypatch.setattr(pipeline, "_save_status", lambda *_a, **_k: None)
    monkeypatch.setattr(pipeline, "_save_browser_session", lambda *_a, **_k: None)

    def _set(state: dict) -> None:
        monkeypatch.setattr(ld, "detect_login_state", lambda _page: state)

    return _set


def test_pipeline_unknown_with_cookie_stops(pipeline_env):
    pipeline_env({"logged_in": False, "state": "unknown", "evidence": {"session_cookie": True}})
    result = pipeline._check_existing_login(object())
    assert result is not None
    assert result["ok"] is False


def test_pipeline_out_proceeds_to_login(pipeline_env):
    pipeline_env({"logged_in": False, "state": "out", "evidence": {"session_cookie": False}})
    assert pipeline._check_existing_login(object()) is None


def test_pipeline_unknown_without_cookie_proceeds_to_login(pipeline_env):
    pipeline_env({"logged_in": False, "state": "unknown", "evidence": {"session_cookie": False}})
    assert pipeline._check_existing_login(object()) is None


def test_pipeline_already_logged_in_returns_ok(pipeline_env):
    pipeline_env({"logged_in": True, "state": "in", "user": None, "evidence": {}})
    result = pipeline._check_existing_login(object())
    assert result
    assert result["ok"] is True


# ── 사이트맵 경고 게이트 ─────────────────────────────────────────────────

AUTO_PATH = "scripts/naver/x/foo.py"


@pytest.fixture
def gate_env(tmp_path, monkeypatch):
    monkeypatch.setattr(sitemap_gate, "SITEMAP_DIR", tmp_path / "sitemap")
    monkeypatch.setattr(sitemap_gate, "LOG_PATH", tmp_path / "gate.jsonl")
    (tmp_path / "sitemap").mkdir()
    return tmp_path


def test_gate_warns_when_no_sitemap(gate_env):
    msg = sitemap_gate.warn(AUTO_PATH, 'page.goto("https://shop.example-none.com"); page.locator("a")')
    assert msg
    assert "shop.example-none.com" in msg
    assert json.loads((gate_env / "gate.jsonl").read_text(encoding="utf-8").splitlines()[-1])["result"] == "warn"


def test_gate_passes_when_sitemap_exists(gate_env):
    (gate_env / "sitemap" / "www.naver.com_.json").write_text("{}", encoding="utf-8")
    assert sitemap_gate.warn(AUTO_PATH, 'page.goto("https://www.naver.com"); page.locator("a")') is None


def test_gate_matches_parent_domain(gate_env):
    (gate_env / "sitemap" / "nid.naver.com_nidlogin.login.json").write_text("{}", encoding="utf-8")
    assert sitemap_gate.warn(AUTO_PATH, 'goto("https://blog.naver.com"); locator("a")') is None


def test_gate_does_not_treat_public_suffix_as_sitemap(gate_env):
    (gate_env / "sitemap" / "other.or.kr_.json").write_text("{}", encoding="utf-8")
    assert sitemap_gate.warn(AUTO_PATH, 'goto("https://eum.cw.or.kr"); locator("a")')


def test_gate_ignores_non_selector_code_and_other_paths(gate_env):
    assert sitemap_gate.warn(AUTO_PATH, 'x = "https://shop.example-none.com"') is None
    assert sitemap_gate.warn("scripts/other/x.py", 'locator("a") "https://shop.example-none.com"') is None


def test_gate_never_blocks(gate_env):
    assert sitemap_gate.check(AUTO_PATH, 'locator("a") "https://shop.example-none.com"') is None
