from __future__ import annotations

import json

import pytest

from scripts.browser.session.browser_cdp_selection_gate import CdpPage, CdpSession
from scripts.naver import router
from scripts.naver.cafe import cli_router as router_cafe
from scripts.naver.cafe import join_request, main_page, member_collect, topic_search
from scripts.naver.cafe import list_background_runner as runner
from scripts.naver.cafe import list_collector as collector
from scripts.naver.cafe.collection import member_collect as member_collect_impl


def _api_payload(*, total: int = 1) -> dict:
    return {
        "message": {
            "status": "200",
            "error": {"code": "", "msg": ""},
            "result": {
                "pageInfo": {"page": 1, "perPage": 100, "totalCount": total, "lastPage": True},
                "cafes": [
                    {
                        "cafeId": 10445200,
                        "cafeName": "건설공무",
                        "cafeUrl": "0moo",
                        "articleNewCounts": 132,
                        "lastUpdateDate": "2026-05-27 00:20:45",
                        "lastVisitDate": "2026-05-20 09:43:53",
                        "favoriteCafe": True,
                        "manageCafe": False,
                        "powerCafe": True,
                        "hasNewArticle": True,
                    }
                ],
            },
        }
    }


def test_parse_api_payload_normalizes_cafe_fields():
    items, page_info = collector.parse_api_payload(_api_payload(), source="join")

    assert page_info["totalCount"] == 1
    assert len(items) == 1
    assert items[0].cafe_id == 10445200
    assert items[0].name == "건설공무"
    assert items[0].url == "https://cafe.naver.com/0moo"
    assert items[0].new_articles == 132
    assert items[0].favorite is True
    assert items[0].power is True


def test_parse_api_payload_accepts_json_string():
    items, _ = collector.parse_api_payload(json.dumps(_api_payload(), ensure_ascii=False), source="favorite")

    assert items[0].source == "favorite"
    assert items[0].cafe_url == "0moo"


def test_parse_api_payload_rejects_error_status():
    payload = _api_payload()
    payload["message"]["status"] = "500"

    with pytest.raises(ValueError, match="cafe_api_status_not_200"):
        collector.parse_api_payload(payload)


def test_build_report_keeps_join_favorite_manage_counts():
    raw = {
        "joinTotal": 77,
        "favoriteTotal": 9,
        "manageTotal": 1,
        "joined": _api_payload()["message"]["result"]["cafes"],
        "favorites": _api_payload()["message"]["result"]["cafes"],
        "manages": _api_payload()["message"]["result"]["cafes"],
    }

    report = collector.build_report(raw)

    assert report.ok is True
    assert report.joined_total == 77
    assert report.favorite_total == 9
    assert report.manage_total == 1
    assert report.joined[0].source == "join"
    assert report.favorites[0].source == "favorite"
    assert report.manages[0].source == "manage"


def test_fetch_expression_uses_readonly_cafe_home_apis():
    expr = collector.build_fetch_expression(per_page=500)

    assert "fetch(" in expr
    assert 'credentials: "include"' in expr
    assert "/v1/cafes/${type}" in expr
    assert "perPage=${perPage}" in expr
    assert "POST" not in expr
    assert "DELETE" not in expr
    assert "PUT" not in expr


def test_background_runner_can_select_mixed_session_for_readonly():
    sessions = [
        CdpSession(
            host="127.0.0.1",
            port=9222,
            pages=[
                CdpPage(url="https://mail.naver.com/", title="Naver Mail"),
                CdpPage(url="https://accounts.google.com/", title="Google"),
            ],
        )
    ]

    session, selection = runner.select_naver_session(sessions=sessions, allow_mixed_readonly=True)

    assert session is sessions[0]
    assert selection.code == "mixed_domain_session"


