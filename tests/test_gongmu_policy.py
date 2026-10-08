"""공무 업무 자동 생성 정책(순수) — 금액 경계값·지위별·변경 재생성·중복 방지·기한 판정."""

from __future__ import annotations

from datetime import date

import pytest

from ai_orchestrator.gongmu import gongmu_task_policy as p

SETTINGS = p.merged_settings(None)
TODAY = date(2026, 10, 2)


def _site(**kw):
    base = {"id": "S1", "role": "prime", "contract_amount": None, "start_date": None, "end_date": None}
    base.update(kw)
    return base


def _codes(tasks):
    return sorted(t.catalog_code for t in tasks)


def _plan(site, contracts=(), today=TODAY, settings=SETTINGS):
    return p.plan_tasks(site, list(contracts), p.DEFAULT_CATALOG, settings, today)


def test_catalog_has_12_items_without_g2b():
    codes = [c["code"] for c in p.DEFAULT_CATALOG]
    assert len(codes) == 12
    assert "P7" not in codes


@pytest.mark.parametrize(
    ("amount", "expect_l2"),
    [(99_999_999, False), (100_000_000, True), (100_000_001, True)],
)
def test_prime_site_notice_boundary(amount, expect_l2):
    assert ("L2" in _codes(_plan(_site(contract_amount=amount)))) is expect_l2


@pytest.mark.parametrize(
    ("amount", "expect_l2"),
    [(39_999_999, False), (40_000_000, True), (40_000_001, True)],
)
def test_sub_contract_notice_boundary(amount, expect_l2):
    contract = {"id": "C1", "kind": "sub", "amount": amount, "contract_date": "2026-09-01", "changes": []}
    codes = _codes(_plan(_site(), [contract]))
    assert ("L2" in codes) is expect_l2
    assert "L1" in codes  # 하도급 계약이면 금액과 무관하게 키스콘 등록


def test_sub_role_site_uses_sub_threshold():
    assert "L2" in _codes(_plan(_site(role="sub", contract_amount=40_000_000)))
    assert "L2" not in _codes(_plan(_site(role="sub", contract_amount=39_999_999)))


def test_threshold_is_setting_not_code():
    custom = p.merged_settings({"prime_notice_min": 50_000_000})
    assert "L2" in _codes(_plan(_site(contract_amount=60_000_000), settings=custom))


def test_site_start_tasks_need_start_date():
    assert not {"P1", "L4", "P8", "P5"} & set(_codes(_plan(_site())))
    codes = _codes(_plan(_site(start_date="2026-10-01")))
    assert {"P1", "L4", "P8", "P5"} <= set(codes)


def test_due_rules_and_unknown_due():
    tasks = {t.catalog_code: t for t in _plan(_site(start_date="2026-10-20"))}
    assert tasks["P1"].due_date == date(2026, 10, 13)  # 착공 7일 전
    assert tasks["L4"].due_date is None  # 규칙 불명 → 기한 확인 필요(추측 금지)
    assert tasks["P4"].due_date == date(2026, 10, 31)  # 월말


def test_monthly_only_when_site_active():
    assert "P4" not in _codes(_plan(_site(start_date="2026-11-01")))  # 착공 전 달
    assert "P4" not in _codes(_plan(_site(start_date="2026-01-01", end_date="2026-09-30")))  # 준공 후
    assert "P4" in _codes(_plan(_site(start_date="2026-01-01", end_date="2026-10-02")))
    assert "L3" in _codes(_plan(_site(start_date="2026-01-01")))


def test_new_month_creates_new_period_key():
    site = _site(start_date="2026-01-01")
    oct_keys = {t.dedupe_key for t in _plan(site)}
    nov_keys = {t.dedupe_key for t in _plan(site, today=date(2026, 11, 3))}
    assert {k for k in oct_keys if "|P4|" in k}.isdisjoint({k for k in nov_keys if "|P4|" in k})


def test_same_input_is_idempotent_and_no_duplicate_keys():
    contract = {"id": "C1", "kind": "sub", "amount": 50_000_000, "contract_date": "2026-09-01", "changes": []}
    first = _plan(_site(start_date="2026-01-01"), [contract])
    second = _plan(_site(start_date="2026-01-01"), [contract])
    assert [t.dedupe_key for t in first] == [t.dedupe_key for t in second]
    assert len({t.dedupe_key for t in first}) == len(first)


def test_contract_change_regenerates_l2_only():
    contract = {
        "id": "C1",
        "kind": "sub",
        "amount": 50_000_000,
        "contract_date": "2026-09-01",
        "changes": [{"date": "2026-09-20", "amount": 55_000_000}],
    }
    tasks = _plan(_site(), [contract])
    l2 = [t for t in tasks if t.catalog_code == "L2"]
    assert len(l2) == 2 and {t.period for t in l2} == {"", "chg:2026-09-20#1"}
    assert [t.catalog_code for t in tasks].count("L1") == 1  # 변경으로 키스콘이 다시 생기지 않는다
    assert [t.catalog_code for t in tasks].count("P3") == 1


def test_change_below_threshold_does_not_create_l2():
    contract = {
        "id": "C1",
        "kind": "sub",
        "amount": 50_000_000,
        "contract_date": "2026-09-01",
        "changes": [{"date": "2026-09-20", "amount": 30_000_000}],
    }
    l2 = [t for t in _plan(_site(), [contract]) if t.catalog_code == "L2"]
    assert [t.period for t in l2] == [""]


def test_prime_contract_row_replaces_site_level_l2():
    contract = {"id": "C9", "kind": "prime", "amount": 200_000_000, "contract_date": "2026-01-10", "changes": []}
    l2 = [t for t in _plan(_site(contract_amount=200_000_000), [contract]) if t.catalog_code == "L2"]
    assert [(t.contract_id, t.period) for t in l2] == [("C9", "")]  # 현장 단위 L2 가 중복으로 생기지 않는다


def test_disabled_catalog_item_skipped():
    catalog = [dict(c, enabled=(c["code"] != "P9")) for c in p.DEFAULT_CATALOG]
    tasks = p.plan_tasks(_site(start_date="2026-01-01"), [], catalog, SETTINGS, TODAY)
    assert "P9" not in _codes(tasks)


@pytest.mark.parametrize(
    ("due", "status", "expected"),
    [
        (date(2026, 10, 1), "todo", p.OVERDUE),
        (date(2026, 10, 2), "todo", p.SOON),  # 오늘 마감은 임박
        (date(2026, 10, 9), "doing", p.SOON),  # 7일 이내 경계
        (date(2026, 10, 10), "todo", p.LATER),
        (None, "todo", p.UNKNOWN),
        (date(2026, 10, 1), "done", p.CLOSED),
        (None, "na", p.CLOSED),
    ],
)
def test_classify_due(due, status, expected):
    assert p.classify_due(due, status, TODAY, 7) == expected


def test_parse_helpers_reject_bad_input():
    assert p.parse_amount("1,000,000원") == 1_000_000
    assert p.parse_amount("") is None
    with pytest.raises(ValueError):
        p.parse_amount("-5")
    with pytest.raises(ValueError):
        p.parse_amount("abc")
    with pytest.raises(ValueError):
        p.parse_date("2026/13/45")
    assert p.parse_date("2026-10-02") == date(2026, 10, 2)


def test_validate_settings():
    assert p.validate_settings({"soon_days": "3"}) == {"soon_days": 3}
    with pytest.raises(ValueError):
        p.validate_settings({"unknown": 1})
    with pytest.raises(ValueError):
        p.validate_settings({"soon_days": -1})
