import json

import pytest

from scripts.smartstore import actions
from scripts.smartstore import advanced_tools
from scripts.smartstore import approved_product_workflow
from scripts.smartstore import draft_fill
from scripts.smartstore import live_probe
from scripts.smartstore import menu_tools
from scripts.smartstore import page_tools
from scripts.smartstore import page_functions
from scripts.smartstore import router
from scripts.smartstore.product_register import build_product_register_pipeline
from scripts.smartstore.product_register import gates as product_register_gates
from scripts.smartstore.product_register.category_resolver import resolve_category_candidates
from scripts.smartstore.product_register.category_taxonomy import build_default_taxonomy
from scripts.smartstore.product_register.input_data import read_utf8_json_file


def test_action_catalog_has_read_prepare_and_approval_sections():
    catalog = actions.build_action_catalog()
    sections = {section["name"]: section for section in catalog["sections"]}

    assert set(sections) == {"read", "prepare", "approval"}
    assert sections["read"]["summary"]["implemented"] >= 1
    assert sections["approval"]["summary"]["approval_gated"] >= 3
    assert catalog["contract"]["submit"].endswith(actions.APPROVAL_CONFIRM_TEXT)


def test_prepare_plan_validates_general_product_and_never_submits():
    plan = actions.build_prepare_plan(
        {"name": "Sample", "price": 1000, "stock": 3},
        product_type="general",
        save_after=True,
        dry_run=True,
    )

    assert plan["validation"]["ok"] is True
    assert plan["approval"]["required"] is True
    assert plan["submit_executed"] is False
    assert plan["saved"] is False


def test_prepare_plan_reports_missing_required_fields():
    plan = actions.build_prepare_plan({"name": "Sample"}, product_type="general")

    assert plan["validation"]["ok"] is False
    assert plan["validation"]["missing"] == ["price", "stock"]


def test_submit_plan_accepts_only_approval_actions():
    actions.save_action_catalog(actions.build_action_catalog())
    plan = actions.build_submit_plan(action_id="product.general.save", approved_by="tester")

    assert plan["approval"]["required"] is True
    assert plan["approval"]["confirm_text_required"] == actions.APPROVAL_CONFIRM_TEXT
    assert plan["submit_executed"] is False

    with pytest.raises(ValueError):
        actions.build_submit_plan(action_id="product.list")


def test_save_records(tmp_path):
    catalog_path = actions.save_action_catalog(actions.build_action_catalog(), tmp_path / "catalog.json")
    plan_path = actions.save_prepare_plan(
        actions.build_prepare_plan({"name": "Sample"}, product_type="group"),
        tmp_path / "plan.json",
    )
    record_path = actions.save_submit_record({"workflow": "product_register", "dry_run": True}, tmp_path / "record.json")

    assert json.loads(catalog_path.read_text(encoding="utf-8"))["site_id"] == "smartstore"
    assert json.loads(plan_path.read_text(encoding="utf-8"))["product_type"] == "group"
    assert json.loads(record_path.read_text(encoding="utf-8"))["workflow"] == "product_register"


def test_smartstore_json_arg_requires_utf8_json_file(tmp_path):
    data_path = tmp_path / "product.json"
    data_path.write_text('{"name":"LED 슬림 T3","price":10000,"stock":5}', encoding="utf-8")

    data, path = router._read_json_arg([f"--data={data_path}"])

    assert data["name"] == "LED 슬림 T3"
    assert path == str(data_path)
    with pytest.raises(SystemExit):
        router._read_json_arg([])
    with pytest.raises(SystemExit):
        router._read_json_arg([f"--data={tmp_path / 'product.txt'}"])


def test_product_register_pipeline_separates_modules_and_gates():
    pipeline = build_product_register_pipeline()

    steps = {step["step"]: step for step in pipeline["steps"]}
    assert steps["input_data"]["module"].endswith("product_register.input_data")
    assert steps["category_taxonomy"]["stage"] == product_register_gates.READ
    assert steps["category_resolver"]["stage"] == product_register_gates.PREPARE
    assert steps["draft"]["stage"] == product_register_gates.PREPARE
    assert steps["approval"]["stage"] == product_register_gates.APPROVAL
    assert f"--confirm={product_register_gates.APPROVAL_CONFIRM_TEXT}" in steps["approval"]["requires"]