def test_background_runner_strict_mode_blocks_mixed_session():
    sessions = [
        CdpSession(
            host="127.0.0.1",
            port=9222,
            pages=[
                CdpPage(url="https://mail.naver.com/", title="Naver Mail"),
                CdpPage(url="https://accounts.google.com/", title="Google"),
            ],
        )
    ]

    session, selection = runner.select_naver_session(sessions=sessions, allow_mixed_readonly=False)

    assert session is None
    assert selection.code == "mixed_domain_session"


def test_find_cafe_target_prefers_section_cafe(monkeypatch):
    pages = [
        {"id": "mail", "url": "https://mail.naver.com/", "title": "Mail"},
        {"id": "cafe", "url": "https://section.cafe.naver.com/ca-fe/home", "title": "Cafe"},
    ]
    monkeypatch.setattr(runner.cdp, "list_pages", lambda port: pages)

    target_id, page = runner.find_cafe_target_id(port=9222)

    assert target_id == "cafe"
    assert page["title"] == "Cafe"


def test_create_isolated_cafe_target_creates_new_tab(monkeypatch):
    calls = []

    class FakeIsolationReport:
        ok = True
        target_id = "iso"
        page = {"id": "iso", "url": "https://cafe.naver.com/royaltyserver", "title": "AI스터디"}

    def fake_create_isolated_target(**kwargs):
        calls.append(kwargs)
        return FakeIsolationReport()

    monkeypatch.setattr(runner, "create_isolated_target", fake_create_isolated_target)

    target_id, page = runner.create_isolated_cafe_target(port=9222, work="join-request", cafe_url="royaltyserver")

    assert target_id == "iso"
    assert calls == [
        {
            "task": "naver",
            "work": "cafe:join-request",
            "port": 9222,
            "start_url": "https://cafe.naver.com/royaltyserver",
        }
    ]
    assert page["title"] == "AI스터디"


def test_router_cafe_list_uses_attach_only_collector(monkeypatch, tmp_path):
    calls = []

    class FakeReport:
        ok = True
        cafes = [{"name": "건설공무", "url": "https://cafe.naver.com/0moo"}]
        favorites = []
        manages = []
        joined_total = 1
        favorite_total = 0
        manage_total = 0

        def to_dict(self):
            return {"ok": True}

    def fake_collect_background(**kwargs):
        calls.append(kwargs)
        return FakeReport()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(router, "gate_check", lambda *a, **k: None)
    monkeypatch.setattr(runner, "collect_background", fake_collect_background)

    router._cmd_cafe("list", [])

    assert calls == [{"allow_mixed_readonly": True, "per_page": 100}]
    payload = json.loads((tmp_path / "data" / "naver_cafes_latest.json").read_text(encoding="utf-8"))
    assert payload["attach_only"] is True
    assert payload["browser_launch"] is False
    assert payload["cafes"][0]["name"] == "건설공무"


