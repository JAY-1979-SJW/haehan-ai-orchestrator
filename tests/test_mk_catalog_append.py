"""MK 카탈로그 수동 판독 행 추가 테스트.

배경 (2026-08-15):
    pipeline.py 가 외부 유료 비전 API 로 p2~p283 만 추출하고 **쿼터 초과로 중단**됐다.
    남은 220쪽(p127, p284~p502)은 Claude Code 가 직접 페이지를 읽어 채운다.

이 파일이 지키는 것:
    제품코드 구조. 이게 틀리면 공급가와 페이지가 통째로 어긋난다.
        299-001-244-400
        └┬┘ └┬┘ └──┬──┘
         │   │     └─ 공급가 244,400원  (실측: 1,651건 100% 일치)
         │   └─────── 페이지 내 순번
         └─────────── 카탈로그 페이지번호 (실측: 1,643건 99.5% 일치)
"""

from __future__ import annotations

import csv

import pytest

from scripts.mk_catalog import append_rows as ar


# ── 코드 파싱 ────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("code", "price"),
    [
        ("299-001-244-400", "244400"),
        ("005-001-017-000", "17000"),  # 오늘 등록한 이지라인 3030 — CSV 값과 일치
        ("283-010-015-600", "15600"),
        ("286-002-201-300", "201300"),
    ],
)
def test_price_from_code(code, price):
    assert ar.price_from_code(code) == price


@pytest.mark.parametrize("bad", ["", "abc", "299-001", "299-001-244", "99-9-9-9-9"])
def test_price_from_bad_code_is_blank_not_guessed(bad):
    """형식이 다르면 **추측하지 않는다**. 0 을 넣으면 무료 상품이 등록된다."""
    assert ar.price_from_code(bad) == ""


def test_page_from_code():
    """코드 첫 3자리 = 카탈로그 페이지, 파일 페이지는 +1 (실측 확인)."""
    assert ar.page_from_code("283-001-112-800") == "284"
    assert ar.page_from_code("299-001-244-400") == "300"


def test_page_from_bad_code_is_blank():
    assert ar.page_from_code("") == ""
    assert ar.page_from_code("xxx-001-000-000") == ""


# ── 추가/갱신 ────────────────────────────────────────────────────
@pytest.fixture
def out(tmp_path, monkeypatch):
    p = tmp_path / "products_manual.csv"
    monkeypatch.setattr(ar, "OUT", p)
    return p


def _read(p):
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_append_creates_file_with_derived_fields(out):
    r = ar.append([{"name": "위티 8등 직부", "code": "283-001-112-800", "led": "E26×8"}])
    assert r == {"added": 1, "updated": 0, "skipped": 0, "total": 1, "pages": 1}
    row = _read(out)[0]
    assert row["supply_price"] == "112800", "코드에서 공급가가 산출돼야 한다"
    assert row["file_page"] == "284"
    assert "MK12_p284.pdf" in row["source_file"]


def test_same_code_updates_not_duplicates(out):
    """같은 페이지를 다시 읽어도 중복 행이 생기면 안 된다(재시작 안전성)."""
    ar.append([{"name": "구명", "code": "283-001-112-800"}])
    r = ar.append([{"name": "새이름", "code": "283-001-112-800"}])
    assert r["added"] == 0 and r["updated"] == 1
    rows = _read(out)
    assert len(rows) == 1
    assert rows[0]["name"] == "새이름"


def test_rows_without_code_are_skipped(out):
    r = ar.append([{"name": "코드없음"}, {"name": "정상", "code": "285-001-153-000"}])
    assert r["skipped"] == 1
    assert r["added"] == 1


def test_accumulates_across_calls(out):
    """페이지 단위로 즉시 저장 — 중간에 끊겨도 앞선 작업이 남아야 한다."""
    ar.append([{"name": "a", "code": "283-001-112-800"}])
    ar.append([{"name": "b", "code": "284-001-052-900"}])
    r = ar.append([{"name": "c", "code": "285-001-153-000"}])
    assert r["total"] == 3
    assert r["pages"] == 3
    assert len(_read(out)) == 3


def test_explicit_price_overrides_derived(out):
    """코드 규칙에서 벗어난 제품이 있을 수 있으므로 명시값이 우선한다."""
    ar.append([{"name": "x", "code": "283-001-112-800", "supply_price": "99999"}])
    assert _read(out)[0]["supply_price"] == "99999"


def test_output_sorted_by_code(out):
    ar.append(
        [
            {"name": "c", "code": "286-001-154-100"},
            {"name": "a", "code": "283-001-112-800"},
            {"name": "b", "code": "285-001-153-000"},
        ]
    )
    codes = [r["code"] for r in _read(out)]
    assert codes == sorted(codes), "코드 정렬이 깨지면 페이지 순서 추적이 어렵다"


def test_schema_matches_pipeline_csv(out):
    """기존 products.csv 와 컬럼이 같아야 병합할 수 있다."""
    ar.append([{"name": "x", "code": "283-001-112-800"}])
    with out.open(encoding="utf-8") as f:
        header = f.readline().strip().split(",")
    assert header == ar.FIELDS
    assert header == [
        "name",
        "code",
        "supply_price",
        "color",
        "size",
        "led",
        "color_temp",
        "features",
        "file_page",
        "source_file",
    ]
