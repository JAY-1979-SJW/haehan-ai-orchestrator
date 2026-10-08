"""지도 기반 실행기(M5) — 순수 규칙, 기록 흐름(가짜 페이지 범위), 그리고 실제 브라우저로 탐색→지도→실행 왕복.

실제 브라우저 시험은 격리된 헤드리스 Chrome 으로 `page.route` 가 내려 주는 가짜 사이트만 연다(외부 접속 없음, 공유 CDP 브라우저·로그인 세션 무관).
Chrome/Playwright 를 띄울 수 없는 환경에서는 그 시험만 건너뛴다.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from ai_orchestrator.site_work import site_task_map as tm
from ai_orchestrator.site_work import site_task_map_store as store
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


SUFFIX_NAME_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>카페</title></head><body>
<button onclick="document.title='CLICKED'">네이버 메이트<br>누적 인용<br>380만 인용</button><button>다른 버튼</button></body></html>"""


def test_click_falls_back_to_substring_when_site_adds_text_after_stored_label(browser):
    """저장된 이름(첫 줄)이 접근 가능한 이름의 앞부분일 때(뒤 수치는 바뀐다) 정확 일치가 없어도 찾아 누른다 — 재개 안정성."""
    context, page = make_page(browser, SUFFIX_NAME_HTML)
    try:
        page.goto(f"http://{HOST}/x")
        found = tr._click_candidates(page, [["aria/네이버 메이트"]])
        assert len(found) == 1
        found[0].click()
        assert page.title() == "CLICKED"
        with pytest.raises(tr.StepMismatch):
            tr._click_candidates(page, [["aria/없는 이름"]])  # 부분 일치도 없으면 여전히 구조 불일치
    finally:
        context.close()


# ── 결과 표 읽기: 비동기 갱신·칸 병합·낡은 표 방지 (실제 브라우저) ─────────────────────

CAFE_LIKE_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>게시판</title></head><body>
<form onsubmit="return false;"><input name="q" placeholder="검색어"><input type="submit" value="검색" onclick="search();return false;"></form>
<div id="board"><table><thead><tr><th colspan="2">제목</th><th>작성자</th><th>작성일</th><th>조회수</th></tr></thead>
<tbody><tr><td>공지</td><td>이전 목록 글</td><td>운영자</td><td>10.01</td><td>9</td></tr>
<tr><td>1</td><td>다른 이전 글</td><td>관리</td><td>10.02</td><td>5</td></tr></tbody></table></div>
<script>function search(){var q=document.getElementsByName('q')[0].value;var b=document.getElementById('board');b.innerHTML='';
setTimeout(function(){b.innerHTML='<table><thead><tr><th colspan="2">제목</th><th>작성자</th><th>작성일</th><th>조회수</th></tr></thead><tbody>'
+'<tr><td>7</td><td>'+q+' 관련 글 하나</td><td>김공무</td><td>10.03</td><td>31</td></tr><tr><td>6</td><td>'+q+' 관련 글 둘</td><td>이현장</td><td>10.04</td><td>12</td></tr></tbody></table>';},1800);}</script>
</body></html>"""

NO_REFRESH_HTML = CAFE_LIKE_HTML.replace("setTimeout(function(){", "setTimeout(function(){return;").replace("b.innerHTML='';", "")  # 클릭해도 화면이 갱신되지 않는 사이트

NO_TH_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>목록</title></head><body>
<form onsubmit="return false;"><input name="q"><input type="submit" value="조회" onclick="go();return false;"></form><div id="out"></div>
<script>function go(){document.getElementById('out').innerHTML='<table><tr><td>이름</td><td>상태</td></tr><tr><td>가</td><td>정상</td></tr></table>';}</script></body></html>"""


def _run_fixture(browser, html, query, tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "maps")
    context, page = make_page(browser, html)
    try:
        task = explored_task_for(page, "q")
        values = tm.validate_run_request(task, {"q": query})
        page.goto("about:blank")
        return tr.execute_task(page, HOST, task, values)
    finally:
        context.close()


