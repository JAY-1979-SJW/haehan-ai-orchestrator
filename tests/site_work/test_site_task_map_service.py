"""사이트 업무 지도 M2 — 서비스·라우터 인증·AI 허용 집합 고정. 임시 폴더만 사용(실제 지도·외부 접속 없음)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.server import mcp_server
from ai_orchestrator.site_work import site_task_map as tm
from ai_orchestrator.site_work import site_task_map_service as service
from ai_orchestrator.site_work import site_task_map_store as store
from ai_orchestrator.site_work.site_task_map_router import site_task_map_router
from tools.gates import auth as auth_module
from tools.gates.auth import get_current_user

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


def test_ai_registry_exposes_two_reads_request_creation_and_read_task_run_only():
    entries = {k: (v["method"], v["path"]) for k, v in mcp_server.API_REGISTRY.items() if "site-map" in v["path"]}
    assert entries == {
        "sitemap.list": ("GET", "/api/v1/site-map/hosts"),
        "sitemap.lookup": ("GET", "/api/v1/site-map/{host}/lookup"),
        "sitemap.explore_request": ("POST", "/api/v1/site-map/explore/requests"),
        "sitemap.run": ("POST", "/api/v1/site-map/{host}/run"),
    }  # classify·outcome·전체 지도·승인·취소는 AI 허용이 아니다 (run 은 서버가 read 업무만 허용)


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


# ── M5: 지도 기반 실행 (가짜 실행기) ───────────────────────────────────────


@pytest.fixture
def runner_calls(env):
    calls = []

    def fake_runner(host, task_id, values):
        calls.append((host, task_id, values))
        return {"ok": True, "task_id": task_id, "tables": [{"headers": ["상호"], "rows": [["x"]], "truncated": False}], "state": "verified"}

    service.configure_runner(fake_runner)
    yield calls
    service.configure_runner(None)


def test_run_task_validates_before_touching_the_browser(env, runner_calls):
    tid = env["tasks"][0]["id"]
    ok = service.run_task(HOST, tid, {"txtSangHo": " 삼성 "})
    assert ok["ok"] is True and runner_calls == [(HOST, tid, {"txtSangHo": "삼성"})]
    for bad in ({}, {"unknown": "x"}, {"txtSangHo": "a" * 201}):
        with pytest.raises(ValueError):
            service.run_task(HOST, tid, bad)
    with pytest.raises(ValueError, match="찾을 수 없"):
        service.run_task(HOST, "nope", {"txtSangHo": "a"})
    assert len(runner_calls) == 1  # 검증에 걸린 요청은 실행기까지 가지 않는다


def test_run_task_refuses_non_read_tasks_on_the_server(env, runner_calls):
    risky = tm.tasks_from_snapshot(_snap([{"text": "신고", "href": "#", "target": "", "visible": True}]), now=NOW)[0]
    risky["id"] = "risky#page"
    store.save(tm.merge_tasks(store.load(HOST), [risky], now=NOW))
    assert risky["risk"] == "submit"
    with pytest.raises(ValueError, match=r"조회\(read\) 업무만"):
        service.run_task(HOST, "risky#page", {"txtSangHo": "a"})
    assert runner_calls == []


def test_run_task_without_runner_and_router_flow(env, monkeypatch):
    service.configure_runner(None)
    with pytest.raises(ValueError, match="실행기가 연결되지"):
        service.run_task(HOST, env["tasks"][0]["id"], {"txtSangHo": "a"})
    service.configure_runner(lambda host, tid, values: {"ok": True, "task_id": tid, "values_seen": values})
    try:
        app = FastAPI()
        app.include_router(site_task_map_router)
        app.dependency_overrides[get_current_user] = lambda: {"role": "admin", "username": "kim"}
        client = TestClient(app)
        tid = env["tasks"][0]["id"]
        got = client.post(f"/site-map/{HOST}/run", json={"task_id": tid, "params": {"txtSangHo": "삼성"}})
        assert got.status_code == 200 and got.json()["values_seen"] == {"txtSangHo": "삼성"}
        assert client.post(f"/site-map/{HOST}/run", json={"task_id": tid, "params": {}}).status_code == 400
        assert client.post(f"/site-map/{HOST}/run", json={"task_id": "nope", "params": {"txtSangHo": "a"}}).status_code == 404
        app.dependency_overrides[get_current_user] = lambda: {"role": "viewer", "username": "v"}
        monkeypatch.setattr(auth_module.config, "AUTH_ENABLED", True)
        assert client.post(f"/site-map/{HOST}/run", json={"task_id": tid, "params": {"txtSangHo": "a"}}).status_code == 403
    finally:
        service.configure_runner(None)


def test_lookup_distinguishes_explored_empty_site_from_unexplored(env):
    store.save(tm.note_exploration(tm.empty_map("empty.example.test", now=NOW), pages=7, auth="public", now=NOW))
    got = service.lookup("empty.example.test", "검색")
    assert got["known"] is False and got["explored"] is True and "7쪽을 탐색했지만" in got["hint"] and "되풀이하지 말고" in got["hint"]
    never = service.lookup("never.example.test", "검색")
    assert never["known"] is False and "explored" not in never and "탐색을 요청" in never["hint"]  # 탐색한 적 없는 사이트는 그대로


def test_lookup_exposes_coverage_warning_so_ai_does_not_assume_no_tasks(env):
    cov = {"pages_read": 3, "tasks": 0, "editable": 0, "buttons_only": 0, "unrecognized": 3, "warning": "화면은 읽었지만 업무를 하나도 인식하지 못했습니다 — 탐색이 불완전하니"}
    store.save(tm.note_exploration(tm.empty_map("cov.example.test", now=NOW), pages=3, auth="login", now=NOW, coverage=cov))
    got = service.lookup("cov.example.test", "글쓰기")
    assert got["explored"] is True and "주의: 화면은 읽었지만" in got["hint"]
    from scripts.explorer import task_mapper

    snap = {"url": "https://part.example.test/a", "title": "t", "frames": [{"url": "https://part.example.test/a", "inputs": [], "links": [], "forms": [], "buttons": [{"text": "조회", "visible": True}]}]}
    task_mapper.merge_snapshots("part.example.test", [snap, {"url": "https://part.example.test/b", "title": "", "frames": [{"url": "https://part.example.test/b", "inputs": [{"type": "hidden", "name": "x", "visible": False}], "buttons": [{"text": " ", "visible": True}], "links": [], "forms": []}]}], explored_pages=4)
    found = service.lookup("part.example.test", "조회")
    assert found["known"] is True and "1쪽에서 업무를 인식하지 못했습니다" in found["warning"]  # 업무가 있어도 불완전하면 알린다


def test_get_map_returns_explored_empty_site_but_not_unexplored(env):
    """화면(사이트 업무 지도)이 탐색은 했지만 업무가 0건인 사이트를 '지도가 없습니다'(404)로 보여주던 문제."""
    store.save(tm.note_exploration(tm.empty_map("empty2.example.test", now=NOW), pages=4, auth="public", now=NOW, coverage={"warning": "업무를 인식하지 못했습니다"}))
    got = service.get_map("empty2.example.test")
    assert got["tasks"] == [] and got["explored"]["coverage"]["warning"]
    with pytest.raises(ValueError, match="지도가 없습니다"):
        service.get_map("never2.example.test")  # 탐색한 적 없는 사이트는 그대로 404


def test_list_hosts_hides_empty_unexplored_files_but_keeps_explored_empty(env):
    store.save(tm.empty_map("blank.example.test", now=NOW))
    store.save(tm.note_exploration(tm.empty_map("seen.example.test", now=NOW), pages=2, auth="public", now=NOW))
    hosts = [h["host"] for h in service.list_hosts()]
    assert "blank.example.test" not in hosts and "seen.example.test" in hosts  # 목록과 상세(get_map)가 같은 기준


def test_lookup_exposes_menu_index_and_open_page_task_id_only_when_map_has_menu(env):
    """M8: 메뉴 색인이 있는 지도는 조회 응답에 menu·open_page_task_id 를 싣고, 키워드가 맞는 메뉴를 앞에 둔다. 없는 지도는 키를 더하지 않는다."""
    assert "menu" not in service.lookup(HOST, "업체")  # 응답 키는 메뉴가 있을 때만 추가

    saved = store.load(HOST)
    entries = [{"label": f"분류{i}", "href": f"https://{HOST}/c/{i}"} for i in range(40)] + [{"label": "추리", "href": f"https://{HOST}/c/mystery"}]
    saved = {**saved, "menu": entries}
    saved = tm.merge_tasks(saved, [tm.open_page_task(HOST, f"https://{HOST}/", now=NOW)], now=NOW)
    store.save(saved)

    got = service.lookup(HOST, "추리")
    assert got["open_page_task_id"] == "__open_page__" and got["menu_total"] == 41
    assert got["menu"][0] == {"label": "추리", "href": f"https://{HOST}/c/mystery"}  # 질문에 맞는 메뉴가 맨 앞
    assert len(got["menu"]) == service.MENU_SHOWN_MAX
    assert "menu" in got["rules"] and "지어내지" in got["rules"]


def test_lookup_exposes_data_sources_declared_tools_and_menu_truncation(env):
    """M9: 조회 응답에 데이터 소스 요약·선언 도구·메뉴 잘림 정보를 싣는다(있을 때만 키가 생긴다)."""
    plain = service.lookup(HOST, "업체")
    assert "data_sources" not in plain and "declared_tools" not in plain

    saved = store.load(HOST)
    sources = [{"host": "api.example.test", "path": f"/v1/p{i}", "query_keys": ["q"], "top_keys": ["message"], "lists": [{"path": "message.items", "count": 5, "fields": ["a"]}], "seen": 30 - i} for i in range(25)]
    saved = {**saved, "data_sources": sources, "declared_tools": [{"name": "find", "description": "d", "kind": "declarative", "fields": ["q"], "required": ["q"]}]}
    saved = {**saved, "menu": [{"label": f"분류{i}", "href": f"https://{HOST}/c/{i}"} for i in range(5)], "menu_total_seen": 12}
    saved = tm.merge_tasks(saved, [tm.open_page_task(HOST, f"https://{HOST}/", now=NOW)], now=NOW)
    store.save(saved)

    got = service.lookup(HOST, "분류")
    assert got["data_sources_total"] == 25 and len(got["data_sources"]) == 20  # 요약은 상위 20개
    assert [t["name"] for t in got["declared_tools"]] == ["find"]
    assert got["menu_total"] == 5 and got["menu_total_seen"] == 12 and got["menu_truncated"] is True  # 잘렸다는 것을 알린다
    assert "data_sources" in got["rules"] and "declared_tools" in got["rules"]


def test_lookup_of_explored_map_without_tasks_still_reports_observed_data_sources(env):
    """카페 포털처럼 화면을 자바스크립트로 그려 업무가 0개여도 데이터 소스를 관측했다면 '빈 사이트'로 오해하지 않게 알린다."""
    empty = tm.empty_map("portal.example.test", now=NOW)
    empty = tm.note_exploration(empty, pages=14, auth="public", now=NOW, coverage={"pages_read": 1, "tasks": 0})
    empty = {**empty, "data_sources": [{"host": "api.example.test", "path": "/v3/home", "query_keys": [], "top_keys": ["message"], "lists": [], "seen": 2}]}
    store.save(empty)
    got = service.lookup("portal.example.test", "카페")
    assert got["known"] is False and got["explored"] is True and got["tasks"] == []
    assert got["data_sources_total"] == 1 and "데이터 소스 1개" in got["hint"]
