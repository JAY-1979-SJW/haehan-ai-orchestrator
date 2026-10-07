"""가입 카페 활동 분석 — 순수 계산. 날짜는 `YYYY-MM-DD HH:MM:SS`(한국 시간), 이름·글 내용은 다루지 않는다(집계)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ai_orchestrator.connectors.naver_cafe import activity as act

NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=act.KST)


def fmt(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).strftime(act.DATE_FORMAT)


def e(i, **kw):
    base = {
        "cafe_id": f"c{i}",
        "name": f"카페{i}",
        "new_articles": 0,
        "last_update": fmt(1),
        "last_visit": fmt(1),
        "favorite": False,
        "manage": False,
        "dormant": False,
        "power": False,
    }
    return {**base, **kw}


def test_parse_kst_accepts_only_the_documented_format():
    assert act.parse_kst("2026-10-05 12:00:00") == NOW
    for bad in ("", None, "2026-10-05", "2026.10.05.", "어제", "2026-13-40 00:00:00", 12345):
        assert act.parse_kst(bad) is None


def test_analyze_counts_activity_without_touching_names():
    entries = [
        e(1, new_articles=74005, favorite=True),
        e(2, new_articles=823, last_visit=fmt(45)),
        e(3, new_articles=0, last_update=fmt(120), manage=True),
        e(4, new_articles=823, dormant=True, power=True),
        e(5, new_articles=427),
        e(6, new_articles=365),
        e(7, new_articles=10),
    ]
    out = act.analyze(entries, now=NOW)
    assert (
        out["total"] == 7
        and out["with_new_articles"] == 6
        and out["new_articles_total"] == 74005 + 823 + 823 + 427 + 365 + 10
    )
    assert [t["new_articles"] for t in out["top_new"]] == [74005, 823, 823, 427, 365]  # 상위 5, 같은 건수는 id 순
    assert [t["cafe_id"] for t in out["top_new"]][1:3] == ["c2", "c4"]
    assert out["favorites"] == 1 and out["managed"] == 1 and out["power"] == 1 and out["dormant"] == 1
    assert (
        out["stale_visit"] == 1 and out["stale_update"] == 1
    )  # 30일 넘게 미방문 1(45일), 90일 넘게 갱신 없음 1(120일)
    assert out["unknown_dates"] == 0


def test_analyze_counts_unknown_dates_instead_of_guessing():
    out = act.analyze([e(1, last_visit=""), e(2, last_update="어제"), e(3)], now=NOW)
    assert out["unknown_dates"] == 2 and out["stale_visit"] == 0 and out["stale_update"] == 0


def test_analyze_boundaries_and_empty_input():
    assert (
        act.analyze([e(1, last_visit=fmt(act.VISIT_STALE_DAYS))], now=NOW)["stale_visit"] == 0
    )  # 정확히 30일은 아직 아니다(초과만)
    assert act.analyze([e(1, last_visit=fmt(act.VISIT_STALE_DAYS + 1))], now=NOW)["stale_visit"] == 1
    empty = act.analyze([], now=NOW)
    assert empty["total"] == 0 and empty["top_new"] == [] and empty["unknown_dates"] == 0


@pytest.mark.parametrize("bad", [None, "x", -5, 1.5])
def test_analyze_tolerates_malformed_counts(bad):
    out = act.analyze([e(1, new_articles=bad)], now=NOW)
    assert out["total"] == 1 and out["new_articles_total"] >= 0
