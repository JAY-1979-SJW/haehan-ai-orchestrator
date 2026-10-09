"""사용자 예약 작업 — 반복 계산·생성 검증·선점·실행·놓침·허용 목록·라우터. 브라우저·네트워크를 쓰지 않는다."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.scheduler import scheduled_job_service as svc
from ai_orchestrator.scheduler import scheduled_job_store as store
from ai_orchestrator.scheduler.scheduled_job_router import scheduled_job_router
from ai_orchestrator.services import scheduled_job_actions as actions
from tools.gates.auth import get_current_user

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


@pytest.mark.parametrize("action", ["nope", "fake_sign"])
def test_actions_outside_the_allowlist_or_user_direct_are_rejected(env, action):
    with pytest.raises(ValueError):
        make(action=action)


def test_delegated_actions_can_be_scheduled_but_need_approval(env):
    assert make(action="fake_publish")["status"] == "active"


@pytest.mark.parametrize("name", ["", "   ", "가" * 81])
def test_bad_name_is_rejected(env, name):
    with pytest.raises(ValueError):
        make(name=name)


def test_once_in_the_past_is_rejected(env):
    with pytest.raises(ValueError):
        make(recurrence={"kind": "once", "at": (NOW - timedelta(hours=1)).isoformat()})


def test_real_catalog_grades_and_param_validation():
    from ai_orchestrator.contracts.action_risk_policy import (
        GRADE_AUTO_ALLOWED,
        GRADE_USER_DELEGATED,
        classify_action,
    )

    for key, spec in actions.ACTIONS.items():
        if key.startswith("fake"):
            continue
        expected = GRADE_USER_DELEGATED if key in ("telegram_notify", "blog_publish", "naver_mail_enable", "naver_mail_send") else GRADE_AUTO_ALLOWED
        assert classify_action(spec.risk_action) == expected, key
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


def test_action_that_became_user_direct_is_skipped_at_run_time(env, monkeypatch):
    """생성 뒤 허용 목록의 위험 등급이 '직접 해야 함'으로 올라간 상황 — 실행 시점에도 다시 판정해 실행하지 않는다."""
    job = make()
    monkeypatch.setitem(actions.ACTIONS, "fake", fake_spec(env, "fake", risk="e_sign"))
    due(job, NOW - timedelta(minutes=1))
    result = svc.tick(NOW)
    assert [r["status"] for r in result] == ["skipped"] and env.runs == []


# ── 승인 흐름 (발행·전송 등 USER_DELEGATED) ─────────────────────────────────


def awaiting_run(env):
    """승인이 필요한 작업이 실행 시각이 되어 '승인 대기' 회차가 만들어진 상태."""
    job = make(action="fake_publish")
    due(job, NOW - timedelta(minutes=1))
    (run,) = svc.tick(NOW)
    return job, run


def test_delegated_job_waits_for_approval_and_is_not_executed(env):
    job, run = awaiting_run(env)
    assert run["status"] == "awaiting_approval" and env.runs == []
    after = store.get_job(job["id"])
    assert after["last_status"] == "awaiting_approval" and after["next_run_at"] == store.iso(NOW + timedelta(minutes=5))
    assert store.get_run(run["id"])["status"] == "awaiting_approval"


def test_approve_executes_exactly_once_and_records_who(env):
    job, run = awaiting_run(env)
    result = svc.approve(run["id"], "kim", now=NOW + timedelta(minutes=1))
    assert result["status"] == "ok" and env.runs == ["fake_publish"]
    saved = store.get_run(run["id"])
    assert saved["status"] == "ok" and saved["decided_by"] == "kim"
    assert store.get_job(job["id"])["last_status"] == "ok"
    with pytest.raises(ValueError):
        svc.approve(run["id"], "lee", now=NOW + timedelta(minutes=2))  # 두 번째 승인은 거부
    assert env.runs == ["fake_publish"]


def test_reject_never_executes_and_blocks_later_approval(env):
    job, run = awaiting_run(env)
    assert svc.reject(run["id"], "kim")["status"] == "rejected"
    assert store.get_job(job["id"])["last_status"] == "rejected" and env.runs == []
    with pytest.raises(ValueError):
        svc.approve(run["id"], "kim", now=NOW + timedelta(minutes=1))
    with pytest.raises(ValueError):
        svc.reject(run["id"], "kim")


def test_unapproved_run_expires_after_the_ttl_and_cannot_be_approved(env):
    job, run = awaiting_run(env)
    assert svc.pending_approvals(NOW + svc.APPROVAL_TTL + timedelta(minutes=1)) == []  # 조회만 해도 만료 처리된다
    assert store.get_run(run["id"])["status"] == "expired" and store.get_job(job["id"])["last_status"] == "expired"
    with pytest.raises(ValueError):
        svc.approve(run["id"], "kim", now=NOW + svc.APPROVAL_TTL + timedelta(minutes=2))
    assert env.runs == []


def test_approving_after_the_ttl_marks_it_expired_without_running(env):
    _, run = awaiting_run(env)
    with pytest.raises(ValueError):
        svc.approve(run["id"], "kim", now=NOW + svc.APPROVAL_TTL + timedelta(seconds=1))
    assert store.get_run(run["id"])["status"] == "expired" and env.runs == []


def test_editing_the_job_cancels_pending_approval_so_what_was_shown_is_what_runs(env):
    job, run = awaiting_run(env)
    svc.update(job["id"], name="바뀜", params={}, recurrence={"kind": "interval", "minutes": 30}, now=NOW)
    assert store.get_run(run["id"])["status"] == "cancelled"
    with pytest.raises(ValueError):
        svc.approve(run["id"], "kim", now=NOW + timedelta(minutes=1))
    assert env.runs == []


def test_run_now_on_a_delegated_job_only_creates_a_pending_approval(env):
    job = make(action="fake_publish")
    run = svc.run_now(job["id"])
    assert run["status"] == "awaiting_approval" and env.runs == []
    assert [a["run_id"] for a in svc.pending_approvals()] == [run["id"]]


def test_pending_approvals_show_what_will_run_and_when_it_expires(env):
    job = make(action="fake_publish", params={"x": 1}, name="공지")
    due(job, NOW - timedelta(minutes=1))
    svc.tick(NOW)
    (item,) = svc.pending_approvals(NOW + timedelta(minutes=1))
    assert item["job_name"] == "공지" and item["action"] == "fake_publish" and item["params"] == {"x": 1}
    assert item["expires_at"] == store.iso(NOW + svc.APPROVAL_TTL)


def test_delegated_run_that_is_too_late_is_missed_not_pending(env):
    job = make(action="fake_publish")
    due(job, NOW - timedelta(minutes=30))
    assert [r["status"] for r in svc.tick(NOW)] == ["missed"] and svc.pending_approvals(NOW) == []


def test_delegated_action_is_never_executed_without_approval_even_if_called_directly(env):
    job = make(action="fake_publish")
    run = store.create_run(job["id"], scheduled_for=store.iso(NOW), started_at=store.iso(NOW))
    assert svc._execute(job, run)["status"] == "skipped" and env.runs == []


def test_database_created_before_the_approval_feature_is_migrated(db):
    import sqlite3

    store._DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(store._DB_PATH))
    con.execute(
        "CREATE TABLE runs (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, scheduled_for TEXT NOT NULL,"
        " started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, message TEXT NOT NULL DEFAULT '')"
    )
    con.commit()
    con.close()
    assert store.list_runs("아무거나") == []  # 연결을 열면서 decided_by 열이 추가된다
    with store._conn() as c:
        assert "decided_by" in {r["name"] for r in c.execute("PRAGMA table_info(runs)")}


# ── 텔레그램 알림 작업 ──────────────────────────────────────────────────────


def test_telegram_params_are_validated():
    validate = actions.ACTIONS["telegram_notify"].validate
    assert validate({"text": "  안녕  "}) == {"text": "안녕"}
    for bad in ({}, {"text": "  "}, {"text": "가" * 1001}, {"text": "a", "chat_id": "1"}):
        with pytest.raises(ValueError):
            validate(bad)


def test_telegram_success_escapes_html_and_sends_the_text(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "ai_orchestrator.core.telegram_sender.send_message", lambda text, **kw: sent.append(text) or {"ok": True}
    )
    assert "보냈습니다" in actions.ACTIONS["telegram_notify"].run({"text": "<b>안녕</b> & 확인"})
    assert sent == ["&lt;b&gt;안녕&lt;/b&gt; &amp; 확인"]


def test_telegram_missing_config_fails_loudly_not_silently(monkeypatch):
    monkeypatch.setattr(
        "ai_orchestrator.core.telegram_sender.send_message", lambda text, **kw: {"ok": False, "skipped": True}
    )
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        actions.ACTIONS["telegram_notify"].run({"text": "x"})


def test_telegram_error_text_is_never_copied_into_the_run_record(monkeypatch):
    leaked_url = "https://api.telegram.org/bot123:SECRET-TOKEN/sendMessage"
    monkeypatch.setattr(
        "ai_orchestrator.core.telegram_sender.send_message",
        lambda text, **kw: {"ok": False, "error": f"Client error 401 for url '{leaked_url}'"},
    )
    with pytest.raises(RuntimeError) as err:
        actions.ACTIONS["telegram_notify"].run({"text": "x"})
    assert "SECRET-TOKEN" not in str(err.value) and "api.telegram.org" not in str(err.value)


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
        {"action": "fake_sign"},
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


# ── 승인 API ────────────────────────────────────────────────────────────


def _pending_run_id(client):
    job = client.post("/scheduled-jobs", json=_body(action="fake_publish")).json()
    run = client.post(f"/scheduled-jobs/{job['id']}/run-now").json()
    assert run["status"] == "awaiting_approval"
    return job, run["id"]


def test_approval_api_lists_approves_once_and_records_the_approver(api, env):
    client, _ = api
    _, run_id = _pending_run_id(client)
    (item,) = client.get("/scheduled-jobs/approvals").json()["approvals"]
    assert item["run_id"] == run_id and item["action"] == "fake_publish"
    done = client.post(f"/scheduled-jobs/runs/{run_id}/approve")
    assert done.status_code == 200 and done.json()["status"] == "ok" and env.runs == ["fake_publish"]
    assert done.json()["decided_by"] == "tester"
    assert client.post(f"/scheduled-jobs/runs/{run_id}/approve").status_code == 409  # 두 번째는 거부
    assert client.get("/scheduled-jobs/approvals").json()["approvals"] == []
    assert env.runs == ["fake_publish"]


def test_reject_api_never_runs_and_unknown_runs_are_404(api, env):
    client, _ = api
    _, run_id = _pending_run_id(client)
    assert client.post(f"/scheduled-jobs/runs/{run_id}/reject").json()["status"] == "rejected"
    assert client.post(f"/scheduled-jobs/runs/{run_id}/approve").status_code == 409 and env.runs == []
    assert client.post("/scheduled-jobs/runs/없음/approve").status_code == 404
    assert client.post("/scheduled-jobs/runs/없음/reject").status_code == 404


def test_approval_api_requires_admin_or_owner(api):
    client, role = api
    _, run_id = _pending_run_id(client)
    role["role"] = "viewer"
    assert client.get("/scheduled-jobs/approvals").status_code == 403
    assert client.post(f"/scheduled-jobs/runs/{run_id}/approve").status_code == 403
    assert client.post(f"/scheduled-jobs/runs/{run_id}/reject").status_code == 403


# ── 블로그 발행 작업 ────────────────────────────────────────────────────


GOOD_POST = {"target": "skyjwsin", "title": "제목", "body": "본문", "tags": " 조명, 인테리어 ,,", "visibility": "private"}


def test_blog_publish_params_are_normalized_and_validated():
    validate = actions.ACTIONS["blog_publish"].validate
    assert validate(GOOD_POST) == {**GOOD_POST, "tags": "조명, 인테리어"}
    assert validate({"title": "t", "body": "b"})["visibility"] == "public"  # 기본값
    too_many = ",".join(f"t{i}" for i in range(31))
    for bad in (
        {**GOOD_POST, "title": ""},
        {**GOOD_POST, "title": "가" * 101},
        {**GOOD_POST, "body": "  "},
        {**GOOD_POST, "body": "가" * 20001},
        {**GOOD_POST, "tags": too_many},
        {**GOOD_POST, "tags": "가" * 41},
        {**GOOD_POST, "visibility": "everyone"},
        {**GOOD_POST, "target": "bigsun2024"},
        {**GOOD_POST, "password": "x"},
    ):
        with pytest.raises(ValueError):
            validate(bad)


class FakeBlog:
    def __init__(self, monkeypatch, alias="skyjwsin", result=None):
        self.calls: list[dict] = []
        self.result = result or {"ok": True, "log_no": "123"}
        monkeypatch.setattr("scripts.browser.cdp.connection.get_page", lambda: object())
        monkeypatch.setattr("scripts.naver.blog.automation.account_probe.read_alias", lambda page: alias)
        monkeypatch.setattr("scripts.naver.blog.core.writer.write_post", self._write)

    def _write(self, page, **kwargs):
        self.calls.append(kwargs)
        return self.result


def test_blog_publish_posts_with_the_approved_content_when_logged_in_as_the_target(monkeypatch):
    fake = FakeBlog(monkeypatch)
    message = actions.ACTIONS["blog_publish"].run(actions.ACTIONS["blog_publish"].validate(GOOD_POST))
    assert "123" in message
    (call,) = fake.calls
    assert call["title"] == "제목" and call["body"] == "본문" and call["tags"] == ["조명", "인테리어"]
    assert call["visibility"] == "private" and call["auto_tags"] is False and call["require_approval"] is False


@pytest.mark.parametrize("alias", [None, "bigsun2024"])
def test_blog_publish_never_posts_when_logged_out_or_as_another_account(monkeypatch, alias):
    fake = FakeBlog(monkeypatch, alias=alias)
    with pytest.raises(RuntimeError):
        actions.ACTIONS["blog_publish"].run(actions.ACTIONS["blog_publish"].validate(GOOD_POST))
    assert fake.calls == []  # 계정을 전환하거나 로그인하려 하지 않고 중단한다


def test_blog_publish_failure_is_reported_not_hidden(monkeypatch):
    FakeBlog(monkeypatch, result={"ok": False, "error": "login_failed"})
    with pytest.raises(RuntimeError, match="실패"):
        actions.ACTIONS["blog_publish"].run(actions.ACTIONS["blog_publish"].validate(GOOD_POST))


def test_blog_publish_job_waits_for_approval_and_publishes_only_after_it(env, monkeypatch):
    fake = FakeBlog(monkeypatch)
    job = make(action="blog_publish", params=GOOD_POST)
    due(job, NOW - timedelta(minutes=1))
    (run,) = svc.tick(NOW)
    assert run["status"] == "awaiting_approval" and fake.calls == []
    assert svc.approve(run["id"], "kim", now=NOW + timedelta(minutes=1))["status"] == "ok"
    assert len(fake.calls) == 1 and env.cdp_calls == 1  # 브라우저 작업이라 CDP 도 보장한다