def test_product_register_gate_blocks_customer_send_without_approval():
    result = product_register_gates.check_action("talk.message.send")

    assert result.ok is False
    assert result.code == "approval_required"
    assert "draft customer replies" in result.message
    assert product_register_gates.check_action(
        "talk.message.send",
        approved=True,
        confirm=product_register_gates.APPROVAL_CONFIRM_TEXT,
    ).ok


def test_product_register_input_data_rejects_non_json(tmp_path):
    data_path = tmp_path / "product.json"
    data_path.write_text('{"name":"LED 슬림 T3"}', encoding="utf-8")
    bad_path = tmp_path / "product.txt"
    bad_path.write_text("{}", encoding="utf-8")

    assert read_utf8_json_file(data_path).data["name"] == "LED 슬림 T3"
    with pytest.raises(ValueError):
        read_utf8_json_file(bad_path)


def test_product_register_input_data_accepts_utf8_bom(tmp_path):
    data_path = tmp_path / "product.json"
    data_path.write_text('\ufeff{"name":"LED 슬림 T3"}', encoding="utf-8")

    assert read_utf8_json_file(data_path).data["name"] == "LED 슬림 T3"


def test_category_resolver_scores_lighting_candidates():
    taxonomy = build_default_taxonomy()
    result = resolve_category_candidates(
        {
            "name": "LED 슬림 T3 라인조명",
            "category": "간접조명",
            "keywords": ["국산 조명", "LED모듈"],
        },
        taxonomy=taxonomy,
    )

    assert result["ok"] is True
    assert result["auto_select_allowed"] is True
    assert result["kc_required"] is True
    assert result["catalog_followup_required"] is True
    assert result["top"]["category_id"]


def test_category_resolver_requires_manual_review_for_unknown_product():
    result = resolve_category_candidates({"name": "unmapped specialty item"}, taxonomy=build_default_taxonomy())

    assert result["auto_select_allowed"] is False
    assert result["manual_review_required"] is True
    assert product_register_gates.check_category_resolution(result).code == "manual_review_required"


def test_smartstore_probe_classifies_login_required():
    verdict = live_probe.classify_probe(
        {
            "href": "https://nid.naver.com/nidlogin.login?url=https%3A%2F%2Fsell.smartstore.naver.com",
            "host": "nid.naver.com",
            "title": "네이버 로그인",
            "markers": {"naverLogin": True, "smartstore": False, "sellerCenter": False, "challenge": False},
            "bodySample": "로그인 아이디 비밀번호",
        }
    )

    assert verdict["code"] == "login_required"
    assert verdict["login_required"] is True
    assert verdict["logged_in"] is False


def test_smartstore_probe_classifies_accessible_dashboard():
    verdict = live_probe.classify_probe(
        {
            "href": "https://sell.smartstore.naver.com/#/home/dashboard",
            "host": "sell.smartstore.naver.com",
            "title": "스마트스토어센터",
            "markers": {"naverLogin": False, "smartstore": True, "sellerCenter": True, "storeNavigation": True, "challenge": False},
            "bodySample": "스마트스토어센터 상품관리 판매관리",
            "bodyLength": 50,
        }
    )

    assert verdict["code"] == "smartstore_accessible"
    assert verdict["smartstore_accessible"] is True
    assert verdict["logged_in"] is True


def test_smartstore_probe_prefers_logout_and_store_navigation_over_login_word():
    verdict = live_probe.classify_probe(
        {
            "href": "https://sell.smartstore.naver.com/#/home/dashboard",
            "host": "sell.smartstore.naver.com",
            "title": "네이버 스마트스토어센터",
            "markers": {
                "naverLogin": True,
                "logout": True,
                "accountUser": True,
                "storeNavigation": True,
                "smartstore": True,
                "sellerCenter": True,
                "challenge": False,
            },
            "bodySample": "skyjwsin님 내정보 로그아웃 상품관리 판매관리",
            "bodyLength": 80,
        }
    )

    assert verdict["code"] == "smartstore_accessible"
    assert verdict["logged_in"] is True
    assert verdict["login_required"] is False


