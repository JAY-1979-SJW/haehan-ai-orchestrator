"""네이버 메일 수신(reader)·발송(sender)·예약 작업 등록 — 가짜 IMAP/SMTP 로 검증(네이버 서버·브라우저 불필요)."""

from __future__ import annotations

import imaplib
import smtplib
from datetime import date
from email.message import EmailMessage

import pytest

from ai_orchestrator.contracts.action_risk_policy import GRADE_AUTO_ALLOWED, GRADE_USER_DELEGATED, classify_action
from ai_orchestrator.services import scheduled_job_actions as actions
from scripts.naver.mail.imap import reader, sender

PW = "not-a-real-value-123456"
ALICE = "a@example.com"


def _mail_bytes(subject="안녕하세요", frm="홍길동 <a@example.com>", body="본문입니다", attach=False) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["Subject"], msg["Date"] = frm, subject, "Thu, 01 Oct 2026 10:00:00 +0900"
    msg.set_content(body)
    if attach:
        msg.add_attachment(b"x" * 10, maintype="application", subtype="pdf", filename="견적서.pdf")
    return msg.as_bytes()


class FakeIMAP:
    def __init__(self, messages: dict[str, bytes], *, auth_ok=True):
        self.messages, self.auth_ok, self.calls, self.readonly, self.logged_out = messages, auth_ok, [], None, False

    def login(self, user, pw):
        if not self.auth_ok:
            raise imaplib.IMAP4.error("[AUTH] Authentication failed")
        return "OK", [b"ok"]

    def select(self, mailbox, readonly=False):
        self.readonly = readonly
        return "OK", [b"3"]

    def uid(self, command, *args):
        self.calls.append((command, args))
        if command == "SEARCH":
            return "OK", [" ".join(self.messages).encode()]
        uid = args[0]
        if uid not in self.messages:
            return "OK", [None]
        return "OK", [(b"1 (BODY[] {n}", self.messages[uid]), b")"]

    def response(self, code):
        return code, [str(getattr(self, "validity", 111)).encode()]

    def logout(self):
        self.logged_out = True


class FakeSMTP:
    def __init__(self, *, auth_ok=True, fail_send=False, refused=None):
        self.auth_ok, self.fail_send, self.refused, self.sent, self.quit_called = (
            auth_ok,
            fail_send,
            refused or {},
            [],
            False,
        )

    def login(self, user, pw):
        if not self.auth_ok:
            raise smtplib.SMTPAuthenticationError(535, b"bad")
        return 235, b"ok"

    def send_message(self, msg):
        if self.fail_send:
            raise smtplib.SMTPDataError(554, b"rejected")
        self.sent.append(msg)
        return self.refused

    def quit(self):
        self.quit_called = True


def _boom(*_args):
    raise AssertionError("접속하면 안 된다")


# ── reader ──────────────────────────────────────────────────────────────


def test_list_returns_newest_first_with_decoded_headers_and_opens_read_only():
    fake = FakeIMAP({"1": _mail_bytes("첫째"), "2": _mail_bytes("둘째"), "3": _mail_bytes("셋째")})
    r = reader.list_messages("skyjwsin", limit=2, password=PW, factory=lambda h, p: fake)
    assert r["ok"] and r["total_matched"] == 3
    assert [m["subject"] for m in r["messages"]] == ["셋째", "둘째"]
    assert fake.readonly is True and fake.logged_out
    assert all("PEEK" in c[1][1] for c in fake.calls if c[0] == "FETCH")


def test_encoded_korean_subject_is_decoded():
    raw = b"From: a@example.com\r\nSubject: =?UTF-8?B?7JWI64WV?=\r\n\r\nbody"
    r = reader.list_messages("skyjwsin", password=PW, factory=lambda h, p: FakeIMAP({"7": raw}))
    assert r["messages"][0]["subject"] == "안녕"


