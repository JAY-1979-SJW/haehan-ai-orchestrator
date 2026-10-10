"""네이버 메일 IMAP/SMTP — 점검(protocol)·웹메일 설정(settings)·예약 작업 등록. 네이버 서버와 브라우저를 쓰지 않는다."""

from __future__ import annotations

import imaplib
import json
import smtplib

import pytest

from ai_orchestrator.contracts.action_risk_policy import GRADE_AUTO_ALLOWED, GRADE_USER_DELEGATED, classify_action
from ai_orchestrator.services import scheduled_job_actions as actions
from scripts.naver.mail.imap import protocol as P
from scripts.naver.mail.imap import settings as S

FAKE_APP_PW = "not-a-real-value-123456"


class FakeIMAP:
    def __init__(self, *, auth_ok=True, status=b'"INBOX" (MESSAGES 155 UNSEEN 76)'):
        self.auth_ok, self.status_line, self.logged_out = auth_ok, status, False

    def login(self, user, pw):
        if not self.auth_ok:
            raise imaplib.IMAP4.error("[AUTH] Authentication failed")
        return "OK", [b"ok"]

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"'] * 14

    def status(self, mailbox, what):
        return "OK", [self.status_line]

    def logout(self):
        self.logged_out = True


class FakeSMTP:
    def __init__(self, *, auth_ok=True):
        self.auth_ok, self.quit_called = auth_ok, False

    def login(self, user, pw):
        if not self.auth_ok:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
        return 235, b"Accepted"

    def quit(self):
        self.quit_called = True


# ── protocol ────────────────────────────────────────────────────────────


def test_password_is_read_from_the_account_specific_env_name(monkeypatch):
    assert P.password_env_name("skyjwsin") == "NAVER_MAIL_PW_SKYJWSIN"
    monkeypatch.setenv("NAVER_MAIL_PW_SKYJWSIN", FAKE_APP_PW)
    assert P.load_password("skyjwsin") == FAKE_APP_PW


def test_inbox_counts_are_parsed():
    assert P._inbox_counts('"INBOX" (MESSAGES 155 UNSEEN 76)') == {"MESSAGES": 155, "UNSEEN": 76}
    assert P._inbox_counts("") == {}


def test_imap_success_reports_folder_and_inbox_counts():
    fake = FakeIMAP()
    result = P.check_imap("skyjwsin", FAKE_APP_PW, factory=lambda host, port: fake)
    assert result == {"ok": True, "folders": 14, "inbox_total": 155, "inbox_unseen": 76} and fake.logged_out


def test_imap_without_password_never_connects():
    def boom(*a):
        raise AssertionError("접속하면 안 된다")

    result = P.check_imap("skyjwsin", "", factory=boom)
    assert result["error"] == "no_password" and "NAVER_MAIL_PW_SKYJWSIN" in result["message"]


def test_imap_auth_failure_gives_the_fix_and_still_logs_out():
    fake = FakeIMAP(auth_ok=False)
    result = P.check_imap("skyjwsin", FAKE_APP_PW, factory=lambda host, port: fake)
    assert result["error"] == "auth_failed" and "IMAP/SMTP 설정" in result["message"] and fake.logged_out


def test_connection_failure_is_reported_without_leaking_anything():
    def refuse(*a):
        raise OSError("connection refused")

    for result in (P.check_imap("a", FAKE_APP_PW, factory=refuse), P.check_smtp("a", FAKE_APP_PW, factory=refuse)):
        assert result["error"] == "connect_failed" and FAKE_APP_PW not in json.dumps(result)


def test_smtp_checks_only_authentication():
    ok, bad = FakeSMTP(), FakeSMTP(auth_ok=False)
    assert P.check_smtp("skyjwsin", FAKE_APP_PW, factory=lambda h, p: ok) == {"ok": True} and ok.quit_called
    assert P.check_smtp("skyjwsin", FAKE_APP_PW, factory=lambda h, p: bad)["error"] == "auth_failed" and bad.quit_called
    assert not hasattr(ok, "sendmail") and not hasattr(ok, "send_message")  # 보내는 기능은 호출조차 할 수 없다