def test_main_page_build_report_covers_home_sections_and_actions():
    raw = {
        "href": "https://section.cafe.naver.com/ca-fe/home",
        "title": "네이버 카페",
        "responses": {
            "user": {
                "ok": True,
                "httpStatus": 200,
                "payload": {"message": {"status": "200", "result": {"loggedIn": True, "userId": "u"}}},
            },
            "home": {
                "ok": True,
                "httpStatus": 200,
                "payload": {
                    "message": {
                        "status": "200",
                        "result": {"myCafe": {"cafes": _api_payload()["message"]["result"]["cafes"]}},
                    }
                },
            },
            "recommend": {
                "ok": True,
                "httpStatus": 200,
                "payload": {
                    "message": {
                        "status": "200",
                        "result": {"themes": [{"themeId": 1, "themeName": "게임"}], "cafes": []},
                    }
                },
            },
            "power_cafes": {
                "ok": True,
                "httpStatus": 200,
                "payload": {
                    "message": {"status": "200", "result": {"cafes": _api_payload()["message"]["result"]["cafes"]}}
                },
            },
            "mynews": {
                "ok": True,
                "httpStatus": 200,
                "payload": {
                    "message": {
                        "status": "200",
                        "result": {
                            "myNewsCounts": {"totalCount": 1},
                            "myNewsActivities": {
                                "messages": [
                                    {
                                        "category": "CAFE_NOTICE",
                                        "messageKey": "m1",
                                        "view": {
                                            "header": "새 공지",
                                            "content": "본문",
                                            "cafeName": "건설공무",
                                            "writeTime": "방금",
                                            "unread": True,
                                        },
                                        "direction": {"cafeId": 10445200, "articleId": 1},
                                        "webDirection": {"url": "https://cafe.naver.com/0moo/1"},
                                    }
                                ]
                            },
                        },
                    }
                },
            },
            "note_count": {"ok": True, "httpStatus": 200, "payload": {"message": {"status": "200", "result": 0}}},
            "notices": {
                "ok": True,
                "httpStatus": 200,
                "payload": {"message": {"status": "200", "result": {"notices": [{"noticeId": 1, "subject": "점검"}]}}},
            },
        },
    }

    report = main_page.build_report(raw)

    assert report.ok is True
    assert report.user["loggedIn"] is True
    assert report.sections["my_cafes"][0]["name"] == "건설공무"
    assert report.sections["power_cafes"][0]["source"] == "power"
    assert report.sections["mynews_counts"]["totalCount"] == 1
    assert report.sections["mynews_items"][0]["url"] == "https://cafe.naver.com/0moo/1"
    feature_keys = {feature.key for feature in report.features}
    assert {"my_cafes", "recommend_cafes", "mynews", "feed_config_update", "create_cafe"} <= feature_keys
    assert all(plan.approval_required and plan.final_submit_blocked for plan in report.action_plans)


def test_main_page_prepare_action_blocks_final_submit():
    plan = main_page.prepare_main_action("favorite_toggle", cafe_id=10445200, enabled=True)

    assert plan.approval_gate == "naver_cafe_favorite_update"
    assert plan.final_submit_blocked is True
    assert plan.fields["cafe_id"] == 10445200


def test_main_page_execute_action_requires_approval():
    plan = main_page.prepare_main_action("mynews_update", message_key="m1")

    with pytest.raises(Exception):
        main_page.execute_main_action_plan(plan)


def test_background_runner_main_mode_returns_sections(monkeypatch):
    sessions = [
        CdpSession(host="127.0.0.1", port=9222, pages=[CdpPage(url="https://section.cafe.naver.com/", title="Cafe")])
    ]

    class FakeReport:
        ok = True
        code = "ok"
        href = "https://section.cafe.naver.com/ca-fe/home"
        title = "네이버 카페"
        user = {"loggedIn": True}
        endpoint_statuses = {"home": {"ok": True}}
        sections = {"my_cafes": [{"name": "건설공무"}]}
        features = [main_page.build_feature_catalog()[0]]
        action_plans = [main_page.prepare_main_action("favorite_toggle")]
        messages = ["ok"]

    monkeypatch.setattr(
        runner, "select_naver_session", lambda **kwargs: (sessions[0], runner.evaluate_sessions("naver", sessions))
    )
    monkeypatch.setattr(
        runner,
        "create_isolated_cafe_target",
        lambda *, port, work, cafe_url="": (
            "target",
            {"id": "target", "url": "https://section.cafe.naver.com/", "title": "Cafe"},
        ),
    )
    monkeypatch.setattr(
        runner.cdp,
        "list_pages",
        lambda port: [{"id": "target", "url": "https://section.cafe.naver.com/ca-fe/home", "title": "네이버 카페"}],
    )
    monkeypatch.setattr(main_page, "collect_main_from_target", lambda target_id, *, port: FakeReport())

    report = runner.collect_main_background(allow_mixed_readonly=True)

    assert report.ok is True
    assert report.sections["my_cafes"][0]["name"] == "건설공무"
    assert report.action_plans[0]["approval_gate"] == "naver_cafe_favorite_update"