def test_read_message_returns_body_and_attachment_names_only():
    fake = FakeIMAP({"5": _mail_bytes(attach=True)})
    r = reader.read_message("skyjwsin", "5", password=PW, factory=lambda h, p: fake)
    assert r["ok"] and "본문입니다" in r["body"]
    assert r["attachments"] == [{"filename": "견적서.pdf", "size": 10}]


def test_read_message_rejects_non_numeric_uid_and_missing_mail():
    assert reader.read_message("skyjwsin", "1; DELETE", password=PW)["error"] == "bad_uid"
    r = reader.read_message("skyjwsin", "9", password=PW, factory=lambda h, p: FakeIMAP({}))
    assert r["error"] == "not_found"


def test_reader_auth_failure_and_missing_password_are_reported_without_secrets():
    r = reader.list_messages("skyjwsin", password=PW, factory=lambda h, p: FakeIMAP({}, auth_ok=False))
    assert r["error"] == "auth_failed" and PW not in str(r)
    assert reader.list_messages("skyjwsin", password="", factory=_boom)["error"] == "no_password"


def test_limit_is_capped():
    msgs = {str(i): _mail_bytes(f"m{i}") for i in range(1, 80)}
    r = reader.list_messages("skyjwsin", limit=999, password=PW, factory=lambda h, p: FakeIMAP(msgs))
    assert len(r["messages"]) == reader.MAX_LIST


# ── 새 메일만 ───────────────────────────────────────────────────────────


def _new(fake, path, **kw):
    return reader.list_new("skyjwsin", password=PW, factory=lambda h, p: fake, checkpoint_path=path, **kw)


def test_first_call_sets_baseline_and_ignores_the_backlog(tmp_path):
    cp = tmp_path / "cp.json"
    fake = FakeIMAP({"1": _mail_bytes("옛1"), "2": _mail_bytes("옛2")})
    r = _new(fake, cp)
    assert r["baseline_set"] and r["messages"] == [] and r["last_uid"] == 2
    assert not any(c[0] == "FETCH" for c in fake.calls)


def test_only_mail_after_the_checkpoint_is_returned_oldest_first(tmp_path):
    cp = tmp_path / "cp.json"
    _new(FakeIMAP({"1": _mail_bytes("옛1"), "2": _mail_bytes("옛2")}), cp)
    r = _new(FakeIMAP({"1": _mail_bytes("옛1"), "2": _mail_bytes("옛2"), "3": _mail_bytes("새3"), "4": _mail_bytes("새4")}), cp)
    assert [m["subject"] for m in r["messages"]] == ["새3", "새4"] and r["total_new"] == 2 and not r["baseline_set"]


def test_checkpoint_does_not_move_until_advanced(tmp_path):
    cp = tmp_path / "cp.json"
    _new(FakeIMAP({"1": _mail_bytes()}), cp)
    box = {"1": _mail_bytes(), "2": _mail_bytes("새2")}
    assert len(_new(FakeIMAP(box), cp)["messages"]) == 1
    assert len(_new(FakeIMAP(box), cp, advance=True)["messages"]) == 1
    assert _new(FakeIMAP(box), cp)["messages"] == []


def test_changed_uidvalidity_resets_baseline_instead_of_flooding(tmp_path):
    cp = tmp_path / "cp.json"
    _new(FakeIMAP({"1": _mail_bytes()}), cp)
    other = FakeIMAP({"1": _mail_bytes(), "2": _mail_bytes(), "3": _mail_bytes()})
    other.validity = 222
    r = _new(other, cp)
    assert r["baseline_set"] and r["messages"] == [] and r["last_uid"] == 3


def test_uid_going_backwards_resets_baseline_even_without_uidvalidity(tmp_path):
    cp = tmp_path / "cp.json"
    _new(FakeIMAP({"500": _mail_bytes()}), cp)
    r = _new(FakeIMAP({"1": _mail_bytes(), "2": _mail_bytes()}), cp)
    assert r["baseline_set"] and r["messages"] == [] and r["last_uid"] == 2


# ── 기존(쌓인) 메일 분석 ────────────────────────────────────────────────


