"""하나팩스 자동 발송 P3 — 발송기 어댑터 · 승인서 서비스 · 예약 작업 `hanafax_send`.

**실제 팩스는 절대 나가지 않는다**: `scripts.hanafax.sender.send_fax` 는 모든 테스트에서 가짜로 바꾼다.
"""

from __future__ import annotations

import pytest

from ai_orchestrator.connectors.hanafax import authorization_service as service
from ai_orchestrator.connectors.hanafax import authorization_store as store
from ai_orchestrator.connectors.hanafax import auto_sender as adapter
from ai_orchestrator.contracts.action_risk_policy import GRADE_AUTO_ALLOWED, classify_action
from ai_orchestrator.services import scheduled_job_actions as actions

RECIPIENTS = [{"fax": "02-111-2222", "name": "가나다"}, {"fax": "031-333-4444", "name": "라마바"}]


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "fax_authorizations.db")


@pytest.fixture(autouse=True)
def _open_path_policy(monkeypatch):
    """임시 폴더(AppData 아래)도 쓰도록 경로 제한을 푼다 — 제한 자체는 test_hanafax_hardening.py 가 검증한다."""
    monkeypatch.setattr(service, "_safe_path", lambda text, label: str(text).strip().strip('"'))


@pytest.fixture(autouse=True)
def sent(monkeypatch):
    """엔진의 send_fax 를 가짜로 바꾸고 호출 기록을 돌려준다(실제 전송 차단)."""
    import scripts.hanafax.sender as engine

    calls: list[dict] = []

    def fake_send_fax(**kwargs):
        calls.append(kwargs)
        return {"success": True, "job_id": f"J{len(calls)}", "message": "팩스 전송 완료", "simulated": False}

    def fake_send_fax_bulk(receivers, subject, attach_file=None, **_):
        for r in receivers:
            calls.append({"receiver_fax": r["receiver_fax"], "attach_file": attach_file, "bulk": True})
        return {"success": True, "job_id": f"B{len(calls)}", "sent_faxes": [r["receiver_fax"] for r in receivers], "missing_faxes": [], "message": "팩스 전송 완료"}

    monkeypatch.setattr(engine, "send_fax", fake_send_fax)
    monkeypatch.setattr(engine, "send_fax_bulk", fake_send_fax_bulk)  # 단체발송 경로도 막는다 — 테스트는 실제 엔진에 닿지 않는다
    return calls


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "공문.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    return path


def _payload(doc, **over):
    return {
        "name": "영업 안내",
        "subject": "영업 안내",
        "document_ref": str(doc),
        "recipients": RECIPIENTS,
        "max_per_run": 10,
        "max_per_day": 50,
        "max_total": 100,
        "allowed_start": "00:00",
        "allowed_end": "23:59",
        **over,
    }


# ── 서비스 ─────────────────────────────────────────────────────────────────


def test_create_fixes_scope_and_normalizes_numbers(doc):
    row = service.create(_payload(doc, recipients=[*RECIPIENTS, {"fax": "021112222", "name": "중복"}]), user="u")
    assert [r["fax"] for r in row["recipients"]] == ["021112222", "0313334444"]  # 숫자만, 중복 제거
    assert row["document_hash"] == adapter.file_sha256(str(doc))
    assert not row["approved"] and not row["live"]


@pytest.mark.parametrize(
    "over",
    [
        {"recipients": []},
        {"recipients": [{"fax": "12", "name": "x"}]},
        {"document_ref": "없는파일.pdf"},
        {"subject": " "},
        {"allowed_start": "20:00", "allowed_end": "09:00"},
        {"max_per_run": -1},
        {"max_per_run": 1001},
    ],
)
def test_create_rejects_bad_input(doc, over):
    with pytest.raises(ValueError):
        service.create(_payload(doc, **over), user="u")


def test_create_rejects_disallowed_extension(tmp_path):
    bad = tmp_path / "비밀.txt"
    bad.write_text("x")
    with pytest.raises(ValueError):
        service.create(_payload(bad), user="u")