def test_check_skips_smtp_when_imap_is_rejected_to_avoid_account_lockout(monkeypatch):
    monkeypatch.setenv("NAVER_MAIL_PW_SKYJWSIN", FAKE_APP_PW)

    def smtp_must_not_run(*a):
        raise AssertionError("SMTP 를 시도하면 안 된다")

    result = P.check("skyjwsin", imap_factory=lambda h, p: FakeIMAP(auth_ok=False), smtp_factory=smtp_must_not_run)
    assert result["ok"] is False and result["smtp"]["error"] == "skipped"


def test_check_success_and_the_password_never_appears_in_results(monkeypatch):
    monkeypatch.setenv("NAVER_MAIL_PW_SKYJWSIN", FAKE_APP_PW)
    result = P.check("skyjwsin", imap_factory=lambda h, p: FakeIMAP(), smtp_factory=lambda h, p: FakeSMTP())
    assert result["ok"] is True
    text = json.dumps(result, ensure_ascii=False) + P.describe(result)
    assert (
        FAKE_APP_PW not in text
        and "받은편지함 155통(안 읽음 76)" in P.describe(result)
        and "SMTP: 인증 성공" in P.describe(result)
    )


# ── settings (가짜 웹메일 화면) ──────────────────────────────────────────


class FakeLocator:
    def __init__(self, page, key):
        self.page, self.key = page, key

    @property
    def first(self):
        return self

    def click(self, **kw):
        self.page.clicks.append(self.key)
        if self.key.startswith("label[for"):
            self.page.pending = True
        if self.key == S.SAVE_BUTTON and self.page.pending and self.page.saves:
            self.page.enabled = True

    def wait_for(self, **kw):
        return None


class FakePage:
    def __init__(
        self, *, url=S.SETTINGS_URL, enabled=False, ready=True, saves=True, text="계정 정보 | 아이디 : skyjwsin"
    ):
        self.url, self.enabled, self.ready, self.saves, self.text = url, enabled, ready, saves, text
        self.clicks: list[str] = []
        self.pending = False

    def goto(self, url, **kw):
        return None

    def wait_for_selector(self, selector, **kw):
        if not self.ready:
            raise TimeoutError("not ready")

    def inner_text(self, selector):
        return self.text

    def is_checked(self, selector):
        return self.enabled

    def locator(self, selector):
        return FakeLocator(self, selector)

    def get_by_text(self, text):
        return FakeLocator(self, "text:" + text)

    def get_by_role(self, role, name=None, exact=False):
        return FakeLocator(self, "role:" + str(name))


def test_read_state_variants():
    assert S.read_state(FakePage(url="https://nid.naver.com/nidlogin.login"))["reason"] == "not_logged_in"
    assert S.read_state(FakePage(ready=False))["reason"] == "page_not_ready"
    assert S.read_state(FakePage(enabled=False)) == {"enabled": False, "account": "skyjwsin", "reason": ""}
    assert S.read_state(FakePage(enabled=True))["enabled"] is True


@pytest.mark.parametrize(
    ("page", "reason"),
    [
        (FakePage(url="https://nid.naver.com/nidlogin.login"), "not_logged_in"),
        (FakePage(ready=False), "page_not_ready"),
        (FakePage(text="아이디 : someone_else"), "other_account"),
    ],
)
def test_enable_changes_nothing_unless_it_is_safe(page, reason):
    result = S.enable(page, "skyjwsin")
    assert result["ok"] is False and result["reason"] == reason and page.clicks == []


def test_enable_is_a_no_op_when_already_enabled():
    page = FakePage(enabled=True)
    assert (
        S.enable(page, "skyjwsin") == {"ok": True, "changed": False, "reason": "already_enabled"} and page.clicks == []
    )


def test_enable_selects_yes_saves_and_verifies_by_reloading():
    page = FakePage(enabled=False)
    result = S.enable(page, "skyjwsin")
    assert result == {"ok": True, "changed": True, "reason": "enabled"}
    assert page.clicks[0] == "label[for='option_radio_1']" and S.SAVE_BUTTON in page.clicks