def test_router_cafe_home_uses_attach_only_main_collector(monkeypatch, tmp_path):
    calls = []

    class FakeReport:
        ok = True
        code = "ok"

        def to_dict(self):
            return {
                "ok": True,
                "code": "ok",
                "sections": {"my_cafes": [{"name": "건설공무"}]},
                "features": [],
                "action_plans": [],
            }

    def fake_collect_main_background(**kwargs):
        calls.append(kwargs)
        return FakeReport()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(router, "gate_check", lambda *a, **k: None)
    monkeypatch.setattr(runner, "collect_main_background", fake_collect_main_background)

    router._cmd_cafe("home", [])

    assert calls == [{"allow_mixed_readonly": True}]
    payload = json.loads((tmp_path / "data" / "naver_cafe_main_latest.json").read_text(encoding="utf-8"))
    assert payload["attach_only"] is True
    assert payload["browser_close"] is False
    assert payload["sections"]["my_cafes"][0]["name"] == "건설공무"


def test_topic_search_builds_utf8_encoded_search_url():
    keyword = "\uc140\ud504 \uc778\ud14c\ub9ac\uc5b4"
    url = topic_search.build_search_url(keyword)

    assert "where=article" in url
    assert "%EC%85%80%ED%94%84+%EC%9D%B8%ED%85%8C%EB%A6%AC%EC%96%B4" in url
    assert keyword not in url


def test_topic_search_split_keywords_defaults_and_dedupes():
    interior = "\uc778\ud14c\ub9ac\uc5b4"
    automation = "AI \uc790\ub3d9\ud654"

    assert topic_search.split_keywords(f"{interior}, {automation}, {interior}") == [interior, automation]
    assert "\ucc57GPT" in topic_search.split_keywords("")


def test_topic_search_build_report_counts_keywords_and_cafes():
    chatgpt = "\ucc57GPT"
    automation = "AI \uc790\ub3d9\ud654"
    cafe = "\uc5c5\ubb34\uc790\ub3d9\ud654 \uce74\ud398"
    report = topic_search.build_report(
        [
            {
                "keyword": chatgpt,
                "items": [
                    {
                        "keyword": chatgpt,
                        "rank": 1,
                        "title": "\ucc57GPT\ub85c PPT \ub9cc\ub4e4\uae30",
                        "url": "https://cafe.naver.com/example/1",
                        "cafe_name": cafe,
                        "snippet": "PPT automation case",
                    }
                ],
            },
            {
                "keyword": automation,
                "items": [
                    {
                        "keyword": automation,
                        "rank": 1,
                        "title": "repetitive task automation",
                        "url": "https://cafe.naver.com/example/2",
                        "cafe_name": cafe,
                        "snippet": "workflow automation question",
                    }
                ],
            },
        ],
        keywords=[chatgpt, automation],
    )

    assert report.ok is True
    assert report.total_items == 2
    assert report.keyword_counts == {chatgpt: 1, automation: 1}
    assert report.top_cafes[0] == {"cafe_name": cafe, "count": 2}


def test_background_runner_topic_search_mode_returns_attach_only_report(monkeypatch):
    sessions = [
        CdpSession(host="127.0.0.1", port=9222, pages=[CdpPage(url="https://section.cafe.naver.com/", title="Cafe")])
    ]
    chatgpt = "\ucc57GPT"

    class FakeReport:
        ok = True
        code = "ok"
        keywords = [chatgpt]
        total_items = 1
        items = [
            topic_search.CafeTopicSearchItem(keyword=chatgpt, rank=1, title="post", url="https://cafe.naver.com/a/1")
        ]
        keyword_counts = {chatgpt: 1}
        top_cafes = [{"cafe_name": "a", "count": 1}]
        messages = ["ok"]

    monkeypatch.setattr(
        runner, "select_naver_session", lambda **kwargs: (sessions[0], runner.evaluate_sessions("naver", sessions))
    )
    monkeypatch.setattr(
        runner,
        "create_isolated_cafe_target",
        lambda *, port, work, cafe_url="": (
            "target",
            {"id": "target", "url": "https://section.cafe.naver.com/", "title": "Cafe"},
        ),
    )
    monkeypatch.setattr(
        runner.cdp,
        "list_pages",
        lambda port: [{"id": "target", "url": "https://search.naver.com/search.naver", "title": "Search"}],
    )
    monkeypatch.setattr(topic_search, "collect_topic_search_from_target", lambda target_id, **kwargs: FakeReport())

    report = runner.collect_topic_search_background(allow_mixed_readonly=True, keywords=chatgpt, limit_per_keyword=3)

    assert report.ok is True
    assert report.keywords == [chatgpt]
    assert report.total_items == 1
    assert "isolated tab" in report.messages[0]
    assert "no browser launch" in report.messages[0]