def test_approve_refuses_when_document_changed(doc):
    row = service.create(_payload(doc), user="u")
    doc.write_bytes(b"%PDF-1.4 changed")
    with pytest.raises(ValueError, match="바뀌"):
        service.approve(row["id"], user="a", live=True)


def test_send_log_masks_numbers(doc):
    row = service.create(_payload(doc), user="u")
    store.record_send(store.SendRecord(row["id"], "0211112222", row["document_hash"], store.SENT, "J1", "ok"))
    assert service.send_log(row["id"])[0]["fax_digits"] == "021*****22"


# ── 어댑터 ─────────────────────────────────────────────────────────────────


def test_build_sender_rejects_changed_document(doc):
    expected = adapter.file_sha256(str(doc))
    doc.write_bytes(b"%PDF-1.4 changed")
    with pytest.raises(adapter.DocumentChanged):
        adapter.build_sender(str(doc), expected)


def test_build_sender_passes_attachment_and_marks_pre_send_failure(doc, monkeypatch):
    import scripts.hanafax.sender as engine

    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        return {"success": False, "job_id": None, "message": "로그인 실패. URL: x", "simulated": False}

    monkeypatch.setattr(engine, "send_fax", fake)
    send = adapter.build_sender(str(doc), adapter.file_sha256(str(doc)))
    result = send("0211112222", "가나다", "제목")
    assert result["definite_failure"] is True
    assert calls[0]["attach_file"] == str(doc) and calls[0]["receiver_fax"] == "0211112222"


@pytest.mark.parametrize("message", ["타임아웃: x", "결과 불명확: y", "전송 경고: 잔액 부족"])
def test_ambiguous_failures_are_not_definite(message):
    assert not adapter.is_pre_send_failure({"success": False, "job_id": None, "message": message})


# ── 예약 작업 ──────────────────────────────────────────────────────────────


def test_action_is_registered_without_per_run_approval():
    spec = actions.get_action("hanafax_send")
    assert spec is not None and classify_action(spec.risk_action) == GRADE_AUTO_ALLOWED
    entry = next(i for i in actions.catalog() if i["key"] == "hanafax_send")
    assert entry["requires_approval"] is False  # 회차 승인 대신 승인서가 승인 역할


def test_validate_requires_approved_authorization(doc):
    spec = actions.get_action("hanafax_send")
    row = service.create(_payload(doc), user="u")
    with pytest.raises(ValueError):
        spec.validate({"authorization_id": row["id"]})  # 승인 전
    with pytest.raises(ValueError):
        spec.validate({"authorization_id": "nope"})
    with pytest.raises(ValueError):
        spec.validate({"authorization_id": row["id"], "to": "x"})  # 승인서 밖 값 금지
    service.approve(row["id"], user="a", live=False)
    assert spec.validate({"authorization_id": row["id"]}) == {"authorization_id": row["id"]}
    service.revoke(row["id"], user="a")
    with pytest.raises(ValueError):
        spec.validate({"authorization_id": row["id"]})


def test_run_dry_run_sends_nothing(doc, sent):
    row = service.create(_payload(doc), user="u")
    service.approve(row["id"], user="a", live=False)
    message = actions.get_action("hanafax_send").run({"authorization_id": row["id"]})
    assert "드라이런" in message and sent == []
    assert {r["status"] for r in store.list_send_log(row["id"])} == {store.DRY_RUN}


def test_run_live_sends_within_scope(doc, sent):
    row = service.create(_payload(doc, max_per_run=1), user="u")
    service.approve(row["id"], user="a", live=True)
    message = actions.get_action("hanafax_send").run({"authorization_id": row["id"]})
    assert "발송 1건" in message and len(sent) == 1  # 1회 한도
    assert sent[0]["attach_file"] == str(doc)


def test_run_live_stops_when_document_changed(doc, sent):
    row = service.create(_payload(doc), user="u")
    service.approve(row["id"], user="a", live=True)
    doc.write_bytes(b"%PDF-1.4 changed")
    with pytest.raises(RuntimeError, match="바뀌"):
        actions.get_action("hanafax_send").run({"authorization_id": row["id"]})
    assert sent == []


