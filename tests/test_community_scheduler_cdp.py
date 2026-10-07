"""커뮤니티 스케줄러 — 사이트 수집 전에 CDP(브라우저)를 먼저 보장하는지. 브라우저·네트워크를 쓰지 않는다."""

from __future__ import annotations

import pytest

from scripts.community import scheduler as S

SITES = [{"name": "A", "url": "http://a.test"}, {"name": "B", "url": "http://b.test"}]


@pytest.fixture
def env(monkeypatch, tmp_path):
    calls: list[str] = []
    monkeypatch.setattr(S, "_DIR", tmp_path)
    monkeypatch.setattr(S, "_REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(S, "_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr("scripts.community.registry.list_sites", lambda: list(env_sites))
    monkeypatch.setattr(
        "scripts.community.universal_extractor.extract_posts",
        lambda page, url, max_posts=40: calls.append(f"extract:{url}") or {"ok": True, "posts": []},
    )
    monkeypatch.setattr(
        "scripts.community.analyzer.prepare_posts_for_review",
        lambda posts, context="": {"ok": True, "post_count": 0, "formatted_text": ""},
    )
    monkeypatch.setattr("scripts.community.notifier.notify_report", lambda report: None)
    env_sites = list(SITES)
    return calls, env_sites, monkeypatch


def _fake_get_page(calls, fail=False):
    def get_page():
        calls.append("get_page")
        if fail:
            raise RuntimeError("CDP 데몬 자동 기동 실패")
        return object()

    return get_page


def test_cdp_is_ensured_before_any_site_is_collected(env):
    calls, _, mp = env
    mp.setattr("scripts.browser.cdp.connection.get_page", _fake_get_page(calls))
    report = S.run_all_sites("scheduled")
    assert calls[0] == "get_page" and calls.index("get_page") < calls.index("extract:http://a.test")
    assert report["ok_count"] == 2


def test_cdp_start_failure_is_reported_once_and_collection_is_skipped(env):
    calls, _, mp = env
    mp.setattr("scripts.browser.cdp.connection.get_page", _fake_get_page(calls, fail=True))
    report = S.run_all_sites("scheduled")
    assert calls == ["get_page"]  # 수집 함수는 호출되지 않고, 브라우저 기동 시도도 1번뿐
    assert report["ok_count"] == 0 and report["site_count"] == 2
    assert all("CDP 브라우저 기동 실패" in r["error"] for r in report["reports"])


def test_no_sites_does_not_touch_the_browser(env):
    calls, sites, mp = env
    sites.clear()
    mp.setattr("scripts.browser.cdp.connection.get_page", _fake_get_page(calls))
    S.run_all_sites("scheduled")
    assert calls == []
