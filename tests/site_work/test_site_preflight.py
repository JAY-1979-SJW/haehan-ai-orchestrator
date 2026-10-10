"""신규 사이트 사전 조사(M10) — robots 해석·판정·조회기·서비스·등록 연결·라우터. 합성 로컬 서버만 쓰고 외부·9222 접속 없음.

기준서: docs/specs/2026-10-05_new_site_onboarding_pipeline.md
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.server import mcp_server
from ai_orchestrator.site_work import site_onboarding_service as onboarding
from ai_orchestrator.site_work import site_preflight as sp
from ai_orchestrator.site_work import site_preflight_service as svc
from ai_orchestrator.site_work import site_registry_store as reg_store
from ai_orchestrator.site_work import site_task_map_explore_service as explore
from ai_orchestrator.site_work import site_task_map_request_store as rstore
from ai_orchestrator.site_work import site_task_map_store as map_store
from ai_orchestrator.site_work.site_onboarding_router import site_onboarding_router
from scripts.explorer import preflight_fetch
from tools.gates import auth as auth_module
from tools.gates.auth import get_current_user

HOST = "new-site.example-test.kr"
ROBOTS = """
# 주석
User-agent: *
Disallow: /private/
Disallow: /admin
Allow: /private/open/
Crawl-delay: 2
Sitemap: https://new-site.example-test.kr/sitemap.xml
User-agent: BadBot
Disallow: /
"""
SITEMAP = (
    "<urlset><url><loc>https://new-site.example-test.kr/a</loc></url>"
    "<url><loc>https://other.test/x</loc></url>"
    "<url><loc>https://new-site.example-test.kr/b?q=1</loc></url></urlset>"
)
INFO_ONLY = {"checked": True, "vendors": []}


# ── 순수 규칙 ────────────────────────────────────────────────────


def test_parse_robots_picks_star_group_and_records_delay_and_sitemaps():
    parsed = sp.parse_robots(ROBOTS)
    assert ("disallow", "/private/") in parsed["rules"] and ("allow", "/private/open/") in parsed["rules"]
    assert parsed["crawl_delay"] == 2.0
    assert parsed["sitemaps"] == ["https://new-site.example-test.kr/sitemap.xml"]
    assert sp.parse_robots(ROBOTS, agent="BadBot")["rules"] == [("disallow", "/")]


def test_is_allowed_longest_match_wins_and_wildcards():
    rules = sp.parse_robots(ROBOTS)["rules"]
    assert not sp.is_allowed(rules, "/private/x")
    assert sp.is_allowed(rules, "/private/open/page")  # 더 긴 Allow 가 이긴다
    assert sp.is_allowed(rules, "/public")
    pdf = [("disallow", "/*.pdf$")]
    assert not sp.is_allowed(pdf, "/a/b.pdf") and sp.is_allowed(pdf, "/a/b.pdf?x")


def test_empty_disallow_means_allow_all():
    assert sp.parse_robots("User-agent: *\nDisallow:\n")["rules"] == []
    assert not sp.fully_blocked([])


def test_fully_blocked_only_when_root_blocked_without_allow():
    assert sp.fully_blocked([("disallow", "/")])
    assert not sp.fully_blocked([("disallow", "/"), ("allow", "/public")])


def test_exclude_prefixes_skip_wildcards_root_and_released_paths():
    rules = sp.parse_robots(ROBOTS)["rules"]
    assert sp.exclude_prefixes(rules) == ["/admin"]  # /private/ 는 더 긴 Allow 가 일부를 풀어 주므로 제외 목록에서 뺀다
    assert sp.exclude_prefixes([("disallow", "/"), ("disallow", "/x/*")]) == []


def test_sitemap_paths_keep_same_host_only_without_query():
    assert sp.sitemap_paths(SITEMAP, HOST) == ["/a", "/b"]


@pytest.mark.parametrize(
    ("status", "robots_text", "api", "compliance", "verdict"),
    [
        (sp.ROBOTS_OK, "User-agent: *\nDisallow: /\n", INFO_ONLY, None, sp.BLOCKED),
        (sp.ROBOTS_UNAVAILABLE, "", INFO_ONLY, None, sp.BLOCKED),
        (sp.ROBOTS_MISSING, "", INFO_ONLY, {"capability": "AUTOMATION_BLOCKED", "message_ko": "금지"}, sp.BLOCKED),
        (sp.ROBOTS_MISSING, "", {"checked": True, "vendors": [{"status": "available"}]}, None, sp.USE_API),
        (
            sp.ROBOTS_OK,
            ROBOTS,
            INFO_ONLY,
            {"capability": "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL", "block_reason": "X", "message_ko": "승인"},
            sp.PROCEED,
        ),
    ],
)
def test_decide_matrix(status, robots_text, api, compliance, verdict):
    got = sp.decide(robots_status=status, robots=sp.parse_robots(robots_text), official_api=api, compliance=compliance)
    assert got["verdict"] == verdict


def test_unknown_site_policy_is_advisory_and_flags_research():
    got = sp.decide(
        robots_status=sp.ROBOTS_MISSING,
        robots=sp.parse_robots(""),
        official_api=INFO_ONLY,
        compliance={"capability": "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL", "block_reason": "X", "message_ko": "승인 필요"},
    )
    assert got["verdict"] == sp.PROCEED and got["research_needed"] and "승인 필요" in got["reasons"][0]


# ── 조회기(합성 로컬 서버) ───────────────────────────────────────


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # http.server 규약 이름
        if self.path == "/robots.txt":
            self._send(200, ROBOTS)
        elif self.path == "/redirect-out":
            self._redirect("http://other.invalid/robots.txt")
        elif self.path == "/redirect-in":
            self._redirect("/robots.txt")
        elif self.path == "/big":
            self._send(200, "x" * (preflight_fetch.MAX_BYTES + 5000))
        else:
            self._send(404, "no")

    def _redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send(self, code, body):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # 시험 출력 정리
        pass


@pytest.fixture(scope="module")
def local_site():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_fetch_refuses_local_addresses_by_default(local_site):
    assert preflight_fetch.fetch_text(f"{local_site}/robots.txt")["error"] == "local_address_refused"


def test_fetch_reads_text_follows_same_host_redirect_and_caps_size(local_site):
    got = preflight_fetch.fetch_text(f"{local_site}/robots.txt", allow_local=True)
    assert got["status"] == 200 and "Disallow: /private/" in got["text"]
    assert preflight_fetch.fetch_text(f"{local_site}/redirect-in", allow_local=True)["status"] == 200
    assert len(preflight_fetch.fetch_text(f"{local_site}/big", allow_local=True)["text"]) == preflight_fetch.MAX_BYTES
    assert preflight_fetch.fetch_text(f"{local_site}/none", allow_local=True)["status"] == 404


def test_fetch_stops_when_redirected_to_another_host(local_site):
    assert (
        preflight_fetch.fetch_text(f"{local_site}/redirect-out", allow_local=True)["error"]
        == "redirected_to_other_host"
    )


def test_fetch_rejects_bad_scheme_and_reports_connection_failure():
    assert preflight_fetch.fetch_text("ftp://x.test/a")["error"] == "invalid_url"
    assert preflight_fetch.fetch_text("http://127.0.0.1:1/robots.txt", allow_local=True, timeout=1.0)["error"]


# ── 서비스·등록 연결·라우터 ──────────────────────────────────────


def _fake_fetch(robots: tuple[int, str], sitemap: tuple[int, str] = (200, SITEMAP)):
    calls: list[str] = []

    def fetch(url: str):
        calls.append(url)
        status, text = robots if url.endswith("/robots.txt") else sitemap
        return {"status": status, "text": text, "error": ""}

    return fetch, calls


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(rstore, "_DIR", tmp_path / "requests")
    monkeypatch.setattr(map_store, "_DIR", tmp_path / "maps")
    monkeypatch.setattr(reg_store, "_FILE", tmp_path / "registry" / "sites.json")
    started: list[str] = []

    def fake_executor(request):
        started.append(request["host"])
        return {"pages": 1, "tasks": 0, "aborted_reason": ""}

    explore.configure(fake_executor, run_async=False)
    explore._active.clear()
    yield started
    explore.configure(None)
    explore._active.clear()


def test_service_requires_configured_fetcher():
    with pytest.raises(ValueError, match="실행기"):
        svc.run(HOST)
    assert svc.run_for_registration(HOST) is None


def test_service_run_collects_robots_sitemap_and_policy_without_bodies(env):
    fetch, calls = _fake_fetch((200, ROBOTS))
    svc.configure_fetcher(fetch)
    got = svc.run(HOST)
    assert got["verdict"] == sp.PROCEED and got["exclude_prefixes"] == ["/admin"] and got["crawl_delay"] == 2.0
    assert got["sitemap_paths"] == ["/a", "/b"] and calls[0].endswith("/robots.txt")
    assert "text" not in got and got["compliance"]["capability"]
    assert svc.latest(HOST) is None  # 등록 전에는 저장하지 않는다


def test_register_blocked_by_robots_does_not_start_exploration(env):
    fetch, _ = _fake_fetch((200, "User-agent: *\nDisallow: /\n"))
    svc.configure_fetcher(fetch)
    out = onboarding.register({"host": HOST}, actor="kim")
    assert out["site"]["state"] == "blocked" and out["explore_request"] is None and env == []
    assert out["preflight"]["verdict"] == "blocked"
    assert svc.latest(HOST)["verdict"] == "blocked"  # 레코드에 구조만 저장


def test_register_proceeds_and_records_preflight_when_allowed(env):
    fetch, _ = _fake_fetch((404, ""), (404, ""))
    svc.configure_fetcher(fetch)
    out = onboarding.register({"host": HOST}, actor="kim")
    assert out["preflight"]["verdict"] == "proceed" and env == [HOST]
    assert out["site"]["state"] != "blocked"


def test_register_without_fetcher_keeps_previous_behavior(env):
    out = onboarding.register({"host": HOST}, actor="kim")
    assert out["preflight"] is None and env == [HOST]


def test_robots_server_error_blocks_with_retry_hint(env):
    fetch, _ = _fake_fetch((503, ""))
    svc.configure_fetcher(fetch)
    got = svc.run(HOST)
    assert got["verdict"] == sp.BLOCKED and "다시 조사" in got["reasons"][0]


def _client(*, as_admin: bool) -> TestClient:
    app = FastAPI()
    app.include_router(site_onboarding_router)
    if as_admin:
        app.dependency_overrides[get_current_user] = lambda: {"sub": "kim", "role": "admin"}
    return TestClient(app)


def test_preflight_routes_require_role_and_return_saved_result(env, monkeypatch):
    monkeypatch.setattr(auth_module.config, "AUTH_ENABLED", True)
    fetch, _ = _fake_fetch((404, ""), (404, ""))
    svc.configure_fetcher(fetch)
    client = _client(as_admin=True)
    assert client.get(f"/site-registry/{HOST}/preflight").status_code == 404
    onboarding.register({"host": HOST}, actor="kim")
    saved = client.get(f"/site-registry/{HOST}/preflight")
    assert saved.status_code == 200 and saved.json()["verdict"] == "proceed"
    ran = client.post(f"/site-registry/{HOST}/preflight")
    assert ran.status_code == 200 and ran.json()["host"] == HOST
    assert _client(as_admin=False).post(f"/site-registry/{HOST}/preflight").status_code in (401, 403)


def test_ai_can_only_read_saved_preflight_never_run_it():
    reg = mcp_server.API_REGISTRY
    assert reg["sites.preflight"]["method"] == "GET" and reg["sites.preflight"]["path"] == "/api/v1/site-registry/{host}/preflight"
    assert not any("preflight" in v["path"] and v["method"] != "GET" for v in reg.values())  # 조사 실행(POST)은 사람만
    assert [k for k in reg if "preflight" in k] == ["sites.preflight"]