def test_async_result_is_awaited_and_colspan_headers_align_with_cells(browser, tmp_path, monkeypatch):
    """실사이트(카페) 실측 회귀: 클릭 직후 화면이 비동기로 다시 그려지는데 0.8초만 기다려 '결과 없음'이 됐고, 제목이 2칸(colspan)이라 열이 밀렸다."""
    result = _run_fixture(browser, CAFE_LIKE_HTML, "공사대장", tmp_path, monkeypatch)
    assert result["result_state"] == "fresh"
    (table,) = result["tables"]
    assert table["headers"] == ["제목", "제목(2)", "작성자", "작성일", "조회수"]  # 병합된 머리글을 펼쳐 데이터 칸(5)과 맞춘다
    assert table["rows"][0] == ["7", "공사대장 관련 글 하나", "김공무", "10.03", "31"]
    assert table["rows"][0][1] != "이전 목록 글" and table["total"] == 2 and "signature" not in table  # 이전 표가 아니라 갱신된 표, 내부 값 미노출


def test_unchanged_screen_is_not_reported_as_a_result(browser, tmp_path, monkeypatch):
    """클릭해도 화면이 갱신되지 않으면 이전 화면의 표를 결과로 내놓지 않는다(틀린 답을 내지 않기 위해)."""
    monkeypatch.setattr(tr, "RESULT_WAIT_S", 1.2)
    result = _run_fixture(browser, NO_REFRESH_HTML, "공사대장", tmp_path, monkeypatch)
    assert result["tables"] == [] and result["result_state"] == "unchanged"


def test_table_without_th_still_uses_first_row_as_headers(browser, tmp_path, monkeypatch):
    result = _run_fixture(browser, NO_TH_HTML, "x", tmp_path, monkeypatch)
    (table,) = result["tables"]
    assert table["headers"] == ["이름", "상태"] and table["rows"] == [["가", "정상"]] and table["header_guessed"] is True


def test_unchanged_note_is_reported_by_run_task(saved_map, monkeypatch):
    out = run({"txtName": "x"}, monkeypatch, result={"steps_done": 3, "url": "u", "tables": [], "result_state": "unchanged"})
    assert out["ok"] is True and "갱신됐는지 확인하지 못했습니다" in out["note"] and state_of()["state"] == "observed"


# ── M8: 링크 이동형 읽기(메뉴 색인·주소 열기·표 아닌 결과) — 실제 브라우저 ─────────────────────

CATALOG_HOME = """<!doctype html><html><head><meta charset="utf-8"><title>상점 홈</title></head><body>
<div class="side"><ul>
<li><a href="/cat/mystery.html">추리</a></li><li><a href="/cat/travel.html">여행</a></li><li><a href="/cat/poetry.html">시</a></li>
<li><a href="/cat/music.html">음악</a></li><li><a href="/cat/art.html">미술</a></li><li><a href="/logout">로그아웃</a></li></ul></div>
<main><h1>전체 상품</h1><ol class="row">
<li class="col"><article><h3><a href="/p/1.html" title="Sharp Objects 전체 제목">Sharp Obj...</a></h3><p class="price">£47.82</p><p>재고 있음</p></article></li>
<li class="col"><article><h3><a href="/p/2.html" title="In a Dark Dark Wood">In a Dark...</a></h3><p class="price">£19.63</p><p>재고 있음</p></article></li>
<li class="col"><article><h3><a href="https://other.test/x" title="외부 링크 상품">외부</a></h3><p class="price">£5.00</p><p>재고 있음</p></article></li>
<li class="col"><article><h3><a href="/p/4.html" title="The Past Never Ends">The Past...</a></h3><p class="price">£56.50</p><p>재고 있음</p></article></li>
</ol><ul class="pager"><li class="next"><a href="/cat/mystery-2.html">다음</a></li></ul></main></body></html>"""

CATALOG_NO_ITEMS = """<!doctype html><html><head><meta charset="utf-8"><title>빈 쪽</title></head><body><p>준비 중입니다</p></body></html>"""


def _catalog_context(browser, pages: dict[str, str]):
    context = browser.new_context()

    def handle(route):
        path = route.request.url.split(HOST, 1)[-1].split("?")[0] or "/"
        body = pages.get(path)
        if body is None:
            route.fulfill(status=404, body="not found")
        else:
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)

    context.route(f"http://{HOST}/**", handle)
    return context, context.new_page()


