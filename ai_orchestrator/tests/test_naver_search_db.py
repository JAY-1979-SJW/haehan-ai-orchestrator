"""Naver 검색 2단계 — DB 적재 / 증분 상태 최소 검증.

- stdlib sqlite3 만 사용.
- live 호출은 transport 주입으로 시뮬레이션.
- dry_run/unconfigured 경로에서 DB write 없음을 확인.
"""

from __future__ import annotations

import sqlite3

from scripts.naver.shopping import naver_search_jobs
from scripts.naver.shopping import naver_search_db as db_mod
from scripts.naver.shopping import naver_search_state as state_mod
from scripts.naver.shopping import (
    naver_openapi_config as cfg_mod,
    naver_search_client,
)


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


def _live_env(monkeypatch):
    monkeypatch.setenv(cfg_mod.ENV_CLIENT_ID, "cid")
    monkeypatch.setenv(cfg_mod.ENV_CLIENT_SECRET, "cs")
    monkeypatch.setenv(cfg_mod.ENV_DRY_RUN, "false")


def _blog_transport(items):
    def transport(method, url, headers, params):
        return 200, {"total": len(items), "start": 1, "display": len(items), "items": items}

    return transport


# ────────────────────────────────────────────────────────────────
# 1) dry_run 에서는 transport 미호출 + DB write 없음 + state 미기록
# ────────────────────────────────────────────────────────────────
def test_dry_run_no_db_no_state(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("NAVER_SEARCH_DB_ENABLED", "true")  # 켜져 있어도 dry_run 이면 skip
    db_path = tmp_path / "db" / "naver_search.db"
    state_path = tmp_path / "data" / "naver_search_state.json"
    store = tmp_path / "data" / "naver_blog_search.json"

    def transport(**_):
        raise AssertionError("transport must not be called in dry_run")

    client = naver_search_client.NaverSearchClient(transport=transport)
    out = naver_search_jobs.run_naver_blog_search_job(
        "python",
        client=client,
        store_path=store,
        db_path=db_path,
        state_path=state_path,
    )
    assert out.status == "dry_run"
    assert out.db_status == "skipped_dry_run"
    assert out.inserted_count == 0
    assert out.state_updated is False
    assert not db_path.exists()
    assert not state_path.exists()
    # JSON 저장은 dry_run 에서도 유지 (1단계 동작 보존)
    assert store.exists()


# ────────────────────────────────────────────────────────────────
# 2) live + env 미설정이면 unconfigured + DB write 없음
# ────────────────────────────────────────────────────────────────
def test_unconfigured_live_skips_db(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv(cfg_mod.ENV_DRY_RUN, "false")
    monkeypatch.setenv("NAVER_SEARCH_DB_ENABLED", "true")
    db_path = tmp_path / "db" / "naver_search.db"

    out = naver_search_jobs.run_naver_blog_search_job(
        "python",
        store_path=tmp_path / "blog.json",
        db_path=db_path,
        state_path=tmp_path / "state.json",
    )
    assert out.status == "unconfigured"
    assert out.db_status == "disabled"
    assert not db_path.exists()


# ────────────────────────────────────────────────────────────────
# 3) live + DB 플래그 off → DB write 없음 (JSON 만 저장)
# ────────────────────────────────────────────────────────────────
def test_live_db_disabled_keeps_json_only(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    _live_env(monkeypatch)
    # flag off
    monkeypatch.setenv("NAVER_SEARCH_DB_ENABLED", "false")

    items = [
        {
            "title": "t",
            "link": "https://blog.example.invalid/a",
            "description": "d",
            "bloggername": "b",
            "bloggerlink": "bl",
            "postdate": "99991231",
        }
    ]
    client = naver_search_client.NaverSearchClient(transport=_blog_transport(items))
    store = tmp_path / "blog.json"
    db_path = tmp_path / "naver_search.db"

    out = naver_search_jobs.run_naver_blog_search_job(
        "python",
        client=client,
        store_path=store,
        db_path=db_path,
        state_path=tmp_path / "state.json",
    )
    assert out.status == "ok"
    assert out.db_status == "disabled"
    assert store.exists()
    assert not db_path.exists()


# ────────────────────────────────────────────────────────────────
# 4) blog 동일 link 재실행 시 duplicate 처리 (INSERT OR IGNORE)
# ────────────────────────────────────────────────────────────────
def test_blog_duplicate_link_is_ignored(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    _live_env(monkeypatch)
    monkeypatch.setenv("NAVER_SEARCH_DB_ENABLED", "true")
    db_path = tmp_path / "naver_search.db"
    state_path = tmp_path / "state.json"

    items_first = [
        {
            "title": "A",
            "link": "https://b.example.invalid/1",
            "description": "",
            "bloggername": "n",
            "bloggerlink": "bl",
            "postdate": "99991231",
        },
        {
            "title": "B",
            "link": "https://b.example.invalid/2",
            "description": "",
            "bloggername": "n",
            "bloggerlink": "bl",
            "postdate": "99991231",
        },
    ]
    client = naver_search_client.NaverSearchClient(
        transport=_blog_transport(items_first),
    )
    out1 = naver_search_jobs.run_naver_blog_search_job(
        "파이썬",
        client=client,
        store_path=tmp_path / "blog1.json",
        db_path=db_path,
        state_path=state_path,
    )
    assert out1.status == "ok"
    assert out1.db_status == "ok"
    assert out1.inserted_count == 2
    assert out1.duplicate_count == 0
    assert out1.state_updated is True

    # 두 번째 실행 — 같은 link 2개 + 새 link 1개
    items_second = items_first + [  # noqa: RUF005
        {
            "title": "C",
            "link": "https://b.example.invalid/3",
            "description": "",
            "bloggername": "n",
            "bloggerlink": "bl",
            "postdate": "99991231",
        },
    ]
    client2 = naver_search_client.NaverSearchClient(
        transport=_blog_transport(items_second),
    )
    out2 = naver_search_jobs.run_naver_blog_search_job(
        "파이썬",
        client=client2,
        store_path=tmp_path / "blog2.json",
        db_path=db_path,
        state_path=state_path,
    )
    assert out2.status == "ok"
    assert out2.inserted_count == 1
    assert out2.duplicate_count == 2

    # 총 row 수 3
    conn = sqlite3.connect(str(db_path))
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM {db_mod.TABLE_BLOG}").fetchone()[0]  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
        assert n == 3
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────
# 5) shopping 동일 product_id 재실행 시 duplicate + product_id 공란은 skipped
# ────────────────────────────────────────────────────────────────
def test_shopping_duplicate_product_id_and_missing_skipped(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    _live_env(monkeypatch)
    monkeypatch.setenv("NAVER_SEARCH_DB_ENABLED", "true")
    db_path = tmp_path / "naver_search.db"
    state_path = tmp_path / "state.json"

    def shop_items(rows):
        def t(method, url, headers, params):
            return 200, {"items": rows}

        return t

    rows1 = [
        {
            "title": "키1",
            "link": "u1",
            "image": "i1",
            "lprice": "10000",
            "hprice": "",
            "mallName": "m",
            "productId": "PID-1",
            "productType": "1",
            "brand": "",
            "maker": "",
            "category1": "",
            "category2": "",
            "category3": "",
            "category4": "",
        },
        # product_id 공란 → skipped
        {
            "title": "키2",
            "link": "u2",
            "image": "i2",
            "lprice": "20000",
            "hprice": "",
            "mallName": "m",
            "productId": "",
            "productType": "1",
            "brand": "",
            "maker": "",
            "category1": "",
            "category2": "",
            "category3": "",
            "category4": "",
        },
    ]
    client = naver_search_client.NaverSearchClient(transport=shop_items(rows1))
    out1 = naver_search_jobs.run_naver_shopping_search_job(
        "키보드",
        client=client,
        store_path=tmp_path / "s1.json",
        db_path=db_path,
        state_path=state_path,
    )
    assert out1.status == "ok"
    assert out1.inserted_count == 1
    assert out1.duplicate_count == 0
    assert out1.skipped_count == 1

    # 같은 PID-1 재실행 → duplicate=1
    client2 = naver_search_client.NaverSearchClient(transport=shop_items(rows1))
    out2 = naver_search_jobs.run_naver_shopping_search_job(
        "키보드",
        client=client2,
        store_path=tmp_path / "s2.json",
        db_path=db_path,
        state_path=state_path,
    )
    assert out2.inserted_count == 0
    assert out2.duplicate_count == 1
    assert out2.skipped_count == 1

    conn = sqlite3.connect(str(db_path))
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM {db_mod.TABLE_SHOP}").fetchone()[0]  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
        assert n == 1
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────
# 6) 증분 상태 파일 — 쿼리별 last_collected_at 기록/조회
# ────────────────────────────────────────────────────────────────
def test_state_file_tracks_last_collected(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    _live_env(monkeypatch)
    monkeypatch.setenv("NAVER_SEARCH_DB_ENABLED", "true")
    db_path = tmp_path / "naver_search.db"
    state_path = tmp_path / "state.json"

    items = [
        {
            "title": "t",
            "link": "https://b.example.invalid/x",
            "description": "",
            "bloggername": "n",
            "bloggerlink": "",
            "postdate": "99991231",
        }
    ]
    client = naver_search_client.NaverSearchClient(transport=_blog_transport(items))
    naver_search_jobs.run_naver_blog_search_job(
        "파이썬",
        client=client,
        store_path=tmp_path / "blog.json",
        db_path=db_path,
        state_path=state_path,
    )
    assert state_path.exists()
    last = state_mod.get_last_collected_at("naver_blog", "파이썬", path=state_path)
    assert isinstance(last, str) and last
    # 다른 쿼리는 None
    assert (
        state_mod.get_last_collected_at(
            "naver_blog",
            "다른쿼리",
            path=state_path,
        )
        is None
    )


# ────────────────────────────────────────────────────────────────
# 7) JSON 저장 1단계 동작 회귀 — 구조/키 그대로 유지
# ────────────────────────────────────────────────────────────────
def test_json_record_schema_preserved(tmp_path, monkeypatch):
    import json

    _clear_env(monkeypatch)  # dry_run 기본
    store = tmp_path / "data" / "blog.json"
    out = naver_search_jobs.run_naver_blog_search_job(
        "x",
        store_path=store,
        db_path=tmp_path / "naver_search.db",
        state_path=tmp_path / "state.json",
    )
    assert out.status == "dry_run"
    data = json.loads(store.read_text(encoding="utf-8"))
    for key in ("source", "query", "collected_at", "items"):
        assert key in data
    assert data["source"] == "naver_blog"
    # 정규화 키 유지
    assert "blogger_name" in data["items"][0]
