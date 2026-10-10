"""블로그 자동 작성 API — 권한·승인 위조 차단·승인 무효화·경로 탈출 차단·동시 실행 방지·감사 이벤트. 네이버·claude 는 부르지 않는다."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.connectors.naver_blog import automation_router as B
from scripts.naver.blog.automation import runner as N
from scripts.naver.blog.automation import store as S
from tools.gates.auth import get_current_user

NOW = datetime(2026, 10, 5, 9, 3)
FRESH_RESEARCH = {
    "generated_at": "2026-10-04T10:00:00",
    "keywords": [{"keyword": "하도급지킴이", "total_search": 44880}],
    "topics": [{"keyword": "하도급지킴이", "question_title": "질문"}],
}


def rule_body(**over):
    body = {
        "name": "건설 주 3회",
        "blog_id": "skyjwsin",
        "user_topics": [{"topic": "직접입력 주제", "keywords": ["하도급지킴이"]}],
        "use_research": False,
        "days": [0, 2, 4],
        "times": ["09:00"],
        "per_day": 1,
        "per_week": 3,
        "mode": "auto_publish",
    }
    body.update(over)
    return body


def good_post():
    return {
        "title": "제목",
        "body": "본" * 2600,
        "tags": [f"t{i}" for i in range(15)],
        "seo": {"ok": True, "warnings": []},
    }


class State:
    """테스트가 바꿔 끼우는 것들: 로그인 사용자, 저장소, 실행 의존, 감사 이벤트."""

    def __init__(self, tmp_path):
        self.user = {"actor": "tester", "role": "owner"}
        self.store = S.Store(tmp_path / "ba")
        self.events = []
        self.factory_calls = []
        self.post = good_post()


@pytest.fixture
def api(tmp_path, monkeypatch):
    state = State(tmp_path)
    app = FastAPI()
    app.include_router(B.blog_automation_router)
    app.dependency_overrides[get_current_user] = lambda: state.user
    app.dependency_overrides[B.get_store] = lambda: state.store

    def factory_provider():
        def factory(store, web):
            state.factory_calls.append(web)
            return N.RunnerDeps(
                store=store,
                llm=lambda *a, **k: {"ok": True, "text": "x"},
                now=lambda: NOW,
                load_research=lambda blog_id: FRESH_RESEARCH,
                research_topics=lambda blog_id: [],
                published_entries=lambda blog_id: [],
                topic_key=lambda t: "k:" + t.lower(),
                product_related=lambda record: False,
                generate_post=lambda topic, llm=None, cta_block=None, blog_id=None: state.post,
                claude_available=lambda: True,
                contact=("https://h.example", "010"),
            )

        return factory

    app.dependency_overrides[B.get_deps_factory] = factory_provider
    monkeypatch.setattr(B, "emit_event", lambda event_type, **kw: state.events.append((event_type, kw)))
    B._RUNNING.clear()
    return TestClient(app), state


def put(client, rule_id="r1", **over):
    return client.put(f"/naver/blog/automation/rules/{rule_id}", json=rule_body(**over))


# ── 권한 ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["viewer", "user", ""])
def test_non_admin_roles_are_rejected_everywhere(api, role):
    client, state = api
    state.user = {"actor": "x", "role": role}
    for method, url in [
        ("get", "/naver/blog/automation/status"),
        ("get", "/naver/blog/automation/rules"),
        ("put", "/naver/blog/automation/rules/r1"),
        ("post", "/naver/blog/automation/rules/r1/run-now"),
        ("get", "/naver/blog/automation/history"),
        ("get", "/naver/blog/automation/drafts"),
    ]:
        kwargs = {"json": rule_body()} if method == "put" else {}
        assert getattr(client, method)(url, **kwargs).status_code == 403, url


def test_only_owner_can_approve(api):
    client, state = api
    put(client)
    state.user = {"actor": "admin1", "role": "admin"}
    assert client.post("/naver/blog/automation/rules/r1/approve").status_code == 403


# ── 규칙 저장·검증 ───────────────────────────────────────────────────────


def test_save_and_list_rule_with_computed_fields(api):
    client, _ = api
    response = put(client)
    assert response.status_code == 200
    view = response.json()
    assert view["id"] == "r1" and view["approval_valid"] is False and view["effective_mode"] == "draft_only"
    assert len(view["rule_hash"]) == 64
    listed = client.get("/naver/blog/automation/rules").json()
    assert [r["id"] for r in listed["rules"]] == ["r1"] and listed["broken"] == {}


@pytest.mark.parametrize(
    ("over", "needle"),
    [
        ({"per_day": 0}, "per_day"),
        ({"blog_id": "ghost"}, "ghost"),
        ({"times": ["25:00"]}, "times"),
        ({"mode": "x"}, "mode"),
    ],
)
def test_invalid_rule_is_422_with_reasons(api, over, needle):
    client, _ = api
    response = put(client, **over)
    assert response.status_code == 422
    assert any(needle in error for error in response.json()["detail"])


def test_bad_ids_are_rejected(api):
    client, _ = api
    assert client.put("/naver/blog/automation/rules/" + "x" * 65, json=rule_body()).status_code == 400
    assert client.put("/naver/blog/automation/rules/a b", json=rule_body()).status_code == 400
    assert client.put("/naver/blog/automation/rules/r1", json=rule_body(id="other")).status_code == 400


def test_client_supplied_approval_is_ignored(api):
    client, _ = api
    forged = {"approved_by": "hacker", "approved_at": "2026-01-01T00:00:00", "rule_hash": "0" * 64}
    view = put(client, approval=forged).json()
    assert view["approval"] is None and view["approval_valid"] is False and view["effective_mode"] == "draft_only"


def test_broken_rule_file_is_reported_not_fatal(api):
    client, state = api
    put(client, "good")
    (state.store.rules_dir / "bad.json").write_text("{nope", encoding="utf-8")
    listed = client.get("/naver/blog/automation/rules").json()
    assert [r["id"] for r in listed["rules"]] == ["good"] and "bad" in listed["broken"]


def test_delete_rule(api):
    client, _ = api
    put(client)
    assert client.delete("/naver/blog/automation/rules/r1").status_code == 200
    assert client.delete("/naver/blog/automation/rules/r1").status_code == 404
    assert client.post("/naver/blog/automation/rules/r1/run-now").status_code == 404


# ── 승인 ─────────────────────────────────────────────────────────────────


def test_approve_makes_auto_publish_effective_and_returns_summary(api):
    client, state = api
    put(client)
    body = client.post("/naver/blog/automation/rules/r1/approve").json()
    assert body["approval_valid"] is True and body["effective_mode"] == "auto_publish"
    assert body["approval"]["approved_by"] == "tester"
    assert any("skyjwsin" in line for line in body["summary"])
    approved_events = [kw for t, kw in state.events if t == "NAVER_BLOG_AUTO_RULE" and kw["status"] == "approved"]
    assert approved_events and approved_events[0]["risk"] == "high"


def test_approval_requires_auto_publish_mode(api):
    client, _ = api
    put(client, mode="draft_only")
    assert client.post("/naver/blog/automation/rules/r1/approve").status_code == 409


def test_editing_after_approval_voids_it_but_identical_resave_keeps_it(api):
    client, _ = api
    put(client)
    client.post("/naver/blog/automation/rules/r1/approve")
    same = put(client).json()  # 내용이 같으면 승인 유지
    assert same["approval_valid"] is True
    edited = put(client, per_day=2, per_week=5).json()
    assert edited["approval_valid"] is False and edited["effective_mode"] == "draft_only"
    assert edited["approval"] is not None  # 기록은 남고 무효일 뿐


def test_lighting_account_approval_never_becomes_auto_publish(api):
    client, _ = api
    put(client, blog_id="skyjwshin")
    body = client.post("/naver/blog/automation/rules/r1/approve").json()
    assert body["approval_valid"] is True and body["effective_mode"] == "draft_only"


# ── 일시정지 ─────────────────────────────────────────────────────────────


def test_pause_resume_and_resave_keeps_pause_state(api):
    client, _ = api
    put(client)
    assert client.post("/naver/blog/automation/rules/r1/pause").json()["paused"] is True
    assert put(client).json()["paused"] is True  # paused 를 안 보내면 저장돼 있던 값 유지
    assert client.post("/naver/blog/automation/rules/r1/resume").json()["paused"] is False
    assert put(client, paused=True).json()["paused"] is True


def test_pausing_keeps_approval_valid(api):
    client, _ = api
    put(client)
    client.post("/naver/blog/automation/rules/r1/approve")
    assert client.post("/naver/blog/automation/rules/r1/pause").json()["approval_valid"] is True


# ── 실행 ─────────────────────────────────────────────────────────────────


def test_run_now_saves_local_draft_and_history(api):
    client, state = api
    put(client)
    result = client.post("/naver/blog/automation/rules/r1/run-now").json()
    assert result["status"] == "draft_saved" and result["ok"]
    assert state.factory_calls == [False]
    drafts = client.get("/naver/blog/automation/drafts", params={"rule_id": "r1"}).json()["drafts"]
    assert len(drafts) == 1 and drafts[0]["title"] == "제목"
    detail = client.get(f"/naver/blog/automation/drafts/{drafts[0]['file']}").json()
    assert detail["post"]["title"] == "제목" and detail["rule_id"] == "r1"
    hist = client.get("/naver/blog/automation/history", params={"rule_id": "r1"}).json()["history"]
    assert hist[0]["status"] == "draft_saved"
    assert any(t == "NAVER_BLOG_AUTO_RUN" and kw["status"] == "draft_saved" for t, kw in state.events)


def test_web_research_flag_reaches_the_factory(api):
    client, state = api
    put(client)
    client.post("/naver/blog/automation/rules/r1/run-now", params={"web_research": "true"})
    assert state.factory_calls == [True]


def test_paused_rule_is_blocked_and_writes_nothing(api):
    client, _ = api
    put(client)
    client.post("/naver/blog/automation/rules/r1/pause")
    result = client.post("/naver/blog/automation/rules/r1/run-now").json()
    assert result["status"] == "blocked" and "paused" in result["blockers"]
    assert client.get("/naver/blog/automation/drafts").json()["drafts"] == []


def test_concurrent_run_of_same_rule_is_409(api):
    client, _ = api
    put(client)
    B._RUNNING.add("r1")
    try:
        assert client.post("/naver/blog/automation/rules/r1/run-now").status_code == 409
    finally:
        B._RUNNING.discard("r1")


def test_running_marker_is_cleared_even_when_the_run_crashes(api, monkeypatch):
    client, _ = api
    put(client)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(B.automation_runner, "run_once", boom)
    with pytest.raises(RuntimeError):
        client.post("/naver/blog/automation/rules/r1/run-now")
    assert "r1" not in B._RUNNING


# ── 기록·초안 조회 ───────────────────────────────────────────────────────


def test_history_newest_first_filtered_and_limited(api):
    client, state = api
    for i, rid in enumerate(["a", "b", "a"]):
        state.store.upsert_history(
            {"rule_id": rid, "slot": f"s{i}", "at": f"2026-10-0{i + 1}T09:00:00", "status": "draft_saved"}
        )
    everything = client.get("/naver/blog/automation/history").json()["history"]
    assert [h["slot"] for h in everything] == ["s2", "s1", "s0"]
    only_a = client.get("/naver/blog/automation/history", params={"rule_id": "a", "limit": 1}).json()["history"]
    assert [h["slot"] for h in only_a] == ["s2"]
    assert client.get("/naver/blog/automation/history", params={"rule_id": "../x"}).status_code == 400


@pytest.mark.parametrize("name", ["..%5C..%5Cetc.json", "a%2F..%2Fb.json", "evil.txt", "..json", "a b.json"])
def test_draft_detail_rejects_traversal_and_bad_names(api, name):
    client, _ = api
    assert client.get(f"/naver/blog/automation/drafts/{name}").status_code in (400, 404)


def test_draft_detail_missing_is_404_and_unknown_rule_filter_is_400(api):
    client, _ = api
    assert client.get("/naver/blog/automation/drafts/nothing.json").status_code == 404
    assert client.get("/naver/blog/automation/drafts", params={"rule_id": "../x"}).status_code == 400


# ── 상태·등록 ────────────────────────────────────────────────────────────


def test_status_reports_environment_and_that_naver_is_untouched(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(B, "claude_available", lambda: True)
    body = client.get("/naver/blog/automation/status").json()
    assert body["claude_available"] is True and body["publishes_to_naver"] is False
    assert body["auto_publish_blog_ids"] == ["skyjwsin"]
    assert set(body["research"]) == set(body["blog_ids"]) and body["research_max_age_days"] == 30


def test_router_is_registered_in_the_main_router():
    """FastAPI 0.142 는 include_router 를 지연 등록해 router.routes 로는 하위 경로가 안 보인다 — openapi 로 확인한다."""
    from ai_orchestrator.routers.registry import router

    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]
    base = "/api/v1/naver/blog/automation"
    expected = {
        "/status": {"get"},
        "/rules": {"get"},
        "/rules/{rule_id}": {"put", "delete"},
        "/rules/{rule_id}/approve": {"post"},
        "/rules/{rule_id}/pause": {"post"},
        "/rules/{rule_id}/resume": {"post"},
        "/rules/{rule_id}/run-now": {"post"},
        "/history": {"get"},
        "/drafts": {"get"},
        "/drafts/{file}": {"get"},
    }
    for suffix, methods in expected.items():
        assert set(paths[base + suffix]) == methods, suffix
    assert not {p for p in paths if p.startswith(base)} - {base + s for s in expected}
