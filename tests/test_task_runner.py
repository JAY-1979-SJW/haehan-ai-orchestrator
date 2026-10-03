"""지도 기반 실행기(M5) — 순수 규칙, 기록 흐름(가짜 페이지 범위), 그리고 실제 브라우저로 탐색→지도→실행 왕복.

실제 브라우저 시험은 격리된 헤드리스 Chrome 으로 `page.route` 가 내려 주는 가짜 사이트만 연다(외부 접속 없음, 공유 CDP 브라우저·로그인 세션 무관).
Chrome/Playwright 를 띄울 수 없는 환경에서는 그 시험만 건너뛴다.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from ai_orchestrator.domain import site_task_map as tm
from ai_orchestrator.persistence import site_task_map_store as store
from scripts.explorer import task_runner as tr

HOST = "fixture.test"
NOW = "2026-10-04T12:00:00+09:00"

PAGE_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>업체검색</title></head><body>
<form id="hdr"><input name="hq" placeholder="통합검색"><a href="#" onclick="document.title='WRONG';return false;">검색</a></form>
<form name="main"><input name="txtName" placeholder="업체명"><input name="txtCeo" placeholder="대표자">
<select name="area"><option>서울</option><option>부산</option></select>
<a href="#" onclick="doSearch();return false;">검색</a></form>
<div id="out"></div>
<script>function doSearch(){var q=document.getElementsByName('txtName')[0].value;
document.getElementById('out').innerHTML='<table><tr><th>상호</th><th>상태</th></tr><tr><td>'+q+'</td><td>정상</td></tr></table>';}</script>
</body></html>"""
# 사이트가 개편돼 입력칸 이름·안내문이 바뀐 버전
CHANGED_HTML = PAGE_HTML.replace('name="txtName" placeholder="업체명"', 'name="company" placeholder="회사"')


def _task(**over: Any) -> dict[str, Any]:
    base = {
        "id": "search#main",
        "name": "검색",
        "category": "search",
        "purpose": "",
        "risk": "read",
        "auth": "public",
        "state": "observed",
        "url": f"http://{HOST}/search",
        "host": HOST,
        "fields": [{"name": "txtName", "id": "", "type": "text", "role": "textbox", "label": "업체명", "required": False}],
        "control": "검색",
        "outputs": [],
        "steps": [
            {"type": "navigate", "url": f"http://{HOST}/search"},
            {"type": "change", "selectors": [["[name='txtName']"], ["aria/업체명"]], "value": "{{txtName}}"},
            {"type": "click", "selectors": [["aria/검색"], ["text/검색"]]},
        ],
        "fingerprint": "abc",
        "observed_at": NOW,
        "verified_at": "",
        "failures": 0,
        "changes": [],
    }
    base.update(over)
    return base


# ── 순수 규칙 (domain) ────────────────────────────────────────────────────


def test_validate_run_request_rules():
    task = _task()
    assert tm.validate_run_request(task, {"txtName": "  삼성  "}) == {"txtName": "삼성"}
    with pytest.raises(ValueError, match="조회\\(read\\) 업무만"):
        tm.validate_run_request(_task(risk="submit"), {"txtName": "a"})
    with pytest.raises(ValueError, match="지도에 없는 매개변수"):
        tm.validate_run_request(task, {"nope": "a"})
    with pytest.raises(ValueError, match="조회할 값이 없습니다"):
        tm.validate_run_request(task, {})
    with pytest.raises(ValueError, match="200자"):
        tm.validate_run_request(task, {"txtName": "가" * 201})
    with pytest.raises(ValueError, match="제어문자"):
        tm.validate_run_request(task, {"txtName": "a\nb"})
    required = _task(fields=[{"name": "txtName", "id": "", "required": True}])
    with pytest.raises(ValueError, match="필수 매개변수"):
        tm.validate_run_request(required, {})


def test_empty_values_are_dropped_and_placeholders_listed_in_order():
    task = _task(steps=[{"type": "change", "value": "{{b}}"}, {"type": "change", "value": "{{a}}"}, {"type": "change", "value": "{{b}}"}])
    assert tm.step_placeholders(task["steps"]) == ["b", "a"]
    assert tm.validate_run_request(task, {"a": "1", "b": "   "}) == {"a": "1"}  # 공백뿐인 값은 비워 둔 것으로 본다


def test_substitute_and_apply_outputs():
    assert tm.substitute("x-{{a}}-{{b}}", {"a": "1", "b": "2"}) == "x-1-2"
    assert tm.substitute("{{a}}", {}) is None  # 값이 없으면 그 단계를 건너뛰라는 신호
    m = tm.merge_tasks(tm.empty_map(HOST, now=NOW), [_task()], now=NOW)
    out = tm.apply_outputs(m, "search#main", ["상호", " ", "상태", "x" * 60], now=NOW)
    assert out["tasks"][0]["outputs"] == ["상호", "상태", "x" * 40]  # 열 이름만, 빈 칸 제외, 길이 상한
    assert m["tasks"][0]["outputs"] == []  # 입력을 바꾸지 않는다


