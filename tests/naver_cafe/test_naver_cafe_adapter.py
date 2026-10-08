"""NaverCafeAdapter — 로그인 판정 / 재인증 / 재개 / 최소 목록 파서 검증.

모든 테스트는 실제 네이버에 접속하지 않는다. fake page/element 기반.
자격증명은 픽스처에도 포함하지 않는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pytest

from ai_orchestrator.sites import job_state, runner, session_manager
from ai_orchestrator.sites.adapters.naver_cafe_adapter import (
    STATUS_LIST_PARSE_OK,
    STATUS_LOGIN_CHECK_FAILED,
    NaverCafeAdapter,
)
from ai_orchestrator.sites.site_adapter import LoginCheckResult


# ── Fake DOM ────────────────────────────────────────────────────
@dataclass
class FakeEl:
    text: str = ""
    attrs: dict = field(default_factory=dict)

    def inner_text(self) -> str:
        return self.text

    def get_attribute(self, name: str) -> str:
        return self.attrs.get(name, "")


@dataclass
class FakeRow:
    link: FakeEl | None = None
    author: FakeEl | None = None
    date: FakeEl | None = None

    def query_selector(self, selector: str):
        # 어댑터의 LINK_SELECTOR / AUTHOR_SELECTOR / DATE_SELECTOR 를 매칭
        if selector == NaverCafeAdapter.LINK_SELECTOR:
            return self.link
        if selector == NaverCafeAdapter.AUTHOR_SELECTOR:
            return self.author
        if selector == NaverCafeAdapter.DATE_SELECTOR:
            return self.date
        return None


@dataclass
class FakePage:
    url: str = ""
    visible_selectors: set = field(default_factory=set)
    rows: list = field(default_factory=list)  # list[FakeRow]
    history: list = field(default_factory=list)

    def goto(self, target: str) -> None:
        self.history.append(("goto", target))
        self.url = target

    def query_selector(self, selector: str):
        return object() if selector in self.visible_selectors else None

    def query_selector_all(self, selector: str):
        if selector == NaverCafeAdapter.ROW_SELECTOR:
            return list(self.rows)
        return []


# ── Fixtures ────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_ROOT", str(tmp_path / "secrets"))
    monkeypatch.setattr(job_state, "_JOBS_PATH", tmp_path / "site_jobs.jsonl")
    job_state.clear()
    session_manager.clear_meta_for_tests("naver_cafe")
    yield


def _fake_sleeper():
    def _sleep(_secs: float) -> None:
        return None

    return _sleep


def _counting_clock():
    n = {"v": 0}

    def clock() -> float:
        n["v"] += 1
        return float(n["v"])

    return clock


# ──────────────────────────────────────────────────────────────────
# 1) 로그인 페이지 감지 → is_logged_in=False (redirected_to_login)
# ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "url",
    [
        "https://nid.naver.com/nidlogin.login",
        "https://nid.naver.com/nidlogin.login?mode=form&url=https://cafe.naver.com/",
        "https://nid.naver.com/login/",
    ],
)
def test_login_page_detected(url):
    adapter = NaverCafeAdapter()
    page = FakePage(url=url)
    r = adapter.check_logged_in(page)
    assert r.is_logged_in is False
    assert r.reason == "redirected_to_login"
    assert any(s.startswith("login_url_hint:") for s in r.matched_signals)


# ──────────────────────────────────────────────────────────────────
# 2) 2차 인증/추가 확인 페이지 → REAUTH_REQUIRED (보수적)
# ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "url",
    [
        "https://nid.naver.com/login2/confirm",
        "https://nid.naver.com/otp/input",
        "https://nid.naver.com/user2/verify?returnUrl=https://cafe.naver.com/",
        "https://nid.naver.com/push/nidlogin_otp",
        "https://nid.naver.com/login/ext/device/confirm",
        "https://nid.naver.com/ivp/check",
    ],
)
def test_reauth_page_detected_conservatively(url):
    adapter = NaverCafeAdapter()
    page = FakePage(url=url)
    r = adapter.check_logged_in(page)
    assert r.is_logged_in is False
    assert r.reason == "reauth_required"
    assert any(s.startswith("reauth_url_hint:") for s in r.matched_signals)


# ──────────────────────────────────────────────────────────────────
# 3) 쿠키/호스트만으로는 로그인으로 판정되지 않는다
# ──────────────────────────────────────────────────────────────────
def test_cookie_only_rejected_no_dom_signal():
    adapter = NaverCafeAdapter()
    # URL 은 카페 메인, 리다이렉트도 없음. 하지만 GNB 로그아웃 버튼 없음.
    page = FakePage(url="https://cafe.naver.com/some_cafe", visible_selectors=set())
    r = adapter.check_logged_in(page)
    assert r.is_logged_in is False
    assert r.reason == "no_user_menu"
    assert r.matched_signals == []


# ──────────────────────────────────────────────────────────────────
# 4) 로그인 상태 신호 존재 시 is_logged_in=True
# ──────────────────────────────────────────────────────────────────
def test_logged_in_when_gnb_logout_visible():
    adapter = NaverCafeAdapter()
    page = FakePage(
        url="https://cafe.naver.com/some_cafe",
        visible_selectors={"a#gnb_logout_button"},
    )
    r = adapter.check_logged_in(page)
    assert r.is_logged_in is True
    assert r.reason == "logged_in_signals_matched"
    assert "selector:a#gnb_logout_button" in r.matched_signals


# ──────────────────────────────────────────────────────────────────
# 5) 세션 ACTIVE 면 로그인 입력 로직 없이 바로 진행 (핵심 원칙)
#    adapter 자체가 입력 로직을 노출하지 않음을 함께 확인.
# ──────────────────────────────────────────────────────────────────
def test_active_session_bypasses_any_login_input():
    adapter = NaverCafeAdapter()
    # 어댑터 인터페이스에 자동 로그인 메서드가 존재하지 않아야 한다.
    for forbidden in ("perform_login", "auto_login", "type_password", "enter_credentials", "submit_otp"):
        assert not hasattr(adapter, forbidden), f"자동 로그인 메서드가 구현되어 있으면 안 된다: {forbidden}"

    page = FakePage(
        url="https://cafe.naver.com/some_cafe",
        visible_selectors={"a#gnb_logout_button"},
    )

    # open_login_page 가 호출되는지 추적 — 세션 ACTIVE 면 호출되면 안 된다.
    called = {"open_login_page": 0}
    original = adapter.open_login_page

    def spy_open_login(page):
        called["open_login_page"] += 1
        original(page)

    adapter.open_login_page = spy_open_login  # type: ignore[method-assign]

    def work(p):
        return "ok"

    msg = runner.run_with_session(
        adapter,
        page,
        job_id="naver-active",
        site_id="naver_cafe",
        work=work,
        auto_reauth=True,
        sleeper=_fake_sleeper(),
        clock=_counting_clock(),
    )
    assert msg == "JOB_DONE"
    assert called["open_login_page"] == 0, "세션 ACTIVE 에서는 로그인 페이지를 열면 안 된다"
    rec = job_state.get("naver-active")
    assert rec.status == "DONE"
    assert session_manager.get_meta("naver_cafe").status == "ACTIVE"


# ──────────────────────────────────────────────────────────────────
# 6) 세션 만료 → PAUSED_FOR_REAUTH 로 전환 (auto_reauth=False)
# ──────────────────────────────────────────────────────────────────
def test_expired_session_pauses_job_without_auto_reauth():
    adapter = NaverCafeAdapter()
    page = FakePage()

    # home 으로 가면 로그인 페이지로 리다이렉트 상황 시뮬레이션
    original_goto = page.goto

    def goto(target: str):
        original_goto(target)
        if target == adapter.HOME_URL:
            page.url = "https://nid.naver.com/nidlogin.login"

    page.goto = goto  # type: ignore[method-assign]

    def work(_p):
        pytest.fail("세션 없는데 work 가 호출되면 안 된다")

    msg = runner.run_with_session(
        adapter,
        page,
        job_id="naver-expired",
        site_id="naver_cafe",
        work=work,
        auto_reauth=False,
    )
    assert msg == runner.MSG_SESSION_EXPIRED
    rec = job_state.get("naver-expired")
    assert rec.status == "PAUSED_FOR_REAUTH"
    meta = session_manager.get_meta("naver_cafe")
    assert meta.status == "REAUTH_REQUIRED"
    assert meta.paused_job_id == "naver-expired"


# ──────────────────────────────────────────────────────────────────
# 7) 재인증 성공 → RESUMABLE → RUNNING → DONE
# ──────────────────────────────────────────────────────────────────
def test_reauth_success_resumes_job():
    adapter = NaverCafeAdapter()
    page = FakePage()
    state = {"logged_in": False}
    original_goto = page.goto

    def goto(target: str):
        original_goto(target)
        if target == adapter.HOME_URL:
            if state["logged_in"]:
                page.url = "https://cafe.naver.com/"
                page.visible_selectors.add("a#gnb_logout_button")
            else:
                page.url = "https://nid.naver.com/nidlogin.login"
        elif target == adapter.LOGIN_URL:
            # "사용자가 로그인 완료했다"고 가정 — 이후 post_login_verify 체크 시 ACTIVE
            page.url = "https://cafe.naver.com/"
            page.visible_selectors.add("a#gnb_logout_button")
            state["logged_in"] = True

    page.goto = goto  # type: ignore[method-assign]

    def work(_p):
        return "resumed=ok"

    msg = runner.run_with_session(
        adapter,
        page,
        job_id="naver-r",
        site_id="naver_cafe",
        work=work,
        auto_reauth=True,
        reauth_timeout_sec=30,
        sleeper=_fake_sleeper(),
        clock=_counting_clock(),
    )
    assert msg == "JOB_DONE"
    rec = job_state.get("naver-r")
    assert rec.status == "DONE"
    meta = session_manager.get_meta("naver_cafe")
    assert meta.status == "ACTIVE"
    assert meta.last_reauth_at  # set


# ──────────────────────────────────────────────────────────────────
# 8) 재인증 타임아웃 시 FAILED 가 아니라 PAUSED 유지 (나중에 resume_job 가능)
# ──────────────────────────────────────────────────────────────────
def test_reauth_timeout_preserves_paused_not_failed():
    adapter = NaverCafeAdapter()
    page = FakePage()
    original_goto = page.goto

    # state 에 따라 goto 가 로그인 페이지 vs 카페 홈으로 유도되게 전환.
    state = {"logged_in": False}

    def goto(target: str):
        original_goto(target)
        if state["logged_in"]:
            page.url = "https://cafe.naver.com/"
            page.visible_selectors.add("a#gnb_logout_button")
        else:
            page.url = "https://nid.naver.com/nidlogin.login"

    page.goto = goto  # type: ignore[method-assign]

    def work(_p):
        pytest.fail("재인증 실패했는데 work 가 호출되면 안 된다")

    msg = runner.run_with_session(
        adapter,
        page,
        job_id="naver-timeout",
        site_id="naver_cafe",
        work=work,
        auto_reauth=True,
        reauth_timeout_sec=1,
        sleeper=_fake_sleeper(),
        clock=_counting_clock(),
    )
    assert msg == runner.MSG_REAUTH_TIMED_OUT
    rec = job_state.get("naver-timeout")
    # FAILED 가 아니라 PAUSED_FOR_REAUTH 로 남아있어야 한다 (나중에 resume_job 가능)
    assert rec.status == "PAUSED_FOR_REAUTH"
    meta = session_manager.get_meta("naver_cafe")
    assert meta.status == "REAUTH_REQUIRED"
    assert meta.paused_job_id == "naver-timeout"

    # 나중에 사람이 로그인 완료 후 resume_job 호출 — 정상 재개 검증
    state["logged_in"] = True

    def work2(_p):
        return "resumed-later=ok"

    msg2 = runner.resume_job(
        adapter,
        page,
        job_id="naver-timeout",
        work=work2,
        sleeper=_fake_sleeper(),
        clock=_counting_clock(),
    )
    assert msg2 == "JOB_DONE"
    assert job_state.get("naver-timeout").status == "DONE"


# ──────────────────────────────────────────────────────────────────
# 9) 게시글 목록 최소 필드 파싱
# ──────────────────────────────────────────────────────────────────
def test_collect_list_parses_minimum_fields():
    adapter = NaverCafeAdapter()

    rows = [
        FakeRow(
            link=FakeEl(text="첫 번째 글", attrs={"href": "/some_cafe/articles/101"}),
            author=FakeEl(text="nick_a"),
            date=FakeEl(text="2026.04.23."),
        ),
        FakeRow(
            link=FakeEl(text="두 번째 글 (레거시)", attrs={"href": "/ArticleRead.nhn?clubid=111&articleid=202"}),
            author=FakeEl(text="nick_b"),
            date=FakeEl(text="2026.04.22."),
        ),
        # 필드 누락 행 — 스킵되어야 함
        FakeRow(link=None),
    ]

    page = FakePage(
        url="https://cafe.naver.com/some_cafe",
        visible_selectors={"a#gnb_logout_button"},
        rows=rows,
    )

    result = adapter.collect_list(page, cursor="https://cafe.naver.com/some_cafe")
    assert result["done"] is True
    assert result["status"] == STATUS_LIST_PARSE_OK
    items = result["items"]
    assert len(items) == 2

    # 필드 존재 확인 — 최소 5개 필드 모두
    required = {"post_id", "title", "author", "date", "url"}
    for it in items:
        assert required.issubset(set(it.keys()))

    # 현대 라우팅에서 post_id 추출
    assert items[0]["post_id"] == "101"
    assert items[0]["title"] == "첫 번째 글"
    assert items[0]["author"] == "nick_a"
    assert items[0]["url"].endswith("/some_cafe/articles/101")

    # 레거시 라우팅에서 post_id 추출
    assert items[1]["post_id"] == "202"


def test_collect_list_blocked_when_not_logged_in():
    adapter = NaverCafeAdapter()
    page = FakePage(
        url="https://cafe.naver.com/some_cafe",
        visible_selectors=set(),  # 로그인 신호 없음
    )
    result = adapter.collect_list(page, cursor="https://cafe.naver.com/some_cafe")
    assert result["done"] is False
    assert result["status"] == STATUS_LOGIN_CHECK_FAILED
    assert result["items"] == []


# ──────────────────────────────────────────────────────────────────
# 10) 민감정보가 로그에 남지 않는다 (password/otp/cookie/token raw)
# ──────────────────────────────────────────────────────────────────
def test_no_sensitive_material_in_logs(caplog):
    caplog.set_level(logging.INFO)
    adapter = NaverCafeAdapter()

    # 로그인 페이지로 튕긴 상태에서 check_logged_in / open_login_page / open_home 모두 호출
    page = FakePage(url="https://nid.naver.com/nidlogin.login?mode=form")
    adapter.check_logged_in(page)
    adapter.open_login_page(page)
    adapter.open_home(page)

    rows = [
        FakeRow(
            link=FakeEl(text="secret", attrs={"href": "/some_cafe/articles/1"}),
            author=FakeEl(text="a"),
            date=FakeEl(text="d"),
        ),
    ]
    page2 = FakePage(
        url="https://cafe.naver.com/some_cafe",
        visible_selectors={"a#gnb_logout_button"},
        rows=rows,
    )
    adapter.collect_list(page2, cursor="https://cafe.naver.com/some_cafe")

    messages = " ".join(r.getMessage() for r in caplog.records).lower()
    for forbidden in ("password", "passwd", "otp", "captcha", "authorization:", "cookie:", "session=", "token="):
        assert forbidden not in messages, f"로그에 민감 패턴이 노출됐다: {forbidden}"


# ──────────────────────────────────────────────────────────────────
# 11) LoginCheckResult 스키마 일관성 (네이버 어댑터에서도 동일)
# ──────────────────────────────────────────────────────────────────
def test_login_check_result_schema():
    adapter = NaverCafeAdapter()
    r = adapter.check_logged_in(FakePage(url="https://nid.naver.com/nidlogin.login"))
    assert isinstance(r, LoginCheckResult)
    assert isinstance(r.is_logged_in, bool)
    assert isinstance(r.reason, str) and r.reason
    assert isinstance(r.detected_url, str)
    assert isinstance(r.matched_signals, list)