def test_smartstore_probe_classifies_blank_dashboard_as_unverified():
    verdict = live_probe.classify_probe(
        {
            "href": "https://sell.smartstore.naver.com/#/home/dashboard",
            "host": "sell.smartstore.naver.com",
            "title": "네이버 스마트스토어센터",
            "markers": {"naverLogin": False, "smartstore": False, "sellerCenter": True, "challenge": False},
            "bodySample": "",
            "bodyLength": 0,
        }
    )

    assert verdict["code"] == "login_unverified_blank_dashboard"
    assert verdict["logged_in"] is False
    assert verdict["blank_dashboard"] is True


def test_smartstore_probe_classifies_public_landing_as_login_required():
    verdict = live_probe.classify_probe(
        {
            "href": "https://sell.smartstore.naver.com/#/home/about",
            "host": "sell.smartstore.naver.com",
            "title": "네이버 스마트스토어센터",
            "markers": {"naverLogin": True, "smartstore": True, "sellerCenter": True, "challenge": False},
            "bodySample": "네이버 스마트스토어센터 로그인하기 가입하기",
        }
    )

    assert verdict["code"] == "login_required"
    assert verdict["smartstore_accessible"] is True
    assert verdict["logged_in"] is False


def test_smartstore_session_cookie_filter_keeps_parent_naver_cookie():
    cookies = [
        {"domain": ".naver.com", "name": "NID_AUT"},
        {"domain": "sell.smartstore.naver.com", "name": "seller"},
        {"domain": "mail.naver.com", "name": "mail"},
        {"domain": ".google.com", "name": "sid"},
    ]

    kept = [
        cookie["name"]
        for cookie in cookies
        if live_probe._cookie_applies_to_host(cookie, live_probe.SMARTSTORE_SESSION_HOST)
    ]

    assert kept == ["NID_AUT", "seller"]


def test_smartstore_select_uses_smartstore_domain_group():
    from scripts.browser_cdp_selection_gate import CdpPage, CdpSession

    session, selection = live_probe.select_smartstore_session(
        sessions=[
            CdpSession("127.0.0.1", 9222, [CdpPage("https://www.naver.com/")]),
            CdpSession("127.0.0.1", 9223, [CdpPage("https://sell.smartstore.naver.com/#/home/dashboard")]),
        ]
    )

    assert selection.ok is True
    assert session is not None
    assert session.port == 9223


def test_smartstore_restore_target_session_reports_missing(monkeypatch):
    import scripts.auth_session as auth_session

    monkeypatch.setattr(auth_session, "_load_bundle", lambda host: None)

    result = live_probe.restore_target_session("target-1", port=9231)

    assert result["ok"] is False
    assert result["reason"] == "no_smartstore_session_saved"


def test_smartstore_login_watch_saves_when_login_detected(monkeypatch):
    from scripts.browser_cdp_selection_gate import CdpPage, CdpSession

    session = CdpSession("127.0.0.1", 9232, [CdpPage("https://sell.smartstore.naver.com/#/home/dashboard")])
    selection = live_probe.evaluate_sessions("smartstore", [session])
    monkeypatch.setattr(live_probe, "select_smartstore_session", lambda **kwargs: (session, selection))
    monkeypatch.setattr(
        live_probe,
        "find_rendered_smartstore_target",
        lambda *, port: (
            "target-1",
            {
                "href": "https://sell.smartstore.naver.com/#/home/dashboard",
                "host": "sell.smartstore.naver.com",
                "title": "네이버 스마트스토어센터",
                "markers": {
                    "naverLogin": True,
                    "logout": True,
                    "accountUser": True,
                    "storeNavigation": True,
                    "smartstore": True,
                    "sellerCenter": True,
                    "challenge": False,
                },
                "bodyLength": 100,
                "bodySample": "skyjwsin님 로그아웃 상품관리 판매관리",
            },
        ),
    )
    monkeypatch.setattr(live_probe, "save_target_session", lambda target_id, *, port: {"ok": True, "path": "session.json", "cookie_count": 3})

    report = live_probe.watch_login_and_save(timeout_seconds=5, interval_seconds=0.2)

    assert report.ok is True
    assert report.code == "login_detected_session_saved"
    assert report.session_saved is True
    assert report.session_cookie_count == 3


