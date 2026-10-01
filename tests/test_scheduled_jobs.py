"""사용자 예약 작업 — 반복 계산·생성 검증·선점·실행·놓침·허용 목록·라우터. 브라우저·네트워크를 쓰지 않는다."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.gates.auth import get_current_user
from ai_orchestrator.persistence import scheduled_job_store as store
from ai_orchestrator.routers.scheduled_job_router import scheduled_job_router
from ai_orchestrator.services import scheduled_job_service as svc
from ai_orchestrator.workflows import scheduled_job_actions as actions

NOW = datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC)


class Recorder:
    def __init__(self):
        self.runs: list[str] = []
        self.cdp_calls = 0


def fake_spec(rec: Recorder, key: str, *, browser=False, risk="extract_text", fail=False):
    def run(params):
        rec.runs.append(key)
        if fail:
            raise RuntimeError("작업 실패 시험")
        return f"{key} 완료"

    return actions.ActionSpec(key, key, "", risk, browser, lambda p: dict(p), run)


@pytest.fixture
def db(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "jobs.db")


@pytest.fixture
def env(db, monkeypatch):
    rec = Recorder()
    for key, kw in {
        "fake": {},
        "fake_browser": {"browser": True},
        "fake_fail": {"fail": True},
        "fake_publish": {"risk": "blog_publish"},
        "fake_sign": {"risk": "e_sign"},
    }.items():
        monkeypatch.setitem(actions.ACTIONS, key, fake_spec(rec, key, **kw))

    def fake_cdp():
        rec.cdp_calls += 1

    monkeypatch.setattr(actions, "ensure_cdp", fake_cdp)
    return rec


def make(action="fake", recurrence=None, **kw):
    return svc.create(
        name=kw.pop("name", "시험"),
        action=action,
        params=kw.pop("params", {}),
        recurrence=recurrence or {"kind": "interval", "minutes": 5},
        created_by="tester",
        now=kw.pop("now", NOW),
    )


def due(job, at):
    store.update_job(job["id"], next_run_at=store.iso(at))


# ── 반복 계산 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rec",
    [
        {"kind": "cron"},
        {"kind": "daily", "time": "25:00"},
        {"kind": "daily", "time": "9:00"},
        {"kind": "weekly", "days": [], "time": "09:00"},
        {"kind": "weekly", "days": [7], "time": "09:00"},
        {"kind": "interval", "minutes": 4},
        {"kind": "interval", "minutes": "10"},
        {"kind": "interval", "minutes": True},
        {"kind": "once", "at": "내일"},
        "daily",
    ],
)
def test_invalid_recurrence_is_rejected(rec):
    with pytest.raises(ValueError):
        svc.validate_recurrence(rec)


def test_interval_next_run_is_after_plus_minutes():
    assert svc.next_run({"kind": "interval", "minutes": 30}, NOW) == NOW + timedelta(minutes=30)


def test_once_is_in_the_future_or_none():
    at = NOW + timedelta(hours=1)
    rec = svc.validate_recurrence({"kind": "once", "at": at.isoformat()})
    assert svc.next_run(rec, NOW) == at
    assert svc.next_run(rec, at) is None


def test_daily_next_run_is_the_next_local_occurrence():
    result = svc.next_run({"kind": "daily", "time": "09:00"}, NOW)
    assert NOW < result <= NOW + timedelta(hours=25)
    assert result.astimezone().strftime("%H:%M") == "09:00"


def test_weekly_next_run_lands_on_a_selected_weekday():
    result = svc.next_run({"kind": "weekly", "days": [0, 3], "time": "07:30"}, NOW)
    assert result > NOW and result.astimezone().weekday() in (0, 3)
    assert result.astimezone().strftime("%H:%M") == "07:30"


# ── 생성·수정 검증 ───────────────────────────────────────────────────────


def test_create_stores_normalized_job_and_first_run(env):
    job = make(recurrence={"kind": "interval", "minutes": 15})
    assert job["status"] == "active" and job["next_run_at"] == store.iso(NOW + timedelta(minutes=15))
    assert job["created_by"] == "tester" and job["params"] == {}


@pytest.mark.parametrize("action", ["nope", "fake_publish", "fake_sign"])
def test_actions_outside_the_allowlist_or_needing_approval_are_rejected(env, action):
    with pytest.raises(ValueError):
        make(action=action)


@pytest.mark.parametrize("name", ["", "   ", "가" * 81])
def test_bad_name_is_rejected(env, name):
    with pytest.raises(ValueError):
        make(name=name)


def test_once_in_the_past_is_rejected(env):
    with pytest.raises(ValueError):
        make(recurrence={"kind": "once", "at": (NOW - timedelta(hours=1)).isoformat()})


def test_real_catalog_actions_are_all_auto_allowed_and_validate_params():
    from ai_orchestrator.local_agent.action_risk_policy import GRADE_AUTO_ALLOWED, classify_action

    for spec in actions.ACTIONS.values():
        assert classify_action(spec.risk_action) == GRADE_AUTO_ALLOWED
    with pytest.raises(ValueError):
        actions.ACTIONS["naver_login_check"].validate({"target": "bigsun2024"})  # 등록되지 않은 계정
    with pytest.raises(ValueError):
        actions.ACTIONS["gonobi_collect"].validate({"x": 1})
    assert actions.ACTIONS["naver_login_check"].validate({}) == {"target": "skyjwsin"}


def test_update_recomputes_next_run_and_pause_resume(env):
    job = make()
    updated = svc.update(job["id"], name="새 이름", params={}, recurrence={"kind": "interval", "minutes": 60}, now=NOW)
    assert updated["name"] == "새 이름" and updated["next_run_at"] == store.iso(NOW + timedelta(minutes=60))
    paused = svc.pause(job["id"])
    assert paused["status"] == "paused" and paused["next_run_at"] is None
    resumed = svc.resume(job["id"], now=NOW + timedelta(days=1))
    assert resumed["status"] == "active" and resumed["next_run_at"] == store.iso(NOW + timedelta(days=1, minutes=60))


def test_unknown_job_raises_keyerror(env):
    for call in (svc.pause, svc.resume, svc.run_now):
        with pytest.raises(KeyError):
            call("없는id")


# ── 선점·실행 ────────────────────────────────────────────────────────────


def test_due_job_runs_once_and_next_time_is_advanced(env):
    job = make()
    due(job, NOW - timedelta(minutes=1))
    first = svc.tick(NOW)
    assert [r["status"] for r in first] == ["ok"] and env.runs == ["fake"]
    assert svc.tick(NOW) == []  # 같은 시각에 다시 집히지 않는다
    after = store.get_job(job["id"])
    assert after["next_run_at"] == store.iso(NOW + timedelta(minutes=5))
    assert after["last_status"] == "ok" and after["last_message"] == "fake 완료"


def test_claim_is_atomic_across_callers(env):
    job = make()
    due(job, NOW - timedelta(minutes=1))
    a = store.claim_due(store.iso(NOW), lambda j, n: store.iso(NOW + timedelta(minutes=5)))
    b = store.claim_due(store.iso(NOW), lambda j, n: store.iso(NOW + timedelta(minutes=5)))
    assert len(a) == 1 and b == []


def test_once_job_becomes_done_after_its_run(env):
    at = NOW + timedelta(hours=1)
    job = make(recurrence={"kind": "once", "at": at.isoformat()})
    svc.tick(at + timedelta(minutes=1))
    done = store.get_job(job["id"])
    assert done["status"] == "done" and done["next_run_at"] is None and env.runs == ["fake"]


def test_late_run_beyond_grace_is_recorded_as_missed_not_executed(env):
    job = make()
    due(job, NOW - timedelta(minutes=30))
    result = svc.tick(NOW)
    assert [r["status"] for r in result] == ["missed"] and env.runs == []
    assert store.get_job(job["id"])["last_status"] == "missed"
    assert store.get_job(job["id"])["next_run_at"] == store.iso(NOW + timedelta(minutes=5))


def test_failure_is_recorded_and_other_jobs_still_run(env):
    bad, good = make(action="fake_fail"), make(action="fake")
    due(bad, NOW - timedelta(minutes=2))
    due(good, NOW - timedelta(minutes=1))
    result = svc.tick(NOW)
    assert [r["status"] for r in result] == ["failed", "ok"]
    assert "작업 실패 시험" in store.get_job(bad["id"])["last_message"] and env.runs == ["fake_fail", "fake"]


def test_paused_job_does_not_run(env):
    job = make()
    svc.pause(job["id"])
    assert svc.tick(NOW + timedelta(days=1)) == [] and env.runs == []


def test_cdp_is_ensured_only_for_browser_actions(env):
    plain, browser = make(action="fake"), make(action="fake_browser")
    due(plain, NOW - timedelta(minutes=1))
    svc.tick(NOW)
    assert env.cdp_calls == 0
    due(browser, NOW - timedelta(minutes=1))
    svc.tick(NOW)
    assert env.cdp_calls == 1


def test_action_that_needs_approval_is_skipped_at_run_time(env, monkeypatch):
    """생성 뒤 허용 목록의 위험 등급이 올라간 상황 — 실행 시점에도 다시 판정해 실행하지 않는다."""
    job = make()
    monkeypatch.setitem(actions.ACTIONS, "fake", fake_spec(env, "fake", risk="blog_publish"))
    due(job, NOW - timedelta(minutes=1))
    result = svc.tick(NOW)
    assert [r["status"] for r in result] == ["skipped"] and env.runs == []


def test_run_now_records_a_run_without_touching_the_schedule(env):
    job = make()
    before = store.get_job(job["id"])["next_run_at"]
    result = svc.run_now(job["id"])
    assert result["status"] == "ok" and env.runs == ["fake"]
    assert store.get_job(job["id"])["next_run_at"] == before
    assert [r["status"] for r in store.list_runs(job["id"])] == ["ok"]


def test_stale_running_runs_are_marked_failed_on_recovery(env):
    job = make()
    store.create_run(job["id"], scheduled_for=store.iso(NOW), started_at=store.iso(NOW))
    assert svc.recover() == 1
    assert store.list_runs(job["id"])[0]["status"] == "failed"


def test_delete_removes_job_and_runs(env):
    job = make()
    svc.run_now(job["id"])
    assert store.delete_job(job["id"]) and store.get_job(job["id"]) is None and store.list_runs(job["id"]) == []


# ── 라우터 ──────────────────────────────────────────────────────────────


@pytest.fixture
def api(env):
    role = {"role": "owner"}
    app = FastAPI()
    app.include_router(scheduled_job_router)
    app.dependency_overrides[get_current_user] = lambda: {"actor": "tester", "role": role["role"]}
    return TestClient(app), role


def _body(**over):
    return {"name": "시험", "action": "fake", "params": {}, "recurrence": {"kind": "interval", "minutes": 10}, **over}


def test_router_requires_admin_or_owner(api):
    client, role = api
    role["role"] = "viewer"
    assert client.get("/scheduled-jobs").status_code == 403
    assert client.post("/scheduled-jobs", json=_body()).status_code == 403


def test_router_crud_flow(api):
    client, _ = api
    created = client.post("/scheduled-jobs", json=_body()).json()
    job_id = created["id"]
    assert created["created_by"] == "tester"
    listed = client.get("/scheduled-jobs").json()["jobs"]
    assert [j["id"] for j in listed] == [job_id] and listed[0]["action_label"] == "fake"
    upd = client.post(
        f"/scheduled-jobs/{job_id}/update",
        json={"name": "바뀜", "params": {}, "recurrence": {"kind": "interval", "minutes": 20}},
    )
    assert upd.status_code == 200 and upd.json()["name"] == "바뀜"
    assert client.post(f"/scheduled-jobs/{job_id}/pause").json()["status"] == "paused"
    assert client.post(f"/scheduled-jobs/{job_id}/resume").json()["status"] == "active"
    assert client.post(f"/scheduled-jobs/{job_id}/run-now").json()["status"] == "ok"
    assert len(client.get(f"/scheduled-jobs/{job_id}/runs").json()["runs"]) == 1
    assert client.delete(f"/scheduled-jobs/{job_id}").json() == {"ok": True}
    assert client.delete(f"/scheduled-jobs/{job_id}").status_code == 404


@pytest.mark.parametrize(
    "over",
    [
        {"action": "fake_publish"},
        {"action": "없는작업"},
        {"recurrence": {"kind": "interval", "minutes": 1}},
        {"name": ""},
    ],
)
def test_router_rejects_bad_requests_with_400(api, over):
    client, _ = api
    assert client.post("/scheduled-jobs", json=_body(**over)).status_code == 400


def test_router_unknown_ids_are_404(api):
    client, _ = api
    for method, path in [
        ("post", "/scheduled-jobs/없음/pause"),
        ("post", "/scheduled-jobs/없음/resume"),
        ("post", "/scheduled-jobs/없음/run-now"),
        ("get", "/scheduled-jobs/없음/runs"),
    ]:
        assert getattr(client, method)(path).status_code == 404


def test_router_catalog_lists_real_actions_with_fields(db):
    app = FastAPI()
    app.include_router(scheduled_job_router)
    app.dependency_overrides[get_current_user] = lambda: {"actor": "tester", "role": "owner"}
    items = {a["key"]: a for a in TestClient(app).get("/scheduled-jobs/actions").json()["actions"]}
    assert {"community_analysis", "naver_login_check", "gonobi_collect"} <= set(items)
    assert items["naver_login_check"]["fields"][0]["name"] == "target"
    assert "skyjwsin" in items["naver_login_check"]["fields"][0]["options"]
