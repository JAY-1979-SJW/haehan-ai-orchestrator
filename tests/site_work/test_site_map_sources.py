"""사이트 업무 지도 M9 — 데이터 소스·사이트 선언 도구 기록. 순수 규칙 + 격리된 헤드리스 Chrome 의 가짜 SPA(외부 접속·사용자 9222 브라우저 없음).

2026-10-05 실측: 카페 포털(SPA)은 DOM 탐색 업무 0개였지만 JSON 데이터 API 11개가 호출됐다 → 그 구조(값 없이)를 지도에 남긴다.
기준서: docs/specs/2026-10-05_site_map_m9_precise_exploration.md
"""

from __future__ import annotations

import json

import pytest

from ai_orchestrator.site_work import site_map_sources as sd
from ai_orchestrator.site_work import site_task_map as tm
from ai_orchestrator.site_work import site_task_map_store as store
from scripts.explorer import data_sources as ds
from scripts.explorer import task_mapper

NOW = "2026-10-05T16:00:00+09:00"
HOST = "spa.fixture.test"

# ── 순수 규칙 ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "masked"),
    [
        ("/v1/cafes/12345/articles", "/v1/cafes/{id}/articles"),
        ("/hot/home/02310", "/hot/home/{id}"),
        ("/o/0123456789abcdef0123", "/o/{id}"),
        ("/o/123e4567-e89b-12d3-a456-426614174000", "/o/{id}"),
        ("/v3/homepc", "/v3/homepc"),
        (
            "/v1.0/cafes/10445200/menus/195/boards",
            "/v1.0/cafes/{id}/menus/{id}/boards",
        ),  # 게시판 번호처럼 짧은 숫자도 가린다(같은 API 가 번호만 달라 쪼개지지 않게)
        ("/v1/page/1234", "/v1/page/{id}"),
        ("/v3/homepc", "/v3/homepc"),
        ("/api/2/x", "/api/2/x"),  # 한 자리 숫자(버전 표지 등)는 그대로
        (
            "/cafe-web/6aJLIc9b3nlMUEwI4On-eZUowq7jq8OmWXgr9u8/profiles",
            "/cafe-web/{id}/profiles",
        ),  # 불투명 회원 키(2026-10-05 실측에서 경로에 그대로 저장됐다)
        (
            "/cafe-mobile/CafeMemberNetworkArticleListV3",
            "/cafe-mobile/CafeMemberNetworkArticleListV3",
        ),  # CamelCase API 이름은 식별자가 아니다
        ("/v1/WeeklyPopularArticleListV3.json", "/v1/WeeklyPopularArticleListV3.json"),
    ],
)
def test_mask_path_hides_long_ids_only(path, masked):
    assert sd.mask_path(path) == masked


@pytest.mark.parametrize(
    ("host", "path"),
    [
        ("nam.veta.naver.com", "/gfp/v1"),
        ("stats.example.test", "/track/click"),
        ("a.test", "/beacon"),
        ("a.test", "/v1/analytics/x"),
        ("a.test", "/ads/serve"),
        ("doubleclick.net", "/x"),
        ("ipada.cafe.naver.com", "/rs"),
    ],
)
def test_advertising_and_tracking_addresses_are_noise(host, path):
    assert sd.is_noise(host, path) is True
    assert sd.observe(host, path, "", {"a": 1}) is None


def test_query_keys_never_keep_values():
    keys = sd.query_keys("token=SECRET123&myCafeCount=500&&a=1&a=2&=x")
    assert keys == ["a", "myCafeCount", "token"] and "SECRET" not in str(keys)


