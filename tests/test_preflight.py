"""상품 등록 사전 검증 테스트 (브라우저 불필요).

이 파일이 지키는 실제 사고 (2026-08-15):
  1. '라인조명' 이라는 없는 카테고리로 등록 시도 → 브라우저 60초 왕복 후 실패
     로컬 목록에 답이 있었는데 조회하지 않았다.
  2. KC 인증번호 없이 전기용품을 판매하면 제재 대상인데, "이번엔 임시저장까지만"
     이라는 사람의 기억에만 의존하고 있었다.
"""

from __future__ import annotations

import json

import pytest

from scripts.naver.smartstore.product.category_resolver import CategoryResolver
from scripts.naver.smartstore.product.preflight import (
    ERROR,
    SALE_BLOCKER,
    WARN,
    preflight,
)

PATHS = [
    "가구/인테리어>인테리어소품>조명>인테리어조명",
    "가구/인테리어>인테리어소품>조명>LED모듈",
    "가구/인테리어>인테리어소품>조명>거실조명",
    "생활/건강>관상어용품>조명",
    "디지털/가전>PC부품>튜닝용품>조명기기",
]


@pytest.fixture
def resolver() -> CategoryResolver:
    return CategoryResolver(PATHS)


@pytest.fixture
def image(tmp_path):
    p = tmp_path / "cover.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    return str(p)


def _data(image: str, **over) -> dict:
    base = {
        "category": "인테리어조명",
        "name": "LED 라인조명 주문제작",
        "price": 24900,
        "stock": 100,
        "main_image": image,
    }
    base.update(over)
    return base


# ── 카테고리 해석기 ──────────────────────────────────────────────
def test_resolve_exact_leaf(resolver):
    m = resolver.resolve("인테리어조명")
    assert m is not None
    assert m.path == "가구/인테리어>인테리어소품>조명>인테리어조명"


def test_resolve_exact_full_path(resolver):
    m = resolver.resolve("가구/인테리어>인테리어소품>조명>거실조명")
    assert m is not None
    assert m.leaf == "거실조명"


def test_resolve_unknown_returns_none(resolver):
    """부분일치를 성공으로 처리하면 엉뚱한 카테고리에 등록된다."""
    assert resolver.resolve("라인조명") is None
    assert resolver.resolve("") is None


def test_candidates_offer_the_real_answer(resolver):
    """'라인조명' 오입력 시 정답('인테리어조명')이 후보에 있어야 한다."""
    assert "인테리어조명" in resolver.candidates("라인조명")


def test_missing_file_yields_empty_resolver(tmp_path):
    r = CategoryResolver.load(tmp_path / "없는파일.json")
    assert r.loaded is False


def test_corrupt_file_does_not_raise(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("{ 깨진 json", encoding="utf-8")
    assert CategoryResolver.load(f).loaded is False


def test_load_reads_paths(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"a": PATHS}, ensure_ascii=False), encoding="utf-8")
    r = CategoryResolver.load(f)
    assert r.loaded is True
    assert r.resolve("인테리어조명") is not None


# ── 카테고리 preflight ───────────────────────────────────────────
def test_bad_category_blocks_browser(resolver, image):
    """핵심: 브라우저를 열기 전에 막고, 고칠 후보를 준다."""
    rep = preflight(_data(image, category="라인조명"), resolver)
    cat = [i for i in rep.issues if i.field == "category"]
    assert cat and cat[0].severity == ERROR
    assert "인테리어조명" in cat[0].candidates
    assert rep.can_fill is False


def test_good_category_resolves_to_full_path(resolver, image):
    rep = preflight(_data(image), resolver)
    assert rep.resolved["category_path"] == "가구/인테리어>인테리어소품>조명>인테리어조명"


def test_unloaded_resolver_does_not_block(image):
    """목록을 못 읽었으면 판정하지 않는다 — 모르면서 막으면 정상 등록까지 막힌다."""
    rep = preflight(_data(image), CategoryResolver([]))
    assert rep.can_fill is True
    assert any(i.field == "category" and i.severity == WARN for i in rep.issues)


# ── 나머지 필드 ──────────────────────────────────────────────────
def test_missing_image_file_is_error(resolver, tmp_path):
    rep = preflight(_data(str(tmp_path / "없음.png")), resolver)
    assert rep.can_fill is False


def test_bad_image_extension_is_error(resolver, tmp_path):
    p = tmp_path / "a.bmp"
    p.write_bytes(b"x")
    rep = preflight(_data(str(p)), resolver)
    assert any(i.field == "main_image" and i.severity == ERROR for i in rep.issues)


def test_too_long_name_is_error(resolver, image):
    rep = preflight(_data(image, name="가" * 101), resolver)
    assert any(i.field == "name" and i.severity == ERROR for i in rep.issues)


@pytest.mark.parametrize("bad", [24905, 5, -100, "24900", True])
def test_invalid_price_is_error(resolver, image, bad):
    rep = preflight(_data(image, price=bad), resolver)
    assert any(i.field == "price" and i.severity == ERROR for i in rep.issues)


def test_missing_price_blocks_sale_only(resolver, image):
    """가격 미정은 임시저장까지는 허용한다(실제 운용 방식)."""
    d = _data(image)
    del d["price"]
    rep = preflight(d, resolver)
    assert rep.can_fill is True
    assert rep.can_publish is False


# ── 판매개시 차단 ────────────────────────────────────────────────
def test_kc_cert_missing_blocks_publish_but_allows_draft(resolver, image):
    """전기용품은 KC 인증번호 없이 판매하면 제재 대상 — 코드가 막는다."""
    rep = preflight(_data(image), resolver)
    assert rep.can_fill is True, "임시저장까지는 되어야 한다"
    assert rep.can_publish is False
    assert any(i.field == "kc_cert" and i.severity == SALE_BLOCKER for i in rep.issues)


def test_complete_data_can_publish(resolver, image):
    rep = preflight(
        _data(
            image,
            kc_cert="XU-12345-6789",
            origin_area="경상북도",
            delivery_fee_policy="무료",
            as_phone="010-0000-0000",
            tags=["라인조명"],
        ),
        resolver,
    )
    assert rep.issues == []
    assert rep.can_publish is True


def test_issues_are_serializable_for_agents(resolver, image):
    """AI 에이전트가 받아서 스스로 고칠 수 있는 형태여야 한다."""
    rep = preflight(_data(image, category="라인조명"), resolver)
    d = rep.as_dicts()
    assert json.dumps(d, ensure_ascii=False)
    assert {"field", "severity", "message", "candidates"} <= set(d[0])


def test_register_product_has_preflight_gate():
    """register_product 가 preflight 를 관문으로 쓰는지 (배선 확인)."""
    import inspect

    from scripts.naver.smartstore.product.general_product import GeneralProductRegister

    src = inspect.getsource(GeneralProductRegister.register_product)
    assert "preflight(" in src
    assert "can_fill" in src
    assert "can_publish" in src
    # 브라우저를 여는 open() 보다 preflight 가 먼저여야 의미가 있다
    assert src.index("preflight(") < src.index("self.open()")
