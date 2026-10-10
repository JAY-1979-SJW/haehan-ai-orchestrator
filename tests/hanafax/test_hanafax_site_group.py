"""하나팩스 사이트 주소록 그룹 가져오기 — 파서·캐시·구간 나눔·수신자 검수. 사이트에는 접속하지 않는다(가짜 fetch)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta

import pytest

from ai_orchestrator.connectors.hanafax import authorization_store as store
from ai_orchestrator.connectors.hanafax import authorization_service as service
from scripts.hanafax import address_book

HEADER = ["", "이름", "회사", "팩스번호", "휴대전화", "일반전화", "이메일"]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("실제 하나팩스에 접속하려 했습니다")

    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "fax_authorizations.db")
    monkeypatch.setattr(service, "_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(service, "_safe_path", lambda text, label: str(text).strip().strip('"'))
    monkeypatch.setattr(service, "already_sent_numbers", lambda: set())
    monkeypatch.setattr(address_book, "_session", boom)


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "공문.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    return path


def _members(n, start=1):
    return [{"fax": f"02-555-{1000 + i:04d}", "name": f"업체{i}"} for i in range(start, start + n)]


def _cache(intid, members, age_hours=0):
    service._CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fetched = (datetime.now(UTC) - timedelta(hours=age_hours)).isoformat(timespec="seconds")
    service._cache_path(intid).write_text(
        json.dumps({"intid": intid, "fetched_at": fetched, "members": members}, ensure_ascii=False), encoding="utf-8"
    )


# ── 파서 ──────────────────────────────────────────────────────────────────────


def test_parse_groups_extracts_counts_and_dedupes():
    items = [
        {"name": "A그룹", "intid": "101", "cells": ["", "A그룹", "1129명", "1129개", "0개", "1개", "0개"]},
        {"name": "A그룹", "intid": "101", "cells": []},  # 같은 그룹 링크가 두 번 잡혀도 한 번만
        {"name": "B그룹", "intid": "102", "cells": ["", "B그룹", "0명", "0개"]},
        {"name": "깨진", "intid": "", "cells": []},
    ]
    assert address_book.parse_groups(items) == [
        {"name": "A그룹", "intid": "101", "members": 1129, "fax_count": 1129},
        {"name": "B그룹", "intid": "102", "members": 0, "fax_count": 0},
    ]


def test_parse_members_uses_header_columns_and_skips_junk_rows():
    rows = [
        ["검색", "그룹명"],
        HEADER,
        ["", "홍길동", "가나건설", "02-123-4567", "", "", ""],
        ["", "", "회사만있음", "031-111-2222", "", "", ""],  # 이름이 없으면 회사명
        ["", "번호없음", "", "", "010-1234-5678", "", ""],  # 팩스번호가 없으면 건너뜀
        ["", "잡음", "", "abc", "", "", ""],
    ]
    assert address_book.parse_members(rows) == [
        {"fax": "02-123-4567", "name": "홍길동"},
        {"fax": "031-111-2222", "name": "회사만있음"},
    ]
    assert address_book.parse_members([["아무 표", "아님"]]) == []


# ── 캐시 → 수신자 ───────────────────────────────────────────────────────────────


def test_recipients_from_cache_screen_and_ranges():
    members = [*_members(25), {"fax": "abc", "name": "잘못"}, {"fax": "02-555-1001", "name": "중복"}]
    _cache("500", members)
    store.add_opt_out("025551003", user="u")
    recipients, summary = service.recipients_from_site_group("500", offset=0, limit=100)
    assert summary["invalid"] == 1 and summary["duplicate"] == 1 and summary["opted_out_or_already_sent"] == 1
    assert len(recipients) == 25 - 1 and summary["group_total"] == 27
    part, psummary = service.recipients_from_site_group("500", offset=10, limit=5)
    assert len(part) == 5 and psummary["range_start"] == 11 and psummary["range_end"] == 15


def test_site_group_rejects_missing_stale_and_out_of_range():
    with pytest.raises(ValueError, match="아직 가져오지 않았습니다"):
        service.recipients_from_site_group("501")
    _cache("502", _members(3), age_hours=service.GROUP_CACHE_TTL_HOURS + 1)
    with pytest.raises(ValueError, match="다시 가져오세요"):
        service.recipients_from_site_group("502")
    _cache("503", _members(3))
    with pytest.raises(ValueError, match="벗어난 구간"):
        service.recipients_from_site_group("503", offset=50)
    with pytest.raises(ValueError, match="구간은"):
        service.recipients_from_site_group("503", limit=service.MAX_RECIPIENTS + 1)


@pytest.mark.parametrize("bad", ["", "abc", "12 34", "../x", "1" * 13])
def test_invalid_group_id_is_rejected_before_touching_files(bad):
    with pytest.raises(ValueError, match="그룹 번호"):
        service.start_group_sync(bad)
    with pytest.raises(ValueError, match="그룹 번호"):
        service.group_sync_status(bad)


# ── 승인서 생성·백그라운드 가져오기 ──────────────────────────────────────────────


def test_create_draft_from_site_group_with_summary(doc):
    _cache("600", _members(12))
    row = service.create(
        {
            "name": "그룹 발송",
            "subject": "제목",
            "document_ref": str(doc),
            "site_group": "600",
            "group_offset": 2,
            "group_limit": 5,
            "allowed_start": "00:00",
            "allowed_end": "23:59",
        },
        user="u",
    )
    assert len(row["recipients"]) == 5 and row["max_per_run"] == 5
    assert row["import_summary"]["range_start"] == 3 and row["import_summary"]["group_total"] == 12
    assert not row["approved"]


def test_background_sync_writes_cache_and_reports_progress(monkeypatch):
    seen = []

    def fake_fetch(intid, progress=None):
        for n in (1, 2, 3):
            progress(n, 3)
            seen.append(n)
        return _members(30)

    monkeypatch.setattr(address_book, "fetch_group", fake_fetch)
    service.start_group_sync("700")
    for _ in range(100):
        status = service.group_sync_status("700")
        if status["state"] and status["state"].get("ok") is not None:
            break
        time.sleep(0.05)
    assert status["state"]["ok"] is True and status["state"]["members"] == 30 and status["cached"] is True
    assert seen == [1, 2, 3] and not status["running"]
    recipients, _ = service.recipients_from_site_group("700")
    assert len(recipients) == 30


def test_background_sync_failure_is_reported_without_cache(monkeypatch):
    def fail(intid, progress=None):
        raise RuntimeError("login failed")

    monkeypatch.setattr(address_book, "fetch_group", fail)
    service.start_group_sync("701")
    for _ in range(100):
        status = service.group_sync_status("701")
        if status["state"] and status["state"].get("ok") is not None:
            break
        time.sleep(0.05)
    assert status["state"]["ok"] is False and "RuntimeError" in status["state"]["message"] and status["cached"] is False


def test_concurrent_sync_of_same_group_is_refused(monkeypatch):
    release = []

    def slow(intid, progress=None):
        while not release:
            time.sleep(0.02)
        return _members(2)

    monkeypatch.setattr(address_book, "fetch_group", slow)
    service.start_group_sync("702")
    with pytest.raises(ValueError, match="읽는 중"):
        service.start_group_sync("702")
    release.append(1)
    for _ in range(100):
        if not service.group_sync_status("702")["running"]:
            break
        time.sleep(0.05)
