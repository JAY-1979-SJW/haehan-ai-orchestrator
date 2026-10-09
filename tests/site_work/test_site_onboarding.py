"""사이트 등록(온보딩, M7-S1) — 규칙·저장소·서비스·라우터·AI 허용 범위. 브라우저·네트워크 없이 가짜 실행기로 검증한다.

기준서: docs/specs/2026-10-05_site_task_map_m7_onboarding_auto_prepare.md (F1)
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.server import mcp_server
from ai_orchestrator.site_work import site_onboarding_service as svc
from ai_orchestrator.site_work import site_registry as sr
from ai_orchestrator.site_work import site_registry_store as reg_store
from ai_orchestrator.site_work import site_task_map as tm
from ai_orchestrator.site_work import site_task_map_explore_service as explore
from ai_orchestrator.site_work import site_task_map_request_store as rstore
from ai_orchestrator.site_work import site_task_map_store as map_store
from ai_orchestrator.site_work.site_onboarding_router import site_onboarding_router
from tools.gates import auth as auth_module
from tools.gates.auth import get_current_user

NOW = "2026-10-05T09:00:00+09:00"
HOST = "work.example-site.test"
URL = f"https://{HOST}/"
TASK = {"id": "t1", "risk": "read", "state": "observed", "name": "조회"}


# ── 규칙(순수) ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "host"),
    [("Work.Example-Site.test", HOST), (f"https://{HOST}/a/b?x=1#f", HOST), (f"http://{HOST}:8080/", HOST)],
)
def test_normalize_host_accepts_names_and_urls(raw, host):
    assert sr.normalize_host(raw) == host


@pytest.mark.parametrize(
    "raw", ["", "  ", "localhost", "127.0.0.1", "10.0.0.5", "http://192.168.0.1/", "printer.local", "db.internal", "https://u:pw@x.test/"]
)
def test_normalize_host_rejects_unsafe_or_internal(raw):
    with pytest.raises(ValueError):
        sr.normalize_host(raw)


def test_policy_defaults_and_bounds():
    assert sr.validate_policy({}) == {"auto_explore": "ask", "daily_explore_max": 1, "max_pages": tm.EXPLORE_DEFAULT_PAGES}
    for bad in ({"auto_explore": "yes"}, {"daily_explore_max": 0}, {"daily_explore_max": 25}, {"max_pages": 0}, {"max_pages": "x"}):
        with pytest.raises(ValueError):
            sr.validate_policy(bad)


def test_transitions_allow_only_defined_paths():
    rec = sr.new_record(HOST, actor="kim", now=NOW)
    exploring = sr.transition(rec, sr.EXPLORING, now=NOW, by="kim")
    assert exploring["state"] == sr.EXPLORING and exploring["history"][-1]["state"] == sr.EXPLORING
    assert sr.transition(rec, sr.REGISTERED, now=NOW) is rec  # 같은 상태 — 변화 없음
    ready = sr.transition(exploring, sr.READY, now=NOW)
    with pytest.raises(ValueError):
        sr.transition(ready, sr.REGISTERED, now=NOW)  # 끝난 탐색을 되돌리지 않는다
    blocked = sr.transition(exploring, sr.BLOCKED, now=NOW)
    with pytest.raises(ValueError):
        sr.transition(blocked, sr.READY, now=NOW)  # 막힌 사이트는 사람이 다시 탐색해야 풀린다
    assert sr.transition(blocked, sr.EXPLORING, now=NOW)["state"] == sr.EXPLORING
    incomplete = sr.transition(exploring, sr.INCOMPLETE, now=NOW)
    with pytest.raises(ValueError):
        sr.transition(incomplete, sr.READY, now=NOW)  # 불완전한 탐색이 저절로 사용 가능이 되지 않는다
    assert sr.transition(incomplete, sr.EXPLORING, now=NOW)["state"] == sr.EXPLORING  # 다시 탐색은 가능
    gone = sr.transition(ready, sr.DEREGISTERED, now=NOW)
    assert sr.transition(gone, sr.REGISTERED, now=NOW)["state"] == sr.REGISTERED


def test_history_is_bounded():
    rec = sr.new_record(HOST, actor="kim", now=NOW)
    for _ in range(80):
        rec = sr.transition(sr.transition(rec, sr.EXPLORING, now=NOW), sr.REGISTERED, now=NOW)
    assert len(rec["history"]) <= 50


@pytest.mark.parametrize(
    ("result", "tasks", "login_only", "state"),
    [
        ({"aborted_reason": "bot_flagged: high"}, 5, False, sr.BLOCKED),
        ({"aborted_reason": "bot_flagged: high"}, 0, False, sr.BLOCKED),  # 차단이 업무 0건보다 먼저
        ({}, 0, False, sr.INCOMPLETE),  # 업무 0건은 "사용 가능"이 아니다(2026-10-05 cafe.naver.com 실검증)
        ({}, 2, True, sr.NEEDS_LOGIN),  # 로그인 화면만 찾음
        ({}, 4, False, sr.READY),
    ],
)
def test_state_after_exploration(result, tasks, login_only, state):
    assert sr.state_after_exploration(result, tasks=tasks, login_only=login_only)[0] == state


def test_incomplete_never_claims_ready_and_explains_next_step():
    state, note = sr.state_after_exploration({}, tasks=0)
    assert state == sr.INCOMPLETE and "다시 등록" in note and "사용 가능" not in note


def test_validate_record_rejects_garbage():
    with pytest.raises(ValueError):
        sr.validate_record({"version": 99})
    with pytest.raises(ValueError):
        sr.validate_record({**sr.new_record(HOST, actor="k", now=NOW), "state": "weird"})


# ── 저장소 ─────────────────────────────────────────────────────


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(rstore, "_DIR", tmp_path / "requests")
    monkeypatch.setattr(map_store, "_DIR", tmp_path / "maps")
    monkeypatch.setattr(reg_store, "_FILE", tmp_path / "registry" / "sites.json")
    seen: list[str] = []

    def fake(request):
        seen.append(request["host"])
        site_map = tm.empty_map(request["host"], auth="login", now=NOW)
        site_map["tasks"] = [dict(TASK)]
        map_store.save(site_map)
        return {"pages": 3, "form_pages": 1, "tasks": 1, "aborted_reason": "", "snapshot_errors": 0}

    explore.configure(fake, run_async=False)
    explore._active.clear()
    yield seen
    explore.configure(None)
    explore._active.clear()


def test_store_roundtrip_and_does_not_pollute_the_map_folder(env, tmp_path):
    rec = reg_store.put(sr.new_record(HOST, actor="kim", now=NOW))
    assert reg_store.get(HOST) == rec and [r["host"] for r in reg_store.load_all()] == [HOST]
    assert map_store.list_hosts() == []  # 등록 파일이 지도 호스트 목록에 섞이지 않는다


def test_store_refuses_a_corrupted_file_instead_of_overwriting(env, tmp_path):
    reg_store.put(sr.new_record(HOST, actor="kim", now=NOW))
    (tmp_path / "registry" / "sites.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="읽을 수 없"):
        reg_store.load_all()
    with pytest.raises(ValueError):
        reg_store.put(sr.new_record("other.example-site.test", actor="kim", now=NOW))  # 깨진 파일 위에 덮어쓰지 않는다


# ── 서비스 ─────────────────────────────────────────────────────


def test_register_explores_and_becomes_ready(env):
    out = svc.register({"host": HOST}, actor="kim")
    assert env == [HOST]  # 등록한 사람이 곧 승인자 — 최초 탐색이 실제로 실행됨
    request = explore.get_request(out["explore_request"]["id"])
    assert request["status"] == "done" and request["decided_by"] == "kim"
    got = svc.get_site(HOST)  # 상태는 읽을 때 지연 평가된다
    assert got["state"] == sr.READY and got["map"]["tasks"] == 1 and got["last_explored_at"]
    assert out["official_api"]["checked"] is True  # 공식 API 확인은 안내만


def test_register_validates_input_before_doing_anything(env):
    for raw in ({"host": "localhost"}, {"host": ""}, {"host": HOST, "start_url": "https://other.example-site.test/"}):
        with pytest.raises(ValueError):
            svc.register(raw, actor="kim")
    assert env == [] and reg_store.load_all() == []


def test_auto_policy_is_not_supported_yet(env):
    with pytest.raises(ValueError, match="아직 지원하지 않"):
        svc.register({"host": HOST, "policy": {"auto_explore": "auto"}}, actor="kim")
    svc.register({"host": HOST}, actor="kim")
    with pytest.raises(ValueError, match="아직 지원하지 않"):
        svc.set_policy(HOST, {"auto_explore": "auto"}, actor="kim")


def test_duplicate_registration_is_rejected_but_reregistration_after_deregister_keeps_history(env):
    svc.register({"host": HOST}, actor="kim")
    with pytest.raises(ValueError, match="이미 등록"):
        svc.register({"host": HOST}, actor="kim")
    gone = svc.deregister(HOST, actor="kim")
    assert gone["state"] == sr.DEREGISTERED
    again = svc.register({"host": HOST}, actor="lee")
    assert again["site"]["registered_by"] == "lee" and len(again["site"]["history"]) > 2  # 이전 이력 보존


def test_deregister_keeps_the_map(env):
    svc.register({"host": HOST}, actor="kim")
    svc.deregister(HOST, actor="kim")
    assert map_store.load(HOST)["tasks"], "등록을 해제해도 지도는 지우지 않는다"


def test_bot_flagged_result_blocks_the_site(env):
    explore.configure(lambda r: {"pages": 1, "tasks": 0, "aborted_reason": "bot_flagged: high"}, run_async=False)
    svc.register({"host": HOST}, actor="kim")
    got = svc.get_site(HOST)
    assert got["state"] == sr.BLOCKED and "사람이" in got["note"]


def test_site_with_no_tasks_is_incomplete_not_ready(env):
    def fake(request):
        map_store.save(tm.empty_map(request["host"], auth="login", now=NOW))
        return {"pages": 1, "tasks": 0, "aborted_reason": ""}

    explore.configure(fake, run_async=False)
    svc.register({"host": HOST, "auth": "login"}, actor="kim")
    got = svc.get_site(HOST)
    assert got["state"] == sr.INCOMPLETE and "업무를 찾지 못했습니다" in got["note"]


def test_login_screen_only_needs_login(env):
    def fake(request):
        site_map = tm.empty_map(request["host"], auth="login", now=NOW)
        site_map["tasks"] = [{**TASK, "id": "login#0", "category": "login", "risk": "submit"}]
        map_store.save(site_map)
        return {"pages": 1, "tasks": 1, "aborted_reason": ""}

    explore.configure(fake, run_async=False)
    svc.register({"host": HOST, "auth": "login"}, actor="kim")
    assert svc.get_site(HOST)["state"] == sr.NEEDS_LOGIN


def test_redirect_to_another_host_is_judged_by_the_explored_host(env):
    """cafe.naver.com 처럼 사이트가 다른 호스트로 넘기면 업무는 거기에 쌓인다 — 등록 호스트의 옛 지도를 보고 사용 가능이라 하지 않는다."""
    moved = "section." + HOST
    old = tm.empty_map(HOST, auth="login", now=NOW)
    old["tasks"] = [dict(TASK, state="verified")]  # 예전에 만든 지도(검증된 업무 1건)가 이미 있다
    map_store.save(old)

    def fake(request):
        map_store.save(tm.empty_map(moved, auth="login", now=NOW))  # 넘어간 호스트에는 업무가 하나도 없다
        return {"host": moved, "pages": 5, "tasks": 0, "aborted_reason": ""}

    explore.configure(fake, run_async=False)
    svc.register({"host": HOST, "auth": "login"}, actor="kim")
    got = svc.get_site(HOST)
    assert got["state"] == sr.INCOMPLETE  # 등록 호스트의 옛 업무 1건 때문에 ready 가 되면 안 된다
    assert got["explored_host"] == moved and f"{moved} 로 이동" in got["note"]
    assert got["map"]["tasks"] == 1 and got["explored"] == {"host": moved, **got["explored"]} and got["explored"]["tasks"] == 0


def test_start_url_path_is_kept_and_host_only_starts_at_root(env):
    starts: list[str] = []

    def fake(request):
        starts.append(request["start_url"])
        return {"pages": 1, "tasks": 1, "aborted_reason": ""}

    explore.configure(fake, run_async=False)
    svc.register({"host": f"https://{HOST}/0moo?x=1#f"}, actor="kim")
    svc.deregister(HOST, actor="kim")
    svc.register({"host": HOST}, actor="kim")
    assert starts == [f"https://{HOST}/0moo?x=1", f"https://{HOST}/"]  # 입력한 주소의 경로에서 시작, 호스트만이면 루트


def test_executor_failure_is_recorded_and_returns_to_registered(env):
    def boom(_request):
        raise RuntimeError("브라우저 없음")

    explore.configure(boom, run_async=False)
    svc.register({"host": HOST}, actor="kim")
    got = svc.get_site(HOST)
    assert got["state"] == sr.REGISTERED and "탐색 실패" in got["note"] and "브라우저 없음" in got["note"]


def test_busy_explorer_leaves_the_first_exploration_waiting_for_a_person(env):
    explore._active.add("someone-else")
    out = svc.register({"host": HOST}, actor="kim")
    assert out["site"]["state"] == sr.REGISTERED and "승인 대기" in out["site"]["note"]
    assert explore.get_request(out["explore_request"]["id"])["status"] == "pending" and env == []


def test_set_policy_and_unknown_host(env):
    svc.register({"host": HOST}, actor="kim")
    assert svc.set_policy(HOST, {"max_pages": 40}, actor="kim")["policy"]["max_pages"] == 40
    with pytest.raises(ValueError):
        svc.set_policy(HOST, {"max_pages": 9999}, actor="kim")
    with pytest.raises(ValueError, match="찾을 수 없"):
        svc.set_policy("nope.example-site.test", {"max_pages": 5}, actor="kim")
    with pytest.raises(ValueError, match="찾을 수 없"):
        svc.get_site("nope.example-site.test")


def test_nothing_sensitive_is_persisted(env, tmp_path):
    svc.register({"host": HOST}, actor="kim")
    text = (tmp_path / "registry" / "sites.json").read_text(encoding="utf-8").lower()
    for word in ("cookie", "token", "password", "secret"):
        assert word not in text
    assert set(json.loads(text)["sites"][HOST]) == {
        "version", "host", "state", "policy", "registered_by", "registered_at", "updated_at",
        "last_explored_at", "explored_host", "explore_request_id", "note", "history",
    }  # fmt: skip


# ── 라우터 ─────────────────────────────────────────────────────


def test_router_flow_and_auth(env, monkeypatch):
    monkeypatch.setattr(auth_module.config, "AUTH_ENABLED", True)
    app = FastAPI()
    app.include_router(site_onboarding_router)
    client = TestClient(app)
    assert client.get("/site-registry").status_code in (401, 403)
    app.dependency_overrides[get_current_user] = lambda: {"role": "viewer", "username": "v"}
    assert client.post("/site-registry", json={"host": HOST}).status_code == 403
    app.dependency_overrides[get_current_user] = lambda: {"role": "admin", "username": "kim"}
    assert client.post("/site-registry", json={"host": "localhost"}).status_code == 400
    r = client.post("/site-registry", json={"host": HOST})
    assert r.status_code == 200 and r.json()["site"]["registered_by"] == "kim"
    assert client.post("/site-registry", json={"host": HOST}).status_code == 409
    assert [i["host"] for i in client.get("/site-registry").json()["items"]] == [HOST]
    assert client.get(f"/site-registry/{HOST}").json()["state"] == "ready"
    assert client.get("/site-registry/nope.example-site.test").status_code == 404
    assert client.patch(f"/site-registry/{HOST}/policy", json={"auto_explore": "auto"}).status_code == 400
    assert client.patch(f"/site-registry/{HOST}/policy", json={"max_pages": 30}).json()["policy"]["max_pages"] == 30
    assert client.post(f"/site-registry/{HOST}/deregister").json()["state"] == "deregistered"


# ── AI 허용 범위 ────────────────────────────────────────────────


def test_ai_can_only_read_registered_sites():
    reg = mcp_server.API_REGISTRY
    assert reg["sites.list"]["method"] == "GET" and reg["sites.list"]["path"] == "/api/v1/site-registry"
    assert reg["sites.get"]["method"] == "GET" and reg["sites.get"]["path"] == "/api/v1/site-registry/{host}"
    assert sorted(k for k in reg if k.startswith("sites.")) == ["sites.get", "sites.list", "sites.preflight"]  # 2026-10-05 사용자 승인: 저장된 사전 조사 결과 조회(GET) 추가
    assert not any("site-registry" in v["path"] and v["method"] != "GET" for v in reg.values())  # 등록·정책·해제는 사람만