# ── 기록 흐름 (가짜 페이지 범위·가짜 실행) ─────────────────────────────────


@pytest.fixture
def saved_map(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "maps")
    monkeypatch.setattr(tr, "_last_run", {})
    store.save(tm.merge_tasks(tm.empty_map(HOST, now=NOW), [_task()], now=NOW))


@contextlib.contextmanager
def fake_scope(_url):
    yield object()


def run(values, monkeypatch, *, result=None, error=None):
    def fake_execute(_page, _host, _task, _values, **_kw):
        if error:
            raise error
        return result

    monkeypatch.setattr(tr, "execute_task", fake_execute)
    return tr.run_task(HOST, "search#main", values, page_scope=fake_scope, clock=lambda: 1000.0, sleep=lambda _s: None)


def state_of(task_id="search#main"):
    return next(t for t in store.load(HOST)["tasks"] if t["id"] == task_id)


def test_success_with_table_marks_verified_and_stores_only_column_names(saved_map, monkeypatch):
    table = {"headers": ["상호", "상태"], "rows": [["비밀업체명", "정상"]], "truncated": False}
    out = run({"txtName": "비밀업체명"}, monkeypatch, result={"steps_done": 3, "url": "u", "tables": [table]})
    assert out["ok"] is True and out["state"] == "verified" and out["tables"] == [table]  # 결과는 응답으로만 돌려준다
    saved = state_of()
    assert saved["state"] == "verified" and saved["outputs"] == ["상호", "상태"] and saved["failures"] == 0
    raw = (store._DIR / f"{HOST}.json").read_text(encoding="utf-8")
    assert "비밀업체명" not in raw  # 입력값·결과 행은 지도에 남지 않는다


def test_structure_mismatch_marks_stale_but_other_failures_do_not(saved_map, monkeypatch):
    out = run({"txtName": "x"}, monkeypatch, error=tr.StepMismatch("입력칸을 찾지 못했습니다"))
    assert out["ok"] is False and out["state"] == "stale" and "재탐색" in out["error"]
    assert state_of()["state"] == "stale" and state_of()["failures"] == 1
    # 시간 초과·다른 호스트 같은 실행 실패는 지도가 틀렸다는 뜻이 아니다 → 상태 불변
    store.save(tm.mark_verified(store.load(HOST), "search#main", now=NOW))
    out = run({"txtName": "x"}, monkeypatch, error=tr.StepFailed("25초 안에 끝내지 못했습니다"))
    assert out["ok"] is False and out["state"] == "verified" and state_of()["state"] == "verified"


def test_no_table_leaves_state_unchanged(saved_map, monkeypatch):
    out = run({"txtName": "x"}, monkeypatch, result={"steps_done": 3, "url": "u", "tables": []})
    assert out["ok"] is True and out["tables"] == [] and "결과 표가 없습니다" in out["note"]
    assert state_of()["state"] == "observed"  # 결과가 없다고 구조 불일치로 보지 않는다


def test_non_read_task_is_refused_before_any_browser_work(saved_map, monkeypatch):
    store.save(tm.merge_tasks(store.load(HOST), [_task(id="submit#x", risk="submit")], now=NOW))
    called = []
    monkeypatch.setattr(tr, "execute_task", lambda *a, **k: called.append(1))
    with pytest.raises(ValueError, match="조회\\(read\\) 업무만"):
        tr.run_task(HOST, "submit#x", {"txtName": "a"}, page_scope=fake_scope)
    with pytest.raises(ValueError, match="찾을 수 없"):
        tr.run_task(HOST, "nope", {"txtName": "a"}, page_scope=fake_scope)
    assert called == []


def test_same_host_calls_are_spaced_apart(saved_map, monkeypatch):
    waits = []
    monkeypatch.setattr(tr, "execute_task", lambda *a, **k: {"steps_done": 1, "url": "u", "tables": []})
    clock = iter([1000.0, 1000.0, 1000.5, 1000.5, 1003.0])  # 첫 호출 후 0.5초 만에 다시 부르면 1.5초를 더 기다린다
    now = lambda: next(clock)  # noqa: E731 - 호출 순서를 고정한 가짜 시계
    tr.run_task(HOST, "search#main", {"txtName": "a"}, page_scope=fake_scope, clock=now, sleep=waits.append)
    tr.run_task(HOST, "search#main", {"txtName": "a"}, page_scope=fake_scope, clock=now, sleep=waits.append)
    assert waits and abs(waits[-1] - 1.5) < 0.01


