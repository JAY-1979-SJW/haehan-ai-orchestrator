"""사이트 지도 이력(M11) — 구조 지문·map_rev·diff·이력 저장소·버전 고정·라우터. 임시 폴더만 사용(실제 지도·외부 접속 없음).

기준서: docs/specs/2026-10-05_new_site_onboarding_pipeline.md
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.server import mcp_server
from ai_orchestrator.site_work import site_map_history as hist
from ai_orchestrator.site_work import site_map_history_store as history_store
from ai_orchestrator.site_work import site_task_map as tm
from ai_orchestrator.site_work import site_task_map_service as service
from ai_orchestrator.site_work import site_task_map_store as store
from ai_orchestrator.site_work.site_task_map_router import site_task_map_router
from tools.gates import auth as auth_module
from tools.gates.auth import get_current_user

HOST = "history.example-test.kr"
NOW = "2026-10-05T12:00:00+09:00"


def _task(task_id: str, fingerprint: str = "fp1", risk: str = "read", state: str = "observed") -> dict[str, Any]:
    return {"id": task_id, "name": f"업무 {task_id}", "category": "search", "purpose": "", "risk": risk, "auth": "public", "state": state, "url": f"https://{HOST}/", "host": HOST,
            "fields": [], "control": "", "outputs": [], "steps": [], "fingerprint": fingerprint, "observed_at": NOW, "verified_at": "", "failures": 0, "changes": []}  # fmt: skip


def _map(tasks: list[dict[str, Any]], menu: list[str] | None = None) -> dict[str, Any]:
    site_map = tm.empty_map(HOST, now=NOW)
    site_map["tasks"] = tasks
    site_map["menu"] = [{"label": m, "href": f"https://{HOST}{m}"} for m in (menu or [])]
    return site_map


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "site_task_map")
    return tmp_path / "site_task_map"


# ── 순수 규칙 ────────────────────────────────────────────────────


def test_fingerprint_ignores_state_and_times_but_sees_structure():
    a = hist.structure(_map([_task("t1")], ["/a"]))
    b = hist.structure(_map([_task("t1", state="verified")], ["/a"]))  # 검증 상태만 다르다
    assert hist.fingerprint(a) == hist.fingerprint(b)
    assert hist.fingerprint(a) != hist.fingerprint(hist.structure(_map([_task("t1", fingerprint="fp2")], ["/a"])))
    assert hist.fingerprint(a) != hist.fingerprint(hist.structure(_map([_task("t1")], ["/a", "/b"])))


def test_next_rev_first_same_and_changed():
    assert hist.next_rev(0, "", "x") == (1, True)
    assert hist.next_rev(3, "x", "x") == (3, False)
    assert hist.next_rev(3, "x", "y") == (4, True)


def test_diff_reports_added_removed_changed_and_stale_candidates():
    old = hist.structure(_map([_task("keep"), _task("gone"), _task("edit", "fp1")], ["/a", "/b"]))
    new = hist.structure(_map([_task("keep"), _task("edit", "fp2"), _task("new")], ["/a", "/c"]))
    got = hist.diff(old, new)
    assert (
        not got["same"]
        and got["tasks_added"] == ["new"]
        and got["tasks_removed"] == ["gone"]
        and got["tasks_changed"] == ["edit"]
    )
    assert got["menu_added"] == [f"https://{HOST}/c"] and got["menu_removed"] == [f"https://{HOST}/b"]
    assert sorted(got["stale_candidates"]) == ["edit", "gone"]
    assert hist.diff(old, old)["same"]


def test_risk_change_counts_as_changed_task():
    old = hist.structure(_map([_task("t1", risk="read")]))
    new = hist.structure(_map([_task("t1", risk="submit")]))
    assert hist.diff(old, new)["tasks_changed"] == ["t1"]


def test_pin_check_matrix():
    assert hist.pin_check(None, 3, "fp") is None  # 지정 없음
    assert hist.pin_check(3, 3, "fp") is None  # 같은 버전
    changed = hist.pin_check(2, 3, "fpNew", "fpOld")
    assert changed is not None and changed["state"] == "map_changed" and changed["ok"] is False
    assert hist.pin_check(2, 3, "fpSame", "fpSame") is None  # 번호만 달라도 구조가 같으면 통과


# ── 저장소 ──────────────────────────────────────────────────────


def test_history_store_roundtrip_retention_and_host_guard(tmp_path):
    for rev in range(1, hist.RETENTION + 6):
        history_store.save(tmp_path, HOST, rev, {"tasks": {}, "menu": [], "sources": []}, at=NOW, fingerprint=f"f{rev}")
    revs = history_store.list_revs(tmp_path, HOST)
    assert (
        len(revs) == hist.RETENTION and revs[0]["map_rev"] == hist.RETENTION + 5 and revs[-1]["map_rev"] == 6
    )  # 최신 20개만 남는다
    assert history_store.load(tmp_path, HOST, 10)["fingerprint"] == "f10"
    with pytest.raises(ValueError, match="찾을 수 없"):
        history_store.load(tmp_path, HOST, 1)  # 오래돼 지워진 버전
    with pytest.raises(ValueError):
        history_store.save(tmp_path, "../evil", 1, {}, at=NOW, fingerprint="x")


def test_history_store_rejects_corrupt_file(tmp_path):
    folder = tmp_path / "_history" / HOST
    folder.mkdir(parents=True)
    (folder / "1.json").write_text("{깨짐", encoding="utf-8")
    with pytest.raises(ValueError, match="읽을 수 없"):
        history_store.load(tmp_path, HOST, 1)


# ── 지도 저장 시 버전 부여 ───────────────────────────────────────


def test_save_stamps_rev_and_only_bumps_on_structure_change(env):
    site_map = _map([_task("t1")], ["/a"])
    store.save(site_map)
    assert site_map["map_rev"] == 1 and site_map["map_fingerprint"]
    first_fp = site_map["map_fingerprint"]

    verified = _map([_task("t1", state="verified")], ["/a"])  # 검증 상태만 바뀐 저장
    store.save(verified)
    assert verified["map_rev"] == 1 and verified["map_fingerprint"] == first_fp

    grown = _map([_task("t1"), _task("t2")], ["/a"])
    store.save(grown)
    assert grown["map_rev"] == 2 and store.load(HOST)["map_rev"] == 2
    assert [r["map_rev"] for r in store.history_list(HOST)] == [2, 1]


def test_old_map_without_rev_starts_at_one(env):
    old = _map([_task("t1")])
    env.mkdir(parents=True)
    (env / f"{HOST}.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")  # map_rev 가 없던 옛 지도
    again = store.load(HOST)
    store.save(again)
    assert again["map_rev"] == 1


def test_history_folder_does_not_count_as_host(env):
    store.save(_map([_task("t1")]))
    assert store.list_hosts() == [HOST]  # `_history` 폴더는 호스트가 아니다


def test_history_holds_structure_only_no_values(env):
    site_map = _map([_task("t1")])
    site_map["tasks"][0]["purpose"] = "비밀 메모 abc123"
    store.save(site_map)
    text = (env / "_history" / HOST / "1.json").read_text(encoding="utf-8")
    assert "비밀 메모" not in text and "abc123" not in text


# ── 서비스 ──────────────────────────────────────────────────────


def test_service_lookup_history_and_diff(env):
    store.save(_map([_task("t1")], ["/a"]))
    store.save(_map([_task("t1"), _task("t2")], ["/a"]))
    found = service.lookup(HOST)
    assert found["map_rev"] == 2 and found["map_fingerprint"]
    shown = service.history(HOST)
    assert shown["map_rev"] == 2 and [r["map_rev"] for r in shown["revisions"]] == [2, 1]
    got = service.diff(HOST, 1)
    assert got["from"] == 1 and got["to"] == 2 and got["tasks_added"] == ["t2"]
    assert service.diff(HOST, 1, 2)["tasks_added"] == ["t2"]
    with pytest.raises(ValueError, match="찾을 수 없"):
        service.diff(HOST, 9)


def test_service_run_pins_map_rev_before_touching_the_browser(env):
    store.save(_map([_task("t1")]))
    store.save(_map([_task("t1"), _task("t2")]))  # 구조가 바뀌어 rev 2
    calls: list[tuple[Any, ...]] = []
    service.configure_runner(lambda host, task_id, values: calls.append((host, task_id)) or {"ok": True})
    try:
        stale = service.run_task(HOST, "t1", {}, map_rev=1)
        assert stale["state"] == "map_changed" and stale["current_rev"] == 2 and calls == []
        assert service.run_task(HOST, "t1", {}, map_rev=2) == {"ok": True}
        assert service.run_task(HOST, "t1", {}) == {"ok": True}  # 지정이 없으면 현재 지도(이전 동작)
    finally:
        service.configure_runner(None)


# ── 라우터·AI 허용 범위 ──────────────────────────────────────────


def _client(role: str | None) -> TestClient:
    app = FastAPI()
    app.include_router(site_task_map_router)
    if role:
        app.dependency_overrides[get_current_user] = lambda: {"role": role, "username": "kim"}
    return TestClient(app)


def test_routes_require_role_and_return_history_and_diff(env, monkeypatch):
    monkeypatch.setattr(auth_module.config, "AUTH_ENABLED", True)
    store.save(_map([_task("t1")]))
    store.save(_map([_task("t1"), _task("t2")]))
    assert _client(None).get(f"/site-map/{HOST}/history").status_code in (401, 403)
    assert _client("viewer").get(f"/site-map/{HOST}/history").status_code == 403
    admin = _client("admin")
    assert admin.get(f"/site-map/{HOST}/history").json()["map_rev"] == 2
    assert admin.get(f"/site-map/{HOST}/diff", params={"from": 1}).json()["tasks_added"] == ["t2"]
    assert admin.get(f"/site-map/{HOST}/diff", params={"from": 9}).status_code == 404
    assert admin.get(f"/site-map/{HOST}/diff").status_code == 422  # from 은 필수


def test_run_route_accepts_map_rev_and_returns_map_changed(env, monkeypatch):
    monkeypatch.setattr(auth_module.config, "AUTH_ENABLED", True)
    store.save(_map([_task("t1")]))
    store.save(_map([_task("t1"), _task("t2")]))
    service.configure_runner(lambda host, task_id, values: {"ok": True})
    try:
        got = _client("admin").post(f"/site-map/{HOST}/run", json={"task_id": "t1", "params": {}, "map_rev": 1})
        assert got.status_code == 200 and got.json()["state"] == "map_changed"
    finally:
        service.configure_runner(None)


def test_history_is_not_exposed_to_ai_registry():
    assert not any(
        key.startswith("sitemap.") and ("history" in key or "diff" in key) for key in mcp_server.API_REGISTRY
    )
    assert not any(
        "/site-map/" in str(v.get("path")) and ("history" in str(v.get("path")) or "diff" in str(v.get("path")))
        for v in mcp_server.API_REGISTRY.values()
    )
