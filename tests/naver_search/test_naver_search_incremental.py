"""Naver 검색 3단계 — 실제 증분 수집 검증 (핵심 케이스만)."""

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


def _blog_page_transport(pages):
    """페이지별 items 리스트를 순서대로 반환하는 transport.

    transport 는 params["start"] 에 따라 페이지를 선택하지 않고, 호출 순서대로 반환한다
    (테스트 단순화 — 실제 Job 은 start 를 증가시키며 연속 호출한다).
    """
    state = {"idx": 0}

    def transport(method, url, headers, params):
        i = state["idx"]
        state["idx"] += 1
        items = pages[i] if i < len(pages) else []
        return 200, {"total": len(items), "start": i, "display": 10, "items": items}

    return transport


def _shop_page_transport(pages):
    state = {"idx": 0}

    def transport(method, url, headers, params):
        i = state["idx"]
        state["idx"] += 1
        items = pages[i] if i < len(pages) else []
        return 200, {"items": items}

    return transport


def _blog_item(link: str, postdate: str, title: str = "t"):
    return {
        "title": title,
        "link": link,
        "description": "",
        "bloggername": "n",
        "bloggerlink": "bl",
        "postdate": postdate,
    }


def _shop_item(pid: str, title: str = "t"):
    return {
        "title": title,
        "link": f"https://shop.example.invalid/{pid}",
        "image": "",
        "lprice": "10000",
        "hprice": "",
        "mallName": "m",
        "productId": pid,
        "productType": "1",
        "brand": "",
        "maker": "",
        "category1": "",
        "category2": "",
        "category3": "",
        "category4": "",
    }