def test_router_cafe_topic_search_uses_attach_only_collector(monkeypatch, tmp_path):
    calls = []
    interior = "\uc778\ud14c\ub9ac\uc5b4"
    automation = "AI \uc790\ub3d9\ud654"

    class FakeReport:
        ok = True
        code = "ok"

        def to_dict(self):
            return {
                "ok": True,
                "code": "ok",
                "keywords": [interior, automation],
                "total_items": 1,
                "items": [
                    {
                        "keyword": interior,
                        "title": "\uc140\ud504 \uc778\ud14c\ub9ac\uc5b4",
                        "url": "https://cafe.naver.com/a/1",
                    }
                ],
                "keyword_counts": {interior: 1, automation: 0},
                "top_cafes": [],
            }

    def fake_collect_topic_search_background(**kwargs):
        calls.append(kwargs)
        return FakeReport()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(router, "gate_check", lambda *a, **k: None)
    monkeypatch.setattr(runner, "collect_topic_search_background", fake_collect_topic_search_background)

    router._cmd_cafe("topic-search", [f"--query={interior},{automation}", "--limit=7"])

    assert calls == [{"allow_mixed_readonly": True, "keywords": f"{interior},{automation}", "limit_per_keyword": 7}]
    payload = json.loads((tmp_path / "data" / "naver_cafe_topic_search_latest.json").read_text(encoding="utf-8"))
    assert payload["attach_only"] is True
    assert payload["browser_launch"] is False
    assert payload["keywords"] == [interior, automation]


def test_member_collect_filters_home_links_readonly():
    links = [
        {"text": "QnA smart store", "href": "https://cafe.naver.com/ArticleList.nhn?search.menuid=633"},
        {"text": "SmartStore upload help", "href": "https://cafe.naver.com/soho/1"},
        {"text": "hello", "href": "https://example.com/"},
    ]

    boards, articles = member_collect_impl._filtered_links(links, terms=["smart", "SmartStore", "upload"])

    assert len(boards) == 2
    assert articles == [
        {
            "text": "SmartStore upload help",
            "href": "https://cafe.naver.com/soho/1",
            "matched_terms": ["SmartStore", "upload"],
        }
    ]


def test_member_collect_soho_board_hints_are_registered():
    hints = member_collect.board_hints_for("https://cafe.naver.com/soho")

    assert [hint.key for hint in hints] == [
        "startup_ops",
        "smartstore",
        "coupang_ads",
        "marketing_ads",
        "logistics",
        "purchase_agent",
    ]
    assert {hint.club_id for hint in hints} == {"10094408"}


def test_member_collect_royaltyserver_board_hints_are_registered():
    hints = member_collect.board_hints_for("royaltyserver")

    assert [hint.key for hint in hints] == [
        "ai_jobs",
        "ai_tool_errors",
        "ai_work_share",
        "ai_news",
        "sns_marketing_ai",
        "ai_image_video",
        "ai_business",
        "ai_education",
    ]
    assert {hint.club_id for hint in hints} == {"22417348"}
    assert hints[1].board_type == "I"


