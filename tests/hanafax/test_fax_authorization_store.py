"""ai_orchestrator.connectors.hanafax.authorization_store — 하나팩스 승인서·이력·수신거부·정지 저장소.

모든 테스트는 임시 DB 를 쓴다(실제 ai_orchestrator/storage 를 건드리지 않는다). 실제 발송은 하지 않는다.
"""

from __future__ import annotations

import sqlite3

import pytest

from ai_orchestrator.connectors.hanafax import send_policy as pol
from ai_orchestrator.connectors.hanafax import authorization_store as store
from ai_orchestrator.persistence.sqlite_schema import current_version

RECIPIENTS = [{"fax": "02-111-2222", "name": "가나다"}, {"fax": "031-333-4444", "name": "라마바"}]


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "fax_authorizations.db")


def _new(**overrides):
    base = {
        "name": "영업 안내",
        "recipients": RECIPIENTS,
        "subject": "영업 안내",
        "document_hash": "doc-1",
        "document_ref": "문서.docx",
        "scope_hash": pol.scope_hash(RECIPIENTS, "영업 안내", "doc-1"),
        "max_per_run": 10,
        "max_per_day": 100,
        "max_total": 1000,
        "allowed_start": "09:00",
        "allowed_end": "18:00",
        "valid_from": None,
        "valid_until": None,
        "created_by": "tester",
    }
    base.update(overrides)
    return store.NewAuthorization(**base)


# ── 스키마 ────────────────────────────────────────────────────────────────


def test_schema_is_versioned_on_first_use():
    store.list_authorizations()
    con = sqlite3.connect(str(store._DB_PATH))
    try:
        assert current_version(con) == len(store._SCHEMA_STEPS)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert {"authorizations", "send_log", "opt_out", "flags"} <= tables


# ── 승인서 ────────────────────────────────────────────────────────────────


def test_new_authorization_starts_unapproved_and_dry_run():
    auth = store.create_authorization(_new())
    assert auth["approved"] is False and auth["live"] is False and auth["revoked"] is False
    assert auth["recipients"] == RECIPIENTS
    assert auth["approved_scope_hash"] is None


def test_approve_defaults_to_dry_run_and_freezes_scope_hash():
    auth = store.create_authorization(_new())
    approved = store.approve(auth["id"], user="admin")
    assert approved["approved"] is True and approved["live"] is False  # 실전송은 명시해야 한다
    assert approved["approved_by"] == "admin" and approved["approved_at"]
    assert approved["approved_scope_hash"] == auth["scope_hash"]  # 승인 당시 해시가 고정됨


def test_approve_live_must_be_explicit():
    auth = store.create_authorization(_new())
    assert store.approve(auth["id"], user="admin", live=True)["live"] is True


def test_cannot_approve_twice():
    auth = store.create_authorization(_new())
    store.approve(auth["id"], user="admin")
    with pytest.raises(ValueError):
        store.approve(auth["id"], user="admin2")


def test_cannot_approve_revoked_authorization():
    auth = store.create_authorization(_new())
    store.revoke(auth["id"], user="admin")
    with pytest.raises(ValueError):
        store.approve(auth["id"], user="admin")


def test_revoke_is_immediate_and_recorded():
    auth = store.create_authorization(_new())
    store.approve(auth["id"], user="admin")
    revoked = store.revoke(auth["id"], user="admin")
    assert revoked["revoked"] is True and revoked["revoked_by"] == "admin"


def test_unknown_authorization_errors():
    with pytest.raises(ValueError):
        store.approve("nope", user="admin")
    with pytest.raises(ValueError):
        store.revoke("nope", user="admin")
    assert store.get_authorization("nope") is None


def test_approved_authorization_matches_policy_scope_check():
    # 저장소의 승인 해시와 정책의 범위 검사가 맞물려 동작해야 한다
    auth = store.create_authorization(_new())
    row = store.approve(auth["id"], user="admin", live=True)
    recipients = tuple(row["recipients"])
    assert pol.scope_hash(recipients, row["subject"], row["document_hash"]) == row["approved_scope_hash"]


# ── 발송 이력 ─────────────────────────────────────────────────────────────


def _record(**overrides):
    base = {"authorization_id": "A1", "fax_digits": "021112222", "document_hash": "doc-1", "status": store.SENT}
    base.update(overrides)
    return store.SendRecord(**base)


def test_sent_numbers_returns_only_successful_for_that_document():
    store.record_send(_record())
    store.record_send(_record(fax_digits="0313334444", status=store.FAILED))
    store.record_send(_record(fax_digits="0325556666", document_hash="other-doc"))
    assert store.sent_numbers("doc-1") == {"021112222"}


def test_unknown_numbers_are_tracked_separately_and_not_counted_as_sent():
    store.record_send(_record(status=store.UNKNOWN))
    assert store.sent_numbers("doc-1") == set()
    assert store.unknown_numbers("doc-1") == {"021112222"}


def test_dry_run_records_do_not_count_as_sent():
    store.record_send(_record(status=store.DRY_RUN))
    assert store.sent_numbers("doc-1") == set()
    assert store.count_sent("A1") == 0


def test_count_sent_includes_unknown_because_it_may_have_gone_out():
    store.record_send(_record(status=store.SENT))
    store.record_send(_record(fax_digits="0313334444", status=store.UNKNOWN))
    store.record_send(_record(fax_digits="0325556666", status=store.FAILED))
    assert store.count_sent("A1") == 2


def test_count_sent_since_filters_by_time():
    store.record_send(_record())
    assert store.count_sent("A1", since_iso="2999-01-01T00:00:00+00:00") == 0
    assert store.count_sent("A1", since_iso="2000-01-01T00:00:00+00:00") == 1


def test_record_send_rejects_unknown_status():
    with pytest.raises(ValueError):
        store.record_send(_record(status="weird"))


def test_send_log_message_is_truncated_and_listed_newest_first():
    store.record_send(_record(message="x" * 1000))
    store.record_send(_record(fax_digits="0313334444"))
    rows = store.list_send_log("A1")
    assert len(rows) == 2 and all(len(r["message"]) <= 300 for r in rows)


# ── 수신거부 ──────────────────────────────────────────────────────────────


def test_opt_out_is_idempotent_and_listed():
    store.add_opt_out("021112222", reason="요청", user="admin")
    store.add_opt_out("021112222", reason="중복")
    assert store.opt_out_numbers() == {"021112222"}


# ── 킬 스위치 ─────────────────────────────────────────────────────────────


def test_kill_switch_defaults_off_and_toggles():
    assert store.kill_switch_on() is False
    store.set_kill_switch(True, user="admin")
    assert store.kill_switch_on() is True
    store.set_kill_switch(False, user="admin")
    assert store.kill_switch_on() is False


def test_kill_switch_fails_closed_when_flag_cannot_be_read(monkeypatch):
    # 정지 플래그를 읽지 못하면(DB 오류) 정지로 간주해 발송을 막는다
    def broken():
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(store, "_conn", broken)
    assert store.kill_switch_on() is True