# ────────────────────────────────────────────────────────────────
# 1) blog: state.last_collected_at 이후 글만 insert, 과거 만나면 loop 종료
# ────────────────────────────────────────────────────────────────
def test_blog_date_cutoff_stops_loop(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    _live_env(monkeypatch)
    monkeypatch.setenv("NAVER_SEARCH_DB_ENABLED", "true")
    db_path = tmp_path / "naver_search.db"
    state_path = tmp_path / "state.json"

    # state 에 2026-05-01 수집 기록을 심어둔다 → cutoff = "2026-05-01".
    state_mod.mark_query_collected(
        "naver_blog",
        "파이썬",
        collected_at="2026-05-01T00:00:00+00:00",
        path=state_path,
    )

    # 1페이지: 신규 2개 + 과거 1개 (과거 만나는 순간 loop 종료).
    # 만약 종료하지 못하면 2페이지에서 추가로 insert 가 발생하거나 transport 가 더 호출된다.
    page1 = [
        _blog_item("https://b.example.invalid/new-1", "20260510"),
        _blog_item("https://b.example.invalid/new-2", "20260505"),
        _blog_item("https://b.example.invalid/old-1", "20260301"),  # cutoff 이전
        _blog_item("https://b.example.invalid/old-2", "20260201"),
    ]
    page2 = [_blog_item("https://b.example.invalid/extra", "20260520")]

    transport = _blog_page_transport([page1, page2])
    client = naver_search_client.NaverSearchClient(transport=transport)

    out = naver_search_jobs.run_naver_blog_search_job(
        "파이썬",
        client=client,
        max_pages=3,
        store_path=tmp_path / "blog.json",
        db_path=db_path,
        state_path=state_path,
    )
    assert out.status == "ok"
    assert out.early_stop_reason == "date_cutoff"
    assert out.inserted_count == 2  # 신규 2개만 적재
    assert out.duplicate_count == 0
    # 과거 글을 마주한 시점에 break — 4번째 item 은 scan 조차 안 될 수도 있지만
    # 구현상 loop 안에서 과거 1건을 확인한 뒤 break 이므로 scanned >= 3.
    assert 3 <= out.scanned_count <= 4
    # 2페이지로 넘어가지 않았는지 — DB row 수로 확인
    conn = sqlite3.connect(str(db_path))
    try:
        n = conn.execute(
            f"SELECT COUNT(*) FROM {db_mod.TABLE_BLOG}"  # nosec B608 - 테이블명은 모듈 상수, 조건/정렬은 고정 조각이고 값은 ? 바인딩(사용자 입력 미결합)
        ).fetchone()[0]
        assert n == 2
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────
# 2) shopping: 연속 duplicate 임계 도달 시 이후 페이지 호출 중단
# ────────────────────────────────────────────────────────────────
def test_shopping_duplicate_threshold_stops_paging(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    _live_env(monkeypatch)
    monkeypatch.setenv("NAVER_SEARCH_DB_ENABLED", "true")
    db_path = tmp_path / "naver_search.db"
    state_path = tmp_path / "state.json"

    # 1페이지로 3건 선 적재 — 이후 중복 판단의 기준.
    seed = [_shop_item(f"PID-{i}") for i in range(3)]
    seed_client = naver_search_client.NaverSearchClient(
        transport=_shop_page_transport([seed]),
    )
    naver_search_jobs.run_naver_shopping_search_job(
        "키보드",
        client=seed_client,
        max_pages=1,
        store_path=tmp_path / "s_seed.json",
        db_path=db_path,
        state_path=state_path,
    )

    # 본 실행: threshold=3 으로 낮춰서 테스트. 페이지1 전부 중복 → 페이지2 호출 안 됨.
    page1 = [_shop_item(f"PID-{i}") for i in range(3)]  # 모두 중복
    page2 = [_shop_item("PID-NEW")]  # 호출되면 안 됨
    tracker = {"count": 0}

    def t(method, url, headers, params):
        tracker["count"] += 1
        pages = [page1, page2]
        i = tracker["count"] - 1
        items = pages[i] if i < len(pages) else []
        return 200, {"items": items}

    client = naver_search_client.NaverSearchClient(transport=t)
    out = naver_search_jobs.run_naver_shopping_search_job(
        "키보드",
        client=client,
        max_pages=5,
        duplicate_stop_threshold=3,
        store_path=tmp_path / "s_run.json",
        db_path=db_path,
        state_path=state_path,
    )
    assert out.status == "ok"
    assert out.early_stop_reason == "duplicate_threshold"
    assert out.inserted_count == 0
    assert out.duplicate_count == 3
    # 2페이지는 호출되지 않았어야 한다
    assert tracker["count"] == 1
    # state 갱신은 없어야 한다 (insert=0)
    assert out.state_updated is False


# ────────────────────────────────────────────────────────────────
# 3) state: 신규 insert 0 이면 last_collected_at 미갱신
# ────────────────────────────────────────────────────────────────
def test_state_not_updated_when_no_insert(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    _live_env(monkeypatch)
    monkeypatch.setenv("NAVER_SEARCH_DB_ENABLED", "true")
    db_path = tmp_path / "naver_search.db"
    state_path = tmp_path / "state.json"

    # 선적재 (state 초기화)
    items = [_blog_item("https://b.example.invalid/x", "99991231")]
    client1 = naver_search_client.NaverSearchClient(
        transport=_blog_page_transport([items]),
    )
    out1 = naver_search_jobs.run_naver_blog_search_job(
        "파이썬",
        client=client1,
        store_path=tmp_path / "blog1.json",
        db_path=db_path,
        state_path=state_path,
    )
    assert out1.inserted_count == 1
    assert out1.state_updated is True
    ts_first = state_mod.get_last_collected_at(
        "naver_blog",
        "파이썬",
        path=state_path,
    )
    assert ts_first

    # 같은 item 재실행 — 전부 duplicate → insert=0 → state 시간 불변
    client2 = naver_search_client.NaverSearchClient(
        transport=_blog_page_transport([items]),
    )
    out2 = naver_search_jobs.run_naver_blog_search_job(
        "파이썬",
        client=client2,
        store_path=tmp_path / "blog2.json",
        db_path=db_path,
        state_path=state_path,
    )
    assert out2.inserted_count == 0
    assert out2.duplicate_count == 1
    assert out2.state_updated is False
    ts_second = state_mod.get_last_collected_at(
        "naver_blog",
        "파이썬",
        path=state_path,
    )
    assert ts_second == ts_first  # 갱신 없음


# ────────────────────────────────────────────────────────────────
# 4) dry_run: 기존 동작 보존 (cutoff 무시 + DB write 없음)
# ────────────────────────────────────────────────────────────────
def test_dry_run_unchanged_by_incremental_layer(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    state_path = tmp_path / "state.json"
    # state 에 이미 미래 기록이 있어도 dry_run 결과에는 영향 없어야 한다.
    state_mod.mark_query_collected(
        "naver_blog",
        "파이썬",
        collected_at="9999-12-31T00:00:00+00:00",
        path=state_path,
    )
    store = tmp_path / "blog.json"
    out = naver_search_jobs.run_naver_blog_search_job(
        "파이썬",
        store_path=store,
        db_path=tmp_path / "naver_search.db",
        state_path=state_path,
    )
    assert out.status == "dry_run"
    assert out.db_status == "skipped_dry_run"
    assert out.early_stop_reason is None
    # mock 1건은 그대로 저장됨
    assert out.item_count >= 1
    assert store.exists()
