"""하나팩스 자동 발송 — 적대적 리뷰 후 보강 검증 (동시 실행·선점·문서 교체·날짜 경계·긴 실행·경로 제한·레거시 API).

**실제 팩스는 절대 나가지 않는다**: 엔진(`scripts.hanafax.sender`)의 전송 함수는 모두 가짜로 바꾼다.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

import pytest

from ai_orchestrator.connectors.hanafax import auto_sender as adapter
from ai_orchestrator.connectors.hanafax import send_policy as pol
from ai_orchestrator.connectors.hanafax import authorization_store as store
from ai_orchestrator.connectors.hanafax import authorization_service as service
from ai_orchestrator.connectors.hanafax import auto_send as flow

_REAL_SAFE_PATH = service._safe_path


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "fax_authorizations.db")


@pytest.fixture(autouse=True)
def _no_real_engine(monkeypatch):
    import scripts.hanafax.sender as engine

    def boom(*_a, **_k):
        raise AssertionError("실제 하나팩스 엔진이 호출되었습니다")

    monkeypatch.setattr(engine, "send_fax", boom)
    monkeypatch.setattr(engine, "send_fax_bulk", boom)


@pytest.fixture(autouse=True)
def _open_path_policy(monkeypatch):
    """임시 폴더(AppData 아래)도 쓰도록 경로 제한을 푼다 — 제한 자체는 전용 테스트가 원본 함수로 검증한다."""
    monkeypatch.setattr(service, "_safe_path", lambda text, label: str(text).strip().strip('"'))


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "공문.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    return path


def _approved(doc, recipients, **over):
    payload = {
        "name": "n",
        "subject": "s",
        "document_ref": str(doc),
        "recipients": recipients,
        "max_per_run": 10,
        "max_per_day": 50,
        "max_total": 100,
        "allowed_start": "00:00",
        "allowed_end": "23:59",
        **over,
    }
    row = service.create(payload, user="u")
    service.approve(row["id"], user="a", live=True)
    return row


def _now() -> datetime:
    return datetime.now().astimezone()


def test_concurrent_runs_cannot_double_send(doc):
    row = _approved(doc, [{"fax": "02-777-0001", "name": "a"}])
    calls: list[str] = []

    def slow(number, name, subject):
        calls.append(number)
        time.sleep(0.3)
        return {"success": True, "job_id": "J", "message": "ok"}

    results: list[flow.RunResult] = []
    threads = [threading.Thread(target=lambda: results.append(flow.run(row["id"], slow, _now()))) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1
    assert any(r.reason == "already_running" for r in results)


def test_claim_blocks_resend_when_result_never_recorded(doc, monkeypatch):
    row = _approved(doc, [{"fax": "02-777-0002", "name": "a"}])
    calls: list[tuple] = []
    real_record = store.record_send

    def failing_after_claim(rec):
        if rec.status == store.CLAIMED:
            return real_record(rec)
        raise RuntimeError("db down")

    ok = {"success": True, "job_id": "J", "message": "ok"}
    monkeypatch.setattr(store, "record_send", failing_after_claim)
    with pytest.raises(RuntimeError):
        flow.run(row["id"], lambda *a: calls.append(a) or ok, _now())
    monkeypatch.setattr(store, "record_send", real_record)
    again = flow.run(row["id"], lambda *a: calls.append(a) or ok, _now())
    assert len(calls) == 1 and again.sent == 0  # 결과를 기록하지 못한 번호는 확인 전까지 다시 보내지 않는다


def test_claim_failure_prevents_sending(doc, monkeypatch):
    row = _approved(doc, [{"fax": "02-777-0003", "name": "a"}])

    def fail(_rec):
        raise RuntimeError("db down")

    monkeypatch.setattr(store, "record_send", fail)
    called: list[tuple] = []
    with pytest.raises(RuntimeError):
        flow.run(row["id"], lambda *a: called.append(a), _now())
    assert called == []  # 선점을 못 하면 전송하지 않는다


def test_failed_after_claim_is_retriable_but_unknown_is_not(doc):
    row = _approved(doc, [{"fax": "02-777-0004", "name": "a"}])
    flow.run(
        row["id"],
        lambda *a: {"success": False, "job_id": None, "definite_failure": True, "message": "로그인 실패"},
        _now(),
    )
    assert store.unknown_numbers(row["document_hash"]) == set()  # 요청 전 명확한 실패는 재시도 가능
    flow.run(row["id"], lambda *a: {"success": False, "job_id": None, "message": "타임아웃"}, _now())
    assert store.unknown_numbers(row["document_hash"]) == {"027770004"}  # 결과 불명은 멈춘다


def test_document_swap_between_sends_is_blocked(doc, monkeypatch):
    import scripts.hanafax.sender as engine

    calls: list[dict] = []
    monkeypatch.setattr(
        engine, "send_fax", lambda **kw: calls.append(kw) or {"success": True, "job_id": "J", "message": "ok"}
    )
    send = adapter.build_sender(str(doc), adapter.file_sha256(str(doc)))
    assert send("0211112222", "a", "s")["success"] is True
    doc.write_bytes(b"%PDF-1.4 SWAPPED")
    result = send("0311112222", "b", "s")
    assert result["success"] is False and result["definite_failure"] is True and len(calls) == 1


def test_bulk_document_swap_is_blocked(doc, monkeypatch):
    import scripts.hanafax.sender as engine

    calls: list[object] = []
    monkeypatch.setattr(
        engine, "send_fax_bulk", lambda *a, **k: calls.append(a) or {"success": True, "job_id": "J", "sent_faxes": []}
    )
    send = adapter.build_bulk_sender(str(doc), adapter.file_sha256(str(doc)))
    doc.write_bytes(b"%PDF-1.4 SWAPPED")
    assert send([{"fax": "0211112222", "name": ""}], "s")["definite_failure"] is True and calls == []


def test_day_boundary_counts_in_utc(doc):
    row = service.create(
        {"name": "n", "subject": "s", "document_ref": str(doc), "recipients": [{"fax": "02-777-0005", "name": ""}]},
        user="u",
    )
    store.record_send(store.SendRecord(row["id"], "027770005", row["document_hash"], store.SENT, "J", "ok"))
    assert store.count_sent(row["id"], since_iso=flow._day_start_iso(_now())) == 1


def test_run_stops_midway_when_window_closes(doc, monkeypatch):
    row = _approved(doc, [{"fax": f"02-888-{1000 + i}", "name": ""} for i in range(3)])
    sent_to: list[str] = []

    def sender(number, name, subject):
        sent_to.append(number)
        monkeypatch.setattr(flow.policy, "recheck", lambda auth, now: "outside_allowed_hours")  # 첫 건 직후 시간대 종료
        return {"success": True, "job_id": "J", "message": "ok"}

    result = flow.run(row["id"], sender, _now())
    assert len(sent_to) == 1 and result.stopped_midway


def test_optout_added_during_run_applies_to_remaining(doc):
    row = _approved(doc, [{"fax": f"02-888-{2000 + i}", "name": ""} for i in range(3)])
    sent_to: list[str] = []

    def sender(number, name, subject):
        sent_to.append(number)
        store.add_opt_out("028882002", user="u")  # 첫 건을 보내는 동안 세 번째 번호가 수신거부됨
        return {"success": True, "job_id": "J", "message": "ok"}

    flow.run(row["id"], sender, _now())
    assert "028882002" not in sent_to and len(sent_to) == 2


def test_log_message_is_shortened_and_digits_masked():
    msg = flow._safe_message("결과 불명확: 계정 exampleuser 전송잔액 12345678원 번호 0212345678 " + "x" * 300)
    assert len(msg) <= 120 and "0212345678" not in msg and "12345678" not in msg


def test_060_and_080_numbers_rejected():
    assert pol.parse_number("060-700-1234") is None and pol.parse_number("080-123-4567") is None


def test_path_policy_blocks_unc_relative_hidden_and_outside_roots(tmp_path, monkeypatch):
    safe_dir = tmp_path / "docs"
    safe_dir.mkdir()
    good = safe_dir / "공문.pdf"
    good.write_bytes(b"%PDF")
    monkeypatch.setattr(service, "_allowed_roots", lambda: [safe_dir.resolve()])
    monkeypatch.setattr(service, "_BLOCKED_PARTS", {".ssh"})
    assert _REAL_SAFE_PATH(str(good), "문서") == str(good.resolve())
    for bad in ("\\\\attacker\\share\\x.pdf", "//attacker/share/x.pdf", "상대/경로.pdf", ""):
        with pytest.raises(ValueError):
            _REAL_SAFE_PATH(bad, "문서")
    outside = tmp_path / "other.pdf"
    outside.write_bytes(b"%PDF")
    with pytest.raises(ValueError, match="허용된 폴더"):
        _REAL_SAFE_PATH(str(outside), "문서")
    hidden = safe_dir / ".ssh"
    hidden.mkdir()
    (hidden / "k.pdf").write_bytes(b"%PDF")
    with pytest.raises(ValueError, match="설정·키"):
        _REAL_SAFE_PATH(str(hidden / "k.pdf"), "문서")
