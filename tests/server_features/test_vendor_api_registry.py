"""벤더 공식 API 레지스트리 테스트.

이 파일이 지키는 실제 사고 (2026-08-15):
    네이버 커머스API가 무료로 제공하는 상품등록을 CDP 브라우저 자동화로 만들었다.
    검색태그에 다섯 번, 옵션 그리드에 여러 번 헛짚고 접힌 섹션으로 네 번 오판했다.
    capability_check 를 돌렸지만 그건 '저장소 안' 만 보는 도구라 잡히지 않았다.

    CLAUDE.md 의 "API가 있으면 API 호출, CDP는 최후 수단" 은 사람이 기억해야 하는
    규칙이었다. 이제 도구가 경고한다.
"""

from __future__ import annotations

import json

from tools.hooks.vendor_api_registry import (
    REGISTRY_FILE,
    STATUS_NOT_REGISTERED,
    VendorAPI,
    cdp_warning,
    find,
    format_report,
    load_registry,
)


def _reg() -> list[VendorAPI]:
    return list(load_registry())


# ── 로드 ────────────────────────────────────────────────────────
def test_registry_file_exists_and_parses():
    assert REGISTRY_FILE.exists(), "configs/vendor_apis.json 이 없다"
    json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    assert _reg(), "벤더 목록이 비어 있다"


def test_missing_file_is_not_fatal(tmp_path):
    """목록이 없어도 capability_check 가 죽으면 안 된다."""
    from tools.hooks.vendor_api_registry import _load

    assert _load(tmp_path / "없음.json") == []


def test_corrupt_file_is_not_fatal(tmp_path):
    from tools.hooks.vendor_api_registry import _load

    f = tmp_path / "bad.json"
    f.write_text("{ 깨진", encoding="utf-8")
    assert _load(f) == []


# ── 검색 ────────────────────────────────────────────────────────
def test_finds_commerce_api_by_english_keyword():
    hits = find(["smartstore"])
    assert any("커머스API" in v.name for v in hits)


def test_finds_commerce_api_by_korean_keyword():
    """한글로 찾아도 걸려야 실효가 있다 — 실제 호출은 한글로도 한다."""
    hits = find(["스마트스토어"])
    assert any("커머스API" in v.name for v in hits)


def test_partial_match_works():
    assert find(["상품등록"]), "'상품등록' 으로도 커머스API 가 잡혀야 한다"


def test_empty_terms_returns_nothing():
    assert find([]) == []
    assert find([""]) == []


def test_unrelated_term_returns_nothing():
    assert find(["존재하지않는도메인xyz"]) == []


# ── 커머스API 내용 (오늘 확인한 사실) ────────────────────────────
def test_commerce_api_lists_the_fields_we_struggled_with():
    """오늘 CDP 로 고생한 것들이 API 에 있다는 사실이 기록돼 있어야 한다."""
    v = next(x for x in _reg() if "커머스API" in x.name)
    joined = " ".join(v.supported)
    for field in ("sellerTags", "optionCombinations", "originAreaInfo", "productCertificationInfos"):
        assert field in joined, f"{field} 가 지원 목록에 없다"


def test_commerce_api_records_smarteditor_limitation():
    """상세페이지만은 API 로 안 된다 — 이걸 잃으면 또 잘못 판단한다."""
    v = next(x for x in _reg() if "커머스API" in x.name)
    assert any("스마트에디터" in s for s in v.not_supported)


def test_commerce_api_warns_about_detailcontent_destruction():
    """API 로 수정 시 detailContent 를 넣으면 스마트에디터 콘텐츠가 파괴된다."""
    v = next(x for x in _reg() if "커머스API" in x.name)
    assert any("detailContent" in c and "파괴" in c for c in v.caveats)


def test_commerce_api_warns_about_kc_exclusion_misuse():
    """인증 대상인데 제외 플래그를 쓰면 법 위반이다."""
    v = next(x for x in _reg() if "커머스API" in x.name)
    assert any("kcCertifiedProductExclusionYn" in c for c in v.caveats)


def test_commerce_api_is_marked_not_registered():
    v = next(x for x in _reg() if "커머스API" in x.name)
    assert v.status == STATUS_NOT_REGISTERED
    assert v.needs_signup is True


# ── 경고 ────────────────────────────────────────────────────────
def test_cdp_warning_fires_when_api_exists():
    warn = cdp_warning(find(["smartstore"]))
    assert warn and "CDP" in warn
    assert "커머스API" in warn


def test_cdp_warning_mentions_signup_when_not_registered():
    assert "미신청" in (cdp_warning(find(["smartstore"])) or "")


def test_no_warning_when_vendor_has_no_usable_api():
    """EUM 처럼 API 가 없는 곳에서는 경고하지 않는다 — 거짓 경보는 신뢰를 깎는다."""
    hits = find(["eum"])
    assert hits, "EUM 항목 자체는 있어야 한다(확인했다는 기록)"
    assert cdp_warning(hits) is None


def test_no_warning_for_unknown_domain():
    assert cdp_warning(find(["존재하지않는도메인xyz"])) is None


# ── 출력 ────────────────────────────────────────────────────────
def test_report_includes_supported_and_unsupported():
    txt = format_report(find(["smartstore"]))
    assert "✅" in txt and "❌" in txt


def test_report_empty_when_no_hits():
    assert format_report([]) == ""


def test_capability_check_runs_vendor_section_first():
    """벤더 API 는 저장소 스캔보다 **먼저** 나와야 의미가 있다."""
    import inspect

    from tools.hooks import capability_check as cc

    src = inspect.getsource(cc.run)
    assert "find_vendor_apis" in src
    assert src.index("find_vendor_apis") < src.index("_scan_catalog")