def test_observe_keeps_structure_only_never_values():
    data = {
        "message": {
            "result": {
                "cafes": [{"cafeName": "비밀 카페 이름", "count": 5, "token": "SECRET"}, {"cafeName": "x"}],
                "total": 2,
            }
        },
        "status": "ok",
    }
    src = sd.observe("api.example.test", "/v3/cafes/987654321/list", "token=SECRET&limit=10", data)
    assert src is not None
    assert (
        src["path"] == "/v3/cafes/{id}/list"
        and src["query_keys"] == ["limit", "token"]
        and src["top_keys"] == ["message", "status"]
    )
    assert src["lists"] == [{"path": "message.result.cafes", "count": 2, "fields": ["cafeName", "count", "token"]}]
    blob = json.dumps(src, ensure_ascii=False)
    assert (
        "비밀 카페" not in blob and "SECRET" not in blob and "987654321" not in blob
    )  # 값·식별자가 지도에 들어가지 않는다


def test_ad_slot_responses_are_dropped_by_field_names():
    """광고 서버는 주소가 낯설어도 응답 필드(adIndex·adUnit)로 가려낸다 — 'ahead…' 같은 평범한 이름은 광고가 아니다."""
    assert sd.observe("x.test", "/v1", "", {"ads": [], "slots": [{"adIndex": 1}]}) is None
    assert sd.observe("x.test", "/rs", "", {"list": [{"adUnit": "a", "sharePercent": 1}]}) is None
    assert sd.observe("x.test", "/ok", "", {"list": [{"aheadOfTime": "1시간 전", "articleId": 1}]}) is not None


def test_lists_of_is_bounded_and_ignores_non_object_lists():
    data = {f"k{i}": [{"a": 1}] for i in range(20)} | {"ids": [1, 2, 3], "empty": []}
    found = sd.lists_of(data)
    assert len(found) == sd.LISTS_MAX and all(item["path"].startswith("k") for item in found)
    assert sd.lists_of([{"x": 1}]) == [{"path": "", "count": 1, "fields": ["x"]}]


def _src(path="/a", count=3, fields=("f",), seen=1, qk=()):
    return {
        "host": "h.test",
        "path": path,
        "query_keys": list(qk),
        "top_keys": ["t"],
        "lists": [{"path": "l", "count": count, "fields": list(fields)}],
        "seen": seen,
    }


def test_merge_sources_merges_same_source_max_count_sum_seen_and_orders_by_seen():
    base = tm.empty_map(HOST, now=NOW)
    one = sd.merge_sources(base, [_src("/a", 3, ("f",), qk=("q",))], now=NOW)
    two = sd.merge_sources(one, [_src("/a", 9, ("g",), seen=2, qk=("z",)), _src("/b")], now="later")
    by_path = {s["path"]: s for s in two["data_sources"]}
    a = by_path["/a"]
    assert (
        a["seen"] == 3
        and a["lists"][0]["count"] == 9
        and a["lists"][0]["fields"] == ["f", "g"]
        and a["query_keys"] == ["q", "z"]
    )
    assert [s["path"] for s in two["data_sources"]] == ["/a", "/b"] and two["data_sources_at"] == "later"


def test_merge_sources_re_masks_previously_stored_paths_and_merges_duplicates():
    """규칙이 강화되기 전에 저장된 식별자(예: 회원 키)가 지도에 남지 않게 — 병합할 때 저장분도 현재 규칙으로 다시 가리고 같아진 것은 합친다."""
    leaked = "6aJLIc9b3nlMUEwI4On-eZUowq7jq8OmWXgr9u8"
    stored = tm.empty_map(HOST, now=NOW)
    stored["data_sources"] = [
        _src(f"/cafe-web/{leaked}/profiles", 2, seen=3),
        _src("/cafe-web/{id}/profiles", 5, seen=2),
        _src("/menus/195/heads", 1),
    ]
    out = sd.merge_sources(stored, [], now="later")
    assert out is not stored and leaked not in json.dumps(out["data_sources"])
    by_path = {s["path"]: s for s in out["data_sources"]}
    assert (
        by_path["/cafe-web/{id}/profiles"]["seen"] == 5 and by_path["/cafe-web/{id}/profiles"]["lists"][0]["count"] == 5
    )  # 같아진 두 건을 합쳤다
    assert "/menus/{id}/heads" in by_path
    assert sd.merge_sources(out, [], now="again") is out  # 이미 정리돼 있으면 그대로