def _box(n=6):
    subjects = ["견적 요청", "광고 안내", "견적서 회신", "세금계산서", "광고 2", "회의 일정"]
    return {str(i + 1): _mail_bytes(subjects[i], frm=f"보낸이{i + 1} <u{i + 1}@example.com>") for i in range(n)}


def _existing(box, **kw):
    fake = FakeIMAP(box)
    return fake, reader.list_existing("skyjwsin", password=PW, factory=lambda h, p: fake, **kw)


def test_existing_is_newest_first_and_builds_server_side_date_criteria():
    fake, r = _existing(_box(), since=date(2026, 9, 1), before=date(2026, 10, 2), unseen_only=True)
    assert [m["uid"] for m in r["messages"]] == ["6", "5", "4", "3", "2", "1"]
    search = next(c for c in fake.calls if c[0] == "SEARCH")
    assert search[1][1:] == ("UNSEEN", "SINCE 01-Sep-2026", "BEFORE 02-Oct-2026")


def test_existing_filters_korean_keywords_in_subject_and_sender():
    _, r = _existing(_box(), subject_contains="견적")
    assert [m["subject"] for m in r["messages"]] == ["견적서 회신", "견적 요청"]
    _, r = _existing(_box(), from_contains="보낸이4")
    assert [m["uid"] for m in r["messages"]] == ["4"]


def test_existing_pages_with_next_before_uid():
    box = _box()
    _, first = _existing(box, limit=2)
    assert [m["uid"] for m in first["messages"]] == ["6", "5"] and first["next_before_uid"] == 5
    _, second = _existing(box, limit=2, before_uid=first["next_before_uid"])
    assert [m["uid"] for m in second["messages"]] == ["4", "3"]
    _, last = _existing(box, limit=50, before_uid=3)
    assert [m["uid"] for m in last["messages"]] == ["2", "1"] and last["next_before_uid"] is None


def test_existing_without_criteria_searches_all_and_reports_auth_failure():
    fake, _ = _existing(_box())
    assert next(c for c in fake.calls if c[0] == "SEARCH")[1][1:] == ("ALL",)
    r = reader.list_existing("skyjwsin", password=PW, factory=lambda h, p: FakeIMAP({}, auth_ok=False))
    assert r["error"] == "auth_failed"


def test_read_messages_reads_many_with_one_connection_and_marks_missing():
    box = {"1": _mail_bytes("a", body="첫 본문"), "2": _mail_bytes("b", body="둘째 본문", attach=True)}
    fake = FakeIMAP(box)
    r = reader.read_messages("skyjwsin", ["1", "2", "9"], password=PW, factory=lambda h, p: fake)
    assert [m["ok"] for m in r["messages"]] == [True, True, False]
    assert "첫 본문" in r["messages"][0]["body"] and r["messages"][1]["attachments"][0]["filename"] == "견적서.pdf"
    assert fake.readonly is True and all("PEEK" in c[1][1] for c in fake.calls if c[0] == "FETCH")


def test_read_messages_validates_uids_and_caps_count():
    assert reader.read_messages("skyjwsin", ["1", "x"], password=PW)["error"] == "bad_uid"
    assert reader.read_messages("skyjwsin", [], password=PW)["error"] == "bad_uid"
    box = {str(i): _mail_bytes(f"m{i}") for i in range(1, 40)}
    r = reader.read_messages("skyjwsin", list(box), password=PW, factory=lambda h, p: FakeIMAP(box))
    assert len(r["messages"]) == reader.MAX_READ_MANY


# ── sender ──────────────────────────────────────────────────────────────


def test_send_builds_message_and_reports_recipients_without_body():
    fake = FakeSMTP()
    r = sender.send_mail(
        "skyjwsin", "a@example.com; b@example.com", "제목", "본문", password=PW, factory=lambda h, p: fake
    )
    assert r == {"ok": True, "recipients": ["a@example.com", "b@example.com"], "refused": []}
    msg = fake.sent[0]
    assert (
        msg["From"] == "skyjwsin@naver.com" and msg["To"] == "a@example.com, b@example.com" and msg["Subject"] == "제목"
    )
    assert fake.quit_called and "본문" not in str(r)