def test_run_denied_by_kill_switch(doc, sent):
    row = service.create(_payload(doc), user="u")
    service.approve(row["id"], user="a", live=True)
    service.set_kill_switch(True, user="a")
    with pytest.raises(RuntimeError, match="kill_switch"):
        actions.get_action("hanafax_send").run({"authorization_id": row["id"]})
    assert sent == []


def test_run_unknown_result_raises_and_does_not_resend(doc, sent, monkeypatch):
    import scripts.hanafax.sender as engine

    timeout = {"success": False, "job_id": None, "message": "타임아웃: x"}
    monkeypatch.setattr(engine, "send_fax", lambda **kw: sent.append(kw) or timeout)
    monkeypatch.setattr(
        engine, "send_fax_bulk", lambda receivers, subject, attach_file=None, **_: sent.extend({"receiver_fax": r["receiver_fax"]} for r in receivers) or timeout
    )
    row = service.create(_payload(doc, max_per_run=1), user="u")
    service.approve(row["id"], user="a", live=True)
    with pytest.raises(RuntimeError, match="확인 필요 1건"):
        actions.get_action("hanafax_send").run({"authorization_id": row["id"]})
    with pytest.raises(RuntimeError):  # 다음 회차: 불명 번호는 건너뛰고 다음 번호만
        actions.get_action("hanafax_send").run({"authorization_id": row["id"]})
    assert len({s["receiver_fax"] for s in sent}) == len(sent)  # 같은 번호로 다시 보내지 않았다


# ── 지금 발송 · AI 허용목록 ──────────────────────────────────────────────────


def test_run_now_requires_approval(doc):
    row = service.create(_payload(doc), user="u")
    with pytest.raises(ValueError, match="승인"):
        service.run_now(row["id"])  # 승인 전 발송 불가
    service.approve(row["id"], user="a", live=True)
    service.revoke(row["id"], user="a")
    with pytest.raises(ValueError, match="취소"):
        service.run_now(row["id"])


def test_run_now_runs_in_background_and_reports(doc, sent):
    import time

    row = service.create(_payload(doc), user="u")
    service.approve(row["id"], user="a", live=True)
    assert service.run_now(row["id"])["running"] is True or service.run_status(row["id"])["last"]
    for _ in range(100):
        last = service.run_status(row["id"])["last"]
        if last:
            break
        time.sleep(0.05)
    assert last and last["status"] == "done" and len(sent) == 2


def test_ai_registry_exposes_draft_only_not_approve_or_run():
    """AI(MCP call_api)는 승인 대기 초안만 만들 수 있다 — 승인·발송·정지·수신거부 경로는 허용목록에 없어야 한다."""
    from ai_orchestrator.server.mcp_server import API_REGISTRY

    fax = {k: v for k, v in API_REGISTRY.items() if "/hanafax/" in v["path"]}
    assert set(fax) == {"hanafax.draft", "hanafax.authorizations", "hanafax.address_groups", "hanafax.address_group_sync", "hanafax.address_group_sync_status"}
    for spec in fax.values():
        assert not any(w in spec["path"] for w in ("approve", "/run", "kill-switch", "opt-out", "revoke", "/send", "batch"))


# ── 주소록 가져오기 · 묶음(단체) 발송 ─────────────────────────────────────────


def _book(tmp_path, rows):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["NO", "업체명", "팩스번호"])
    for i, (name, fax) in enumerate(rows, 1):
        ws.append([i, name, fax])
    path = tmp_path / "주소록.xlsx"
    wb.save(path)
    return path


