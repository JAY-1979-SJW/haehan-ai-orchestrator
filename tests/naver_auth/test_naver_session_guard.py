"""네이버 세션 지킴이 — 로그인 안 돼 있으면 바로 자동 로그인, 시도 제한 없음, 계정 확인, 이미 로그인된 세션 보호. 브라우저·자격증명을 쓰지 않는다."""

from __future__ import annotations

from datetime import datetime

import pytest

from ai_orchestrator.connectors.naver_auth import session_guard as G
from scripts.naver.common import auth as A
from scripts.naver.blog.automation import account_probe as P

NOW = datetime(2026, 10, 1, 9, 0, 0)


def attempt(at, target="skyjwsin", result="failed"):
    return {"at": at.isoformat(), "target": target, "result": result}


class Env:
    """가짜 브라우저·파이프라인. 어떤 호출이 있었는지 기록한다."""

    def __init__(self, states, *, alias="skyjwsin", login_result=None, attempts=()):
        self.states = list(states)  # detect 가 호출될 때마다 하나씩 돌려줌(마지막 값 반복)
        self.alias = alias
        self.login_result = login_result or {"ok": True, "logged_in": True, "message": "ok"}
        self.attempts = list(attempts)
        self.login_calls: list[str] = []
        self.alias_reads = 0
        self.sleeps: list[float] = []

    def deps(self):
        def detect():
            state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
            return {"state": state, "cookie": state == "in"}

        def read_alias():
            self.alias_reads += 1
            return self.alias

        def run_login(target):
            self.login_calls.append(target)
            return self.login_result

        return G.GuardDeps(
            now=lambda: NOW,
            detect=detect,
            read_alias=read_alias,
            run_login=run_login,
            save_attempt=self.attempts.append,
            sleep=self.sleeps.append,
        )


# ── 관찰 ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("alias", "account"),
    [("skyjwsin", "verified"), ("beautiful-light", "other"), ("bigsun2024", "other"), (None, "unknown")],
)
def test_observe_identifies_the_account_only_when_logged_in(alias, account):
    env = Env(["in"], alias=alias)
    seen = G.observe("skyjwsin", env.deps())
    assert seen["state"] == "in" and seen["account"] == account and seen["alias"] == alias


@pytest.mark.parametrize("state", ["out", "unknown", "unavailable"])
def test_observe_does_not_read_alias_unless_logged_in(state):
    env = Env([state])
    assert G.observe("skyjwsin", env.deps())["account"] is None
    assert env.alias_reads == 0


def test_lighting_account_is_verified_by_its_public_alias():
    """skyjwshin 의 공개 주소는 하이픈 포함 beautiful-light (2026-08-24 오판 사고 유형)."""
    seen = G.observe("skyjwshin", Env(["in"], alias="beautiful-light").deps())
    assert seen["account"] == "verified"


# ── 자동 로그인 결정 ─────────────────────────────────────────────────────


def test_out_triggers_exactly_one_login_for_the_target_account():
    env = Env(["out", "in"])
    result = G.ensure_login("skyjwsin", env.deps())
    assert env.login_calls == ["skyjwsin"]
    assert result["action"] == "logged_in" and result["account"] == "verified"
    assert len(env.attempts) == 1 and env.attempts[0]["result"] == "ok" and env.attempts[0]["target"] == "skyjwsin"


@pytest.mark.parametrize("state", ["in", "unavailable"])
def test_login_is_not_attempted_when_logged_in_or_browser_unavailable(state):
    env = Env([state])
    result = G.ensure_login("skyjwsin", env.deps())
    assert env.login_calls == [] and env.attempts == []
    assert result["action"] == "none"


def test_unknown_state_also_logs_in_right_away():
    """2026-10-01 사용자 지시: 로그인돼 있지 않으면 사이트 호출 즉시 로그인(상태 불명확도 시도)."""
    env = Env(["unknown", "in"])
    result = G.ensure_login("skyjwsin", env.deps())
    assert env.login_calls == ["skyjwsin"] and result["action"] == "logged_in"


def test_repeated_calls_are_never_throttled():
    env = Env(
        ["out", "out"],
        attempts=[attempt(NOW, result="failed") for _ in range(10)],
        login_result={"ok": False, "logged_in": False, "message": "x"},
    )
    G.ensure_login("skyjwsin", env.deps())
    G.ensure_login("skyjwsin", env.deps())
    assert env.login_calls == ["skyjwsin", "skyjwsin"]