def test_merge_sources_returns_same_object_when_nothing_new_and_respects_cap():
    base = sd.merge_sources(tm.empty_map(HOST, now=NOW), [_src("/a")], now=NOW)
    assert (
        sd.merge_sources(base, [_src("/a", 3, ("f",), seen=0)], now="later") is base
        or sd.merge_sources(base, [], now="later") is base
    )
    many = sd.merge_sources(tm.empty_map(HOST, now=NOW), [_src(f"/p{i}") for i in range(sd.SOURCES_MAX + 20)], now=NOW)
    assert (
        len(many["data_sources"]) == sd.SOURCES_MAX and many["data_sources_seen"] == sd.SOURCES_MAX + 20
    )  # 잘렸다는 것을 총수로 알린다
    assert sd.merge_sources(many, [_src("/p0")], now="later")["data_sources_seen"] == sd.SOURCES_MAX + 20


def test_clean_tool_normalizes_and_limits_site_supplied_text():
    tool = sd.clean_tool(
        {
            "kind": "declarative",
            "name": "검색\n도구" + "x" * 100,
            "description": "설명 \x00 줄\n바꿈 " + "y" * 500,
            "input_schema": {"properties": {"q": {}, "page": {}}, "required": ["q", 7]},
        }
    )
    assert tool is not None and "\n" not in tool["name"] and len(tool["description"]) <= sd.TOOL_TEXT_MAX
    assert tool["fields"] == ["page", "q"] and tool["required"] == ["q"] and tool["kind"] == "declarative"
    assert sd.clean_tool({"name": "  "}) is None and sd.clean_tool({"description": "이름 없음"}) is None
    assert sd.clean_tool({"name": "t", "input_schema": "not a dict"})["fields"] == []  # 형식이 틀려도 죽지 않는다


def test_merge_tools_dedupes_by_name_and_is_noop_without_new_tools():
    base = tm.empty_map(HOST, now=NOW)
    one = sd.merge_tools(base, [{"name": "a", "description": "d"}, {"name": "a"}, {"name": ""}], now=NOW)
    assert [t["name"] for t in one["declared_tools"]] == ["a"]
    assert sd.merge_tools(one, [{"name": "a"}], now="later") is one


def test_summary_limits_sources_and_reports_total():
    site_map = sd.merge_sources(tm.empty_map(HOST, now=NOW), [_src(f"/p{i}") for i in range(30)], now=NOW)
    out = sd.summary(site_map, limit=20)
    assert len(out["data_sources"]) == 20 and out["data_sources_total"] == 30 and "declared_tools" not in out
    assert out["data_sources_seen"] == 30 and out["data_sources_truncated"] is False
    assert sd.summary(tm.empty_map(HOST, now=NOW)) == {}


# ── 기록기(가짜 페이지·응답) ───────────────────────────────────


class FakeResp:
    def __init__(self, url, *, body, **opts):
        """opts: ctype·status·method·rtype·length·boom (모두 선택)."""
        self.url, self._body, self.status = url, body, opts.get("status", 200)
        self._boom = opts.get("boom", False)
        length = opts.get("length")
        self.headers = {
            "content-type": opts.get("ctype", "application/json"),
            **({"content-length": str(length)} if length is not None else {}),
        }
        self.request = type(
            "Req", (), {"method": opts.get("method", "GET"), "resource_type": opts.get("rtype", "xhr")}
        )()

    def json(self):
        if self._boom:
            raise ValueError("본문 없음")
        return self._body


class FakePage:
    def __init__(self, tools=None):
        self.handlers, self.waited, self._tools = [], [], tools or []

    def on(self, name, handler):
        self.handlers.append((name, handler))

    def remove_listener(self, name, handler):
        self.handlers.remove((name, handler))

    def wait_for_timeout(self, ms):
        self.waited.append(ms)

    def evaluate(self, _js):
        return self._tools


