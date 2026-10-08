"""ai_orchestrator.connectors.hanafax.send_policy — 하나팩스 자동 발송 정책 판정 (순수 함수).

외부 수신자에게 나가는 되돌릴 수 없는 발송을 가두는 로직이라, 모든 거부 경로와 fail-closed 동작을 검증한다.
실제 발송은 하지 않는다(이 모듈은 판정만 한다).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta, timezone

import pytest

from ai_orchestrator.connectors.hanafax import send_policy as pol

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 2, 10, 0, tzinfo=KST)  # 금요일 오전 10시(허용 시간대 안)

RECIPIENTS = (
    {"fax": "02-111-2222", "name": "가나다 주식회사"},
    {"fax": "031-333-4444", "name": "라마바 주식회사"},
    {"fax": "032-555-6666", "name": "사아자 주식회사"},
)


def _auth(**overrides):
    base = {
        "id": "A1",
        "recipients": RECIPIENTS,
        "subject": "영업 안내",
        "document_hash": "doc-hash-1",
        "approved_scope_hash": pol.scope_hash(RECIPIENTS, "영업 안내", "doc-hash-1"),
        "approved": True,
        "revoked": False,
        "live": True,
        "valid_from": None,
        "valid_until": None,
        "max_per_run": 10,
        "max_per_day": 100,
        "max_total": 1000,
        "allowed_start": time(9, 0),
        "allowed_end": time(18, 0),
    }
    base.update(overrides)
    return pol.Authorization(**base)


def _state(**overrides):
    base = {
        "now": NOW,
        "kill_switch_on": False,
        "sent_today": 0,
        "sent_total": 0,
        "already_sent": frozenset(),
        "opted_out": frozenset(),
        "unknown_result": frozenset(),
    }
    base.update(overrides)
    return pol.State(**base)


# ── 번호·범위 해시 ─────────────────────────────────────────────────────────


def test_normalize_and_validate_numbers():
    assert pol.normalize_number(" 02-123-4567 ") == "021234567"
    assert pol.is_valid_number("02-1234-5678")
    assert not pol.is_valid_number("1234567")  # 0 으로 시작하지 않음
    assert not pol.is_valid_number("02-12")  # 너무 짧음
    assert not pol.is_valid_number("0212345678901234")  # 너무 김
    assert not pol.is_valid_number("")


def test_mask_number_hides_middle():
    masked = pol.mask_number("02-1234-5678")
    assert masked.startswith("021") and masked.endswith("78") and "*" in masked
    assert "1234" not in masked


def test_scope_hash_ignores_format_and_order_but_not_content():
    base = pol.scope_hash(RECIPIENTS, "영업 안내", "d")
    reordered = pol.scope_hash(tuple(reversed(RECIPIENTS)), "영업 안내", "d")
    spaced = pol.scope_hash(
        [{"fax": "021112222", "name": " 가나다 주식회사 "}, RECIPIENTS[1], RECIPIENTS[2]], " 영업 안내 ", "d"
    )
    assert base == reordered == spaced
    assert pol.scope_hash(RECIPIENTS, "영업 안내!", "d") != base  # 제목
    assert pol.scope_hash(RECIPIENTS, "영업 안내", "d2") != base  # 문서
    changed = ({"fax": "02-111-2223", "name": "가나다 주식회사"}, RECIPIENTS[1], RECIPIENTS[2])
    assert pol.scope_hash(changed, "영업 안내", "d") != base  # 번호 한 자리
    renamed = ({"fax": "02-111-2222", "name": "다른 회사"}, RECIPIENTS[1], RECIPIENTS[2])
    assert pol.scope_hash(renamed, "영업 안내", "d") != base  # 이름
    assert pol.scope_hash(RECIPIENTS[:2], "영업 안내", "d") != base  # 수신자 삭제
    assert (
        pol.scope_hash((*RECIPIENTS, {"fax": "02-999-9999", "name": "신규"}), "영업 안내", "d") != base
    )  # 수신자 추가


# ── 정상 경로 ─────────────────────────────────────────────────────────────


def test_approved_authorization_sends_to_all_recipients():
    decision = pol.evaluate(_auth(), _state())
    assert decision.action == pol.SEND
    assert [r["fax"] for r in decision.to_send] == ["021112222", "0313334444", "0325556666"]
    assert decision.dry_run is False
    assert decision.skipped == ()


def test_dry_run_authorization_never_marks_live():
    decision = pol.evaluate(_auth(live=False), _state())
    assert decision.action == pol.SEND and decision.dry_run is True


# ── 승인서 자체의 거부 사유 (fail-closed) ──────────────────────────────────────


@pytest.mark.parametrize(
    ("overrides", "state_overrides", "expected_action", "expected_reason"),
    [
        ({}, {"kill_switch_on": True}, pol.DENY, pol.KILL_SWITCH),
        ({"approved": False}, {}, pol.DENY, pol.NOT_APPROVED),
        ({"revoked": True}, {}, pol.DENY, pol.REVOKED),
        ({"valid_until": NOW - timedelta(seconds=1)}, {}, pol.DENY, pol.EXPIRED),
        ({"valid_from": NOW + timedelta(hours=1)}, {}, pol.SKIP, pol.NOT_YET_VALID),
        ({"allowed_start": time(13, 0), "allowed_end": time(18, 0)}, {}, pol.SKIP, pol.OUTSIDE_HOURS),
    ],
)
def test_authorization_gates(overrides, state_overrides, expected_action, expected_reason):
    decision = pol.evaluate(_auth(**overrides), _state(**state_overrides))
    assert decision.action == expected_action
    assert decision.reason == expected_reason
    assert decision.to_send == ()


def test_kill_switch_overrides_everything_even_a_perfect_authorization():
    decision = pol.evaluate(_auth(), _state(kill_switch_on=True))
    assert decision.action == pol.DENY and decision.reason == pol.KILL_SWITCH


def test_revoked_beats_expiry_and_scope_checks_order_is_fail_closed():
    # 정지·미승인·취소는 다른 사유보다 먼저 막는다
    decision = pol.evaluate(_auth(revoked=True, valid_until=NOW - timedelta(days=1)), _state())
    assert decision.reason == pol.REVOKED


# ── 범위 변경 — 가장 중요한 안전장치 ───────────────────────────────────────────


def test_changed_recipient_after_approval_is_denied():
    tampered = ({"fax": "02-111-2223", "name": "가나다 주식회사"}, RECIPIENTS[1], RECIPIENTS[2])
    decision = pol.evaluate(_auth(recipients=tampered), _state())  # 승인 해시는 원래 값 기준
    assert decision.action == pol.DENY and decision.reason == pol.SCOPE_CHANGED
    assert decision.to_send == ()


def test_added_recipient_after_approval_is_denied():
    added = (*RECIPIENTS, {"fax": "02-999-9999", "name": "몰래 추가"})
    decision = pol.evaluate(_auth(recipients=added), _state())
    assert decision.reason == pol.SCOPE_CHANGED


def test_changed_subject_or_document_after_approval_is_denied():
    assert pol.evaluate(_auth(subject="다른 제목"), _state()).reason == pol.SCOPE_CHANGED
    assert pol.evaluate(_auth(document_hash="다른-문서"), _state()).reason == pol.SCOPE_CHANGED


def test_tampered_scope_is_denied_even_with_kill_switch_off_and_dry_run():
    decision = pol.evaluate(_auth(live=False, subject="바꿈"), _state())
    assert decision.action == pol.DENY  # 드라이런이라도 승인 범위를 벗어나면 거부


# ── 수신자 단위 건너뜀 ────────────────────────────────────────────────────


def test_already_sent_numbers_are_skipped():
    decision = pol.evaluate(_auth(), _state(already_sent={"021112222"}))
    assert [r["fax"] for r in decision.to_send] == ["0313334444", "0325556666"]
    assert any(reason == pol.ALREADY_SENT for _, reason in decision.skipped)


def test_opted_out_numbers_are_never_sent():
    decision = pol.evaluate(_auth(), _state(opted_out={"0313334444"}))
    assert "0313334444" not in [r["fax"] for r in decision.to_send]
    assert any(reason == pol.OPTED_OUT for _, reason in decision.skipped)


def test_unknown_result_numbers_are_not_retried():
    # 전송 결과를 확정 못 한 번호는 중복 발송 위험 때문에 재전송하지 않는다
    decision = pol.evaluate(_auth(), _state(unknown_result={"0325556666"}))
    assert "0325556666" not in [r["fax"] for r in decision.to_send]
    assert any(reason == pol.UNKNOWN_RESULT_PENDING for _, reason in decision.skipped)


def test_invalid_numbers_are_skipped_not_sent():
    recipients = ({"fax": "123", "name": "잘못"}, RECIPIENTS[0])
    auth = _auth(recipients=recipients, approved_scope_hash=pol.scope_hash(recipients, "영업 안내", "doc-hash-1"))
    decision = pol.evaluate(auth, _state())
    assert [r["fax"] for r in decision.to_send] == ["021112222"]
    assert any(reason == pol.INVALID_NUMBER for _, reason in decision.skipped)


def test_duplicate_numbers_in_list_are_sent_only_once():
    recipients = (RECIPIENTS[0], {"fax": "021112222", "name": "같은 번호 다른 표기"}, RECIPIENTS[1])
    auth = _auth(recipients=recipients, approved_scope_hash=pol.scope_hash(recipients, "영업 안내", "doc-hash-1"))
    decision = pol.evaluate(auth, _state())
    assert [r["fax"] for r in decision.to_send] == ["021112222", "0313334444"]


def test_skipped_numbers_in_decision_are_masked():
    decision = pol.evaluate(_auth(), _state(opted_out={"021112222"}))
    masked_numbers = [n for n, _ in decision.skipped]
    assert masked_numbers and all("*" in n for n in masked_numbers)
    assert "1112" not in "".join(masked_numbers)


# ── 한도 ──────────────────────────────────────────────────────────────────


def test_per_run_limit_caps_recipients_and_marks_the_rest():
    decision = pol.evaluate(_auth(max_per_run=2), _state())
    assert len(decision.to_send) == 2
    assert [r["fax"] for r in decision.to_send] == ["021112222", "0313334444"]  # 앞에서부터
    assert any(reason == pol.LIMIT_REACHED for _, reason in decision.skipped)


def test_daily_limit_accounts_for_already_sent_today():
    decision = pol.evaluate(_auth(max_per_day=10), _state(sent_today=9))
    assert len(decision.to_send) == 1


def test_total_limit_accounts_for_already_sent_overall():
    decision = pol.evaluate(_auth(max_total=5), _state(sent_total=4))
    assert len(decision.to_send) == 1


def test_limit_reached_sends_nothing():
    decision = pol.evaluate(_auth(max_per_day=5), _state(sent_today=5))
    assert decision.action == pol.SKIP and decision.reason == pol.LIMIT_REACHED
    assert decision.to_send == ()


def test_zero_limits_never_send():
    assert pol.evaluate(_auth(max_per_run=0), _state()).to_send == ()
    assert pol.evaluate(_auth(max_total=0), _state()).to_send == ()


def test_negative_remaining_capacity_is_clamped_to_zero():
    decision = pol.evaluate(_auth(max_per_day=3), _state(sent_today=10))  # 이미 한도를 넘김
    assert decision.to_send == ()


# ── 시간대 ────────────────────────────────────────────────────────────────


def test_hours_boundaries_inclusive():
    assert pol.evaluate(_auth(), _state(now=NOW.replace(hour=9, minute=0))).action == pol.SEND
    assert pol.evaluate(_auth(), _state(now=NOW.replace(hour=18, minute=0))).action == pol.SEND
    assert pol.evaluate(_auth(), _state(now=NOW.replace(hour=18, minute=1))).reason == pol.OUTSIDE_HOURS
    assert pol.evaluate(_auth(), _state(now=NOW.replace(hour=8, minute=59))).reason == pol.OUTSIDE_HOURS


def test_hours_window_that_crosses_midnight():
    auth = _auth(allowed_start=time(22, 0), allowed_end=time(6, 0))
    assert pol.evaluate(auth, _state(now=NOW.replace(hour=23))).action == pol.SEND
    assert pol.evaluate(auth, _state(now=NOW.replace(hour=3))).action == pol.SEND
    assert pol.evaluate(auth, _state(now=NOW.replace(hour=12))).reason == pol.OUTSIDE_HOURS


def test_naive_and_aware_datetimes_do_not_crash():
    naive_now = datetime(2026, 10, 2, 10, 0)
    auth = _auth(valid_from=NOW - timedelta(days=1), valid_until=NOW + timedelta(days=1))
    assert pol.evaluate(auth, _state(now=naive_now)).action == pol.SEND


# ── 순수성·요약 ───────────────────────────────────────────────────────────


def test_evaluate_does_not_mutate_inputs():
    auth, state = _auth(), _state()
    before = (auth, state)
    pol.evaluate(auth, state)
    assert (auth, state) == before


def test_decision_is_immutable():
    decision = pol.evaluate(_auth(), _state())
    with pytest.raises(AttributeError):
        decision.action = pol.DENY  # type: ignore[misc]


def test_describe_summary_contains_no_full_numbers():
    decision = pol.evaluate(_auth(), _state(opted_out={"021112222"}))
    summary = pol.describe(decision, {"authorization_id": "A1"})
    text = str(summary)
    assert summary["send_count"] == 2 and summary["authorization_id"] == "A1"
    assert "021112222" not in text


def test_replace_helper_keeps_frozen_dataclass_semantics():
    auth = _auth()
    assert replace(auth, live=False).live is False and auth.live is True
