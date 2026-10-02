"""하나팩스 — '확인 필요' 번호 해소와 초안 만료. 실제 팩스는 나가지 않는다(엔진 호출 시 즉시 실패하도록 가짜로 막음)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from ai_orchestrator.persistence import fax_authorization_store as store
from ai_orchestrator.services import fax_approval_pin as approval_pin
from ai_orchestrator.services import hanafax_authorization_service as service
from ai_orchestrator.workflows import hanafax_auto_send as flow

PIN = "test-pin-123"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    import scripts.hanafax.sender as engine

    def boom(*_a, **_k):
        raise AssertionError("실제 하나팩스 엔진이 호출되었습니다")

    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "fax_authorizations.db")
    monkeypatch.setattr(service, "_safe_path", lambda text, label: str(text).strip().strip('"'))
    monkeypatch.setattr(engine, "send_fax", boom)
    monkeypatch.setattr(engine, "send_fax_bulk", boom)
    approval_pin.set_pin(PIN)


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "공문.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    return path


def _row(doc, fax="02-777-1001"):
    return service.create(
        {
            "name": "n",
            "subject": "s",
            "document_ref": str(doc),
            "recipients": [{"fax": fax, "name": "a"}],
            "allowed_start": "00:00",
            "allowed_end": "23:59",
        },
        user="u",
    )


def _make_unknown(row):
    service.approve(row["id"], user="a", live=True, pin=PIN)
    flow.run(
        row["id"], lambda *a: {"success": False, "job_id": None, "message": "타임아웃"}, datetime.now().astimezone()
    )


def test_unknown_number_appears_as_pending_and_blocks_resend(doc):
    row = _row(doc)
    _make_unknown(row)
    assert service.preview(row["id"])["pending_numbers"] == ["027771001"]
    again = flow.run(row["id"], lambda *a: pytest.fail("재전송되면 안 된다"), datetime.now().astimezone())
    assert again.sent == 0


def test_resolve_sent_marks_success_and_never_resends(doc):
    row = _row(doc)
    _make_unknown(row)
    detail = service.resolve_pending(row["id"], "027771001", "sent", pin=PIN, user="a")
    assert detail["pending_numbers"] == []
    assert store.sent_numbers(row["document_hash"]) == {"027771001"}
    assert store.count_sent(row["id"]) == 1  # 같은 번호가 불명 + 확인된 성공으로 두 번 세어지지 않는다
    again = flow.run(row["id"], lambda *a: pytest.fail("이미 발송됨 — 재전송되면 안 된다"), datetime.now().astimezone())
    assert again.sent == 0


def test_resolve_not_sent_allows_retry(doc):
    row = _row(doc)
    _make_unknown(row)
    service.resolve_pending(row["id"], "027771001", "not_sent", pin=PIN, user="a")
    sent: list[tuple] = []
    result = flow.run(
        row["id"],
        lambda *a: sent.append(a) or {"success": True, "job_id": "J", "message": "ok"},
        datetime.now().astimezone(),
    )
    assert result.sent == 1 and len(sent) == 1


def test_resolve_requires_pin_and_pending_number(doc):
    row = _row(doc)
    _make_unknown(row)
    with pytest.raises(ValueError, match="PIN"):
        service.resolve_pending(row["id"], "027771001", "sent", pin="wrong", user="a")
    with pytest.raises(ValueError, match="확인 필요"):
        service.resolve_pending(row["id"], "031-000-0000", "sent", pin=PIN, user="a")  # 대기 상태가 아닌 번호
    with pytest.raises(ValueError, match="outcome"):
        service.resolve_pending(row["id"], "027771001", "maybe", pin=PIN, user="a")
    assert service.preview(row["id"])["pending_numbers"] == ["027771001"]  # 거부된 시도는 상태를 바꾸지 않는다


def test_stale_draft_cannot_be_approved(doc):
    row = _row(doc)
    old = (datetime.now(UTC) - timedelta(hours=service.DRAFT_TTL_HOURS + 1)).isoformat(timespec="seconds")
    con = sqlite3.connect(str(store._DB_PATH))
    con.execute("UPDATE authorizations SET created_at=? WHERE id=?", (old, row["id"]))
    con.commit()
    con.close()
    assert service.preview(row["id"])["draft_expired"] is True
    with pytest.raises(ValueError, match="만료"):
        service.approve(row["id"], user="a", live=False, pin=PIN)
    assert not store.get_authorization(row["id"])["approved"]


def test_fresh_draft_is_not_expired_and_approved_never_expires(doc):
    row = _row(doc)
    assert service.preview(row["id"])["draft_expired"] is False
    service.approve(row["id"], user="a", live=False, pin=PIN)
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat(timespec="seconds")
    con = sqlite3.connect(str(store._DB_PATH))
    con.execute("UPDATE authorizations SET created_at=? WHERE id=?", (old, row["id"]))
    con.commit()
    con.close()
    assert service.preview(row["id"])["draft_expired"] is False  # 이미 승인된 건은 만료 대상이 아니다
