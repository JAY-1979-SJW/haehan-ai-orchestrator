"""메일 순차 대량 발송 실행기 — 가짜 발송기로만 시험(실제 메일·대기 없음). 기준서 2026-10-02_mail_bulk_sequential.md B2."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from ai_orchestrator.connectors.naver_mail import bulk_policy as pol
from ai_orchestrator.connectors.naver_mail import bulk_store as store
from ai_orchestrator.connectors.naver_mail import bulk_workflow as bulk

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 5, 10, 0, tzinfo=KST)


CLOCK = {"now": NOW}


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "bulk.db")
    CLOCK["now"] = NOW
    # 발송 이력의 시각도 시험 시계를 따른다(실제 현재 시각과 섞이면 '오늘 건수'가 어긋난다)
    monkeypatch.setattr(store, "_now", lambda: CLOCK["now"].astimezone(UTC).isoformat(timespec="seconds"))


def _make(n=5, *, live=True, subject="{업체명} 안내", body="{이름}님 안녕하세요", **over) -> str:
    recipients = [{"email": f"u{i}@example.com", "name": f"고객{i}", "company": f"회사{i}"} for i in range(n)]
    new = store.NewAuthorization(
        name="시험",
        account="skyjwsin",
        kind="transaction",
        recipients=recipients,
        subject=subject,
        body=body,
        attachments=[],
        attachments_hash="",
        document_hash=pol.document_hash(subject, body, ""),
        scope_hash=pol.scope_hash(recipients, subject, body, "", "transaction"),
        interval_sec=over.pop("interval_sec", 30),
        max_per_run=over.pop("max_per_run", 1000),
        max_per_day=over.pop("max_per_day", 1000),
        max_total=over.pop("max_total", 5000),
        allowed_start="09:00",
        allowed_end="18:00",
        valid_from=None,
        valid_until=None,
        created_by="t",
    )
    auth = store.create_authorization(new)
    if live:
        store.mark_test_sent(auth["id"])
    store.approve(auth["id"], user="t", live=live)
    return auth["id"]


class FakeSend:
    """미리 정한 결과를 차례로 돌려주는 가짜 발송기. 받은 Draft 를 모두 기록한다."""

    def __init__(self, results=None, hook=None):
        self.results = list(results or [])
        self.drafts = []
        self.hook = hook

    def __call__(self, draft):
        self.drafts.append(draft)
        if self.hook:
            self.hook(len(self.drafts))
        item = self.results.pop(0) if self.results else {"ok": True, "refused": []}
        if isinstance(item, Exception):
            raise item
        return item


def _run(auth_id, send, **kw):
    sleeps: list[float] = []
    out = bulk.run(auth_id, send, lambda: CLOCK["now"], sleep=sleeps.append, rand=lambda: 0.5, **kw)
    return out, sleeps


OK = {"ok": True, "refused": []}
TRANSIENT = {"ok": False, "error": "send_failed", "code": 451, "message": "try again later"}
LIMIT = {"ok": False, "error": "send_failed", "code": 554, "message": "Daily sending quota exceeded"}
REFUSED = {"ok": False, "error": "send_failed", "code": 550, "message": "mailbox unavailable"}
AUTH = {"ok": False, "error": "auth_failed", "code": 535, "message": "denied"}
UNKNOWN = {"ok": False, "error": "send_unknown", "code": None, "message": "connection lost"}


def test_sends_one_by_one_in_order_with_interval_and_personalization(db):
    auth_id = _make(4)
    send = FakeSend()
    out, sleeps = _run(auth_id, send)
    assert (out.sent, out.failed, out.unknown) == (4, 0, 0)
    assert [d.to for d in send.drafts] == [[f"u{i}@example.com"] for i in range(4)]  # 1통 1수신자, 목록 순서
    assert [d.subject for d in send.drafts] == [f"회사{i} 안내" for i in range(4)]
    assert send.drafts[2].body == "고객2님 안녕하세요"
    assert sleeps == [30.0] * 3  # 첫 통 앞에는 대기 없음, 이후 건마다 간격


def test_200_recipients_run_sequentially(db):
    auth_id = _make(200)
    send = FakeSend()
    out, sleeps = _run(auth_id, send)
    assert out.sent == 200
    assert len(sleeps) == 199
    assert [d.to[0] for d in send.drafts] == [f"u{i}@example.com" for i in range(200)]
    assert store.count_by_status(auth_id) == {"sent": 200}


def test_daily_cap_stops_then_next_run_same_day_sends_nothing(db):
    auth_id = _make(5, max_per_day=3)
    first, _ = _run(auth_id, FakeSend())
    assert first.sent == 3
    second, _ = _run(auth_id, FakeSend())
    assert (second.decision, second.reason) == (pol.SKIP, pol.LIMIT_REACHED)


def test_next_day_resumes_with_remaining_only(db):
    auth_id = _make(5, max_per_day=3)
    _run(auth_id, FakeSend())
    CLOCK["now"] = NOW + timedelta(days=1)
    send = FakeSend()
    out, _ = _run(auth_id, send)
    assert out.sent == 2
    assert [d.to[0] for d in send.drafts] == ["u3@example.com", "u4@example.com"]  # 이미 보낸 3명은 건너뜀


def test_three_transient_failures_pause_and_resume_continues(db):
    auth_id = _make(6)
    send = FakeSend([OK, TRANSIENT, TRANSIENT, TRANSIENT])
    out, _ = _run(auth_id, send)
    assert (out.sent, out.failed) == (1, 3)
    assert out.paused_reason == "consecutive_failures"
    assert len(send.drafts) == 4  # 5번째 이후는 보내지 않음
    denied, _ = _run(auth_id, FakeSend())
    assert (denied.decision, denied.reason) == (pol.DENY, pol.PAUSED)
    store.resume(auth_id)
    send2 = FakeSend()
    again, _ = _run(auth_id, send2)
    assert again.sent == 5  # 성공 1명만 빼고 실패했던 3명 포함 재시도


def test_success_resets_failure_streak(db):
    auth_id = _make(6)
    out, _ = _run(auth_id, FakeSend([TRANSIENT, TRANSIENT, OK, TRANSIENT, TRANSIENT, OK]))
    assert out.paused_reason == ""
    assert (out.sent, out.failed) == (2, 4)


def test_limit_response_pauses_immediately(db):
    auth_id = _make(5)
    send = FakeSend([OK, LIMIT])
    out, _ = _run(auth_id, send)
    assert out.paused_reason == "limit_or_block"
    assert len(send.drafts) == 2


def test_auth_failure_pauses_without_recording_that_recipient(db):
    auth_id = _make(3)
    out, _ = _run(auth_id, FakeSend([AUTH]))
    assert out.paused_reason == "auth_failed"
    assert store.count_by_status(auth_id) == {}  # 그 수신자의 잘못이 아니므로 이력 없음
    store.resume(auth_id)
    again, _ = _run(auth_id, FakeSend())
    assert again.sent == 3


def test_single_recipient_refusal_continues_without_pause(db):
    auth_id = _make(4)
    out, _ = _run(auth_id, FakeSend([OK, REFUSED, OK, OK]))
    assert (out.sent, out.failed, out.paused_reason) == (3, 1, "")


def test_unknown_result_is_never_retried_and_pauses(db):
    auth_id = _make(4)
    out, _ = _run(auth_id, FakeSend([OK, UNKNOWN]))
    assert (out.sent, out.unknown) == (1, 1)
    assert out.paused_reason == "unknown_result"
    store.resume(auth_id)
    send = FakeSend()
    again, _ = _run(auth_id, send)
    assert [d.to[0] for d in send.drafts] == ["u2@example.com", "u3@example.com"]  # u1(불확실)은 재전송하지 않음
    assert any(s["reason"] == pol.UNKNOWN_RESULT_PENDING for s in again.skipped)


def test_exception_from_sender_is_unknown_not_retried(db):
    auth_id = _make(3)
    out, _ = _run(auth_id, FakeSend([RuntimeError("boom")]))
    assert out.unknown == 1
    assert out.paused_reason == "unknown_result"


def test_dry_run_never_calls_sender(db):
    auth_id = _make(3, live=False)
    send = FakeSend()
    out, sleeps = _run(auth_id, send)
    assert out.dry_run is True
    assert send.drafts == []
    assert sleeps == []
    assert store.count_by_status(auth_id) == {"dry_run": 3}


def test_kill_switch_pressed_mid_run_stops_remaining(db):
    auth_id = _make(5)

    def flip(n):
        if n == 2:
            store.set_kill_switch(True, user="t")

    send = FakeSend(hook=flip)
    out, _ = _run(auth_id, send)
    assert out.sent == 2
    assert out.stopped_midway is True
    assert len(send.drafts) == 2


def test_revoke_mid_run_stops(db):
    auth_id = _make(5)
    send = FakeSend(hook=lambda n: store.revoke(auth_id, user="t") if n == 1 else None)
    out, _ = _run(auth_id, send)
    assert out.sent == 1
    assert out.stopped_midway is True


def test_outside_allowed_hours_sends_nothing(db):
    auth_id = _make(3)
    send = FakeSend()
    CLOCK["now"] = datetime(2026, 10, 5, 22, 0, tzinfo=KST)
    out, _ = _run(auth_id, send)
    assert out.reason == pol.OUTSIDE_HOURS
    assert send.drafts == []


def test_opted_out_recipient_is_skipped(db):
    auth_id = _make(3)
    store.add_opt_out("u1@example.com")
    send = FakeSend()
    out, _ = _run(auth_id, send)
    assert [d.to[0] for d in send.drafts] == ["u0@example.com", "u2@example.com"]
    assert any(s["reason"] == pol.OPTED_OUT for s in out.skipped)


def test_summary_masks_addresses(db):
    auth_id = _make(2, max_per_run=1)
    out, _ = _run(auth_id, FakeSend())
    text = str(out.summary())
    assert "u1@example.com" not in text
    assert "u1@example.com".replace("u1", "u*") in text or "*" in text
