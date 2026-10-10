"""사이트 탐색 요청(M3) — 검증 규칙·승인 상태 전이·실행기 연결·라우터 인증. 브라우저·네트워크 없이 가짜 실행기/페이지만 사용."""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.site_work import site_task_map as tm
from ai_orchestrator.site_work import site_task_map_explore_service as svc
from ai_orchestrator.site_work import site_task_map_request_store as rstore
from ai_orchestrator.site_work import site_task_map_store as store
from ai_orchestrator.site_work.site_task_map_router import site_task_map_router
from scripts.explorer import task_mapper
from tools.gates import auth as auth_module
from tools.gates.auth import get_current_user

URL = "https://www.example-kiscon.test/gongsi/ksc_dft.asp"
OK_RESULT = {"pages": 3, "form_pages": 1, "tasks": 1, "aborted_reason": "", "snapshot_errors": 0}


# ── 요청 검증(순수) ───────────────────────────────────────────────────────


def test_validate_defaults_and_normalization():
    n = tm.validate_explore_request({"start_url": "https://WWW.Example-Kiscon.test/a/b?x=1#frag"})
    assert n["host"] == "www.example-kiscon.test" and n["start_url"].endswith("/a/b?x=1")
    assert (n["depth"], n["max_pages"], n["auth"]) == (2, 20, "public")


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://x.test/",
        "javascript:alert(1)",
        "not a url",
        "https://user:pw@x.test/",
        "http://localhost/",
        "http://127.0.0.1:8401/",
        "http://10.0.0.5/",
        "http://192.168.0.1/",
        "http://169.254.1.1/",
        "http://[::1]/",
        "http://printer.local/",
        "http://db.internal/",
    ],
)
def test_validate_rejects_unsafe_or_internal_addresses(url):
    with pytest.raises(ValueError):
        tm.validate_explore_request({"start_url": url})


@pytest.mark.parametrize(("key", "value"), [("depth", 0), ("depth", 5), ("max_pages", 0), ("max_pages", 201), ("depth", "x")])
def test_validate_rejects_out_of_range(key, value):
    with pytest.raises(ValueError):
        tm.validate_explore_request({"start_url": URL, key: value})


def test_validate_accepts_upper_bounds():
    n = tm.validate_explore_request({"start_url": URL, "depth": 4, "max_pages": 200, "auth": "certificate"})
    assert (n["depth"], n["max_pages"], n["auth"]) == (4, 200, "certificate")


# ── 상태 전이 ─────────────────────────────────────────────────────────────


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(rstore, "_DIR", tmp_path / "requests")
    monkeypatch.setattr(store, "_DIR", tmp_path / "maps")
    calls = []

    def fake(request):
        calls.append(request["id"])
        return dict(OK_RESULT)

    svc.configure(fake, run_async=False)
    svc._active.clear()
    yield calls
    svc.configure(None)
    svc._active.clear()


def test_create_does_not_execute(env):
    r = svc.create_request({"start_url": URL, "reason": "협력업체 확인"}, actor="ai")
    assert r["status"] == "pending" and r["host"] == "www.example-kiscon.test" and env == []


def test_approve_runs_once_and_records_result(env):
    r = svc.create_request({"start_url": URL}, actor="ai")
    svc.approve_request(r["id"], actor="kim")
    done = svc.get_request(r["id"])
    assert done["status"] == "done" and done["decided_by"] == "kim" and done["result"]["pages"] == 3
    assert env == [r["id"]]
    with pytest.raises(ValueError, match="이미 처리"):
        svc.approve_request(r["id"], actor="kim")  # 두 번 실행되지 않는다
    assert env == [r["id"]]


def test_executor_failure_is_recorded_not_swallowed(env):
    def boom(_request):
        raise RuntimeError("브라우저 없음")

    svc.configure(boom, run_async=False)
    r = svc.create_request({"start_url": URL}, actor="ai")
    svc.approve_request(r["id"], actor="kim")
    got = svc.get_request(r["id"])
    assert got["status"] == "failed" and "브라우저 없음" in got["error"]
    assert not svc._active


