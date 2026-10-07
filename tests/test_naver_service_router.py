from __future__ import annotations

import json

from scripts.naver import router, router_social, service_catalog
from scripts.naver.cafe import cli_router as router_cafe


def test_service_catalog_lists_all_naver_sections(tmp_path):
    catalog = service_catalog.build_catalog()

    for key in (
        "mail",
        "blog-assets",
        "content",
        "cafe",
        "keyword-tools",
        "calendar",
        "mybox",
        "pay",
        "talk",
        "place",
        "smartstore",
    ):
        assert key in catalog["features"]

    path = service_catalog.save_catalog(catalog, tmp_path / "catalog.json")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["site"] == "naver"
    assert saved["features"]["cafe"]["read"] == ["list", "home", "topic-search", "collect", "boards", "posts", "read"]
    assert "join-request" in saved["features"]["cafe"]["prepare"]
    assert "topic-search uses Naver search API" in saved["features"]["cafe"]["policy"]
    assert "approval-gated" in saved["features"]["cafe"]["policy"]
    assert "paid Naver API" in saved["features"]["keyword-tools"]["policy"]
    assert "rights confirmation" in saved["features"]["blog-assets"]["policy"]


def test_dry_run_calendar_add_does_not_open_browser(monkeypatch):
    saved = {}
    monkeypatch.setattr(router_cafe, "gate_check", lambda *a, **k: None)
    monkeypatch.setattr(router_cafe, "_save_latest", lambda name, payload: saved.setdefault(name, payload) or name)
    monkeypatch.setattr(router_cafe, "_print_saved", lambda payload, path: None)

    router._cmd_calendar(
        "add",
        ["--title=Meet", "--start=2026-05-13T15:00:00", "--dry-run"],
    )

    payload = saved["naver_calendar_add_latest.json"]
    assert payload["workflow"] == "calendar_add"
    assert payload["dry_run"] is True
    assert payload["save_requested"] is False


def test_dry_run_mybox_upload_requires_file_but_not_browser(tmp_path, monkeypatch):
    target = tmp_path / "sample.txt"
    target.write_text("sample", encoding="utf-8")
    saved = {}
    monkeypatch.setattr(router_cafe, "gate_check", lambda *a, **k: None)
    monkeypatch.setattr(router_cafe, "_save_latest", lambda name, payload: saved.setdefault(name, payload) or name)
    monkeypatch.setattr(router_cafe, "_print_saved", lambda payload, path: None)

    router._cmd_mybox("upload", [f"--file={target}", "--dry-run"])

    payload = saved["naver_mybox_upload_latest.json"]
    assert payload["workflow"] == "mybox_upload"
    assert payload["file_name"] == "sample.txt"
    assert payload["dry_run"] is True


def test_dry_run_talk_send_records_approval_gate_shape(monkeypatch):
    saved = {}
    monkeypatch.setattr(router_social, "gate_check", lambda *a, **k: None)
    monkeypatch.setattr(router_social, "_save_latest", lambda name, payload: saved.setdefault(name, payload) or name)
    monkeypatch.setattr(router_social, "_print_saved", lambda payload, path: None)

    router._cmd_talk("send", ["--partner=Client", "--message=Hello", "--dry-run"])

    payload = saved["naver_talk_send_latest.json"]
    assert payload["workflow"] == "talk_send"
    assert payload["approval_required"] is True
    assert payload["dry_run"] is True


def test_smartstore_alias_routes_to_smartstore_router(monkeypatch):
    calls = []

    def fake_run_smartstore(task, sub, args):
        calls.append((task, sub, args))

    import scripts.naver.smartstore.api.router as smartstore_router

    monkeypatch.setattr(smartstore_router, "run_smartstore", fake_run_smartstore)

    router._cmd_smartstore("product", ["list"])

    assert calls == [("product", "list", [])]


def test_option_phrase_preserves_korean_query_with_spaces():
    assert (
        router._option_phrase(
            ["--query=AI", "업무", "자동화", "--display=20"],
            "--query=",
        )
        == "AI 업무 자동화"
    )


def test_keyword_tools_plan_records_free_only_policy(monkeypatch):
    saved = {}
    monkeypatch.setattr(router, "gate_check", lambda *a, **k: None)

    import scripts.naver.keyword_tools as kt

    monkeypatch.setattr(kt, "save_payload", lambda payload: saved.setdefault("payload", payload) or "path")
    monkeypatch.setattr(kt, "print_summary", lambda payload, path: None)

    router._cmd_keyword_tools("plan", ["--query=인테리어", "AI"])

    payload = saved["payload"]
    assert payload["workflow"] == "naver_keyword_research_plan"
    assert payload["keywords"] == ["인테리어 AI"]
    assert payload["free_only_policy"]["paid_api_key_issue"] == "blocked"
    assert any(item["gate"] == "naver_ad_publish" for item in payload["paid_actions_blocked"])


def test_keyword_tools_paid_blocks_are_blocked():
    from scripts.naver import keyword_tools

    result = keyword_tools.assert_paid_actions_blocked()

    assert result["ok"] is True
    assert "naver_paid_api_key_issue" in result["blocked_gates"]
    assert "naver_payment_method_register" in result["blocked_gates"]