def test_member_collect_board_urls_use_registered_club_id(monkeypatch):
    navigated = []

    monkeypatch.setattr(member_collect, "gate_check", lambda *a, **k: None)
    monkeypatch.setattr(member_collect.cdp, "navigate", lambda target_id, url, *, port: navigated.append(url))
    monkeypatch.setattr(
        member_collect.list_collector,
        "evaluate_async",
        lambda target_id, expr, *, port, timeout: {"frameHref": "https://cafe.naver.com/", "body": "", "links": []},
    )

    hint = member_collect.CafeBoardHint(
        key="ai_business",
        label="AI업무활용법",
        club_id="22417348",
        menu_id="67",
        board_type="L",
    )
    report = member_collect.collect_boards_from_target(
        "target", port=9222, cafe_url="royaltyserver", hints=[hint], wait_s=0
    )

    assert report.ok is True
    assert "search.clubid%3D22417348" in navigated[0]
    assert "search.menuid%3D67" in navigated[0]


def test_background_runner_joined_cafe_collect_returns_payload(monkeypatch):
    sessions = [
        CdpSession(host="127.0.0.1", port=9222, pages=[CdpPage(url="https://cafe.naver.com/soho", title="Cafe")])
    ]

    class FakeReport:
        ok = True
        code = "ok"
        messages = ["ok"]

        def to_dict(self):
            return {"ok": True, "cafe_url": "soho", "articles": [{"text": "SmartStore upload help"}]}

    monkeypatch.setattr(
        runner, "select_naver_session", lambda **kwargs: (sessions[0], runner.evaluate_sessions("naver", sessions))
    )
    monkeypatch.setattr(
        runner,
        "create_isolated_cafe_target",
        lambda *, port, work, cafe_url="": (
            "target",
            {"id": "target", "url": "https://cafe.naver.com/soho", "title": "Cafe"},
        ),
    )
    monkeypatch.setattr(
        runner.cdp, "list_pages", lambda port: [{"id": "target", "url": "https://cafe.naver.com/soho", "title": "Cafe"}]
    )
    monkeypatch.setattr(member_collect, "collect_home_from_target", lambda target_id, **kwargs: FakeReport())

    report = runner.collect_joined_cafe_background(cafe_url="soho", mode="home", allow_mixed_readonly=True)

    assert report.ok is True
    assert report.payload["articles"][0]["text"] == "SmartStore upload help"
    assert "isolated tab" in report.messages[0]
    assert "no browser launch" in report.messages[0]


def test_join_request_build_plan_is_approval_gated():
    report = join_request.build_join_plan(
        cafe_url="royaltyserver",
        nickname="해한AI",
        purpose="AI 자동화 사례 조사",
        raw={
            "href": "https://cafe.naver.com/royaltyserver",
            "title": "AI스터디",
            "joinAvailable": True,
            "fields": [{"name": "nickname", "label": "별명", "kind": "text", "required": True}],
            "buttons": [{"text": "가입하기"}],
        },
    )

    assert report.ok is True
    assert report.cafe_url == "royaltyserver"
    assert report.approval_gate == "naver_cafe_join_submit"
    assert report.final_submit_blocked is True
    assert report.join_available is True