def test_cancel_only_pending_and_blocks_later_approve(env):
    r = svc.create_request({"start_url": URL}, actor="ai")
    assert svc.cancel_request(r["id"], actor="kim")["status"] == "cancelled"
    with pytest.raises(ValueError, match="이미 처리"):
        svc.approve_request(r["id"], actor="kim")
    with pytest.raises(ValueError, match="승인 대기"):
        svc.cancel_request(r["id"], actor="kim")
    assert env == []


def test_only_one_exploration_at_a_time(env):
    a = svc.create_request({"start_url": URL}, actor="ai")
    b = svc.create_request({"start_url": URL}, actor="ai")
    svc._active.add(a["id"])
    with pytest.raises(ValueError, match="실행 중"):
        svc.approve_request(b["id"], actor="kim")
    assert svc.get_request(b["id"])["status"] == "pending"


def test_running_after_restart_shows_interrupted(env):
    r = svc.create_request({"start_url": URL}, actor="ai")
    rstore.save(dict(r, status="running"))  # 실행 중 기록만 남고 서버가 재시작됨(_active 비어 있음)
    assert svc.get_request(r["id"])["status"] == "interrupted"


def test_approve_without_executor_and_bad_ids(env):
    r = svc.create_request({"start_url": URL}, actor="ai")
    svc.configure(None)
    with pytest.raises(ValueError, match="실행기"):
        svc.approve_request(r["id"], actor="kim")
    for bad in ("../x", "zz", ""):
        with pytest.raises(ValueError):
            svc.get_request(bad)
    with pytest.raises(ValueError, match="찾을 수 없"):
        svc.get_request("0" * 32)


def test_async_run_finishes_in_background(env):
    svc.configure(lambda _r: dict(OK_RESULT), run_async=True)
    r = svc.create_request({"start_url": URL}, actor="ai")
    svc.approve_request(r["id"], actor="kim")
    for _ in range(100):
        if svc.get_request(r["id"])["status"] == "done":
            break
        time.sleep(0.05)
    assert svc.get_request(r["id"])["status"] == "done"


# ── 탐색 실행기(가짜 페이지) ──────────────────────────────────────────────


class FakePage:
    def __init__(self):
        self.visited = []

    def goto(self, url, timeout=0):
        self.visited.append(url)


def _form_snapshot(url):
    return {
        "url": url,
        "title": "업체검색",
        "frames": [
            {
                "idx": 0,
                "url": url,
                "inputs": [
                    {"tag": "INPUT", "type": "text", "name": "q", "id": "", "placeholder": "업체명", "aria": "", "required": False, "visible": True, "form": "0:f", "pos": 10}
                ],
                "buttons": [],
                "links": [{"text": "검색", "href": "#", "target": "", "visible": True, "form": "0:f", "pos": 12}],
                "forms": [],
                "headings": [],
            }
        ],
    }


def _explore_result(pages, aborted=""):
    return lambda page, **kw: {"visited_count": len(pages), "aborted_reason": aborted, "pages": pages}


def test_explore_to_map_visits_form_pages_only_and_merges(env):
    seen = {}

    def fake_explore(page, **kw):
        seen.update(kw)
        return {
            "visited_count": 3,
            "aborted_reason": "",
            "pages": [
                {"url": "https://www.example-kiscon.test/a", "forms_count": 1},
                {"url": "https://www.example-kiscon.test/menu", "forms_count": 0},
                {"url": "https://www.example-kiscon.test/err", "error": "goto"},
            ],
        }

    page = FakePage()
    sleeps = []
    out = task_mapper.explore_to_map(
        page, URL, depth=2, max_pages=5, delay_s=1.5, explore_fn=fake_explore, collect_fn=lambda p: _form_snapshot(p.visited[-1]), sleep_fn=sleeps.append
    )
    assert page.visited == ["https://www.example-kiscon.test/a"]  # 입력창 있는 화면만 다시 연다(클릭·제출 없음)
    assert sleeps == [1.5] and (out["pages"], out["form_pages"], out["tasks"]) == (3, 1, 1)
    # 위험 주소 회피·같은 호스트·간격이 탐색기에 전달된다
    assert seen["same_host_only"] is True and seen["save"] is False and seen["delay_s"] == 1.5
    assert "logout" in seen["skip_url_patterns"] and "delete" in seen["skip_url_patterns"]
    assert store.load("www.example-kiscon.test")["tasks"][0]["risk"] == "read"