def test_other_account_logged_in_is_reported_not_switched():
    env = Env(["in"], alias="bigsun2024")
    result = G.ensure_login("skyjwsin", env.deps())
    assert env.login_calls == [] and result["account"] == "other"
    assert "bigsun2024" in result["message"] and "전환하지 않습니다" in result["message"]


def test_allow_attempt_false_only_observes():
    env = Env(["out"])
    result = G.ensure_login("skyjwsin", env.deps(), allow_attempt=False)
    assert env.login_calls == [] and result["reason"] == "attempt_not_allowed"


def test_failed_login_is_recorded_and_reported():
    env = Env(["out", "out"], login_result={"ok": False, "logged_in": False, "message": "pw_input_failed:timeout"})
    result = G.ensure_login("skyjwsin", env.deps())
    assert result["action"] == "failed" and "pw_input_failed" in result["message"]
    assert env.attempts[-1]["result"] == "failed"


def test_captcha_is_reported_for_the_user_to_handle():
    env = Env(["out", "out"], login_result={"ok": False, "logged_in": False, "captcha": True, "message": "captcha"})
    result = G.ensure_login("skyjwsin", env.deps())
    assert result["action"] == "captcha" and "직접 처리" in result["message"]
    assert env.attempts[-1]["result"] == "captcha"


def test_transient_unknown_right_after_login_is_re_read_until_it_settles():
    """2026-10-01 실측: 로그인 직후 페이지가 이동 중이라 unknown 으로 읽혀 성공을 실패로 보고했다."""
    env = Env(["out", "unknown", "unknown", "in"])
    result = G.ensure_login("skyjwsin", env.deps())
    assert result["action"] == "logged_in" and result["account"] == "verified"
    assert len(env.sleeps) == 2 and all(s == G.SETTLE_WAIT_SECONDS for s in env.sleeps)


def test_pipeline_success_but_screen_never_settles_is_unverified_not_failed():
    env = Env(["out", "unknown"])
    result = G.ensure_login("skyjwsin", env.deps())
    assert result["action"] == "unverified" and "확인하지 못했습니다" in result["message"]
    assert len(env.sleeps) == G.SETTLE_CHECKS
    assert env.attempts[-1]["result"] == "ok"  # 시도 기록은 파이프라인 결과 그대로


def test_settle_wait_is_not_used_when_state_is_already_clear():
    env = Env(["out", "in"])
    G.ensure_login("skyjwsin", env.deps())
    assert env.sleeps == []


def test_success_is_judged_by_a_fresh_read_not_by_the_pipeline_claim():
    """파이프라인이 성공이라 해도 다시 읽은 상태가 in 이 아니면 성공으로 보고하지 않는다."""
    env = Env(["out", "out"], login_result={"ok": True, "logged_in": True, "message": "ok"})
    assert G.ensure_login("skyjwsin", env.deps())["action"] == "failed"


def test_secrets_never_appear_in_attempt_records():
    env = Env(["out", "in"], login_result={"ok": True, "logged_in": True, "message": "ok"})
    G.ensure_login("skyjwsin", env.deps())
    assert set(env.attempts[0]) == {"at", "target", "result", "reason"}