def test_smartstore_page_tools_builds_conservative_candidates():
    candidates = page_tools.build_tool_candidates(
        {
            "menus": [{"text": "상품관리", "selector": "a", "href": "https://sell.smartstore.naver.com/"}],
            "buttons": [{"text": "저장", "selector": "button"}],
            "inputs": [{"placeholder": "상품명", "selector": "input[name=\"productName\"]"}],
        }
    )
    by_id = {candidate.action_id: candidate for candidate in candidates}

    assert by_id["page.menu.상품관리"].risk == "read"
    assert by_id["page.button.저장"].risk == "approval"
    assert by_id["page.button.저장"].status == "observed_approval_required"
    assert by_id["page.input.상품명"].risk == "prepare"
    assert by_id["page.input.상품명"].status == "observed_prepare_only"


def test_smartstore_page_tools_extracts_accessibility_controls():
    payload = page_tools.extract_accessibility_controls(
        [
            {"role": {"value": "heading"}, "name": {"value": "스마트스토어센터"}},
            {"role": {"value": "button"}, "name": {"value": "저장"}},
            {"role": {"value": "link"}, "name": {"value": "상품관리"}},
            {"role": {"value": "textbox"}, "name": {"value": "상품명"}},
        ]
    )

    assert payload["headings"] == ["스마트스토어센터"]
    assert payload["buttons"][0]["text"] == "저장"
    assert payload["links"][0]["text"] == "상품관리"
    assert payload["inputs"][0]["label"] == "상품명"


def test_smartstore_dashboard_summary_uses_rendered_logged_in_tab(monkeypatch):
    from scripts.browser_cdp_selection_gate import CdpPage, CdpSession

    session = CdpSession("127.0.0.1", 9232, [CdpPage("https://sell.smartstore.naver.com/#/home/dashboard")])
    selection = live_probe.evaluate_sessions("smartstore", [session])
    raw = {
        "href": "https://sell.smartstore.naver.com/#/home/dashboard",
        "host": "sell.smartstore.naver.com",
        "title": "SmartStore Center",
        "markers": {
            "naverLogin": False,
            "logout": True,
            "accountUser": True,
            "storeNavigation": True,
            "smartstore": True,
            "sellerCenter": True,
            "challenge": False,
        },
        "bodyLength": 100,
        "bodySample": "Dashboard product management sales management",
    }

    monkeypatch.setattr(page_tools, "select_smartstore_session", lambda **kwargs: (session, selection))
    monkeypatch.setattr(page_tools, "find_rendered_smartstore_target", lambda *, port: ("target-1", raw))
    monkeypatch.setattr(
        page_tools,
        "_read_page_tools_snapshot",
        lambda target_id, *, port: {
            "href": raw["href"],
            "title": raw["title"],
            "menus": [{"text": "Product Management"}, {"text": "Sales Management"}],
            "buttons": [{"text": "Search"}, {"text": "Notifications"}],
            "inputs": [{"placeholder": "Search orders"}],
        },
    )

    report = page_tools.collect_dashboard_summary()

    assert report.ok is True
    assert report.code == "ok"
    assert report.port == 9232
    assert report.target_id == "target-1"
    assert report.logged_in is True
    assert report.utility_buttons == ["Search", "Notifications"]
    assert report.search_inputs == ["Search orders"]


def test_smartstore_menu_catalog_covers_primary_menus():
    catalog = menu_tools.build_menu_catalog()

    assert catalog["menu_count"] == 13
    menu_ids = {menu["menu_id"] for menu in catalog["menus"]}
    assert {
        "product",
        "sales",
        "settlement",
        "inquiry_review",
        "store",
        "benefit_marketing",
        "n_delivery",
        "commerce_solution",
        "data_analysis",
        "ads",
        "promotion",
        "shopping_connect",
        "seller_info",
    } == menu_ids
    assert catalog["summary"]["read_tools"] >= 13
    assert catalog["summary"]["prepare_tools"] >= 1
    assert catalog["summary"]["approval_tools"] >= 1


