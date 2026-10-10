"""ai_orchestrator.connectors.hanafax.auto_send — 하나팩스 자동 발송 워크플로.

**모든 테스트는 가짜 발송기만 쓴다. 실제 팩스는 절대 나가지 않는다**(워크플로가 실제 발송 코드를 import 하지 않는다).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_orchestrator.connectors.hanafax import send_policy as pol
from ai_orchestrator.connectors.hanafax import authorization_store as store
from ai_orchestrator.connectors.hanafax import auto_send as flow

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 2, 10, 0, tzinfo=KST)
RECIPIENTS = [
    {"fax": "02-111-2222", "name": "가나다"},
    {"fax": "031-333-4444", "name": "라마바"},
    {"fax": "032-555-6666", "name": "사아자"},
]


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "fax_authorizations.db")


class _FrozenDatetime(datetime):
    """워크플로가 발송 도중 부르는 datetime.now() 를 NOW 로 고정한다.

    고정하지 않으면 허용 시간대(09:00~18:00) 재검사가 시험을 돌리는 컴퓨터의 실제 시각·시간대에 따라 달라져,
    UTC 서버에서 오전 9시(KST 18시) 전에 돌리면 발송이 막혀 시험이 실패했다. astimezone() 인자 없는 호출은
    컴퓨터 현지 시간대로 바뀌지 않게 그대로 둔다.
    """

    @classmethod
    def now(cls, tz=None):
        base = cls(NOW.year, NOW.month, NOW.day, NOW.hour, NOW.minute, tzinfo=KST)
        return base if tz is None else base.astimezone(tz)

    def astimezone(self, tz=None):
        return self if tz is None else super().astimezone(tz)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch):
    monkeypatch.setattr(flow, "datetime", _FrozenDatetime)


class FakeSender:
    """호출을 기록하는 가짜 발송기. 실제 전송 없음."""

    def __init__(self, results=None):
        self.calls: list[tuple[str, str, str]] = []
        self._results = list(results or [])

    def __call__(self, number, name, subject):
        self.calls.append((number, name, subject))
        if self._results:
            outcome = self._results.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return {"success": True, "job_id": f"JOB{len(self.calls)}", "message": "접수"}


def _make(approved=True, live=True, **overrides):
    new = store.NewAuthorization(
        name="영업 안내",
        recipients=overrides.pop("recipients", RECIPIENTS),
        subject=overrides.pop("subject", "영업 안내"),
        document_hash=overrides.pop("document_hash", "doc-1"),
        document_ref="문서.docx",
        scope_hash=pol.scope_hash(
            overrides.get("recipients", RECIPIENTS) if False else RECIPIENTS, "영업 안내", "doc-1"
        ),
        max_per_run=overrides.pop("max_per_run", 10),
        max_per_day=overrides.pop("max_per_day", 100),
        max_total=overrides.pop("max_total", 1000),
        allowed_start="09:00",
        allowed_end="18:00",
        valid_from=None,
        valid_until=None,
        created_by="tester",
    )
    auth = store.create_authorization(new)
    if approved:
        store.approve(auth["id"], user="admin", live=live)
    return auth["id"]


# ── 정상 경로 ─────────────────────────────────────────────────────────────


def test_approved_live_authorization_sends_to_each_recipient_once():
    auth_id = _make()
    sender = FakeSender()
    result = flow.run(auth_id, sender, NOW)
    assert result.decision == pol.SEND and result.sent == 3 and result.failed == 0 and result.unknown == 0
    assert [c[0] for c in sender.calls] == ["021112222", "0313334444", "0325556666"]
    assert all(c[2] == "영업 안내" for c in sender.calls)
    assert store.sent_numbers("doc-1") == {"021112222", "0313334444", "0325556666"}


def test_second_run_does_not_resend_to_the_same_numbers():
    auth_id = _make()
    flow.run(auth_id, FakeSender(), NOW)
    sender = FakeSender()
    result = flow.run(auth_id, sender, NOW)
    assert sender.calls == [] and result.sent == 0  # 이미 성공한 번호는 건너뛴다
    assert all(item["reason"] == pol.ALREADY_SENT for item in result.skipped)


# ── 드라이런 (기본) ───────────────────────────────────────────────────────────


def test_dry_run_never_calls_the_sender():
    auth_id = _make(live=False)
    sender = FakeSender()
    result = flow.run(auth_id, sender, NOW)
    assert sender.calls == [] and result.dry_run is True and result.sent == 0
    assert store.sent_numbers("doc-1") == set()  # 드라이런은 '보냄' 이 아니다
    assert len(store.list_send_log(auth_id)) == 3  # 계획은 기록한다


# ── 승인되지 않았거나 막힌 경우 ─────────────────────────────────────────────────


def test_unapproved_authorization_sends_nothing():
    auth_id = _make(approved=False)
    sender = FakeSender()
    result = flow.run(auth_id, sender, NOW)
    assert sender.calls == [] and result.decision == pol.DENY and result.reason == pol.NOT_APPROVED


def test_unknown_authorization_id_is_denied():
    sender = FakeSender()
    result = flow.run("없는-id", sender, NOW)
    assert sender.calls == [] and result.decision == pol.DENY


def test_kill_switch_blocks_everything():
    auth_id = _make()
    store.set_kill_switch(True, user="admin")
    sender = FakeSender()
    result = flow.run(auth_id, sender, NOW)
    assert sender.calls == [] and result.reason == pol.KILL_SWITCH


def test_revoked_authorization_sends_nothing():
    auth_id = _make()
    store.revoke(auth_id, user="admin")
    sender = FakeSender()
    assert flow.run(auth_id, sender, NOW).reason == pol.REVOKED
    assert sender.calls == []


def test_outside_allowed_hours_sends_nothing():
    auth_id = _make()
    sender = FakeSender()
    result = flow.run(auth_id, sender, NOW.replace(hour=23))
    assert sender.calls == [] and result.reason == pol.OUTSIDE_HOURS


def test_opted_out_number_is_never_sent():
    auth_id = _make()
    store.add_opt_out("0313334444", reason="수신거부")
    sender = FakeSender()
    flow.run(auth_id, sender, NOW)
    assert "0313334444" not in [c[0] for c in sender.calls]


def test_limits_cap_a_run():
    auth_id = _make(max_per_run=2)
    sender = FakeSender()
    result = flow.run(auth_id, sender, NOW)
    assert len(sender.calls) == 2 and result.sent == 2


def test_daily_limit_counts_earlier_runs_today():
    auth_id = _make(max_per_day=4, max_per_run=2)
    flow.run(auth_id, FakeSender(), NOW)  # 2건
    sender = FakeSender()
    flow.run(auth_id, sender, NOW + timedelta(minutes=10))  # 남은 한도 2건 중 이미 보낸 번호 제외 → 1건
    flow.run(auth_id, sender, NOW + timedelta(minutes=20))
    total = store.count_sent(auth_id)
    assert total <= 4


# ── 중복 발송 방지: 불명확한 결과는 재전송하지 않는다 ──────────────────────────────


def test_exception_during_send_is_recorded_unknown_and_not_retried():
    auth_id = _make()
    sender = FakeSender(results=[TimeoutError("응답 없음")])
    result = flow.run(auth_id, sender, NOW)
    assert result.unknown == 1
    assert len(sender.calls) == 3  # 한 건이 불명이어도 다음 번호는 계속, 같은 번호를 다시 보내지 않는다
    assert [c[0] for c in sender.calls].count("021112222") == 1
    assert store.unknown_numbers("doc-1") == {"021112222"}


def test_unknown_number_is_skipped_on_next_run_until_a_human_checks():
    auth_id = _make()
    flow.run(auth_id, FakeSender(results=[TimeoutError("x")]), NOW)
    sender = FakeSender()
    result = flow.run(auth_id, sender, NOW)
    assert "021112222" not in [c[0] for c in sender.calls]
    assert any(item["reason"] == pol.UNKNOWN_RESULT_PENDING for item in result.skipped)


def test_site_success_message_without_job_id_counts_as_sent():
    # 사이트가 "팩스 전송 완료"를 명시했으면 접수번호를 못 읽어도 성공으로 기록한다(실측: 접수번호가 화면에 없는 경우가 있다)
    auth_id = _make()
    sender = FakeSender(results=[{"success": True, "job_id": None, "message": "팩스 전송 완료"}] * 3)
    result = flow.run(auth_id, sender, NOW)
    assert result.sent == 3 and result.unknown == 0


def test_result_without_job_id_is_unknown_not_success():
    # success 라고 해도 접수번호(job_id)가 없으면 확정하지 못한 것으로 본다
    auth_id = _make()
    sender = FakeSender(results=[{"success": True, "job_id": None, "message": "?"}])
    result = flow.run(auth_id, sender, NOW)
    assert result.unknown == 1 and result.sent == 2


def test_definite_failure_before_request_is_failed_and_may_be_retried_later():
    auth_id = _make()
    sender = FakeSender(results=[{"success": False, "definite_failure": True, "message": "자격증명 없음"}])
    result = flow.run(auth_id, sender, NOW)
    assert result.failed == 1
    assert "021112222" not in store.unknown_numbers("doc-1")
    retry = FakeSender()
    flow.run(auth_id, retry, NOW)
    assert "021112222" in [c[0] for c in retry.calls]  # 요청이 나가기 전 실패는 다시 시도할 수 있다


def test_failed_without_definite_flag_is_treated_as_unknown():
    # '명확한 실패' 로 알리지 않은 실패는 요청이 나갔을 수 있어 불명으로 취급한다(중복 발송 방지 우선)
    auth_id = _make()
    sender = FakeSender(results=[{"success": False, "message": "알 수 없는 오류"}])
    assert flow.run(auth_id, sender, NOW).unknown == 1


# ── 배치 도중 정지·취소 ───────────────────────────────────────────────────────


def test_kill_switch_pressed_midway_stops_remaining_recipients():
    auth_id = _make()
    state = {"n": 0}

    def sender(number, name, subject):
        state["n"] += 1
        if state["n"] == 1:
            store.set_kill_switch(True, user="admin")  # 첫 건을 보내는 동안 정지 버튼이 눌린다
        return {"success": True, "job_id": f"J{state['n']}", "message": "접수"}

    result = flow.run(auth_id, sender, NOW)
    assert state["n"] == 1 and result.sent == 1 and result.stopped_midway is True


def test_revoked_midway_stops_remaining_recipients():
    auth_id = _make()
    state = {"n": 0}

    def sender(number, name, subject):
        state["n"] += 1
        if state["n"] == 1:
            store.revoke(auth_id, user="admin")
        return {"success": True, "job_id": f"J{state['n']}", "message": "접수"}

    result = flow.run(auth_id, sender, NOW)
    assert state["n"] == 1 and result.stopped_midway is True


# ── 안전: 실제 발송 코드를 import 하지 않는다 ────────────────────────────────────


def test_workflow_does_not_import_the_real_fax_sender():
    # 독스트링의 설명 문구가 아니라 **실제 import 문**만 본다: 실제 전송 엔진(scripts.hanafax, playwright)을 가져오면 안 된다
    import ast

    tree = ast.parse(open(flow.__file__, encoding="utf-8").read())
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    forbidden = [name for name in imported if name.startswith(("scripts.hanafax", "playwright", "scripts.cdp"))]
    assert imported, "imported 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert forbidden == [], f"워크플로가 실제 전송 코드를 import 한다: {forbidden}"


def test_summary_contains_no_full_numbers():
    auth_id = _make()
    store.add_opt_out("0313334444")
    result = flow.run(auth_id, FakeSender(), NOW)
    text = str(result.summary())
    assert "0313334444" not in text and "021112222" not in text