def test_enable_reports_when_the_save_did_not_stick():
    result = S.enable(FakePage(enabled=False, saves=False), "skyjwsin")
    assert result == {"ok": False, "changed": True, "reason": "not_saved"}


# ── 예약 작업(앱 파이프라인) 등록 ────────────────────────────────────────


def test_mail_actions_are_registered_with_the_right_approval_grades():
    assert classify_action(actions.ACTIONS["naver_mail_check"].risk_action) == GRADE_AUTO_ALLOWED
    assert classify_action(actions.ACTIONS["naver_mail_enable"].risk_action) == GRADE_USER_DELEGATED
    items = {c["key"]: c for c in actions.catalog()}
    assert (
        items["naver_mail_enable"]["requires_approval"] is True
        and items["naver_mail_check"]["requires_approval"] is False
    )
    assert items["naver_mail_check"]["fields"][0]["name"] == "target"


def test_mail_action_params_only_accept_registered_accounts():
    validate = actions.ACTIONS["naver_mail_check"].validate
    assert validate({}) == {"target": "skyjwsin"}
    with pytest.raises(ValueError):
        validate({"target": "bigsun2024"})


def _patch_check(monkeypatch, *, state, result):
    monkeypatch.setattr(actions, "_in_new_tab", lambda fn: state)
    monkeypatch.setattr(P, "check", lambda account: result)


GOOD = {
    "account": "skyjwsin",
    "ok": True,
    "imap": {"ok": True, "folders": 14, "inbox_total": 155, "inbox_unseen": 76},
    "smtp": {"ok": True},
}
BAD = {
    "account": "skyjwsin",
    "ok": False,
    "imap": {"ok": False, "error": "auth_failed", "message": "IMAP 로그인이 거부되었습니다"},
    "smtp": {"ok": False, "error": "skipped", "message": "건너뜀"},
}


def test_check_action_reports_success_line(monkeypatch):
    _patch_check(monkeypatch, state={"enabled": True, "account": "skyjwsin", "reason": ""}, result=GOOD)
    line = actions.ACTIONS["naver_mail_check"].run({"target": "skyjwsin"})
    assert "사용함" in line and "155통" in line and "SMTP: 인증 성공" in line


def test_check_action_tells_the_user_which_action_fixes_a_disabled_setting(monkeypatch):
    _patch_check(monkeypatch, state={"enabled": False, "account": "skyjwsin", "reason": ""}, result=BAD)
    with pytest.raises(RuntimeError, match="IMAP/SMTP 켜기"):
        actions.ACTIONS["naver_mail_check"].run({"target": "skyjwsin"})


def test_check_action_fails_when_protocol_login_fails_even_if_setting_is_on(monkeypatch):
    _patch_check(monkeypatch, state={"enabled": True, "account": "skyjwsin", "reason": ""}, result=BAD)
    with pytest.raises(RuntimeError, match="거부"):
        actions.ACTIONS["naver_mail_check"].run({"target": "skyjwsin"})


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ({"ok": True, "changed": True, "reason": "enabled"}, "저장하고 반영을 확인"),
        ({"ok": True, "changed": False, "reason": "already_enabled"}, "변경 없음"),
    ],
)
def test_enable_action_success_messages(monkeypatch, outcome, expected):
    monkeypatch.setattr(actions, "_in_new_tab", lambda fn: outcome)
    assert expected in actions.ACTIONS["naver_mail_enable"].run({"target": "skyjwsin"})


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("not_logged_in", "로그인돼 있지 않아"),
        ("page_not_ready", "읽지 못해"),
        ("other_account", "다른 계정"),
        ("not_saved", "반영이 확인되지 않았습니다"),
    ],
)
def test_enable_action_failure_messages_say_why_nothing_was_changed(monkeypatch, reason, expected):
    monkeypatch.setattr(
        actions,
        "_in_new_tab",
        lambda fn: {"ok": False, "changed": reason == "not_saved", "reason": reason, "account": "x"},
    )
    with pytest.raises(RuntimeError, match=expected):
        actions.ACTIONS["naver_mail_enable"].run({"target": "skyjwsin"})