def test_smartstore_menu_snapshot_clicks_logged_in_menu(monkeypatch):
    from scripts.browser_cdp_selection_gate import CdpPage, CdpSession

    session = CdpSession("127.0.0.1", 9232, [CdpPage("https://sell.smartstore.naver.com/#/home/dashboard")])
    selection = live_probe.evaluate_sessions("smartstore", [session])
    raw = {
        "href": "https://sell.smartstore.naver.com/#/home/dashboard",
        "host": "sell.smartstore.naver.com",
        "title": "SmartStore Center",
        "markers": {
            "naverLogin": False,
            "logout": True,
            "accountUser": True,
            "storeNavigation": True,
            "smartstore": True,
            "sellerCenter": True,
            "challenge": False,
        },
        "bodyLength": 100,
        "bodySample": "Dashboard product management sales management",
    }

    calls = []
    monkeypatch.setattr(menu_tools, "select_smartstore_session", lambda **kwargs: (session, selection))
    monkeypatch.setattr(menu_tools, "find_rendered_smartstore_target", lambda *, port: ("target-1", raw))
    monkeypatch.setattr(menu_tools.cdp, "evaluate", lambda target_id, expr, timeout, port: calls.append(expr) or {"ok": True})
    monkeypatch.setattr(
        menu_tools,
        "_read_page_tools_snapshot",
        lambda target_id, *, port: {
            "href": "https://sell.smartstore.naver.com/#/products/origin-list",
            "title": "Products",
            "readyState": "complete",
            "headings": ["Products"],
            "buttons": [{"text": "Search"}],
            "links": [],
            "inputs": [{"placeholder": "Product name"}],
            "counts": {"menus": 13, "buttons": 1, "links": 0, "inputs": 1, "tables": 1},
        },
    )

    report = menu_tools.collect_menu_snapshot("product", wait_seconds=1)

    assert report.ok is True
    assert report.menu_id == "product"
    assert report.label == "상품관리"
    assert report.after_url.endswith("/origin-list")
    assert report.counts["tables"] == 1
    assert report.visible_menus == []
    assert any(tool["risk"] == "approval" for tool in report.tool_candidates)
    assert calls


def test_smartstore_all_menu_snapshots_reports_each_menu(monkeypatch):
    calls = []

    def fake_collect(menu_id, *, allow_mixed_readonly=False, wait_seconds=4.0):
        calls.append((menu_id, allow_mixed_readonly, wait_seconds))
        return menu_tools.SmartStoreMenuSnapshotReport(ok=True, code="ok", menu_id=menu_id)

    monkeypatch.setattr(menu_tools, "collect_menu_snapshot", fake_collect)

    payload = menu_tools.collect_all_menu_snapshots(allow_mixed_readonly=True, wait_seconds=2)

    assert payload["menu_count"] == 13
    assert payload["ok_count"] == 13
    assert len(payload["reports"]) == 13
    assert calls[0] == ("product", True, 2)


def test_smartstore_advanced_catalog_marks_high_value_profiles():
    catalog = advanced_tools.build_advanced_catalog()

    assert catalog["profile_count"] == 13
    assert {"product", "sales", "settlement", "inquiry_review", "data_analysis"}.issubset(
        set(catalog["high_value_profiles"])
    )
    product = next(profile for profile in catalog["profiles"] if profile["menu_id"] == "product")
    assert "product.list.normalized" in product["supported_tools"]


def test_smartstore_advanced_analyze_menu_normalizes_payload(monkeypatch):
    snapshot = menu_tools.SmartStoreMenuSnapshotReport(
        ok=True,
        code="ok",
        menu_id="product",
        label="Product",
        port=9232,
        target_id="target-1",
        tool_candidates=[{"tool_id": "product.delete", "risk": "approval"}],
    )
    monkeypatch.setattr(advanced_tools, "collect_menu_snapshot", lambda *args, **kwargs: snapshot)
    monkeypatch.setattr(
        advanced_tools.cdp,
        "evaluate",
        lambda target_id, expr, timeout, port: {
            "href": "https://sell.smartstore.naver.com/#/products/origin-list",
            "title": "Products",
            "headings": ["Products"],
            "tables": [{"headers": ["Name", "Stock"], "rows": [["A", "3"]], "row_count": 1}],
            "cards": [{"text": "Total 3", "rect": {}}],
            "fields": [{"placeholder": "Product name", "type": "text"}],
            "controls": [{"text": "Search"}, {"text": "Delete"}],
            "body_sample": "Total 3 Stock 10",
            "counts": {"tables": 1, "cards": 1, "fields": 1, "controls": 2},
        },
    )

    report = advanced_tools.analyze_menu("product")

    assert report.ok is True
    assert report.normalized["table_count"] == 1
    assert report.normalized["metric_card_count"] == 1
    assert report.menu_insights["entity"] == "product"
    assert report.menu_insights["detectors"]["stock_visible"] is True
    assert report.prepare_fields[0]["label"] == "Product name"
    assert report.approval_controls[0]["text"] == "Delete"
    assert any(step["step"] == "approval_guard" for step in report.automation_plan)