def test_recorder_collects_in_handler_but_reads_only_on_flush():
    rec, page = ds.ResponseRecorder(settle_ms=250), FakePage()
    rec.attach(page)
    ((_, handler),) = page.handlers
    good = FakeResp("https://api.test/v1/list/12345678?token=SECRET&n=1", body={"items": [{"a": 1}]})
    reads = []
    good.json = lambda: reads.append("read") or {"items": [{"a": 1}]}  # type: ignore[method-assign]
    handler(good)
    assert reads == [] and rec.sources == []  # 핸들러 안에서는 본문을 읽지 않는다(동기 호출은 이동을 멈춘다)
    assert rec.flush(page) == 1 and reads == ["read"] and page.waited == [250]
    (src,) = rec.sources
    assert src["path"] == "/v1/list/{id}" and src["query_keys"] == ["n", "token"] and "SECRET" not in json.dumps(src)
    assert rec.flush(page) == 0  # 이미 읽은 응답은 다시 읽지 않는다
    rec.detach(page)
    assert page.handlers == []


def test_recorder_ignores_non_get_non_xhr_non_json_error_status_noise_and_unreadable():
    rec, page = ds.ResponseRecorder(), FakePage()
    rec.attach(page)
    ((_, handler),) = page.handlers
    for resp in (
        FakeResp("https://a.test/x", body={"a": 1}, method="POST"),
        FakeResp("https://a.test/img.png", body={"a": 1}, rtype="image"),
        FakeResp("https://a.test/x", body={"a": 1}, status=500),
        FakeResp("https://a.test/html", body={}, ctype="text/html"),
        FakeResp("https://nam.veta.test/gfp/v1", body={"a": 1}),  # 광고·추적
        FakeResp("https://a.test/big", body={"a": 1}, length=ds.BODY_MAX + 1),
        FakeResp("https://a.test/broken", body=None, boom=True),
    ):
        handler(resp)
    assert rec.flush(page) == 0 and rec.sources == []


def test_recorder_pending_is_bounded_and_survives_pages_without_events():
    rec, page = ds.ResponseRecorder(pending_max=3), FakePage()
    rec.attach(page)
    ((_, handler),) = page.handlers
    for i in range(10):
        handler(FakeResp(f"https://a.test/p{i}", body={"k": [{"a": 1}]}))
    assert rec.flush(page) == 3
    rec2 = ds.ResponseRecorder()
    rec2.attach(object())  # on() 이 없는 페이지에서도 예외 없이 건너뛴다
    assert rec2.flush(None) == 0


def test_recorder_reads_declared_tools_from_the_page():
    rec = ds.ResponseRecorder()
    rec.flush(
        FakePage(
            tools=[
                {
                    "kind": "declarative",
                    "name": "search",
                    "description": "검색",
                    "input_schema": {"properties": {"q": {}}, "required": ["q"]},
                },
                "not a dict",
            ]
        )
    )
    assert [t["name"] for t in rec.tools] == ["search"]


# ── 탐색 연결(가짜 탐색 함수) ────────────────────────────────


class ExplorePage:
    def __init__(self):
        self.url = f"https://{HOST}/"

    def on(self, *_a):
        pass

    def remove_listener(self, *_a):
        pass

    def goto(self, url, **_k):
        self.url = url


@pytest.fixture
def maps(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path / "maps")


