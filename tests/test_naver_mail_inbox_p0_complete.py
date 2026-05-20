"""NAVER-MAIL-INBOX-P0-COMPLETE-01 — P0 운영 가능 등급 테스트.

필수 항목 (10) 전부 커버.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from scripts.naver_mail import (
    inbox_collector as ic,
    read_state_guard as rsg,
    time_parser as tp,
)
from scripts.naver_mail.inbox_collector import LIST_EXPR, PAGES_EXPR

KST = timezone(timedelta(hours=9))


# ── Fake Actions — CDP I/O 흉내 ────────────────────────────────────


@dataclass
class _PageRows:
    items: list[dict]


class FakeActions:
    """페이지별 응답을 사전에 큐로 적재하고 evaluate 호출에 응답.

    또한 모든 호출을 call_log 에 기록 → 금지 동작 탐지.
    """

    def __init__(self, *, title="받은메일함(3) : 네이버 메일",
                 url="https://mail.naver.com/v2/folders/0/all",
                 page_buttons=None, page_responses=None):
        self.title = title
        self.url = url
        self.page_buttons = page_buttons or ["1", "2"]  # 가용 페이지
        self.page_responses = page_responses or {}  # {pg: [items_dict, ...]}
        self.current_page = "1"
        self.call_log: list[str] = []
        self.click_log: list[str] = []
        self.nav_log: list[str] = []

    def _list_payload(self) -> dict:
        rows = self.page_responses.get(self.current_page, [])
        return {
            "href": self.url, "title": self.title,
            "count": len(rows), "items": rows,
        }

    def evaluate(self, expr: str):
        self.call_log.append(f"eval:{expr[:40]}")
        if "JSON.stringify" in expr and "li.mail_item" in expr and "rows" in expr:
            return self._list_payload()
        if "page_link" in expr and "querySelectorAll" in expr and ".pagination" in expr and "return btns.map" in expr:
            return list(self.page_buttons)
        if "page_link" in expr and "btns[i].click" in expr:
            # 페이지 클릭 — expr 안에 페이지 번호 포함
            for pg in self.page_buttons:
                if f"==='{pg}'" in expr:
                    if pg in self.page_responses:
                        self.current_page = pg
                        self.click_log.append(f"page:{pg}")
                        return True
            return False
        if "안읽은 메일" in expr or "filter_unread" in expr:
            self.click_log.append("unread_filter")
            return True
        # popup/read 또는 본문 호출 — 금지 동작 탐지용
        return None

    def click(self, sel):
        self.click_log.append(f"click:{sel[:40]}")
        return True

    def navigate(self, url):
        self.nav_log.append(url)
        self.call_log.append(f"nav:{url[:60]}")

    def wait_dom(self, expr, timeout_s=8.0):
        return True


def _mk_row(sn, subject="제목", sender_name="A", sender_full='"A"<a@x.com>',
            time_txt="오전 10:00", is_unread=True, size="1KB", href=""):
    return {
        "sn": sn, "is_unread": is_unread,
        "sender_name": sender_name, "sender_full": sender_full,
        "subject": subject, "time_txt": time_txt, "size_txt": size,
        "href": href or f"/v2/popup/read/0/{sn}",
    }


# ── 1) 페이지네이션 종료 조건 ────────────────────────────────────────


def test_pagination_terminates_when_no_more_pages():
    fa = FakeActions(
        page_buttons=["1", "2", "3"],
        page_responses={
            "1": [_mk_row("100"), _mk_row("101")],
            "2": [_mk_row("102")],
            "3": [],  # 빈 페이지
        },
    )
    r = ic.collect_inbox(fa, mode=rsg.MODE_LIST_ONLY)
    # 3건 수집, last_page_reached True, warn_limit X
    assert len(r.items) == 3
    assert r.last_page_reached is True
    assert r.warn_limit_reached is False
    assert set(i.sn for i in r.items) == {"100", "101", "102"}
    assert "1" in r.pages_visited and "2" in r.pages_visited


def test_pagination_max_pages_limit_emits_warn():
    fa = FakeActions(
        page_buttons=[str(i) for i in range(1, 11)],
        page_responses={str(i): [_mk_row(f"{i}00")] for i in range(1, 11)},
    )
    r = ic.collect_inbox(fa, mode=rsg.MODE_LIST_ONLY, max_pages=3)
    assert r.warn_limit_reached is True
    assert any("max_pages" in n for n in r.notes)


# ── 2) 중복 sn 제거 ──────────────────────────────────────────────────


def test_duplicate_sn_dedup():
    fa = FakeActions(
        page_buttons=["1", "2"],
        page_responses={
            "1": [_mk_row("100"), _mk_row("101")],
            "2": [_mk_row("101"), _mk_row("102")],  # 101 중복
        },
    )
    r = ic.collect_inbox(fa, mode=rsg.MODE_LIST_ONLY)
    assert len(r.items) == 3
    assert r.dup_count == 1
    assert "101" in r.duplicate_sns


# ── 3) unread only 필터 ──────────────────────────────────────────────


def test_unread_only_mode_clicks_filter_before_collect():
    fa = FakeActions(
        page_buttons=["1"],
        page_responses={"1": [_mk_row("100", is_unread=True),
                              _mk_row("101", is_unread=False)]},
    )
    r = ic.collect_inbox(fa, mode=rsg.MODE_UNREAD_ONLY)
    assert "unread_filter" in fa.click_log
    # 필터 클릭 후에도 fake는 그대로 반환 — 실제 환경에서는 unread만 남음
    # 본 테스트는 필터 호출 여부 검증이 핵심
    assert r.mode == rsg.MODE_UNREAD_ONLY
    assert all(i.collect_mode == rsg.MODE_UNREAD_ONLY for i in r.items)


# ── 4) LIST_ONLY 모드에서 본문 열람 금지 ─────────────────────────────


def test_list_only_mode_no_body_open():
    fa = FakeActions(
        page_buttons=["1"],
        page_responses={"1": [_mk_row("100")]},
    )
    ic.collect_inbox(fa, mode=rsg.MODE_LIST_ONLY)
    # call_log 에 read_body / popup/read / captureScreenshot 호출이 없어야 함
    rsg.list_only_assert_no_body_eval(fa.call_log)  # no raise


def test_list_only_mode_violation_detected():
    log = ["eval:read_body for sn=100", "Page.captureScreenshot"]
    with pytest.raises(rsg.ForbiddenActionError, match="LIST_ONLY_MODE_VIOLATED"):
        rsg.list_only_assert_no_body_eval(log)


# ── 5) FULL_READ 안읽음 복구 plan/결과 ───────────────────────────────


def test_full_read_plan_records_unread_only_for_restore():
    items = [
        type("X", (), {"sn": "100", "is_unread": True})(),
        type("X", (), {"sn": "101", "is_unread": False})(),
        type("X", (), {"sn": "102", "is_unread": True})(),
    ]
    plan = rsg.plan_full_read(items, max_bodies=3)
    assert len(plan.targets) == 3
    # 복구 시도는 was_unread True 인 2건만
    needs_restore = [t for t in plan.targets if t.was_unread]
    assert len(needs_restore) == 2


def test_full_read_restore_records_success_and_failure():
    items = [type("X", (), {"sn": str(i), "is_unread": True})() for i in range(2)]
    plan = rsg.plan_full_read(items, max_bodies=2)

    def fake_mark(sn):
        return sn == "0"  # 첫 번째만 성공, 두 번째 실패

    rsg.attempt_restore_unread(plan, fake_mark)
    assert plan.restore_attempted == 2
    assert plan.restore_succeeded == 1
    assert plan.restore_failed == 1
    assert plan.all_restored is False  # 1건 실패


def test_full_read_restore_exception_recorded():
    items = [type("X", (), {"sn": "1", "is_unread": True})()]
    plan = rsg.plan_full_read(items, max_bodies=1)

    def raise_mark(sn):
        raise RuntimeError("network_error")

    rsg.attempt_restore_unread(plan, raise_mark)
    assert plan.restore_failed == 1
    assert "network_error" in plan.targets[0].restore_error


# ── 6) 한국어 시간 파싱 ──────────────────────────────────────────────


@pytest.fixture
def fixed_now():
    return datetime(2026, 5, 20, 14, 30, tzinfo=KST)


def test_time_parse_am_pm(fixed_now):
    p = tp.parse_korean_time("오전 10:00", now=fixed_now)
    assert p.iso.startswith("2026-05-20T10:00:00")
    assert "오늘_가정" in p.warning


def test_time_parse_pm(fixed_now):
    p = tp.parse_korean_time("오후 3:12", now=fixed_now)
    assert p.iso.startswith("2026-05-20T15:12:00")


def test_time_parse_pm_12_handled(fixed_now):
    p = tp.parse_korean_time("오후 12:00", now=fixed_now)
    assert p.iso.startswith("2026-05-20T12:00:00")


def test_time_parse_am_12_midnight(fixed_now):
    p = tp.parse_korean_time("오전 12:00", now=fixed_now)
    assert p.iso.startswith("2026-05-20T00:00:00")


def test_time_parse_yesterday(fixed_now):
    p = tp.parse_korean_time("어제", now=fixed_now)
    assert p.iso.startswith("2026-05-19T00:00:00")


def test_time_parse_mmdd_current_year(fixed_now):
    p = tp.parse_korean_time("05.18", now=fixed_now)
    assert p.iso.startswith("2026-05-18T00:00:00")
    assert "연도_가정=2026" in p.warning


def test_time_parse_mmdd_future_falls_back_to_prev_year(fixed_now):
    p = tp.parse_korean_time("12.31", now=fixed_now)
    assert p.iso.startswith("2025-12-31T00:00:00")
    assert "미래보정" in p.warning


def test_time_parse_yyyy_mm_dd_full(fixed_now):
    p = tp.parse_korean_time("2026.05.18 09:30", now=fixed_now)
    assert p.iso.startswith("2026-05-18T09:30:00")


def test_time_parse_relative_minutes(fixed_now):
    p = tp.parse_korean_time("5분 전", now=fixed_now)
    assert p.iso.startswith("2026-05-20T14:25:00")


def test_time_parse_unknown_format_keeps_warning(fixed_now):
    p = tp.parse_korean_time("xxxx-yy-zz", now=fixed_now)
    assert p.iso == ""
    assert "unknown_format" in p.warning


def test_time_parse_empty():
    p = tp.parse_korean_time("")
    assert p.iso == ""
    assert p.warning == "empty_display"


# ── 7) PII 마스킹 ────────────────────────────────────────────────────


def test_pii_mask_sender_email_localpart():
    fa = FakeActions(
        page_buttons=["1"],
        page_responses={"1": [_mk_row("100",
            sender_full='"Google"<no-reply@accounts.google.com>',
            sender_name="Google")]},
    )
    r = ic.collect_inbox(fa, mode=rsg.MODE_LIST_ONLY)
    item = r.items[0]
    assert "no-reply@accounts.google.com" not in item.sender_masked
    assert "@accounts.google.com" in item.sender_masked


def test_pii_mask_subject_with_phone():
    fa = FakeActions(
        page_buttons=["1"],
        page_responses={"1": [_mk_row("100", subject="연락 010-1234-5678 바랍니다")]},
    )
    r = ic.collect_inbox(fa, mode=rsg.MODE_LIST_ONLY)
    assert "010-****-****" in r.items[0].subject_masked
    assert "1234-5678" not in r.items[0].subject_masked


# ── 8) 금지 동작 — send/delete/move/download 미호출 ──────────────────


def test_forbidden_actions_blocked_at_guard():
    for act in ("send", "delete", "move", "spam", "star", "label",
                "download_attachment", "open_attachment", "screenshot_body",
                "reply", "forward"):
        with pytest.raises(rsg.ForbiddenActionError):
            rsg.assert_action_allowed(act)


def test_collect_does_not_invoke_destructive_calls():
    fa = FakeActions(
        page_buttons=["1", "2"],
        page_responses={
            "1": [_mk_row("100"), _mk_row("101")],
            "2": [_mk_row("102")],
        },
    )
    ic.collect_inbox(fa, mode=rsg.MODE_LIST_ONLY)
    # call_log 안에 금지 패턴이 한 번도 없어야 함
    bad_patterns = ("send", "delete", "remove", "spam", "trash", "download",
                    "submit", "star", "label", "captureScreenshot")
    for entry in fa.call_log + fa.click_log + fa.nav_log:
        for bad in bad_patterns:
            assert bad not in entry, f"forbidden 호출 감지: {entry}"


# ── 9) JSON schema ──────────────────────────────────────────────────


def test_result_item_schema_complete():
    fa = FakeActions(
        page_buttons=["1"],
        page_responses={"1": [_mk_row("100")]},
    )
    r = ic.collect_inbox(fa, mode=rsg.MODE_LIST_ONLY)
    d = ic.result_to_dict(r)
    assert "items" in d and len(d["items"]) == 1
    item_d = d["items"][0]
    missing = ic.validate_item_schema(item_d)
    assert missing == [], f"필수 필드 누락: {missing}"
    # 명세 필드 모두 존재
    for k in ("folder_id", "folder_name", "sn", "subject_masked",
              "sender_masked", "display_time", "parsed_at_iso",
              "read_state", "has_attachment", "collect_mode"):
        assert k in item_d


def test_result_meta_records_all_required_counters():
    fa = FakeActions(
        title="받은메일함(5) : 네이버 메일",
        page_buttons=["1"],
        page_responses={"1": [_mk_row("100"), _mk_row("101", is_unread=False)]},
    )
    r = ic.collect_inbox(fa, mode=rsg.MODE_LIST_ONLY)
    d = ic.result_to_dict(r)
    assert d["unread_count_ui"] == 5
    assert d["collected_unread"] == 1
    assert d["total_seen"] == 2
    assert d["dup_count"] == 0
    assert d["last_page_reached"] is True


# ── 10) audit script PASS ───────────────────────────────────────────


def test_audit_module_judges_pass_on_normal_result():
    """audit 함수가 정상 결과를 PASS 판정하는지."""
    from scripts.ops import audit_naver_mail_inbox_p0_complete as audit
    fa = FakeActions(
        title="받은메일함(2) : 네이버 메일",
        page_buttons=["1"],
        page_responses={"1": [_mk_row("100"), _mk_row("101")]},
    )
    r = ic.collect_inbox(fa, mode=rsg.MODE_LIST_ONLY)
    verdict = audit.judge(r, mode=rsg.MODE_LIST_ONLY)
    assert verdict.passed is True, verdict.reasons


def test_audit_module_judges_warn_on_limit_reached():
    from scripts.ops import audit_naver_mail_inbox_p0_complete as audit
    fa = FakeActions(
        page_buttons=[str(i) for i in range(1, 11)],
        page_responses={str(i): [_mk_row(f"{i}00")] for i in range(1, 11)},
    )
    r = ic.collect_inbox(fa, mode=rsg.MODE_LIST_ONLY, max_pages=3)
    verdict = audit.judge(r, mode=rsg.MODE_LIST_ONLY)
    assert verdict.passed is False
    assert any("limit" in x.lower() or "warn" in x.lower() for x in verdict.reasons)