def test_import_recipients_excludes_bad_duplicate_optout_and_old_log(tmp_path, monkeypatch):
    store.add_opt_out("0311111111", user="u")
    monkeypatch.setattr(service, "already_sent_numbers", lambda: {"0322222222"})
    rows = [("가", "02-111-2222"), ("나", "021112222"), ("다", "abc"), ("라", "031-111-1111"), ("마", "032-222-2222"), ("바", "042-333-4444")]
    recipients, summary = service.import_recipients(str(_book(tmp_path, rows)))
    assert [r["fax"] for r in recipients] == ["021112222", "0423334444"]
    assert summary == {"rows": 6, "invalid": 1, "duplicate": 1, "opted_out_or_already_sent": 2, "to_send": 2}


def test_create_from_file_defaults_limits_to_recipient_count(tmp_path, doc, monkeypatch):
    monkeypatch.setattr(service, "already_sent_numbers", lambda: set())
    book = _book(tmp_path, [(f"업체{i}", f"02-300-{1000 + i}") for i in range(7)])
    row = service.create(
        {"name": "대량", "subject": "제목", "document_ref": str(doc), "recipients_file": str(book), "allowed_start": "00:00", "allowed_end": "23:59"},
        user="u",
    )
    assert row["max_per_run"] == row["max_per_day"] == row["max_total"] == 7
    assert row["import_summary"]["to_send"] == 7


def test_bulk_run_sends_in_chunks_via_group_sender(doc, monkeypatch):
    import scripts.hanafax.sender as engine

    calls = []

    def fake_bulk(receivers, subject, attach_file=None, **_):
        calls.append([r["receiver_fax"] for r in receivers])
        return {"success": True, "job_id": f"B{len(calls)}", "sent_faxes": [r["receiver_fax"] for r in receivers], "missing_faxes": [], "message": "팩스 전송 완료"}

    monkeypatch.setattr(engine, "send_fax_bulk", fake_bulk)
    monkeypatch.setattr("ai_orchestrator.connectors.hanafax.auto_send.BULK_CHUNK", 2)
    recipients = [{"fax": f"02-400-{1000 + i}", "name": f"업체{i}"} for i in range(5)]
    row = service.create(_payload(doc, recipients=recipients, max_per_run=10), user="u")
    service.approve(row["id"], user="a", live=True)
    from datetime import datetime

    from ai_orchestrator.connectors.hanafax import auto_send as flow

    result = flow.run_bulk(row["id"], adapter.build_bulk_sender(str(doc), row["document_hash"]), datetime.now().astimezone(), chunk_size=2)
    assert result.sent == 5 and [len(c) for c in calls] == [2, 2, 1]


def test_bulk_unknown_chunk_stops_remaining_chunks(doc, monkeypatch):
    from datetime import datetime

    import scripts.hanafax.sender as engine
    from ai_orchestrator.connectors.hanafax import auto_send as flow

    calls = []
    monkeypatch.setattr(
        engine, "send_fax_bulk", lambda receivers, subject, attach_file=None, **_: calls.append(receivers) or {"success": False, "job_id": None, "message": "타임아웃: x"}
    )
    recipients = [{"fax": f"02-500-{1000 + i}", "name": ""} for i in range(4)]
    row = service.create(_payload(doc, recipients=recipients, max_per_run=10), user="u")
    service.approve(row["id"], user="a", live=True)
    result = flow.run_bulk(row["id"], adapter.build_bulk_sender(str(doc), row["document_hash"]), datetime.now().astimezone(), chunk_size=2)
    assert result.unknown == 2 and result.stopped_midway and len(calls) == 1  # 첫 묶음 결과 불명 → 다음 묶음은 보내지 않는다


# ── 하나팩스 실제 화면 미리보기(전송 없음) ──────────────────────────────────────