def test_explore_to_map_stores_sources_and_tools_and_reports_counts(maps):
    class Rec:
        def __init__(self):
            self.sources = [_src("/portal/list", 5, ("cafeName",))]
            self.tools = [{"kind": "declarative", "name": "find", "description": "d"}]
            self.flushed = 0

        def attach(self, _page):
            pass

        def detach(self, _page):
            pass

        def flush(self, _page=None):
            self.flushed += 1

    rec = Rec()
    seen_kwargs = {}

    def fake_explore(page, **kw):
        seen_kwargs.update(kw)
        kw["on_page"](page)  # 탐색기가 쪽을 읽은 직후 콜백을 부른다
        return {
            "host": HOST,
            "pages": [{"url": f"https://{HOST}/", "forms_count": 0, "controls_count": 0, "form_summary": {}}],
            "visited_count": 1,
            "aborted_reason": "",
        }

    out = task_mapper.explore_to_map(
        ExplorePage(),
        f"https://{HOST}/",
        explore_fn=fake_explore,
        collect_fn=lambda _p: {},
        sleep_fn=lambda _s: None,
        recorder_factory=lambda: rec,
    )
    assert rec.flushed == 1 and "on_page" in seen_kwargs
    assert out["data_sources"] == 1 and out["declared_tools"] == 1
    saved = store.load(HOST)
    assert saved["data_sources"][0]["path"] == "/portal/list" and saved["declared_tools"][0]["name"] == "find"
    assert "SECRET" not in json.dumps(saved)


# ── 실제 헤드리스 브라우저: 가짜 SPA ──────────────────────────

SPA_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>포털</title></head><body><div id="app">로딩</div>
<form toolname="find_cafe" tooldescription="카페 검색"><input name="q" required><input name="page"></form>
<script>
fetch('/api/v3/cafes/987654321/list?token=SECRET&limit=5').then(r => r.json()).then(d => { document.getElementById('app').textContent = d.items.length; });
fetch('/gfp/v1/track?x=1');
fetch('/api/echo', {method: 'POST', body: '{}'});
fetch('/api/text');
</script></body></html>"""


def _route(route):
    path = route.request.url.split(HOST, 1)[-1]
    if path == "/":
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=SPA_HTML)
    elif path.startswith("/api/v3/cafes/"):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"items": [{"cafeName": "비밀 이름", "n": 1}, {"cafeName": "다른 이름", "n": 2}], "total": 2}
            ),
        )
    elif path.startswith("/gfp/"):
        route.fulfill(status=200, content_type="application/json", body='{"track": [{"a": 1}]}')
    elif path.startswith("/api/echo"):
        route.fulfill(status=200, content_type="application/json", body='{"ok": [{"a": 1}]}')
    else:
        route.fulfill(status=200, content_type="text/plain", body="plain")




def test_real_spa_page_yields_structure_without_values_and_navigation_is_not_blocked(browser):
    context = browser.new_context()
    context.route(f"https://{HOST}/**", _route)
    page = context.new_page()
    rec = ds.ResponseRecorder(settle_ms=600)
    rec.attach(page)
    try:
        page.goto(f"https://{HOST}/", wait_until="domcontentloaded", timeout=15000)  # 핸들러가 이동을 막지 않는다
        assert rec.flush(page) >= 1
        paths = {(s["host"], s["path"]) for s in rec.sources}
        assert paths == {(HOST, "/api/v3/cafes/{id}/list")}  # POST·텍스트·광고·추적은 빠졌다
        (src,) = rec.sources
        assert src["query_keys"] == ["limit", "token"]
        assert src["lists"] == [{"path": "items", "count": 2, "fields": ["cafeName", "n"]}] and src["top_keys"] == [
            "items",
            "total",
        ]
        blob = json.dumps(rec.sources, ensure_ascii=False)
        assert "비밀 이름" not in blob and "SECRET" not in blob and "987654321" not in blob
        assert [t["name"] for t in rec.tools] == ["find_cafe"]  # 선언형 도구 탐지(실행하지 않음)
        cleaned = sd.clean_tool(rec.tools[0])  # 기록기는 원본을 들고 있고 정리는 병합(merge_tools)에서 한다
        assert (
            cleaned is not None
            and cleaned["fields"] == ["page", "q"]
            and cleaned["required"] == ["q"]
            and cleaned["kind"] == "declarative"
        )
    finally:
        rec.detach(page)
        context.close()