def test_smartstore_menu_specific_insights_cover_each_domain():
    payload = {
        "href": "https://sell.smartstore.naver.com/",
        "title": "SmartStore",
        "headings": ["Orders", "Settlement", "Review", "Ads"],
        "tables": [{"headers": ["Order", "Delivery", "Fee"], "rows": [["A", "Ready", "10"]], "row_count": 1}],
        "cards": [{"text": "Sales 10 Conversion 3"}],
        "fields": [{"placeholder": "campaign budget"}, {"placeholder": "seller business"}],
        "controls": [{"text": "Start"}, {"text": "Save"}, {"text": "Reply send"}],
        "body_sample": "order delivery claim settlement fee review reply sales traffic conversion campaign budget seller business permission",
        "counts": {"tables": 1, "cards": 1, "fields": 2, "controls": 3},
    }
    normalized = advanced_tools._normalize_payload("sales", payload)

    expected_entities = {
        "product": "product",
        "sales": "order",
        "settlement": "settlement",
        "inquiry_review": "customer_message",
        "store": "store_profile",
        "benefit_marketing": "benefit_campaign",
        "n_delivery": "n_delivery",
        "commerce_solution": "solution",
        "data_analysis": "analytics_metric",
        "ads": "ad_campaign",
        "promotion": "promotion",
        "shopping_connect": "shopping_connect",
        "seller_info": "seller_account",
    }

    for menu_id, entity in expected_entities.items():
        insights = advanced_tools._menu_specific_insights(
            menu_id,
            payload,
            normalized | {"menu_id": menu_id},
            list(payload["controls"]),
            list(payload["fields"]),
        )
        assert insights["entity"] == entity
        assert insights["read_models"]
        assert "detectors" in insights


def test_smartstore_draft_fill_sample_product_has_required_fields():
    data = draft_fill.sample_product_data()

    assert data["name"]
    assert data["price"] > 0
    assert data["stock"] > 0
    assert "저장" in data["name"]