# ── 실제 브라우저(격리 헤드리스 Chrome)로 탐색 → 지도 → 실행 왕복 ──────────────────


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    pw = sync_api.sync_playwright().start()
    try:
        instance = pw.chromium.launch(channel="chrome", headless=True)
    except Exception as exc:  # noqa: BLE001 - Chrome 을 못 띄우는 환경은 이 시험만 건너뛴다
        pw.stop()
        pytest.skip(f"헤드리스 Chrome 을 띄울 수 없음: {type(exc).__name__}")
    yield instance
    instance.close()
    pw.stop()


def make_page(browser, html):
    context = browser.new_context()
    context.route(f"http://{HOST}/**", lambda route: route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html))
    return context, context.new_page()


def explored_task_for(page, field_name):
    """실제로 화면을 읽어(page_snapshot) 지도 업무를 만든다 — 탐색 결과를 그대로 실행에 쓰는 왕복."""
    from scripts.explorer.page_snapshot import collect

    page.goto(f"http://{HOST}/search")
    tasks = tm.tasks_from_snapshot(collect(page), now=NOW)
    return next(t for t in tasks if any(f["name"] == field_name for f in t["fields"]))


def explored_task(page):
    return explored_task_for(page, "txtName")


def test_roundtrip_explore_then_run_clicks_nearest_search_and_reads_table(browser, tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "maps")
    context, page = make_page(browser, PAGE_HTML)
    try:
        task = explored_task(page)
        assert task["risk"] == "read" and task["control"] == "검색"
        values = tm.validate_run_request(task, {"txtName": "삼성물산"})
        page.goto("about:blank")
        result = tr.execute_task(page, HOST, task, values)
        assert result["steps_done"] == len(task["steps"])
        assert page.title() == "업체검색"  # 머리글의 같은 이름 "검색"(제목을 WRONG 으로 바꾸는 쪽)을 누르지 않았다
        (table,) = result["tables"]
        assert table["headers"] == ["상호", "상태"] and table["rows"] == [["삼성물산", "정상"]]
    finally:
        context.close()


def test_roundtrip_site_change_is_detected_as_mismatch_and_marks_stale(browser, tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "maps")
    monkeypatch.setattr(tr, "_last_run", {})
    context, page = make_page(browser, PAGE_HTML)
    try:
        task = explored_task(page)
        store.save(tm.merge_tasks(tm.empty_map(HOST, now=NOW), [task], now=NOW))
        context.unroute(f"http://{HOST}/**")
        context.route(f"http://{HOST}/**", lambda route: route.fulfill(status=200, content_type="text/html; charset=utf-8", body=CHANGED_HTML))

        @contextlib.contextmanager
        def scope(_url):
            yield page

        out = tr.run_task(HOST, task["id"], {"txtName": "삼성"}, page_scope=scope, sleep=lambda _s: None)
        assert out["ok"] is False and out["state"] == "stale"
        assert next(t for t in store.load(HOST)["tasks"] if t["id"] == task["id"])["state"] == "stale"
    finally:
        context.close()


def test_real_run_never_leaves_the_map_host(browser):
    context, page = make_page(browser, PAGE_HTML)
    try:
        foreign = _task(steps=[{"type": "navigate", "url": "http://other.test/x"}])
        with pytest.raises(tr.StepFailed, match="다른 주소"):
            tr.execute_task(page, HOST, foreign, {})
        with pytest.raises(tr.StepFailed, match="실행할 수 없는 단계"):
            tr.execute_task(page, HOST, _task(steps=[{"type": "keyDown"}]), {})
    finally:
        context.close()


SUBMIT_INPUT_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>팀검색</title></head><body>
<form method="GET" action="/teams" onsubmit="show();return false;"><label for="q">팀 이름</label>
<input type="text" name="q" id="q" placeholder="팀 이름 검색"><input type="submit" value="조회"></form>
<div id="out"></div>
<script>function show(){var q=document.getElementById('q').value;
document.getElementById('out').innerHTML='<table><tr><th>팀</th><th>승</th></tr><tr><td>'+q+'</td><td>44</td></tr></table>';}</script>
</body></html>"""


def test_submit_input_button_is_collected_so_the_search_can_be_clicked(browser, tmp_path, monkeypatch):
    """실사이트(크롤링 연습 사이트) 실측 회귀: <input type=submit value=Search> 를 버튼으로 모으지 않아 control 이 비고 클릭 단계가 빠졌다."""
    monkeypatch.setattr(store, "_DIR", tmp_path / "maps")
    context, page = make_page(browser, SUBMIT_INPUT_HTML)
    try:
        task = explored_task_for(page, "q")
        assert task["control"] == "조회" and task["risk"] == "read"
        assert [s["type"] for s in task["steps"]] == ["navigate", "change", "click"]  # 클릭 단계가 있다
        page.goto("about:blank")
        result = tr.execute_task(page, HOST, task, tm.validate_run_request(task, {"q": "보스턴"}))
        assert result["tables"][0]["rows"] == [["보스턴", "44"]]
    finally:
        context.close()