@pytest.mark.parametrize("to", ["", "not-an-address", "a@example.com,b@", "a@example.com\nBcc: x@example.com@"])
def test_bad_recipients_are_rejected_before_connecting(to):
    with pytest.raises(ValueError):
        sender.send_mail("skyjwsin", to, "제목", "본문", password=PW, factory=_boom)


def test_header_injection_in_subject_is_rejected():
    with pytest.raises(ValueError):
        sender.validate_content("제목\nBcc: evil@example.com", "본문")


def test_too_many_recipients_rejected():
    with pytest.raises(ValueError):
        sender.parse_recipients([f"u{i}@example.com" for i in range(11)])


def test_send_failures_are_reported_not_raised():
    r = sender.send_mail("skyjwsin", ALICE, "s", "b", password=PW, factory=lambda h, p: FakeSMTP(auth_ok=False))
    assert r["error"] == "auth_failed"
    r = sender.send_mail("skyjwsin", ALICE, "s", "b", password=PW, factory=lambda h, p: FakeSMTP(fail_send=True))
    assert r["error"] == "send_failed" and PW not in str(r)
    assert sender.send_mail("skyjwsin", ALICE, "s", "b", password="")["error"] == "no_password"


# ── 예약 작업 등록 ──────────────────────────────────────────────────────


def test_fetch_is_auto_allowed_and_send_requires_approval():
    assert classify_action(actions.ACTIONS["naver_mail_fetch"].risk_action) == GRADE_AUTO_ALLOWED
    assert classify_action(actions.ACTIONS["naver_mail_send"].risk_action) == GRADE_USER_DELEGATED
    items = {i["key"]: i for i in actions.catalog()}
    assert items["naver_mail_send"]["requires_approval"] and not items["naver_mail_fetch"]["requires_approval"]
    assert {f["name"] for f in items["naver_mail_send"]["fields"]} == {"target", "to", "subject", "body"}


def test_send_params_validation():
    ok = actions._mail_send_params({"to": ALICE, "subject": "s", "body": "b"})
    assert ok["target"] == "skyjwsin" and ok["to"] == ALICE
    bad_cases = (
        {"to": "x", "subject": "s", "body": "b"},
        {"to": ALICE, "subject": "", "body": "b"},
        {"to": ALICE, "subject": "s", "body": "b", "cc": "z"},
        {"target": "nobody", "to": ALICE, "subject": "s", "body": "b"},
    )
    for bad in bad_cases:
        with pytest.raises(ValueError):
            actions._mail_send_params(bad)


def test_fetch_params_validation():
    assert actions._mail_fetch_params({}) == {"target": "skyjwsin", "unseen_only": True, "limit": 20}
    assert actions._mail_fetch_params({"unseen_only": "false", "limit": "5"})["unseen_only"] is False
    for bad in ({"limit": 0}, {"limit": 51}, {"limit": "abc"}, {"x": 1}):
        with pytest.raises(ValueError):
            actions._mail_fetch_params(bad)


def test_fetch_and_send_actions_run_through_reader_and_sender(monkeypatch):
    rows = [{"date": "d", "from": "f", "subject": "s"}]
    monkeypatch.setattr(reader, "list_messages", lambda *a, **k: {"ok": True, "total_matched": 1, "messages": rows})
    assert "최근 1통" in actions._run_naver_mail_fetch({"target": "skyjwsin", "unseen_only": True, "limit": 5})
    job = {"target": "skyjwsin", "to": ALICE, "subject": "s", "body": "b"}
    monkeypatch.setattr(sender, "send_mail", lambda *a, **k: {"ok": True, "recipients": [ALICE], "refused": []})
    assert "1명" in actions._run_naver_mail_send(job)
    monkeypatch.setattr(sender, "send_mail", lambda *a, **k: {"ok": False, "message": "거부"})
    with pytest.raises(RuntimeError, match="거부"):
        actions._run_naver_mail_send(job)