def test_smartstore_product_draft_fill_types_without_submit(monkeypatch):
    from scripts.browser_cdp_selection_gate import CdpPage, CdpSession

    session = CdpSession("127.0.0.1", 9232, [CdpPage("https://sell.smartstore.naver.com/#/home/dashboard")])
    selection = live_probe.evaluate_sessions("smartstore", [session])
    raw = {
        "href": "https://sell.smartstore.naver.com/#/home/dashboard",
        "host": "sell.smartstore.naver.com",
        "title": "SmartStore Center",
        "markers": {
            "naverLogin": False,
            "logout": True,
            "accountUser": True,
            "storeNavigation": True,
            "smartstore": True,
            "sellerCenter": True,
            "challenge": False,
        },
        "bodyLength": 100,
        "bodySample": "Dashboard product management sales management",
    }
    evaluate_calls = []
    navigate_calls = []
    probes = []

    monkeypatch.setattr(draft_fill, "select_smartstore_session", lambda **kwargs: (session, selection))
    monkeypatch.setattr(draft_fill, "find_rendered_smartstore_target", lambda *, port: ("target-1", raw))
    monkeypatch.setattr(draft_fill.cdp, "navigate", lambda target_id, url, port: navigate_calls.append((target_id, url, port)))
    monkeypatch.setattr(
        draft_fill,
        "_field_probe",
        lambda target_id, *, port: probes.append(target_id) or {"productName": True, "price": True, "stock": True, "visibleInputs": 10},
    )

    def fake_evaluate(target_id, expr, timeout, port):
        evaluate_calls.append(expr)
        if "filled" in expr and "blocked_controls" in expr:
            return {
                "href": draft_fill.PRODUCT_REGISTER_URL,
                "title": "Product Register",
                "filled": [{"key": "name", "selector": "input[name=\"product.name\"]"}],
                "skipped": [{"key": "category", "reason": "field_not_found"}],
                "blocked_controls": [{"text": "저장하기"}],
            }
        return {
            "href": draft_fill.PRODUCT_REGISTER_URL,
            "host": "sell.smartstore.naver.com",
            "title": "Product Register",
            "markers": {},
            "bodyLength": 10,
            "bodySample": "",
        }

    monkeypatch.setattr(draft_fill.cdp, "evaluate", fake_evaluate)

    report = draft_fill.fill_product_draft({"name": "Test", "price": 1000, "stock": 1}, wait_seconds=1)

    assert report.ok is True
    assert report.final_submit_blocked is True
    assert report.approval_required_for_submit is True
    assert report.filled[0]["key"] == "name"
    assert report.blocked_controls[0]["text"] == "저장하기"
    assert navigate_calls[0][1] == draft_fill.PRODUCT_REGISTER_CANDIDATE_URLS[0]
    assert evaluate_calls


def test_smartstore_page_functions_classifies_current_page_tools():
    snapshot = {
        "href": "https://sell.smartstore.naver.com/#/products/create",
        "title": "Product Register",
        "bodySample": "상품등록",
        "headings": [{"text": "상품등록"}],
        "fields": [
            {"label": "상품명", "tag": "input", "type": "text", "selector": "input[name=\"product.name\"]"},
            {"label": "대표이미지", "tag": "input", "type": "file", "selector": "input[type=\"file\"]"},
            {"label": "전시여부", "tag": "input", "type": "radio", "selector": "input[type=\"radio\"]"},
        ],
        "fileInputs": [{"label": "이미지 등록", "selector": "input[type=\"file\"]"}],
        "controls": [{"text": "저장하기"}, {"text": "도움말"}, {"text": "취소"}],
        "tables": [{"headers": ["항목", "값"], "rows": 1}],
    }

    functions = page_functions.build_page_functions(snapshot)
    by_label = {item["label"]: item for item in functions}

    assert by_label["상품명"]["risk"] == "prepare"
    assert by_label["대표이미지"]["risk"] == "approval"
    assert by_label["전시여부"]["kind"] == "prepare_choice"
    assert by_label["저장하기"]["risk"] == "approval"
    assert by_label["도움말"]["risk"] == "read"
    assert any(item["kind"] == "table" for item in functions)


def test_smartstore_page_functions_flags_customer_reply_controls():
    functions = page_functions.build_page_functions(
        {
            "href": "https://sell.smartstore.naver.com/#/comments/reviews",
            "bodySample": "review reply",
            "headings": [],
            "fields": [],
            "fileInputs": [],
            "controls": [{"text": "Reply send", "href": "", "type": "", "selector": "button"}],
            "tables": [],
        }
    )

    reply = next(item for item in functions if item["label"] == "Reply send")
    assert reply["risk"] == "approval"
    assert reply["policy"] == "customer_communication_approval_required"


def test_smartstore_page_functions_keeps_search_submit_read_only():
    functions = page_functions.build_page_functions(
        {
            "href": "https://sell.smartstore.naver.com/#/products/origin-list",
            "bodySample": "product list",
            "headings": [],
            "fields": [],
            "fileInputs": [],
            "controls": [
                {"text": "Search", "href": "", "type": "submit", "selector": "button"},
                {"text": "Approval pending 0", "href": "https://sell.smartstore.naver.com/", "type": "", "selector": "a"},
            ],
            "tables": [],
        }
    )

    by_label = {item["label"]: item for item in functions}
    assert by_label["Search"]["risk"] == "read"
    assert by_label["Approval pending 0"]["risk"] == "read"


def test_smartstore_approved_product_save_requires_approval():
    report = approved_product_workflow.approved_save_product(approved=False, confirm="")

    assert report.ok is False
    assert report.code == "approval_required"


