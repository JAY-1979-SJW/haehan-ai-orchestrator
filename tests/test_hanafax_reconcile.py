"""하나팩스 전송결과 파서와 대조(reconcile). 사이트에는 접속하지 않는다(표 셀 텍스트·가짜 fetch 사용)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from ai_orchestrator.persistence import fax_authorization_store as store
from ai_orchestrator.services import fax_approval_pin as approval_pin
from ai_orchestrator.services import hanafax_authorization_service as service
from ai_orchestrator.services import hanafax_reconcile as rec
from ai_orchestrator.workflows import hanafax_auto_send as flow
from scripts.hanafax import send_result

PIN = "test-pin-123"
NOW = datetime(2026, 10, 2, 15, 0).astimezone()

# 실제 전송결과 화면(2026-10-02 실사)에서 읽은 안쪽 행의 셀 구조 — 번호는 가짜
BULK_ROW = [
    "",
    "",
    "~2026.12.01",
    "",
    "",
    "[테스트] 단체발송 검증",
    "",
    "+",
    "수신번호",
    "로딩중..",
    "",
    "",
    "3",
    "",
    "0",
    "",
    "3",
    "",
    "전송 실패",
    "",
    "",
    "발신내용",
    "문서_261002140236186635.tif",
    "",
    "",
    "외 2명",
    "",
    "오늘 08:59",
]
SINGLE_ROW = [
    "",
    "",
    "~2026.12.01",
    "",
    "",
    "[테스트] 앱 연동 검증3",
    "",
    "0200000000",
    "수신번호",
    "로딩중..",
    "",
    "",
    "1",
    "",
    "0",
    "",
    "1",
    "",
    "전송 실패",
    "",
    "",
    "발신내용",
    "x.tif",
    "",
    "",
    "",
    "",
    "오늘 01:47",
]
OLD_ROW = [
    "",
    "",
    "~2026.11.01",
    "",
    "",
    "귀사만을 위한 AI 안전관리..",
    "",
    "0546727719",
    "수신번호",
    "로딩중..",
    "",
    "",
    "1",
    "",
    "1",
    "",
    "0",
    "",
    "전송 성공",
    "",
    "",
    "발신내용",
    "y.tif",
    "",
    "",
    "",
    "",
    "2026.09.08",
]
# 앱에서 직계 셀만 읽었을 때의 실제 행(2026-10-02 실측 — 위 행보다 셀이 적다)
DIRECT_ROW = [
    "",
    "",
    "~2026.12.01",
    "",
    "",
    "[테스트] 단체발송 검증",
    "",
    "+",
    "",
    "3",
    "",
    "0",
    "",
    "3",
    "",
    "전송 실패",
    "",
    "",
    "",
    "외 2명",
    "",
    "오늘 08:59",
]
NOISE_ROW = [
    "기본 보관 기한이 지난 후에는",
    "",
    "10개씩 20개씩 50개씩",
    "",
    "관리제목",
    "수신번호",
    "전체",
    "성공",
    "실패",
    "상태",
]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "fax_authorizations.db")
    monkeypatch.setattr(service, "_safe_path", lambda text, label: str(text).strip().strip('"'))
    approval_pin.set_pin(PIN)


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "공문.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    return path


# ── 파서 ──────────────────────────────────────────────────────────────────────


def test_parse_real_row_structures():
    rows = send_result.parse_rows([NOISE_ROW, BULK_ROW, SINGLE_ROW, OLD_ROW], NOW)
    assert len(rows) == 3  # 잡음 행은 건너뛴다
    bulk, single, old = rows
    assert (bulk["title"], bulk["number"], bulk["total"], bulk["success"], bulk["failure"], bulk["status"]) == (
        "[테스트] 단체발송 검증",
        "",
        3,
        0,
        3,
        "전송 실패",
    )
    assert (
        bulk["extra_recipients"] == 2 and bulk["minute_known"] and bulk["when"].hour == 8 and bulk["when"].minute == 59
    )
    assert single["number"] == "0200000000" and single["total"] == 1 and single["failure"] == 1
    assert (
        old["status"] == "전송 성공"
        and old["minute_known"] is False
        and old["when"].year == 2026
        and old["when"].month == 9
    )


def test_parse_directly_read_row_from_real_site():
    (row,) = send_result.parse_rows([DIRECT_ROW], NOW)
    assert (row["title"], row["total"], row["success"], row["failure"], row["status"]) == (
        "[테스트] 단체발송 검증",
        3,
        0,
        3,
        "전송 실패",
    )
    assert row["when"].hour == 8 and row["when"].minute == 59 and row["minute_known"]


def test_parse_skips_rows_it_cannot_read():
    assert send_result.parse_rows([["~2026.12.01", "제목만"], []], NOW) == []


# ── 대조 ──────────────────────────────────────────────────────────────────────


def _sent_batch(doc, numbers, subject="[테스트] 단체발송 검증"):
    row = service.create(
        {
            "name": "n",
            "subject": subject,
            "document_ref": str(doc),
            "recipients": [{"fax": n, "name": ""} for n in numbers],
            "allowed_start": "00:00",
            "allowed_end": "23:59",
        },
        user="u",
    )
    for n in numbers:
        store.record_send(
            store.SendRecord(row["id"], n.replace("-", ""), row["document_hash"], store.SENT, None, "팩스 전송 완료")
        )
    return row


def _site(**over):
    base = {
        "title": "[테스트] 단체발송 검증",
        "number": "",
        "total": 3,
        "success": 0,
        "failure": 3,
        "status": "전송 실패",
        "when": datetime.now().astimezone(),
        "minute_known": True,
    }
    return {**base, **over}


NUMS = ["02-111-0001", "02-111-0002", "02-111-0003"]


def test_all_failed_marks_delivery_failed_and_blocks_auto_resend(doc):
    row = _sent_batch(doc, NUMS)
    out = rec.reconcile(row["id"], fetch=lambda: [_site()])
    assert out["delivery_failed"] == 3 and out["delivered"] == 0 and out["unmatched"] == 0
    assert store.unknown_numbers(row["document_hash"]) == {"021110001", "021110002", "021110003"}
    assert store.sent_numbers(row["document_hash"]) == set()
    service.approve(row["id"], user="a", live=True, pin=PIN)
    again = flow.run_bulk(
        row["id"],
        lambda *a: pytest.fail("전송 실패 확인된 번호는 사람이 해소하기 전에는 다시 보내지 않는다"),
        datetime.now().astimezone(),
    )
    assert again.sent == 0


def test_human_can_resolve_delivery_failed_to_allow_retry(doc):
    row = _sent_batch(doc, NUMS)
    rec.reconcile(row["id"], fetch=lambda: [_site()])
    assert len(service.preview(row["id"])["pending_numbers"]) == 3  # '확인 필요' 목록에 나타난다
    service.resolve_pending(row["id"], "021110001", "not_sent", pin=PIN, user="a")
    assert "021110001" not in store.unknown_numbers(row["document_hash"]) and "021110001" not in store.sent_numbers(
        row["document_hash"]
    )


def test_all_success_marks_delivered_and_counts_once(doc):
    row = _sent_batch(doc, NUMS)
    out = rec.reconcile(row["id"], fetch=lambda: [_site(success=3, failure=0, status="전송 성공")])
    assert out["delivered"] == 3
    assert store.sent_numbers(row["document_hash"]) == {"021110001", "021110002", "021110003"}
    assert store.count_sent(row["id"]) == 3
    assert rec.reconcile(row["id"], fetch=lambda: [_site()])["checked"] == 0  # 이미 확정된 건은 다시 대조하지 않는다


def test_mixed_result_changes_nothing(doc):
    row = _sent_batch(doc, NUMS)
    out = rec.reconcile(row["id"], fetch=lambda: [_site(success=2, failure=1)])
    assert out["partial"] == 3 and out["delivered"] == 0 and out["delivery_failed"] == 0
    assert store.sent_numbers(row["document_hash"]) == {"021110001", "021110002", "021110003"}


@pytest.mark.parametrize(
    "override",
    [
        {"title": "다른 제목"},  # 제목 불일치
        {"total": 2, "failure": 2},  # 건수 불일치
        {"when": datetime.now().astimezone() - timedelta(hours=2)},  # 시각 불일치
        {"minute_known": False},  # 날짜만 있는 행
        {"status": "전송중"},  # 아직 진행 중
    ],
)
def test_ambiguous_site_rows_are_never_matched(doc, override):
    row = _sent_batch(doc, NUMS)
    out = rec.reconcile(row["id"], fetch=lambda: [_site(**override)])
    assert out["delivered"] == 0 and out["delivery_failed"] == 0 and out["unmatched"] == 3
    assert store.sent_numbers(row["document_hash"]) == {"021110001", "021110002", "021110003"}


def test_truncated_site_title_matches_by_prefix(doc):
    row = _sent_batch(doc, NUMS, subject="귀사만을 위한 AI 안전관리 서비스 안내")
    out = rec.reconcile(row["id"], fetch=lambda: [_site(title="귀사만을 위한 AI 안전관리..")])
    assert out["delivery_failed"] == 3


def test_single_recipient_requires_matching_number(doc):
    row = _sent_batch(doc, ["02-222-0001"], subject="단건")
    wrong = rec.reconcile(row["id"], fetch=lambda: [_site(title="단건", total=1, failure=1, number="0299999999")])
    assert wrong["unmatched"] == 1 and wrong["delivery_failed"] == 0
    right = rec.reconcile(row["id"], fetch=lambda: [_site(title="단건", total=1, failure=1, number="022220001")])
    assert right["delivery_failed"] == 1


def test_two_runs_are_matched_separately_by_time(doc):
    row = _sent_batch(doc, NUMS)
    later = ["02-333-0001", "02-333-0002"]
    for n in later:
        store.record_send(store.SendRecord(row["id"], n.replace("-", ""), row["document_hash"], store.SENT, None, "ok"))
    con = sqlite3.connect(str(store._DB_PATH))  # 첫 묶음 3건을 한 시간 전으로
    con.execute(
        "UPDATE send_log SET created_at=? WHERE fax_digits IN ('021110001','021110002','021110003')",
        (
            (datetime.now().astimezone() - timedelta(hours=1))
            .astimezone(tz=None)
            .astimezone()
            .isoformat(timespec="seconds"),
        ),
    )
    con.commit()
    con.close()
    out = rec.reconcile(
        row["id"],
        fetch=lambda: [
            _site(total=2, success=2, failure=0, status="전송 성공"),
            _site(when=datetime.now().astimezone() - timedelta(hours=1), total=3, failure=3),
        ],
    )
    assert out["delivered"] == 2 and out["delivery_failed"] == 3 and out["unmatched"] == 0


def test_unknown_authorization_and_nothing_pending(doc):
    with pytest.raises(ValueError):
        rec.reconcile("nope", fetch=lambda: [])
    row = service.create(
        {"name": "n", "subject": "s", "document_ref": str(doc), "recipients": [{"fax": "02-444-0001", "name": ""}]},
        user="u",
    )
    assert rec.reconcile(row["id"], fetch=lambda: pytest.fail("대상이 없으면 사이트를 읽지 않는다"))["checked"] == 0
