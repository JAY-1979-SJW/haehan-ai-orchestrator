"""하나팩스 — '확인 필요' 번호 해소와 초안 만료. 실제 팩스는 나가지 않는다(엔진 호출 시 즉시 실패하도록 가짜로 막음)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from ai_orchestrator.connectors.hanafax import authorization_store as store
from ai_orchestrator.connectors.hanafax import authorization_service as service
from ai_orchestrator.connectors.hanafax import auto_send as flow


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    import scripts.hanafax.sender as engine

    def boom(*_a, **_k):
        raise AssertionError("실제 하나팩스 엔진이 호출되었습니다")

    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "fax_authorizations.db")
    monkeypatch.setattr(service, "_safe_path", lambda text, label: str(text).strip().strip('"'))
    monkeypatch.setattr(engine, "send_fax", boom)
    monkeypatch.setattr(engine, "send_fax_bulk", boom)


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
    service.approve(row["id"], user="a", live=True)
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
    detail = service.resolve_pending(row["id"], "027771001", "sent", user="a")
    assert detail["pending_numbers"] == []
    assert store.sent_numbers(row["document_hash"]) == {"027771001"}
    assert store.count_sent(row["id"]) == 1  # 같은 번호가 불명 + 확인된 성공으로 두 번 세어지지 않는다
    again = flow.run(row["id"], lambda *a: pytest.fail("이미 발송됨 — 재전송되면 안 된다"), datetime.now().astimezone())
    assert again.sent == 0


def test_resolve_not_sent_allows_retry(doc):
    row = _row(doc)
    _make_unknown(row)
    service.resolve_pending(row["id"], "027771001", "not_sent", user="a")
    sent: list[tuple] = []
    result = flow.run(
        row["id"],
        lambda *a: sent.append(a) or {"success": True, "job_id": "J", "message": "ok"},
        datetime.now().astimezone(),
    )
    assert result.sent == 1 and len(sent) == 1


def test_resolve_requires_pending_number_and_valid_outcome(doc):
    row = _row(doc)
    _make_unknown(row)
    with pytest.raises(ValueError, match="확인 필요"):
        service.resolve_pending(row["id"], "031-000-0000", "sent", user="a")  # 대기 상태가 아닌 번호
    with pytest.raises(ValueError, match="outcome"):
        service.resolve_pending(row["id"], "027771001", "maybe", user="a")
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
        service.approve(row["id"], user="a", live=False)
    assert not store.get_authorization(row["id"])["approved"]


def test_fresh_draft_is_not_expired_and_approved_never_expires(doc):
    row = _row(doc)
    assert service.preview(row["id"])["draft_expired"] is False
    service.approve(row["id"], user="a", live=False)
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat(timespec="seconds")
    con = sqlite3.connect(str(store._DB_PATH))
    con.execute("UPDATE authorizations SET created_at=? WHERE id=?", (old, row["id"]))
    con.commit()
    con.close()
    assert service.preview(row["id"])["draft_expired"] is False  # 이미 승인된 건은 만료 대상이 아니다


def test_scheduler_catalog_labels_distinguish_and_flag_live_authorizations(doc):
    from ai_orchestrator.services import scheduled_job_actions as actions

    dry = _row(doc, "02-777-2001")
    live = _row(doc, "02-777-2002")
    service.approve(dry["id"], user="a", live=False)
    service.approve(live["id"], user="a", live=True)
    entry = next(i for i in actions.catalog() if i["key"] == "hanafax_send")
    field = next(f for f in entry["fields"] if f["name"] == "authorization_id")
    assert "⚠ 실전송" in field["option_labels"][live["id"]] and "1곳" in field["option_labels"][live["id"]]
    assert "드라이런" in field["option_labels"][dry["id"]] and "⚠" not in field["option_labels"][dry["id"]]
    assert field["default"] == field["options"][0]  # 화면이 보여 주는 첫 항목과 기본값이 같다(빈 값 저장 방지)