def test_background_runner_join_request_returns_payload(monkeypatch):
    sessions = [
        CdpSession(
            host="127.0.0.1", port=9222, pages=[CdpPage(url="https://cafe.naver.com/royaltyserver", title="Cafe")]
        )
    ]

    class FakeReport:
        ok = True
        code = "ok"
        messages = ["ok"]

        def to_dict(self):
            return {"ok": True, "cafe_url": "royaltyserver", "final_submit_blocked": True}

    monkeypatch.setattr(
        runner, "select_naver_session", lambda **kwargs: (sessions[0], runner.evaluate_sessions("naver", sessions))
    )
    monkeypatch.setattr(
        runner,
        "create_isolated_cafe_target",
        lambda *, port, work, cafe_url="": (
            "target",
            {"id": "target", "url": "https://cafe.naver.com/royaltyserver", "title": "Cafe"},
        ),
    )
    monkeypatch.setattr(
        runner.cdp,
        "list_pages",
        lambda port: [{"id": "target", "url": "https://cafe.naver.com/royaltyserver", "title": "Cafe"}],
    )
    monkeypatch.setattr(join_request, "inspect_join_request_from_target", lambda target_id, **kwargs: FakeReport())

    report = runner.collect_joined_cafe_background(
        cafe_url="royaltyserver",
        mode="join-request",
        allow_mixed_readonly=True,
        nickname="해한AI",
        purpose="AI 자동화 사례 조사",
    )

    assert report.ok is True
    assert report.payload["final_submit_blocked"] is True
    assert "isolated tab" in report.messages[0]
    assert "no browser launch" in report.messages[0]


def test_router_cafe_collect_saves_readonly_payload(monkeypatch, tmp_path):
    calls = []

    class FakeReport:
        ok = True
        code = "ok"

        def to_dict(self):
            return {"ok": True, "payload": {"articles": [{"text": "SmartStore upload help"}]}}

    def fake_collect_joined_cafe_background(**kwargs):
        calls.append(kwargs)
        return FakeReport()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(router, "gate_check", lambda *a, **k: None)
    monkeypatch.setattr(runner, "collect_joined_cafe_background", fake_collect_joined_cafe_background)

    router._cmd_cafe("collect", ["--cafe-url=soho"])

    assert calls == [{"cafe_url": "soho", "mode": "home", "allow_mixed_readonly": True}]
    payload = json.loads((tmp_path / "data" / "naver_cafe_soho_collect_latest.json").read_text(encoding="utf-8"))
    assert payload["readonly"] is True
    assert payload["browser_close"] is False


def test_router_cafe_join_request_saves_prepare_only_payload(monkeypatch, tmp_path):
    calls = []

    class FakeReport:
        ok = True
        code = "ok"

        def to_dict(self):
            return {"ok": True, "payload": {"final_submit_blocked": True}}

    def fake_collect_joined_cafe_background(**kwargs):
        calls.append(kwargs)
        return FakeReport()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(router, "gate_check", lambda *a, **k: None)
    monkeypatch.setattr(runner, "collect_joined_cafe_background", fake_collect_joined_cafe_background)

    router._cmd_cafe("join-request", ["--cafe-url=royaltyserver", "--nickname=haehan", "--purpose=AI 자동화"])

    assert calls == [
        {
            "cafe_url": "royaltyserver",
            "mode": "join-request",
            "allow_mixed_readonly": True,
            "nickname": "haehan",
            "purpose": "AI 자동화",
            "answers": {},
        }
    ]
    payload = json.loads(
        (tmp_path / "data" / "naver_cafe_royaltyserver_join_request_latest.json").read_text(encoding="utf-8")
    )
    assert payload["prepare_only"] is True
    assert payload["final_submit_blocked"] is True
    assert payload["browser_launch"] is False


def test_router_cafe_join_submit_requires_approval():
    with pytest.raises(SystemExit, match="NAVER_APPROVED_CAFE_JOIN"):
        router._cmd_cafe("join-submit", ["--cafe-url=royaltyserver"])


def test_router_cafe_join_submit_records_gate_pass(monkeypatch, tmp_path):
    calls = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(router_cafe, "gate_check", lambda *a, **k: calls.append((a, k)))

    router._cmd_cafe("join-submit", ["--cafe-url=royaltyserver", "--approved", "--confirm=NAVER_APPROVED_CAFE_JOIN"])

    payload = json.loads(
        (tmp_path / "data" / "naver_cafe_royaltyserver_join_submit_latest.json").read_text(encoding="utf-8")
    )
    assert calls[0][0] == ("naver_cafe_join_submit",)
    assert calls[0][1]["force"] is True
    assert payload["browser_submit_executed"] is False
    assert payload["final_click_adapter_required"] is True
