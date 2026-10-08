"""메일 순차 대량 발송 — 정책(순수)·저장소. 기준서 docs/specs/2026-10-02_mail_bulk_sequential.md B1."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time
from typing import Any

import pytest

from ai_orchestrator.connectors.naver_mail import bulk_policy as pol
from ai_orchestrator.connectors.naver_mail import bulk_store as store

NOW = datetime(2026, 10, 5, 10, 0)
RECIPS = tuple({"email": f"user{i}@example.com", "name": f"고객{i}"} for i in range(5))


def _auth(**over) -> pol.Authorization:
    kind, subject, body = pol.KIND_TRANSACTION, "안내", "본문"
    base: dict[str, Any] = dict(
        id="a1",
        recipients=RECIPS,
        subject=subject,
        body=body,
        attachments_hash="",
        kind=kind,
        approved_scope_hash=pol.scope_hash(RECIPS, subject, body, "", kind),
        approved=True,
        revoked=False,
        paused=False,
        live=True,
        valid_from=None,
        valid_until=None,
        max_per_run=100,
        max_per_day=200,
        max_total=1000,
        allowed_start=time(9, 0),
        allowed_end=time(18, 0),
    )
    base.update(over)
    return pol.Authorization(**base)


def _state(**over) -> pol.State:
    base: dict[str, Any] = dict(
        now=NOW,
        kill_switch_on=False,
        sent_today=0,
        sent_total=0,
        already_sent=set(),
        opted_out=set(),
        unknown_result=set(),
    )
    base.update(over)
    return pol.State(**base)


# ── 정책 ────────────────────────────────────────────────────────────────


def test_email_helpers():
    assert pol.is_valid_email(" A@Example.com ")
    assert not pol.is_valid_email("a@b")
    assert not pol.is_valid_email("")
    assert pol.mask_email("kim.chulsoo@naver.com") == "ki*********@naver.com"
    assert pol.mask_email("u0@example.com") == "u*@example.com"
    assert pol.mask_email("abc@example.com") == "a**@example.com"


def test_scope_hash_ignores_order_and_case_but_not_content():
    h = pol.scope_hash(RECIPS, "s", "b", "", "transaction")
    assert h == pol.scope_hash(tuple(reversed(RECIPS)), " s ", "b", "", "transaction")
    assert h != pol.scope_hash(RECIPS, "s", "b2", "", "transaction")
    assert h != pol.scope_hash(RECIPS, "s", "b", "att", "transaction")
    assert h != pol.scope_hash(RECIPS[:4], "s", "b", "", "transaction")


def test_send_keeps_order_and_respects_capacity():
    d = pol.evaluate(_auth(max_per_run=3), _state())
    assert d.action == pol.SEND
    assert [r["email"] for r in d.to_send] == ["user0@example.com", "user1@example.com", "user2@example.com"]
    assert [r for _, r in d.skipped] == [pol.LIMIT_REACHED] * 2


def test_daily_cap_and_total_cap():
    assert len(pol.evaluate(_auth(), _state(sent_today=198)).to_send) == 2
    assert pol.evaluate(_auth(), _state(sent_today=200)).reason == pol.LIMIT_REACHED
    assert len(pol.evaluate(_auth(max_total=3), _state(sent_total=2)).to_send) == 1


def test_resume_skips_already_sent_and_blocks_unknown_and_optout():
    d = pol.evaluate(
        _auth(),
        _state(
            already_sent={"user0@example.com"}, opted_out={"user1@example.com"}, unknown_result={"user2@example.com"}
        ),
    )
    assert [r["email"] for r in d.to_send] == ["user3@example.com", "user4@example.com"]
    assert {r for _, r in d.skipped} == {pol.ALREADY_SENT, pol.OPTED_OUT, pol.UNKNOWN_RESULT_PENDING}


@pytest.mark.parametrize(
    ("auth_over", "state_over", "reason"),
    [
        ({}, {"kill_switch_on": True}, pol.KILL_SWITCH),
        ({"approved": False}, {}, pol.NOT_APPROVED),
        ({"revoked": True}, {}, pol.REVOKED),
        ({"paused": True}, {}, pol.PAUSED),
        ({"valid_until": datetime(2026, 10, 1)}, {}, pol.EXPIRED),
        ({"valid_from": datetime(2026, 10, 6)}, {}, pol.NOT_YET_VALID),
        ({}, {"now": datetime(2026, 10, 5, 20, 0)}, pol.OUTSIDE_HOURS),
        ({"subject": "바뀐 제목"}, {}, pol.SCOPE_CHANGED),
    ],
)
def test_gates_block(auth_over, state_over, reason):
    d = pol.evaluate(_auth(**auth_over), _state(**state_over))
    assert d.reason == reason
    assert not d.to_send


def test_dry_run_flag_and_duplicates_and_invalid_addresses():
    dup = (*RECIPS, {"email": "USER0@example.com", "name": "x"}, {"email": "bad", "name": ""})
    auth = _auth(recipients=dup, live=False)
    auth = replace(auth, approved_scope_hash=pol.scope_hash(dup, "안내", "본문", "", "transaction"))
    d = pol.evaluate(auth, _state())
    assert d.dry_run is True
    assert len(d.to_send) == 5
    assert {r for _, r in d.skipped} == {pol.ALREADY_SENT, pol.INVALID_ADDRESS}


def test_interval_has_jitter_within_20_percent():
    assert pol.next_delay_sec(30, 0.0) == 24.0
    assert pol.next_delay_sec(30, 1.0) == 36.0
    assert pol.next_delay_sec(30, 0.5) == 30.0
    assert pol.next_delay_sec(1, 0.5) == pol.MIN_INTERVAL_SEC


def test_error_classification_and_pause_rules():
    assert pol.classify_error(535, "Authentication failed") == pol.ERR_AUTH
    assert pol.classify_error(554, "Daily sending quota exceeded") == pol.ERR_LIMIT
    assert pol.classify_error(550, "mailbox unavailable") == pol.ERR_RECIPIENT
    assert pol.classify_error(None, "timeout") == pol.ERR_TRANSIENT
    assert pol.should_pause(pol.ERR_AUTH, 0) == "auth_failed"
    assert pol.should_pause(pol.ERR_LIMIT, 0) == "limit_or_block"
    assert pol.should_pause(pol.ERR_TRANSIENT, 2) == ""
    assert pol.should_pause(pol.ERR_TRANSIENT, 3) == "consecutive_failures"
    assert pol.should_pause(pol.ERR_RECIPIENT, 0) == ""


def test_compliance_for_promo():
    assert pol.compliance_errors(pol.KIND_TRANSACTION, "견적 안내", "본문") == []
    assert len(pol.compliance_errors(pol.KIND_PROMO, "신제품 안내", "본문")) == 2
    assert pol.compliance_errors(pol.KIND_PROMO, "(광고) 신제품", "수신거부: 회신 주세요") == []
    assert pol.compliance_errors("other", "s", "b")


def test_render_personalization_escapes_html():
    f = {"이름": "<b>김</b>", "업체명": "해한"}
    assert pol.render("{업체명} {이름}님", f) == "해한 <b>김</b>님"
    assert pol.render("{업체명} {이름}님", f, html=True) == "해한 &lt;b&gt;김&lt;/b&gt;님"
    assert pol.render("{이름}", {}) == ""


# ── 저장소 ──────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "bulk.db")


def _new(**over) -> store.NewAuthorization:
    base: dict[str, Any] = dict(
        name="10월 안내",
        account="skyjwsin",
        kind="transaction",
        recipients=[{"email": "a@example.com", "name": "가"}],
        subject="안내",
        body="본문",
        attachments=[],
        attachments_hash="",
        document_hash=pol.document_hash("안내", "본문", ""),
        scope_hash="h1",
        interval_sec=30,
        max_per_run=50,
        max_per_day=200,
        max_total=1000,
        allowed_start="09:00",
        allowed_end="18:00",
        valid_from=None,
        valid_until=None,
        created_by="tester",
    )
    base.update(over)
    return store.NewAuthorization(**base)


def test_new_authorization_starts_unapproved_dry(db):
    a = store.create_authorization(_new())
    assert a["approved"] is False
    assert a["live"] is False
    assert a["paused"] is False
    assert a["recipients"][0]["email"] == "a@example.com"


def test_live_approval_requires_self_test(db):
    a = store.create_authorization(_new())
    with pytest.raises(ValueError, match="시험 발송"):
        store.approve(a["id"], user="u", live=True)
    store.mark_test_sent(a["id"])
    got = store.approve(a["id"], user="u", live=True)
    assert got["approved"]
    assert got["live"]
    assert got["approved_scope_hash"] == "h1"
    with pytest.raises(ValueError, match="이미 승인"):
        store.approve(a["id"], user="u")


def test_dry_run_approval_without_self_test_and_revoke(db):
    a = store.create_authorization(_new())
    assert store.approve(a["id"], user="u")["live"] is False
    assert store.revoke(a["id"], user="u")["revoked"] is True
    with pytest.raises(ValueError, match="취소"):
        store.resume(a["id"])


def test_pause_and_resume(db):
    a = store.create_authorization(_new())
    store.pause(a["id"], "limit_or_block")
    got = store.get_authorization(a["id"])
    assert got["paused"]
    assert got["paused_reason"] == "limit_or_block"
    assert store.resume(a["id"])["paused"] is False


def test_send_log_counts_dedupe_and_status_rules(db):
    a = store.create_authorization(_new())
    dh = a["document_hash"]
    for email, status in [("a@x.com", "sent"), ("b@x.com", "unknown"), ("c@x.com", "failed"), ("d@x.com", "dry_run")]:
        store.record_send(store.SendRecord(a["id"], email, dh, status))
    assert store.sent_emails(dh) == {"a@x.com"}
    assert store.unknown_emails(dh) == {"b@x.com"}
    assert store.count_sent(a["id"]) == 2  # sent + unknown
    assert store.count_by_status(a["id"]) == {"sent": 1, "unknown": 1, "failed": 1, "dry_run": 1}
    assert store.count_sent(a["id"], since_iso="2999-01-01T00:00:00+00:00") == 0
    with pytest.raises(ValueError, match="알 수 없는"):
        store.record_send(store.SendRecord(a["id"], "z@x.com", dh, "weird"))
    assert len(store.list_send_log(a["id"])) == 4


def test_opt_out_and_kill_switch(db):
    assert store.kill_switch_on() is False
    store.set_kill_switch(True, user="u")
    assert store.kill_switch_on() is True
    store.set_kill_switch(False, user="u")
    assert store.kill_switch_on() is False
    store.add_opt_out("x@example.com", reason="요청", user="u")
    store.add_opt_out("x@example.com")
    assert store.opt_out_emails() == {"x@example.com"}