# ── 계정 확인 (alias) ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("href", "alias"),
    [
        ("https://admin.blog.naver.com/skyjwsin/", "skyjwsin"),
        ("https://admin.blog.naver.com/beautiful-light/posting", "beautiful-light"),
        ("https://admin.blog.naver.com/a_b-c9/", "a_b-c9"),
        ("https://blog.naver.com/skyjwsin", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_alias_handles_hyphens(href, alias):
    assert P.extract_alias(href) == alias


def test_alias_maps_to_registered_accounts_only():
    assert P.alias_to_blog_id("skyjwsin") == "skyjwsin"
    assert P.alias_to_blog_id("beautiful-light") == "skyjwshin"
    assert P.alias_to_blog_id("bigsun2024") is None
    assert P.alias_to_blog_id(None) is None


def test_read_alias_navigates_read_only_and_parses_the_link():
    class Page:
        def __init__(self):
            self.visited = []

        def goto(self, url, wait_until, timeout):
            self.visited.append(url)

        def wait_for_timeout(self, ms):
            return None

        def evaluate(self, js):
            return "https://admin.blog.naver.com/beautiful-light/"

    page = Page()
    assert P.read_alias(page) == "beautiful-light"
    assert page.visited == [P.BLOG_HOME_URL]
    assert "logout" not in P._ALIAS_JS.lower() and "cookie" not in P._ALIAS_JS.lower()


# ── auth.login_naver 의 "이미 로그인됨" 판정 ─────────────────────────────


class FakeNaverPage:
    url = "https://www.naver.com/"


@pytest.mark.parametrize(
    ("state", "kwargs", "expected"),
    [
        ({"logged_in": True, "user": "skyjwsin"}, {}, ("ok", "already_logged_in")),
        ({"logged_in": True, "user": "skyjwsin님"}, {}, ("ok", "already_logged_in")),
        ({"logged_in": True, "user": None}, {}, ("fail", "logged_in_account_unknown")),
        ({"logged_in": True, "user": ""}, {}, ("fail", "logged_in_account_unknown")),
        ({"logged_in": True, "user": "bigsun2024"}, {}, ("fail", "different_user_logged_in")),
        ({"logged_in": False, "user": None}, {}, None),
        ({"logged_in": True, "user": "bigsun2024"}, {"force": True}, None),
    ],
)
def test_existing_login_verdict(monkeypatch, state, kwargs, expected):
    monkeypatch.setattr(A, "detect_login_state", lambda page: state)
    result = A._existing_login_verdict(FakeNaverPage(), "skyjwsin", kwargs.get("force", False))
    if expected is None:
        assert result is None
    else:
        assert (("ok" if result["ok"] else "fail"), result["reason"]) == expected


def test_existing_login_verdict_survives_detection_errors(monkeypatch):
    def boom(page):
        raise RuntimeError("no page")

    monkeypatch.setattr(A, "detect_login_state", boom)
    assert A._existing_login_verdict(FakeNaverPage(), "skyjwsin", False) is None


def test_non_naver_page_is_not_treated_as_logged_in(monkeypatch):
    class Other:
        url = "https://example.com/"

    monkeypatch.setattr(A, "detect_login_state", lambda page: {"logged_in": True, "user": "skyjwsin"})
    assert A._existing_login_verdict(Other(), "skyjwsin", False) is None


# ── 읽기 전용 확인은 브라우저를 시작하지 않는다 (2026-10-04 앱 실검증 D7) ─────────────────


def _deps_with_starting(calls):
    return G.GuardDeps(
        now=lambda: NOW,
        detect=lambda: calls.append("detect") or {"state": "unavailable", "cookie": None},
        detect_starting=lambda: calls.append("detect_starting") or {"state": "in", "cookie": True},
        read_alias=lambda: "skyjwsin",
        run_login=lambda target: {"ok": True, "logged_in": True},
        save_attempt=lambda a: None,
    )


def test_observe_is_read_only_by_default_and_never_uses_the_starting_detector():
    calls: list[str] = []
    seen = G.observe("skyjwsin", _deps_with_starting(calls))
    assert calls == ["detect"] and seen["state"] == "unavailable"


def test_ensure_login_may_start_the_browser():
    calls: list[str] = []
    res = G.ensure_login("skyjwsin", _deps_with_starting(calls))
    assert calls == ["detect_starting"]  # 자동 로그인 흐름만 브라우저를 시작할 수 있다
    assert res["action"] == "none" and res["reason"] == "already_logged_in"


def test_default_deps_detect_does_not_launch_chrome_when_cdp_is_down(monkeypatch):
    from ai_orchestrator.connectors.naver_auth import login_pipeline as pipeline

    started: list[int] = []
    monkeypatch.setattr(pipeline, "_is_cdp_alive", lambda *a, **k: False)
    monkeypatch.setattr(pipeline, "_start_cdp", lambda: started.append(1) or (_ for _ in ()).throw(RuntimeError("stub")))
    deps = G.default_deps()

    assert deps.detect() == {"state": "unavailable", "cookie": None}
    assert started == []  # 상태 확인만으로 Chrome 이 뜨면 안 된다

    assert deps.detect_starting()["state"] == "unavailable"  # 시작을 시도했지만(스텁이 실패) 불가로 알린다
    assert started == [1]
