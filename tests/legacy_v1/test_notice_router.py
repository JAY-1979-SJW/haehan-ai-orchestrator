from __future__ import annotations

import base64
from pathlib import Path

from orchestrator_v1.monitoring.dashboard import create_app


def _auth_header() -> dict[str, str]:
    token = base64.b64encode(b"admin:secret").decode("ascii")
    return {"Authorization": f"Basic {token}"}


def test_notice_health_route_is_registered(monkeypatch):
    monkeypatch.setenv("ORCH_DASHBOARD_USER", "admin")
    monkeypatch.setenv("ORCH_DASHBOARD_PASSWORD", "secret")
    app = create_app()
    client = app.test_client()

    resp = client.get("/api/v1/notices/health", headers=_auth_header())

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "notice_radar"
    assert "cdp_url" in data


def test_notice_daily_sites_route(monkeypatch):
    monkeypatch.setenv("ORCH_DASHBOARD_USER", "admin")
    monkeypatch.setenv("ORCH_DASHBOARD_PASSWORD", "secret")
    app = create_app()
    client = app.test_client()

    resp = client.get("/api/v1/notices/daily-sites", headers=_auth_header())

    assert resp.status_code == 200
    data = resp.get_json()
    keys = {site["key"] for site in data["sites"]}
    assert "kstartup" in keys
    assert "molit" in keys
    assert "nfa" in keys


def test_notice_current_browser_route_is_registered(monkeypatch):
    monkeypatch.setenv("ORCH_DASHBOARD_USER", "admin")
    monkeypatch.setenv("ORCH_DASHBOARD_PASSWORD", "secret")
    app = create_app()
    rules = {str(rule) for rule in app.url_map.iter_rules()}

    assert "/api/v1/notices/analyze-current-browser" in rules


def test_notice_folder_route_runs_analysis(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("ORCH_DASHBOARD_USER", "admin")
    monkeypatch.setenv("ORCH_DASHBOARD_PASSWORD", "secret")

    project_root = Path(__file__).resolve().parents[2]
    folder = project_root / "storage" / "notices" / "router_test_notice"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "notice_page.txt").write_text(
        "스마트도시 실증 구매 공고 2026.07.22까지 AI CAD 도면 소방 안전 자동화 사업계획서",
        encoding="utf-8",
    )

    app = create_app()
    client = app.test_client()
    resp = client.post(
        "/api/v1/notices/analyze-folder",
        json={"folder": str(folder), "title": "스마트도시 런타임 테스트", "source": "test"},
        headers=_auth_header(),
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["analysis"]["title"] == "스마트도시 런타임 테스트"
    assert data["analysis"]["fit_score"] >= 70
