"""SiteAdapter + runner 통합 검증 — fake page 로 세션/재인증/재개 시나리오 시뮬레이션."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from ai_orchestrator.sites import job_state, runner, session_manager
from ai_orchestrator.sites.adapters.example_portal_adapter import ExamplePortalAdapter
from ai_orchestrator.sites.site_adapter import LoginCheckResult


# ── Fake Playwright Page ─────────────────────────────────────────
@dataclass
class FakePage:
    """로그인/재인증 플로우 검증용 최소 page mock.

    .url 과 .query_selector 만 제공. 실제 네트워크/브라우저 없음.
    """

    url: str = ""
    visible_selectors: set = field(default_factory=set)
    history: list = field(default_factory=list)

    def goto(self, target: str) -> None:
        self.history.append(("goto", target))
        self.url = target

    def query_selector(self, selector: str):
        return object() if selector in self.visible_selectors else None


# ── Fixtures ─────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _isolated_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_ROOT", str(tmp_path / "secrets"))
    monkeypatch.setattr(job_state, "_JOBS_PATH", tmp_path / "site_jobs.jsonl")
    job_state.clear()
    session_manager.clear_meta_for_tests("example_portal")
    yield


def _fake_sleeper():
    def _sleep(_secs: float) -> None:
        return None

    return _sleep


def _counting_clock(max_ticks: int = 5):
    """단조증가 clock — 각 호출마다 interval=1 씩 증가한다고 가정."""
    n = {"v": 0}

    def clock() -> float:
        n["v"] += 1
        return float(n["v"])

    return clock


# ── 1) LoginCheckResult 구조 일관성 ──────────────────────────────
def test_login_check_result_schema_consistent():
    adapter = ExamplePortalAdapter()
    page = FakePage(url="https://example.test/login")  # login 페이지로 튕긴 상태
    r = adapter.check_logged_in(page)
    assert isinstance(r, LoginCheckResult)
    assert r.is_logged_in is False
    assert r.reason == "redirected_to_login"
    assert r.detected_url == "https://example.test/login"
    assert any(s.startswith("url_hint:") for s in r.matched_signals)

    # 로그인 상태 (DOM 신호 존재)
    page2 = FakePage(
        url="https://example.test/dashboard",
        visible_selectors={"#user-menu"},
    )
    r2 = adapter.check_logged_in(page2)
    assert r2.is_logged_in is True
    assert r2.reason == "logged_in_signals_matched"
    assert "selector:#user-menu" in r2.matched_signals


def test_login_check_cookie_only_not_sufficient():
    """쿠키 존재만으로 is_logged_in=True 로 판정하지 않는다."""
    adapter = ExamplePortalAdapter()
    # URL 은 홈, 하지만 로그아웃/사용자 메뉴 셀렉터 없음
    page = FakePage(url="https://example.test/", visible_selectors=set())
    r = adapter.check_logged_in(page)
    assert r.is_logged_in is False
    assert r.reason == "no_user_menu"


# ── 2) 세션 만료 → PAUSED_FOR_REAUTH ─────────────────────────────
def test_session_expired_transitions_job_to_paused():
    adapter = ExamplePortalAdapter()
    # home 으로 가면 login 으로 튕기도록
    page = FakePage()
    orig_goto = page.goto

    def goto(target: str):
        orig_goto(target)
        if target == adapter.HOME_URL:
            page.url = "https://example.test/login"

    page.goto = goto  # type: ignore[method-assign]

    # auto_reauth=False 로 PAUSED 이행만 확인 (대기 없이 즉시 반환)
    def work(_p):
        pytest.fail("work 호출되면 안 된다 (세션 없음)")

    msg = runner.run_with_session(
        adapter,
        page,
        job_id="job-expired",
        site_id="example_portal",
        work=work,
        auto_reauth=False,
    )
    assert msg == runner.MSG_SESSION_EXPIRED
    rec = job_state.get("job-expired")
    assert rec is not None
    assert rec.status == "PAUSED_FOR_REAUTH"
    # 세션 메타도 REAUTH_REQUIRED
    meta = session_manager.get_meta("example_portal")
    assert meta.status == "REAUTH_REQUIRED"
    assert meta.paused_job_id == "job-expired"


# ── 3) 재인증 성공 → RESUMABLE/RUNNING 복귀 + 작업 재개 ─────────
def test_reauth_success_resumes_job():
    adapter = ExamplePortalAdapter()

    # 초기 상태: login 으로 튕김 → 재인증 후 dashboard
    page = FakePage()
    state = {"logged_in": False}
    orig_goto = page.goto

    def goto(target: str):
        orig_goto(target)
        if target == adapter.HOME_URL:
            page.url = "https://example.test/login" if not state["logged_in"] else "https://example.test/"
        elif target == adapter.LOGIN_URL:
            # 로그인 화면 진입 → (테스트에서는 즉시 "사람이 로그인 완료했다"고 가정)
            page.url = "https://example.test/login"
            state["logged_in"] = True
            page.visible_selectors.add("#user-menu")
            page.url = "https://example.test/"

    page.goto = goto  # type: ignore[method-assign]

    # 첫 실행 → 세션 없음 → 재인증 대기 → 성공 → work 실행 → DONE
    def work(p):
        assert p is page
        return "collected=3"

    msg = runner.run_with_session(
        adapter,
        page,
        job_id="job-r",
        site_id="example_portal",
        work=work,
        auto_reauth=True,
        reauth_timeout_sec=10,
        sleeper=_fake_sleeper(),
        clock=_counting_clock(),
    )
    assert msg == "JOB_DONE"
    rec = job_state.get("job-r")
    assert rec.status == "DONE"
    assert rec.result_summary == "collected=3"
    meta = session_manager.get_meta("example_portal")
    assert meta.status == "ACTIVE"
    assert meta.paused_job_id == ""
    assert meta.last_reauth_at


# ── 4) 작업 중 세션 만료 → PAUSED → resume_job 으로 복귀 ─────────
def test_mid_job_expiry_then_resume():
    adapter = ExamplePortalAdapter()
    page = FakePage(url="https://example.test/", visible_selectors={"#user-menu"})

    # 첫 실행에서 work 는 mid-job 만료 발생시킴
    run_count = {"v": 0}

    def work(_p):
        run_count["v"] += 1
        if run_count["v"] == 1:
            raise runner.SessionExpiredMidJob(
                reason="kicked_out_midway",
                current_step="fetch_page_5",
                cursor="page=5",
            )
        return "resumed=ok"

    msg = runner.run_with_session(
        adapter,
        page,
        job_id="job-mid",
        site_id="example_portal",
        work=work,
        auto_reauth=True,
        reauth_timeout_sec=10,
        sleeper=_fake_sleeper(),
        clock=_counting_clock(),
    )
    assert msg == runner.MSG_SESSION_EXPIRED
    rec = job_state.get("job-mid")
    assert rec.status == "PAUSED_FOR_REAUTH"
    assert rec.current_step == "fetch_page_5"
    assert rec.cursor == "page=5"

    # 사용자 재인증 완료 가정 — 세션은 계속 ACTIVE 유지 (#user-menu 유지).
    # resume_job 호출 → DONE 으로 마무리
    msg2 = runner.resume_job(
        adapter,
        page,
        job_id="job-mid",
        work=work,
        sleeper=_fake_sleeper(),
        clock=_counting_clock(),
    )
    assert msg2 == "JOB_DONE"
    rec2 = job_state.get("job-mid")
    assert rec2.status == "DONE"


# ── 5) 민감정보가 로그/상태에 남지 않는다 ──────────────────────────
def test_no_sensitive_material_in_job_state():
    adapter = ExamplePortalAdapter()  # noqa: F841
    page = FakePage(url="https://example.test/", visible_selectors={"#user-menu"})  # noqa: F841
    job_state.start(
        job_id="job-s",
        site_id="example_portal",
        params={"cursor": "0", "report_type": "monthly"},
    )
    # params 에 민감 키가 들어있지 않은지 확인 (설계상 요구)
    rec = job_state.get("job-s")
    low_keys = {k.lower() for k in rec.params}
    assert "password" not in low_keys
    assert "otp" not in low_keys
    assert "cookie" not in low_keys
    assert "authorization" not in low_keys


def test_reauth_timeout_preserves_paused_state():
    """재인증 대기 중 타임아웃 시 FAIL 이 아니라 PAUSED_FOR_REAUTH 보존."""
    adapter = ExamplePortalAdapter()

    page = FakePage()
    orig_goto = page.goto

    def goto(target: str):
        orig_goto(target)
        # 어떤 페이지로 가도 계속 로그인 안 된 상태
        page.url = "https://example.test/login"

    page.goto = goto  # type: ignore[method-assign]

    def work(_p):
        pytest.fail("work 가 호출되면 안 됨 (재인증 실패)")

    # 대기 1회만 허용하도록 clock/sleeper 조합
    clock = _counting_clock()
    msg = runner.run_with_session(
        adapter,
        page,
        job_id="job-timeout",
        site_id="example_portal",
        work=work,
        auto_reauth=True,
        reauth_timeout_sec=1,  # 1초 타임아웃
        sleeper=_fake_sleeper(),
        clock=clock,
    )
    assert msg == runner.MSG_REAUTH_TIMED_OUT
    rec = job_state.get("job-timeout")
    assert rec.status == "PAUSED_FOR_REAUTH"  # FAILED 가 아니라 보존
    meta = session_manager.get_meta("example_portal")
    assert meta.status == "REAUTH_REQUIRED"
    assert meta.last_reason == "reauth_timed_out"
    assert meta.paused_job_id == "job-timeout"