def test_explore_to_map_stops_snapshots_when_bot_detected(env):
    pages = [{"url": "https://www.example-kiscon.test/a", "forms_count": 1}]
    page = FakePage()
    out = task_mapper.explore_to_map(
        page, URL, explore_fn=_explore_result(pages, "bot_flagged: high"), collect_fn=lambda p: _form_snapshot(p.visited[-1]), sleep_fn=lambda _s: None
    )
    assert page.visited == [] and out["aborted_reason"].startswith("bot_flagged")


def test_snapshot_failure_on_one_page_does_not_stop_the_rest(env):
    class Flaky(FakePage):
        def goto(self, url, timeout=0):
            if url.endswith("/bad"):
                raise RuntimeError("timeout")
            super().goto(url, timeout)

    pages = [{"url": "https://www.example-kiscon.test/bad", "forms_count": 1}, {"url": "https://www.example-kiscon.test/ok", "forms_count": 1}]
    page = Flaky()
    out = task_mapper.explore_to_map(
        page, URL, explore_fn=_explore_result(pages), collect_fn=lambda p: _form_snapshot(p.visited[-1]), sleep_fn=lambda _s: None
    )
    assert out["snapshot_errors"] == 1 and out["tasks"] == 1


class FakeContext:
    def __init__(self, existing_urls):
        self.pages = [FakePage() for _ in existing_urls]
        for page, url in zip(self.pages, existing_urls, strict=True):
            page.url = url


class FakeHandle:
    def __init__(self, tab_id):
        self.tab_id = tab_id


def test_private_tab_uses_http_opener_and_never_touches_user_tabs():
    """실사이트 실측 회귀: 같은 호스트의 사용자 탭을 재사용해 이동시키면 안 된다. 탭은 검증된 HTTP 경로로 만든다."""
    ctx = FakeContext(["https://www.example-kiscon.test/my/login-session"])
    user_tab = ctx.pages[0]
    new_page = FakePage()
    opened = []
    page, handle = task_mapper.open_private_tab(
        ctx,
        URL,
        opener=lambda url, reason: opened.append((url, reason)) or FakeHandle("T1"),
        finder=lambda _ctx, tab_id: new_page if tab_id == "T1" else user_tab,
    )
    assert page is new_page and handle.tab_id == "T1"
    assert opened == [(URL, "사이트 업무 지도 탐색")]
    assert user_tab.visited == []  # 사용자 탭은 이동하지 않았다 (ctx.new_page()+goto 도 쓰지 않는다)


def test_private_tab_closed_when_page_cannot_be_found():
    closed = []

    def not_found(_ctx, _tab_id):
        raise LookupError("페이지 없음")

    with pytest.raises(LookupError):
        task_mapper.open_private_tab(
            FakeContext([]), URL, opener=lambda url, reason: FakeHandle("T2"), closer=closed.append, finder=not_found
        )
    assert [h.tab_id for h in closed] == ["T2"]  # 실패해도 빈 탭이 남지 않는다


def test_page_for_tab_matches_by_target_id_and_times_out(monkeypatch):
    ctx = FakeContext(["https://a.test/", "https://b.test/"])
    ids = {id(ctx.pages[0]): "AAA", id(ctx.pages[1]): "BBB"}
    monkeypatch.setattr(task_mapper, "_target_id", lambda _ctx, page: ids[id(page)])
    assert task_mapper.page_for_tab(ctx, "BBB") is ctx.pages[1]
    waits = []
    with pytest.raises(LookupError, match="찾지 못했습니다"):
        task_mapper.page_for_tab(ctx, "ZZZ", timeout_s=0.6, sleep_fn=waits.append)
    assert len(waits) == 2  # 기다린 만큼만 재시도하고 끝낸다