def test_preview_module_never_presses_send_button():
    """미리보기 모듈에는 '팩스보내기' 버튼 셀렉터가 없고, 결과(전송) 페이지 이동을 차단하며 대화상자를 취소한다."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "scripts" / "hanafax" / "preview.py").read_text(encoding="utf-8")
    assert "e_money_chk" not in src
    assert "submit_Result*" in src and "route.abort()" in src
    assert "d.dismiss()" in src and "d.accept()" not in src


def test_start_preview_runs_in_background_and_reports(doc, monkeypatch, tmp_path):
    import time

    import scripts.hanafax.preview as preview_mod

    monkeypatch.setattr(service, "_PREVIEW_DIR", tmp_path / "pv")

    def fake_capture(fax_nos, subject, attach_file, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake png")
        return {"ok": True, "message": "미리보기 완료 — 전송하지 않았습니다", "shown": len(fax_nos), "total": len(fax_nos), "missing": []}

    monkeypatch.setattr(preview_mod, "capture_preview", fake_capture)
    row = service.create(_payload(doc), user="u")
    service.start_preview(row["id"])
    status = service.preview_status(row["id"])
    for _ in range(100):
        status = service.preview_status(row["id"])
        if status["state"]:
            break
        time.sleep(0.05)
    assert status["state"]["ok"] and status["image_ready"] and not status["running"]


def test_preview_rejected_for_changed_document_or_unknown_id(doc):
    row = service.create(_payload(doc), user="u")
    doc.write_bytes(b"%PDF-1.4 changed")
    with pytest.raises(ValueError, match="달라"):
        service.start_preview(row["id"])
    with pytest.raises(ValueError, match="찾을 수"):
        service.start_preview("nope")


# ── 적대적 검토 후 보강 (번호 정규화·유효기간) ───────────────────────────────────


@pytest.mark.parametrize("raw", ["02-111-2222 #5", "+82-2-111-2222", "001-1234-5678", "010-1234-5678", "02-111-2222 ext5", "02/111/2222", "1588-1234"])
def test_parse_number_rejects_ambiguous_or_costly_numbers(raw):
    from ai_orchestrator.connectors.hanafax import send_policy as pol

    assert pol.parse_number(raw) is None


@pytest.mark.parametrize("raw", ["02-111-2222", "(02) 111-2222", "031 333 4444", "0311112222"])
def test_parse_number_accepts_domestic_numbers(raw):
    from ai_orchestrator.connectors.hanafax import send_policy as pol

    assert pol.parse_number(raw) and pol.parse_number(raw).startswith("0")


def test_create_rejects_extension_and_international_recipients(doc):
    for bad in ("02-111-2222 #5", "001-1234-5678"):
        with pytest.raises(ValueError, match="형식"):
            service.create(_payload(doc, recipients=[{"fax": bad, "name": "x"}]), user="u")


def test_create_rejects_unreadable_or_inverted_validity(doc):
    with pytest.raises(ValueError, match="ISO"):
        service.create(_payload(doc, valid_until="내일"), user="u")
    with pytest.raises(ValueError, match="빨라야"):
        service.create(_payload(doc, valid_from="2027-01-02T00:00:00", valid_until="2027-01-01T00:00:00"), user="u")


def test_run_denies_when_stored_validity_is_unreadable(doc, sent):
    """저장소 값이 깨져 있어도(예: 수동 편집) 만료를 무시하지 않고 거부한다."""
    import sqlite3

    from ai_orchestrator.connectors.hanafax import auto_send as flow

    row = service.create(_payload(doc), user="u")
    service.approve(row["id"], user="a", live=True)
    con = sqlite3.connect(str(store._DB_PATH))
    con.execute("UPDATE authorizations SET valid_until='내일' WHERE id=?", (row["id"],))
    con.commit()
    con.close()
    result = flow.run(row["id"], lambda *a: {"success": True, "job_id": "x"}, __import__("datetime").datetime.now().astimezone())
    assert result.decision == "deny" and result.reason == "invalid_validity_period" and sent == []


# ── 승인·정지 해제에는 PIN 이 필요 없다(사용자 결정으로 PIN 제거) ───────────────────────────────


def test_approve_and_kill_switch_need_no_pin(doc):
    row = service.create(_payload(doc), user="u")
    assert service.approve(row["id"], user="a", live=False)["approved"]
    service.set_kill_switch(True, user="a")
    assert store.kill_switch_on()
    assert service.set_kill_switch(False, user="a") == {"kill_switch": False}
