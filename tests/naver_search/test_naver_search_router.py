"""Naver 검색 read-only 엔드포인트 + 운영 점검 스크립트 검증.

- 기존 `AUTH_ENABLED=False` (dummy owner) 흐름에서 TestClient 로 호출.
- DB 조회는 naver_search_jobs 로 실제 sqlite 파일을 준비한 뒤 쿼리.
- DB 없음 상태에서도 status 엔드포인트가 WARN 으로 안전 응답하는지 확인.
- 민감정보(client_id/secret) 노출 여부를 응답 전체에서 검증.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts.naver.shopping import naver_search_jobs
from scripts.naver.shopping import naver_search_queries as q
from ai_orchestrator.connectors.naver_search.naver_search_router import naver_search_router
from scripts.naver.shopping import (
    naver_openapi_config as cfg_mod,
    naver_search_client,
)


# ── fixtures ────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    """모든 테스트 동안 AUTH_ENABLED=False 로 고정 → dummy owner 통과.
    다른 테스트에서 True 로 세팅한 잔존 상태를 무효화한다."""
    from ai_orchestrator.core import config as _config

    monkeypatch.setattr(_config, "AUTH_ENABLED", False, raising=False)
    yield


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(naver_search_router, prefix="/api/v1")
    return TestClient(app)


def _clear_env(monkeypatch):
    for k in (
        cfg_mod.ENV_BASE_URL,
        cfg_mod.ENV_CLIENT_ID,
        cfg_mod.ENV_CLIENT_SECRET,
        cfg_mod.ENV_DRY_RUN,
        "NAVER_SEARCH_DB_ENABLED",
        "NAVER_SEARCH_DB_PATH",
        "NAVER_SEARCH_STATE_PATH",
    ):
        monkeypatch.delenv(k, raising=False)


def _live_env(monkeypatch, *, db_path, state_path):
    monkeypatch.setenv(cfg_mod.ENV_CLIENT_ID, "supersecret-cid")
    monkeypatch.setenv(cfg_mod.ENV_CLIENT_SECRET, "supersecret-secret")
    monkeypatch.setenv(cfg_mod.ENV_DRY_RUN, "false")
    monkeypatch.setenv("NAVER_SEARCH_DB_ENABLED", "true")
    monkeypatch.setenv("NAVER_SEARCH_DB_PATH", str(db_path))
    monkeypatch.setenv("NAVER_SEARCH_STATE_PATH", str(state_path))


def _blog_items():
    return [
        {
            "title": "<b>py</b>",
            "link": "https://b.example.invalid/1",
            "description": "d1",
            "bloggername": "n1",
            "bloggerlink": "bl",
            "postdate": "99991231",
        },
        {
            "title": "py2",
            "link": "https://b.example.invalid/2",
            "description": "d2",
            "bloggername": "n2",
            "bloggerlink": "bl",
            "postdate": "99991230",
        },
    ]


def _shop_items():
    return [
        {
            "title": "kbd A",
            "link": "u1",
            "image": "i1",
            "lprice": "10000",
            "hprice": "",
            "mallName": "MallA",
            "productId": "PID-A",
            "productType": "1",
            "brand": "BrandX",
            "maker": "MakerY",
            "category1": "디지털",
            "category2": "주변기기",
            "category3": "키보드",
            "category4": "",
        },
        {
            "title": "kbd B",
            "link": "u2",
            "image": "i2",
            "lprice": "50000",
            "hprice": "60000",
            "mallName": "MallB",
            "productId": "PID-B",
            "productType": "1",
            "brand": "BrandZ",
            "maker": "",
            "category1": "디지털",
            "category2": "주변기기",
            "category3": "키보드",
            "category4": "",
        },
    ]


def _seed_db(tmp_path, monkeypatch):
    """테스트용 DB/state 를 실제 Job 흐름으로 채워둔다."""
    db_path = tmp_path / "naver_search.db"
    state_path = tmp_path / "state.json"
    _live_env(monkeypatch, db_path=db_path, state_path=state_path)

    def blog_t(method, url, headers, params):
        return 200, {"items": _blog_items()}

    def shop_t(method, url, headers, params):
        return 200, {"items": _shop_items()}

    client_blog = naver_search_client.NaverSearchClient(transport=blog_t)
    client_shop = naver_search_client.NaverSearchClient(transport=shop_t)
    naver_search_jobs.run_naver_blog_search_job(
        "파이썬",
        client=client_blog,
        store_path=tmp_path / "blog.json",
        db_path=db_path,
        state_path=state_path,
    )
    naver_search_jobs.run_naver_shopping_search_job(
        "키보드",
        client=client_shop,
        store_path=tmp_path / "shop.json",
        db_path=db_path,
        state_path=state_path,
    )
    return db_path, state_path


# ────────────────────────────────────────────────────────────────
# 1) blog-search 조회/필터/정렬
# ────────────────────────────────────────────────────────────────
def test_blog_search_returns_rows_and_filters(tmp_path, monkeypatch, client):
    _clear_env(monkeypatch)
    _seed_db(tmp_path, monkeypatch)

    r = client.get("/api/v1/external/naver/blog-search")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert len(body["items"]) == 2
    # 정렬: post_date DESC → "99991231" 가 먼저.
    assert body["items"][0]["post_date"] == "9999-12-31"
    # HTML 태그는 이미 정규화 단계에서 제거된 값이 DB 에 있다.
    assert "<b>" not in body["items"][0]["title"]
    # 응답 필드 키 존재
    expected_keys = {"query", "title", "link", "blogger_name", "post_date", "collected_at", "source"}
    assert expected_keys.issubset(body["items"][0].keys())

    # query 필터
    r2 = client.get("/api/v1/external/naver/blog-search?query=존재없음")
    assert r2.status_code == 200
    assert r2.json()["total"] == 0


# ────────────────────────────────────────────────────────────────
# 2) shopping-search 조회/필터/정렬
# ────────────────────────────────────────────────────────────────
def test_shopping_search_returns_rows_and_filters(tmp_path, monkeypatch, client):
    _clear_env(monkeypatch)
    _seed_db(tmp_path, monkeypatch)

    r = client.get("/api/v1/external/naver/shopping-search")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["sort"] == q.SHOP_SORT_COLLECTED_DESC
    assert {it["product_id"] for it in body["items"]} == {"PID-A", "PID-B"}

    # min_price 필터
    r2 = client.get("/api/v1/external/naver/shopping-search?min_price=30000")
    b2 = r2.json()
    assert b2["total"] == 1
    assert b2["items"][0]["product_id"] == "PID-B"

    # brand 필터
    r3 = client.get("/api/v1/external/naver/shopping-search?brand=BrandX")
    b3 = r3.json()
    assert b3["total"] == 1
    assert b3["items"][0]["product_id"] == "PID-A"

    # lprice_asc 정렬
    r4 = client.get(
        "/api/v1/external/naver/shopping-search?sort=lprice_asc",
    )
    b4 = r4.json()
    assert b4["items"][0]["lprice"] == 10000
    assert b4["items"][1]["lprice"] == 50000


# ────────────────────────────────────────────────────────────────
# 3) search-status 에 secret 미노출 + 주요 키 존재
# ────────────────────────────────────────────────────────────────
def test_search_status_no_secret_and_has_counts(tmp_path, monkeypatch, client):
    _clear_env(monkeypatch)
    db_path, state_path = _seed_db(tmp_path, monkeypatch)

    r = client.get("/api/v1/external/naver/search-status")
    assert r.status_code == 200
    body = r.json()
    blob = json.dumps(body, ensure_ascii=False)
    # 절대 섞이면 안 되는 값들
    for forbidden in ("supersecret-cid", "supersecret-secret", "X-Naver-Client-Secret", str(db_path), str(state_path)):
        assert forbidden not in blob, f"응답에 민감/원문 경로 노출: {forbidden}"
    assert body["status"] == "PASS"
    assert body["db_enabled"] is True
    assert body["db_exists"] is True
    assert body["db_path_basename"] == "naver_search.db"
    assert body["state_path_basename"] == "state.json"
    assert body["row_counts"]["naver_blog_posts"] == 2
    assert body["row_counts"]["naver_shopping_items"] == 2
    assert body["latest_collected_at"]["blog"]
    assert body["latest_collected_at"]["shopping"]
    # 마지막 수집 쿼리 리스트
    assert any(x["query"] == "파이썬" for x in body["last_blog_queries"])
    assert any(x["query"] == "키보드" for x in body["last_shop_queries"])


# ────────────────────────────────────────────────────────────────
# 4) DB 없음 / state 없음 → WARN 안전 응답
# ────────────────────────────────────────────────────────────────
def test_search_status_warn_when_nothing_configured(tmp_path, monkeypatch, client):
    _clear_env(monkeypatch)
    # DB 경로는 존재하지 않는 경로로 override → 파일 없음
    monkeypatch.setenv("NAVER_SEARCH_DB_PATH", str(tmp_path / "missing.db"))
    monkeypatch.setenv("NAVER_SEARCH_STATE_PATH", str(tmp_path / "missing.json"))
    # DB_ENABLED 는 unset → False

    r = client.get("/api/v1/external/naver/search-status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "WARN"
    assert body["db_exists"] is False
    assert body["state_exists"] is False
    assert body["row_counts"] is None
    assert "DB_DISABLED" in body["warnings"]
    assert "STATE_FILE_MISSING" in body["warnings"]

    # blog/shopping 조회도 DB 없이 안전하게 total=0
    r2 = client.get("/api/v1/external/naver/blog-search")
    assert r2.status_code == 200
    assert r2.json() == {**{"total": 0, "items": [], "limit": 50, "offset": 0, "duration_ms": r2.json()["duration_ms"]}}

    r3 = client.get("/api/v1/external/naver/shopping-search")
    assert r3.status_code == 200
    assert r3.json()["total"] == 0


# ────────────────────────────────────────────────────────────────
# 5) limit/offset 경계값 clamp
# ────────────────────────────────────────────────────────────────
def test_limit_is_clamped(tmp_path, monkeypatch, client):
    _clear_env(monkeypatch)
    _seed_db(tmp_path, monkeypatch)
    # limit=9999 → 최대 200 으로 clamp
    r = client.get("/api/v1/external/naver/blog-search?limit=9999")
    assert r.status_code == 200
    assert r.json()["limit"] == 200
    r2 = client.get("/api/v1/external/naver/blog-search?limit=-5")
    assert r2.json()["limit"] == 1  # 하한 1 로 clamp
