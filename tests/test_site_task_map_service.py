"""사이트 업무 지도 M2 — 서비스·라우터 인증·AI 허용 집합 고정. 임시 폴더만 사용(실제 지도·외부 접속 없음)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator import mcp_server
from ai_orchestrator.domain import site_task_map as tm
from ai_orchestrator.gates import auth as auth_module
from ai_orchestrator.gates.auth import get_current_user
from ai_orchestrator.persistence import site_task_map_store as store
from ai_orchestrator.routers.site_task_map_router import site_task_map_router
from ai_orchestrator.services import site_task_map_service as service

HOST = "www.example-kiscon.test"
NOW = "2026-10-03T12:00:00+09:00"


def _snap(links, host=HOST):
    url = f"https://{host}/gongsi/ksc_dft.asp"
    return {
        "url": url,
        "title": "업체정보입력검색",
        "frames": [
            {
                "idx": 0,
                "url": url,
                "inputs": [{"tag": "INPUT", "type": "text", "name": "txtSangHo", "id": "", "placeholder": "업체명", "aria": "", "required": False, "visible": True}],
                "buttons": [],
                "links": links,
                "forms": [],
                "headings": [],
            }
        ],
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "site_task_map")
    m = tm.empty_map(HOST, now=NOW)
    m = tm.merge_tasks(m, tm.tasks_from_snapshot(_snap([{"text": "검색", "href": "#", "target": "", "visible": True}]), now=NOW), now=NOW)
    store.save(m)
    return m


def test_list_hosts_summary_and_corrupt_file_does_not_block(env, tmp_path):
    (tmp_path / "site_task_map" / "broken.example.json").write_text("{깨짐", encoding="utf-8")
    items = {i["host"]: i for i in service.list_hosts()}
    assert items[HOST]["tasks"] == 1 and items[HOST]["verified"] == 0
    assert "error" in items["broken.example"]  # 한 항목만 오류로 표시, 목록은 계속


def test_lookup_known_and_unknown_host(env):
    got = service.lookup(HOST, "업체 txtsangho")
    assert got["known"] is True and got["count"] == 1 and got["tasks"][0]["risk"] == "read"
    assert "write·submit" in got["rules"]  # 실행 규칙이 응답에 함께 실린다
    none = service.lookup("never-seen.example.test", "x")
    assert none["known"] is False and none["tasks"] == [] and "탐색" in none["hint"]


def test_lookup_limit_is_clamped(env):
    assert service.lookup(HOST, "", limit=0)["count"] == 1  # 최소 1
    assert service.lookup(HOST, "", limit=10_000)["count"] == 1  # 상한 안에서만


def test_classify_and_outcome_flow(env):
    tid = env["tasks"][0]["id"]
    done = service.classify(HOST, tid, name="업체정보 검색", purpose="협력업체 상태 확인", category="search")
    assert done["name"] == "업체정보 검색" and done["risk"] == "read"
    assert service.record_outcome(HOST, tid, ok=True)["state"] == "verified"
    failed = service.record_outcome(HOST, tid, ok=False)
    assert (failed["state"], failed["failures"]) == ("stale", 1)
    with pytest.raises(ValueError, match="분류"):
        service.classify(HOST, tid, category="bogus")
    with pytest.raises(ValueError, match="찾을 수 없"):
        service.record_outcome(HOST, "nope", ok=True)


def test_ai_registry_exposes_only_two_read_endpoints():
    entries = {k: (v["method"], v["path"]) for k, v in mcp_server.API_REGISTRY.items() if "site-map" in v["path"]}
    assert entries == {
        "sitemap.list": ("GET", "/api/v1/site-map/hosts"),
        "sitemap.lookup": ("GET", "/api/v1/site-map/{host}/lookup"),
    }  # classify·outcome·전체 지도는 AI 허용이 아니다


def test_router_requires_admin_and_flows(env, monkeypatch):
    monkeypatch.setattr(auth_module.config, "AUTH_ENABLED", True)
    app = FastAPI()
    app.include_router(site_task_map_router)
    client = TestClient(app)
    assert client.get("/site-map/hosts").status_code in (401, 403)
    app.dependency_overrides[get_current_user] = lambda: {"role": "viewer", "username": "v"}
    assert client.get("/site-map/hosts").status_code == 403
    app.dependency_overrides[get_current_user] = lambda: {"role": "admin", "username": "kim"}
    assert client.get("/site-map/hosts").json()["items"][0]["host"] == HOST
    lk = client.get(f"/site-map/{HOST}/lookup", params={"q": "업체"}).json()
    assert lk["known"] is True
    tid = lk["tasks"][0]["id"]
    assert client.post(f"/site-map/{HOST}/classify", json={"task_id": tid, "name": "검색"}).json()["name"] == "검색"
    assert client.post(f"/site-map/{HOST}/outcome", json={"task_id": tid, "ok": True}).json()["state"] == "verified"
    assert client.get(f"/site-map/{HOST}").json()["tasks"][0]["state"] == "verified"
    assert client.get("/site-map/unknown.example.test").status_code == 404
    assert client.post(f"/site-map/{HOST}/classify", json={"task_id": "nope"}).status_code == 404
    assert client.get("/site-map/bad host/lookup").status_code in (404, 422)
    assert client.get("/site-map/..%2Fetc/lookup").status_code in (404, 422)
