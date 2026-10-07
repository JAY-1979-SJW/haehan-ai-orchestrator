"""BulkSmtp(연결 1개 재사용 SMTP 어댑터) — 가짜 연결만 사용(실제 접속·발송 없음). 기준서 2026-10-02_mail_bulk_sequential.md §3."""

from __future__ import annotations

import smtplib

from scripts.naver.mail.imap import bulk_sender, sender

PW = "fake-secret"  # 시험용 값(실제 비밀번호 아님)


class FakeConn:
    """smtplib.SMTP_SSL 대용. 동작은 생성 시 지정한 값으로 결정한다."""

    logins = 0

    def __init__(self, *_a, **_k):
        self.logged_in = False
        self.sent = []
        self.noop_ok = True
        self.send_error = None
        self.login_error = None
        self.quit_called = False

    def login(self, user, pw):
        if self.login_error:
            raise self.login_error
        FakeConn.logins += 1
        self.logged_in = True

    def noop(self):
        if not self.noop_ok:
            raise smtplib.SMTPServerDisconnected("closed")
        return 250, b"ok"

    def send_message(self, msg):
        if self.send_error:
            raise self.send_error
        self.sent.append(msg["To"])
        return {}

    def quit(self):
        self.quit_called = True


def _draft(to="a@example.com"):
    return sender.make_draft("skyjwsin", to, "제목", "본문")


def _make(conns):
    """factory 가 호출될 때마다 conns 의 다음 연결을 돌려준다."""
    queue = list(conns)
    FakeConn.logins = 0
    return bulk_sender.BulkSmtp("skyjwsin", password=PW, factory=lambda *_a, **_k: queue.pop(0))


def test_reuses_one_connection_for_many_mails():
    c = FakeConn()
    with _make([c]) as smtp:
        results = [smtp.send(_draft(f"u{i}@example.com")) for i in range(5)]
    assert all(r["ok"] for r in results)
    assert FakeConn.logins == 1  # 로그인은 한 번
    assert len(c.sent) == 5
    assert c.quit_called is True


def test_reconnects_when_connection_died_before_sending():
    first, second = FakeConn(), FakeConn()
    with _make([first, second]) as smtp:
        assert smtp.send(_draft())["ok"]
        first.noop_ok = False  # 서버가 연결을 끊음 — 아직 메일이 나가기 전이므로 재접속해도 중복이 아니다
        assert smtp.send(_draft("b@example.com"))["ok"]
    assert FakeConn.logins == 2
    assert second.sent == ["b@example.com"]


def test_auth_failure_is_reported_with_code():
    c = FakeConn()
    c.login_error = smtplib.SMTPAuthenticationError(535, b"denied")
    with _make([c]) as smtp:
        r = smtp.send(_draft())
    assert (r["ok"], r["error"], r["code"]) == (False, "auth_failed", 535)


def test_no_password_is_reported(monkeypatch):
    monkeypatch.setattr(bulk_sender, "load_password", lambda _a: "")
    r = bulk_sender.BulkSmtp("skyjwsin").send(_draft())
    assert r["error"] == "no_password"


def test_connect_failure_is_reported():
    def boom(*_a, **_k):
        raise OSError("down")

    r = bulk_sender.BulkSmtp("skyjwsin", password=PW, factory=boom).send(_draft())
    assert r["error"] == "connect_failed"


def test_recipient_refused_carries_code_and_is_definite_failure():
    c = FakeConn()
    c.send_error = smtplib.SMTPRecipientsRefused({"a@example.com": (550, b"no such user")})
    with _make([c]) as smtp:
        r = smtp.send(_draft())
    assert (r["ok"], r["error"], r["code"]) == (False, "send_failed", 550)


def test_response_error_keeps_code_and_text():
    c = FakeConn()
    c.send_error = smtplib.SMTPDataError(554, b"Daily quota exceeded")
    with _make([c]) as smtp:
        r = smtp.send(_draft())
    assert r["code"] == 554
    assert "quota" in r["message"].lower()


def test_disconnect_during_send_is_unknown_and_next_mail_reconnects():
    first, second = FakeConn(), FakeConn()
    first.send_error = smtplib.SMTPServerDisconnected("lost")
    with _make([first, second]) as smtp:
        r = smtp.send(_draft())
        assert r["error"] == "send_unknown"  # 서버가 받았는지 모른다 — 호출부가 재시도하지 않는다
        assert smtp.send(_draft("b@example.com"))["ok"]  # 다음 사람은 새 연결로
    assert FakeConn.logins == 2
