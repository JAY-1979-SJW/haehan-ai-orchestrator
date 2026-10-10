"""scripts/naver/shopping 버그 수정 회귀 테스트 (2026-08-14).

수정된 실제 사고:
  1. ROOT = parents[4] 가 저장소 밖(C:\\work)을 가리켜 크롤러 DB가 repo 밖에 생성됨
  2. search.py 가 .env 를 로드하지 않아 조용히 dry_run(mock 1건)을 실제 결과처럼 반환
  3. search_shopping(display, sort) 인자를 받고도 하위 job 에 전달하지 않아 항상 10건/1페이지
  4. HTTPError 를 그대로 던져 네이버 errorCode(SE05 등) 원인이 사라짐
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ── 1. ROOT 경로 ────────────────────────────────────────────────
@pytest.mark.parametrize(
    "module_name",
    ["analytics", "cli", "competitor", "crawl", "search"],
)
def test_root_points_to_repo_root(module_name):
    """ROOT 가 저장소 루트여야 한다 — parents[4] 는 repo 밖을 가리켰다."""
    import importlib

    mod = importlib.import_module(f"scripts.naver.shopping.{module_name}")
    assert mod.ROOT == REPO_ROOT, f"{module_name}.ROOT={mod.ROOT} 가 repo root({REPO_ROOT}) 가 아니다"


def test_crawler_db_path_inside_repo():
    """크롤러 DB 는 반드시 저장소 안에 생성돼야 한다(repo boundary)."""
    from scripts.naver.shopping.crawl import DB_PATH

    assert DB_PATH.is_relative_to(REPO_ROOT), f"{DB_PATH} 가 repo 밖이다"
    assert DB_PATH.parent.name == "data"


# ── 2. display / sort / max_pages 전달 ──────────────────────────
def test_search_shopping_passes_display_and_sort(monkeypatch):
    """요청한 display/sort 가 실제 API 파라미터까지 전달돼야 한다."""
    from scripts.naver.shopping import search as search_mod

    captured: dict = {}

    def fake_job(query, *, display=10, start=1, sort="sim", max_pages=1, client=None, **kw):
        captured.update({"query": query, "display": display, "sort": sort, "max_pages": max_pages})

        class _Outcome:
            status = "ok"
            item_count = 0
            error_code = None
            error_message = None
            db_status = "disabled"
            inserted_count = 0

        return _Outcome()

    monkeypatch.setattr(
        "scripts.naver.shopping.naver_search_jobs.run_naver_shopping_search_job",
        fake_job,
    )

    search_mod.search_shopping("테스트키워드", display=100, sort="date", max_pages=5)

    assert captured["display"] == 100, "display 가 전달되지 않았다"
    assert captured["sort"] == "date", "sort 가 전달되지 않았다"
    assert captured["max_pages"] == 5, "max_pages 가 전달되지 않았다"


# ── 3. dry_run 을 실제 결과로 오인하지 않도록 is_live 노출 ────────
def test_search_shopping_exposes_is_live(monkeypatch):
    """dry_run/error 는 is_live=False 로 명확히 구분돼야 한다."""
    from scripts.naver.shopping import search as search_mod

    def make_job(status):
        def _job(query, **kw):
            class _Outcome:
                pass

            o = _Outcome()
            o.status = status
            o.item_count = 1
            o.error_code = None
            o.error_message = None
            o.db_status = "disabled"
            o.inserted_count = 0
            return o

        return _job

    for status, expected_live in (("ok", True), ("dry_run", False), ("error", False)):
        monkeypatch.setattr(
            "scripts.naver.shopping.naver_search_jobs.run_naver_shopping_search_job",
            make_job(status),
        )
        r = search_mod.search_shopping("테스트")
        assert r["status"] == status
        assert r["is_live"] is expected_live, f"status={status} 인데 is_live={r['is_live']}"


# ── 4. 크롤러 추출 JS 계약 ──────────────────────────────────────
def test_extract_js_uses_measured_card_selectors():
    """실측 확인된 카드 컨테이너 클래스를 사용해야 한다."""
    from scripts.naver.shopping.crawl import _EXTRACT_JS

    assert "adProduct_item" in _EXTRACT_JS, "광고 상품 카드 셀렉터 누락"
    assert "product_item" in _EXTRACT_JS, "일반 상품 카드 셀렉터 누락"
    assert "is_ad" in _EXTRACT_JS, "광고/일반 구분 필드 누락 — 가격통계가 왜곡된다"


def test_crawl_shopping_accepts_max_pages():
    """페이지네이션 인자가 있어야 1페이지(5건) 한계를 넘을 수 있다."""
    import inspect

    from scripts.naver.shopping.crawl import crawl_shopping

    params = inspect.signature(crawl_shopping).parameters
    assert "max_pages" in params