# ── 라우터 ────────────────────────────────────────────────────────────────


def test_router_explore_flow_and_auth(env, monkeypatch):
    monkeypatch.setattr(auth_module.config, "AUTH_ENABLED", True)
    app = FastAPI()
    app.include_router(site_task_map_router)
    svc.configure(lambda _r: dict(OK_RESULT), run_async=False)  # 라우터 import 시 연결된 실행기를 시험용으로 교체
    client = TestClient(app)
    assert client.post("/site-map/explore/requests", json={"start_url": URL}).status_code in (401, 403)
    app.dependency_overrides[get_current_user] = lambda: {"role": "viewer", "username": "v"}
    assert client.post("/site-map/explore/requests", json={"start_url": URL}).status_code == 403
    app.dependency_overrides[get_current_user] = lambda: {"role": "admin", "username": "kim"}
    assert client.post("/site-map/explore/requests", json={"start_url": "http://127.0.0.1/"}).status_code == 400
    r = client.post("/site-map/explore/requests", json={"start_url": URL, "depth": 3}).json()
    assert r["status"] == "pending" and r["depth"] == 3
    assert [i["id"] for i in client.get("/site-map/explore/requests", params={"status": "pending"}).json()["items"]] == [r["id"]]
    assert client.get("/site-map/explore/requests", params={"status": "zzz"}).status_code == 400
    assert client.post(f"/site-map/explore/requests/{r['id']}/approve").json()["status"] in ("running", "done")
    assert client.get(f"/site-map/explore/requests/{r['id']}").json()["status"] == "done"
    assert client.post(f"/site-map/explore/requests/{r['id']}/approve").status_code == 400
    assert client.get("/site-map/explore/requests/" + "0" * 32).status_code == 404
    assert client.get("/site-map/explore/requests/not-an-id").status_code == 422


def test_explore_reads_screens_with_controls_even_without_form(env):
    """<form> 없이 버튼·편집 영역으로만 동작하는 화면(controls_count)도 다시 읽는다 — 블로그 글쓰기·발행 화면."""
    pages = [
        {"url": "https://www.example-kiscon.test/write", "forms_count": 0, "controls_count": 4},
        {"url": "https://www.example-kiscon.test/menu", "forms_count": 0, "controls_count": 0},
    ]
    page = FakePage()
    out = task_mapper.explore_to_map(page, URL, explore_fn=_explore_result(pages), collect_fn=lambda p: _form_snapshot(p.visited[-1]), sleep_fn=lambda s: None)
    assert page.visited == ["https://www.example-kiscon.test/write"] and out["form_pages"] == 1


def test_redirected_start_host_is_mapped_under_actual_host_and_noted_on_requested(env):
    """blog.naver.com → section.blog.naver.com 처럼 시작 주소가 다른 호스트로 이동하면 실제 호스트 지도에 담고, 요청 호스트에는 안내를 남긴다."""
    actual = "https://www.example-kiscon.test/a"

    def fake_explore(page, **kw):
        return {"host": "www.example-kiscon.test", "visited_count": 1, "aborted_reason": "", "pages": [{"url": actual, "forms_count": 1}]}

    out = task_mapper.explore_to_map(
        FakePage(), "https://start.example.test/", explore_fn=fake_explore, collect_fn=lambda p: _form_snapshot(p.visited[-1]), sleep_fn=lambda s: None
    )
    assert out["host"] == "www.example-kiscon.test" and out["tasks"] == 1
    note = store.load("start.example.test")
    assert note["tasks"] == [] and "www.example-kiscon.test 지도에 있습니다" in note["explored"]["coverage"]["warning"]
    from ai_orchestrator.site_work import site_task_map_service as service

    assert "주의:" in service.lookup("start.example.test", "검색")["hint"]  # 요청 호스트로 물어도 어디를 봐야 하는지 알려 준다