def test_smartstore_approved_product_save_blocks_non_test_name(monkeypatch):
    from scripts.browser_cdp_selection_gate import CdpPage, CdpSession

    session = CdpSession("127.0.0.1", 9232, [CdpPage("https://sell.smartstore.naver.com/#/products/create")])
    selection = live_probe.evaluate_sessions("smartstore", [session])
    raw = {
        "href": "https://sell.smartstore.naver.com/#/products/create",
        "host": "sell.smartstore.naver.com",
        "title": "SmartStore Center",
        "markers": {
            "naverLogin": False,
            "logout": True,
            "accountUser": True,
            "storeNavigation": True,
            "smartstore": True,
            "sellerCenter": True,
            "challenge": False,
        },
        "bodyLength": 100,
        "bodySample": "Dashboard product management sales management",
    }
    monkeypatch.setattr(approved_product_workflow, "select_smartstore_session", lambda **kwargs: (session, selection))
    monkeypatch.setattr(approved_product_workflow.cdp, "list_pages", lambda port: [{"id": "target-1", "url": raw["href"], "type": "page"}])
    monkeypatch.setattr(
        approved_product_workflow.cdp,
        "evaluate",
        lambda target_id, expr, timeout, port: {"value": "실제 판매 상품", "href": "https://sell.smartstore.naver.com/#/products/create"},
    )

    report = approved_product_workflow.approved_save_product(
        approved=True,
        confirm=approved_product_workflow.APPROVAL_CONFIRM_TEXT,
    )

    assert report.ok is False
    assert report.code == "unsafe_product_name"


def test_smartstore_approved_product_save_clicks_test_product(monkeypatch):
    from scripts.browser_cdp_selection_gate import CdpPage, CdpSession

    session = CdpSession("127.0.0.1", 9232, [CdpPage("https://sell.smartstore.naver.com/#/products/create")])
    selection = live_probe.evaluate_sessions("smartstore", [session])
    raw = {
        "href": "https://sell.smartstore.naver.com/#/products/create",
        "host": "sell.smartstore.naver.com",
        "title": "SmartStore Center",
        "markers": {
            "naverLogin": False,
            "logout": True,
            "accountUser": True,
            "storeNavigation": True,
            "smartstore": True,
            "sellerCenter": True,
            "challenge": False,
        },
        "bodyLength": 100,
        "bodySample": "Dashboard product management sales management",
    }
    calls = []
    monkeypatch.setattr(approved_product_workflow, "select_smartstore_session", lambda **kwargs: (session, selection))
    monkeypatch.setattr(approved_product_workflow.cdp, "list_pages", lambda port: [{"id": "target-1", "url": raw["href"], "type": "page"}])

    def fake_evaluate(target_id, expr, timeout, port):
        calls.append(expr)
        if "product.name" in expr and "value" in expr:
            return {"value": "AI 테스트 상품", "href": "https://sell.smartstore.naver.com/#/products/create"}
        if "저장하기" in expr:
            return {"ok": True, "text": "저장하기"}
        return {"href": "https://sell.smartstore.naver.com/#/products/create", "alerts": ["필수항목 확인"], "validation": ["이미지 필수"]}

    monkeypatch.setattr(approved_product_workflow.cdp, "evaluate", fake_evaluate)
    monkeypatch.setattr(approved_product_workflow.time, "sleep", lambda seconds: None)

    report = approved_product_workflow.approved_save_product(
        approved=True,
        confirm=approved_product_workflow.APPROVAL_CONFIRM_TEXT,
    )

    assert report.ok is False
    assert report.code == "validation_blocked"
    assert report.product_name == "AI 테스트 상품"
    assert report.validation_errors == ["이미지 필수"]
    assert calls


def test_smartstore_test_image_is_valid_png(tmp_path):
    path = draft_fill.create_test_image(tmp_path / "test.png")

    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(data) > 1000


def test_smartstore_approved_test_cycle_requires_approval():
    report = approved_product_workflow.approved_test_product_cycle(
        product_type="individual",
        approved=False,
        confirm="",
    )

    assert report.ok is False
    assert report.code == "approval_required"
