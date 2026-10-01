"""하나팩스 자동 발송 P3 — 발송기 어댑터 · 승인서 서비스 · 예약 작업 `hanafax_send`.

**실제 팩스는 절대 나가지 않는다**: `scripts.hanafax.sender.send_fax` 는 모든 테스트에서 가짜로 바꾼다.
"""

from __future__ import annotations

import pytest

from ai_orchestrator.connectors import hanafax_auto_sender as adapter
from ai_orchestrator.local_agent.action_risk_policy import GRADE_AUTO_ALLOWED, classify_action
from ai_orchestrator.persistence import fax_authorization_store as store
from ai_orchestrator.services import hanafax_authorization_service as service
from ai_orchestrator.workflows import scheduled_job_actions as actions

RECIPIENTS = [{"fax": "02-111-2222", "name": "가나다"}, {"fax": "031-333-4444", "name": "라마바"}]


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "fax_authorizations.db")


@pytest.fixture(autouse=True)
def sent(monkeypatch):
    """엔진의 send_fax 를 가짜로 바꾸고 호출 기록을 돌려준다(실제 전송 차단)."""
    import scripts.hanafax.sender as engine

    calls: list[dict] = []

    def fake_send_fax(**kwargs):
        calls.append(kwargs)
        return {"success": True, "job_id": f"J{len(calls)}", "message": "팩스 전송 완료", "simulated": False}

    monkeypatch.setattr(engine, "send_fax", fake_send_fax)
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
        {"max_per_run": 0},
        {"max_per_run": 1000},
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

    monkeypatch.setattr(
        engine, "send_fax", lambda **kw: sent.append(kw) or {"success": False, "job_id": None, "message": "타임아웃: x"}
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
    from ai_orchestrator.mcp_server import API_REGISTRY

    fax = {k: v for k, v in API_REGISTRY.items() if "/hanafax/" in v["path"]}
    assert set(fax) == {"hanafax.draft", "hanafax.authorizations"}
    for spec in fax.values():
        assert not any(w in spec["path"] for w in ("approve", "/run", "kill-switch", "opt-out", "revoke", "/send", "batch"))
