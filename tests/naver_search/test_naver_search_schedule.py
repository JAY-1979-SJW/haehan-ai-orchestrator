"""5단계 스케줄/실행 기록/상태 확장 검증.

검증 항목:
1. flag off → run_scheduled_collection 즉시 return, 기록 없음
2. 쿼리 미설정 → skipped 기록 남음
3. 정상 실행 → recent run 기록 남음 (ok 상태)
4. search-status 응답에 recent_runs 포함
5. audit 스크립트가 NO_RECENT_RUNS WARN 판정
6. 민감정보 미노출 회귀
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.connectors.naver_search.naver_search_router import naver_search_router
from scripts.naver.shopping.naver_search_run_log import append_run, load_recent_runs
from ai_orchestrator.connectors.naver_search.naver_search_runner import (
    ENV_BLOG_QUERIES,
    ENV_SCHEDULE_ENABLED,
    ENV_SHOP_QUERIES,
    run_scheduled_collection,
)
from scripts.naver.shopping import naver_openapi_config as cfg_mod

# ── 공통 fixtures ────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    from ai_orchestrator.core import config as _config

    monkeypatch.setattr(_config, "AUTH_ENABLED", False, raising=False)
    yield


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(naver_search_router, prefix="/api/v1")
    return TestClient(app)


def _clear_naver_env(monkeypatch):
    for k in (
        cfg_mod.ENV_BASE_URL,
        cfg_mod.ENV_CLIENT_ID,
        cfg_mod.ENV_CLIENT_SECRET,
        cfg_mod.ENV_DRY_RUN,
        "NAVER_SEARCH_DB_ENABLED",
        "NAVER_SEARCH_DB_PATH",
        "NAVER_SEARCH_STATE_PATH",
        "NAVER_SEARCH_RUN_LOG_PATH",
        ENV_SCHEDULE_ENABLED,
        ENV_BLOG_QUERIES,
        ENV_SHOP_QUERIES,
    ):
        monkeypatch.delenv(k, raising=False)


def _mock_transport(items: list):
    def transport(method, url, headers, params):
        return 200, {"items": items}

    return transport


_BLOG_ITEMS = [
    {
        "title": "테스트글",
        "link": "https://b.example.invalid/1",
        "description": "d1",
        "bloggername": "n1",
        "bloggerlink": "bl",
        "postdate": "99991231",
    },
]
_SHOP_ITEMS = [
    {
        "title": "상품A",
        "link": "u1",
        "image": "i1",
        "lprice": "10000",
        "hprice": "",
        "mallName": "M",
        "productId": "PID-X",
        "productType": "1",
        "brand": "B",
        "maker": "M2",
        "category1": "디지털",
        "category2": "",
        "category3": "",
        "category4": "",
    },
]


# ── 1. flag off → skip ───────────────────────────────────────────


def test_flag_off_produces_no_run_record(tmp_path, monkeypatch):
    _clear_naver_env(monkeypatch)
    run_log = tmp_path / "runs.jsonl"
    monkeypatch.setenv(ENV_SCHEDULE_ENABLED, "false")
    monkeypatch.setenv(ENV_BLOG_QUERIES, "파이썬")

    run_scheduled_collection(run_log_path=run_log)

    assert not run_log.exists()


# ── 2. 쿼리 미설정 → skipped 기록 ───────────────────────────────


def test_no_queries_writes_skipped_record(tmp_path, monkeypatch):
    _clear_naver_env(monkeypatch)
    run_log = tmp_path / "runs.jsonl"
    monkeypatch.setenv(ENV_SCHEDULE_ENABLED, "true")
    monkeypatch.delenv(ENV_BLOG_QUERIES, raising=False)
    monkeypatch.delenv(ENV_SHOP_QUERIES, raising=False)

    run_scheduled_collection(run_log_path=run_log)

    runs = load_recent_runs(path=run_log)
    assert len(runs) == 1
    assert runs[0]["status"] == "skipped"
    assert runs[0]["error_summary"] == "NO_QUERIES_CONFIGURED"


# ── 3. 정상 실행 → ok 기록 ──────────────────────────────────────


def test_normal_run_writes_ok_record(tmp_path, monkeypatch):
    _clear_naver_env(monkeypatch)
    run_log = tmp_path / "runs.jsonl"
    monkeypatch.setenv(ENV_SCHEDULE_ENABLED, "true")
    monkeypatch.setenv(ENV_BLOG_QUERIES, "테스트쿼리")
    monkeypatch.setenv(cfg_mod.ENV_DRY_RUN, "true")  # dry_run → 실제 외부 호출 없음

    run_scheduled_collection(run_log_path=run_log)

    runs = load_recent_runs(path=run_log)
    assert len(runs) == 1
    rec = runs[0]
    assert rec["job_type"] == "blog"
    assert rec["status"] == "ok"
    assert rec["query"] == "테스트쿼리"
    assert "started_at" in rec
    assert "finished_at" in rec
    # 민감정보 없음
    blob = json.dumps(rec)
    for forbidden in ("client_id", "client_secret", "X-Naver", "SECRET"):
        assert forbidden not in blob


def test_shop_run_writes_ok_record(tmp_path, monkeypatch):
    _clear_naver_env(monkeypatch)
    run_log = tmp_path / "runs.jsonl"
    monkeypatch.setenv(ENV_SCHEDULE_ENABLED, "true")
    monkeypatch.setenv(ENV_SHOP_QUERIES, "키보드")
    monkeypatch.setenv(cfg_mod.ENV_DRY_RUN, "true")

    run_scheduled_collection(run_log_path=run_log)

    runs = load_recent_runs(path=run_log)
    assert any(r["job_type"] == "shopping" for r in runs)
    assert all(r["status"] == "ok" for r in runs)


# ── 4. search-status 응답에 recent_runs 포함 ──────────────────────


def test_search_status_includes_recent_runs(tmp_path, monkeypatch, api_client):
    _clear_naver_env(monkeypatch)
    run_log = tmp_path / "runs.jsonl"
    monkeypatch.setenv("NAVER_SEARCH_RUN_LOG_PATH", str(run_log))

    # 실행 기록 수동 추가
    append_run(
        {
            "job_type": "blog",
            "query": "파이썬",
            "started_at": "2026-04-24T01:00:00+00:00",
            "finished_at": "2026-04-24T01:00:01+00:00",
            "status": "ok",
            "scanned_count": 5,
            "inserted_count": 3,
            "duplicate_count": 2,
            "skipped_count": 0,
            "db_status": "disabled",
        },
        path=run_log,
    )

    r = api_client.get("/api/v1/external/naver/search-status")
    assert r.status_code == 200
    body = r.json()
    assert "recent_runs" in body
    assert len(body["recent_runs"]) == 1
    assert body["recent_runs"][0]["status"] == "ok"
    assert body["last_success_at"] == "2026-04-24T01:00:01+00:00"
    assert body["last_fail_at"] is None

    # 민감정보 없음
    blob = json.dumps(body, ensure_ascii=False)
    for forbidden in ("client_id", "client_secret", "SECRET"):
        assert forbidden not in blob


def test_search_status_empty_recent_runs_when_no_log(tmp_path, monkeypatch, api_client):
    _clear_naver_env(monkeypatch)
    monkeypatch.setenv("NAVER_SEARCH_RUN_LOG_PATH", str(tmp_path / "missing.jsonl"))

    r = api_client.get("/api/v1/external/naver/search-status")
    assert r.status_code == 200
    body = r.json()
    assert body["recent_runs"] == []
    assert body["last_success_at"] is None


# ── 6. run_log 필드 민감정보 미노출 ─────────────────────────────


def test_append_run_strips_sensitive_fields(tmp_path):
    run_log = tmp_path / "runs.jsonl"
    append_run(
        {
            "job_type": "blog",
            "query": "safe",
            "status": "ok",
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:01+00:00",
            # 아래는 허용 필드 외 — 저장되면 안 됨
            "client_id": "SHOULD_NOT_APPEAR",
            "client_secret": "SHOULD_NOT_APPEAR",
            "db_path": "/full/path/to/db",
        },
        path=run_log,
    )

    raw = run_log.read_text(encoding="utf-8")
    for forbidden in ("SHOULD_NOT_APPEAR", "client_id", "client_secret", "db_path"):
        assert forbidden not in raw