def test_real_snapshot_menu_excludes_product_cards_and_risky_links(browser):
    from ai_orchestrator.site_work import site_map_menu as menu
    from scripts.explorer.page_snapshot import collect

    context, page = _catalog_context(browser, {"/": CATALOG_HOME})
    try:
        page.goto(f"http://{HOST}/")
        got = menu.menu_from_snapshot(collect(page), risk_of=tm.risk_of, skip_fragments=tm.EXPLORE_SKIP_URL)
        assert [m["label"] for m in got] == ["추리", "여행", "시", "음악", "미술"]  # 사이드바 목록만 — 상품 링크·로그아웃·외부 링크 제외
        assert got[0]["href"] == f"http://{HOST}/cat/mystery.html"
    finally:
        context.close()


def test_page_without_table_returns_product_items_not_sidebar_and_next_url(browser):
    context, page = _catalog_context(browser, {"/": CATALOG_HOME})
    try:
        page.goto(f"http://{HOST}/")
        content = tr.read_page_content(page, HOST)
        assert content is not None and content["headings"][0] == "전체 상품"
        texts = [i["text"] for i in content["items"]]
        assert len(texts) == 4 and "£47.82" in texts[0] and "추리" not in " ".join(texts)  # 사이드바 카테고리가 아니라 상품 카드
        assert content["items"][0]["label"] == "Sharp Objects 전체 제목"  # 사이트가 줄인 글자 대신 title 속성
        assert content["items"][0]["href"] == f"http://{HOST}/p/1.html"
        assert content["items"][2]["href"] == ""  # 다른 호스트 링크는 돌려주지 않는다
        assert content["next_url"] == f"http://{HOST}/cat/mystery-2.html"
    finally:
        context.close()


def test_open_page_task_runs_on_a_page_without_table_and_returns_items(browser, tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "maps")
    context, page = _catalog_context(browser, {"/": CATALOG_HOME, "/cat/mystery.html": CATALOG_HOME})
    try:
        task = tm.open_page_task(HOST, f"http://{HOST}/", now=NOW)
        values = tm.validate_run_request(task, {"url": f"http://{HOST}/cat/mystery.html"})
        page.goto("about:blank")
        result = tr.execute_task(page, HOST, task, values)
        assert result["tables"] == [] and result["steps_done"] == 1
        assert len(result["items"]) == 4 and result["page"]["next_url"].endswith("/cat/mystery-2.html")
        assert "items" not in result["page"]  # 항목은 한 곳(items)에만
    finally:
        context.close()


def test_open_page_navigate_only_task_does_not_wait_for_a_table(browser):
    import time

    context, page = _catalog_context(browser, {"/": CATALOG_NO_ITEMS})
    try:
        task = tm.open_page_task(HOST, f"http://{HOST}/", now=NOW)
        t0 = time.monotonic()
        result = tr.execute_task(page, HOST, task, {"url": f"http://{HOST}/"})
        assert time.monotonic() - t0 < tr.RESULT_WAIT_S - 2  # 표가 없는 화면에서 갱신을 기다리지 않는다
        assert result["tables"] == [] and "items" not in result  # 항목도 소제목도 없으면 아무것도 지어내지 않는다
    finally:
        context.close()


def test_open_page_refuses_other_host_even_if_validation_were_skipped(browser):
    context, page = _catalog_context(browser, {"/": CATALOG_NO_ITEMS})
    try:
        task = tm.open_page_task(HOST, f"http://{HOST}/", now=NOW)
        with pytest.raises(tr.StepFailed, match="다른 주소"):
            tr.execute_task(page, HOST, task, {"url": "http://other.test/x"})  # 실행기의 이중 방어
        with pytest.raises(tr.StepFailed, match="열 주소"):
            tr.execute_task(page, HOST, task, {})
    finally:
        context.close()


def test_table_page_keeps_tables_and_adds_no_items(browser, tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "maps")
    context, page = make_page(browser, PAGE_HTML)
    try:
        task = explored_task(page)
        values = tm.validate_run_request(task, {"txtName": "삼성물산"})
        page.goto("about:blank")
        result = tr.execute_task(page, HOST, task, values)
        assert result["tables"] and "items" not in result and "page" not in result  # 표가 있으면 기존 응답 그대로
    finally:
        context.close()
