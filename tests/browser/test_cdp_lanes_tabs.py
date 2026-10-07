"""CDP 칸 등록표·새 탭 안전 열기·칸 시작 CLI — 가짜 CDP 서버만 사용(실제 브라우저 없음). 기준서 2026-10-02_app_agent_dispatch.md §9."""

from __future__ import annotations

import json
import threading
import urllib.parse
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from scripts.browser.cdp import cdp_lane_start, cdp_lanes, cdp_tabs


class FakeChrome:
    """가짜 CDP HTTP 서버. mode: navigate(주소로 이동) | blank(about:blank 에 머묾) | error(오류 페이지)."""

    def __init__(self, mode: str = "navigate", lag: int = 0, ready: str = "complete"):
        self.mode = mode
        self.lag = lag  # 탭 안 페이지가 목표 주소로 바뀌기 전까지 about:blank 로 보이는 확인 횟수
        self.ready = ready
        self.probes: dict[str, int] = {}
        self.tabs: dict[str, str] = {"USER01": "https://example.org/mine", "USER02": "http://localhost:3000/scheduled"}
        self.closed: list[str] = []
        self.created = 0
        parent = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj, code=200):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _new(self):
                url = urllib.parse.unquote(self.path.split("?", 1)[1]) if "?" in self.path else ""
                parent.created += 1
                tab_id = f"NEW{parent.created:03d}"
                parent.tabs[tab_id] = {
                    "navigate": url,
                    "blank": "about:blank",
                    "error": "chrome-error://chromewebdata/",
                }[parent.mode]
                self._send(
                    {
                        "id": tab_id,
                        "type": "page",
                        "url": parent.tabs[tab_id],
                        "webSocketDebuggerUrl": f"ws://x/{tab_id}",
                    }
                )

            def do_PUT(self):
                if self.path.startswith("/json/new"):
                    self._new()
                else:
                    self._send({}, 404)

            def do_GET(self):
                if self.path.startswith("/json/list"):
                    self._send([{"id": i, "type": "page", "url": u, "title": ""} for i, u in parent.tabs.items()])
                elif self.path.startswith("/json/close/"):
                    tab_id = self.path.rsplit("/", 1)[1]
                    parent.tabs.pop(tab_id, None)
                    parent.closed.append(tab_id)
                    self._send({})
                elif self.path.startswith("/json/version"):
                    self._send({"Browser": "Fake/1"})
                else:
                    self._send({}, 404)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def probe(self, ws_url: str) -> tuple[str, str]:
        """탭 안의 실제 상태(location.href, readyState) — /json/list 의 미리 채워진 주소와 다를 수 있다."""
        tab_id = ws_url.rsplit("/", 1)[1]
        n = self.probes[tab_id] = self.probes.get(tab_id, 0) + 1
        if self.mode == "blank":
            return "about:blank", "complete"
        if self.mode == "error":
            return "chrome-error://chromewebdata/", "complete"
        if n <= self.lag:
            return "about:blank", "complete"
        return self.tabs.get(tab_id, ""), self.ready

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def chrome(monkeypatch, tmp_path):
    made: list[FakeChrome] = []

    def make(mode="navigate", **kw):
        fake = FakeChrome(mode, **kw)
        made.append(fake)
        monkeypatch.setitem(cdp_lanes.LANES, "fake", cdp_lanes.Lane("fake", fake.port, tmp_path / "p", ()))
        return fake

    yield make
    cdp_tabs.close_owned()
    for f in made:
        f.stop()


def _open(fake, **kw):
    kw.setdefault("wait_sec", 0.6)
    return cdp_tabs.open_tab(
        "https://developers.hiworks.com/", lane="fake", reason="test", probe=fake.probe, sleep=lambda _s: None, **kw
    )


# ── 칸 등록표 ───────────────────────────────────────────────────────────


def test_registry_is_consistent_and_general_keeps_existing_port():
    assert cdp_lanes.validate_registry() == []
    general = cdp_lanes.get_lane("general")
    assert general.port == 9222
    assert general.pid_file.name == "cdp_force_pid.json"  # 기존 PID 파일 그대로
    assert cdp_lanes.get_lane("naver").pid_file.name == "cdp_force_pid_naver.json"


def test_lane_for_site_and_unknown_defaults():
    assert cdp_lanes.lane_for_site("Naver").name == "naver"
    assert cdp_lanes.lane_for_site("hiworks").name == "groupware"
    assert cdp_lanes.lane_for_site("eum").name == "groupware"
    assert cdp_lanes.lane_for_site("google").name == "general"
    assert cdp_lanes.lane_for_site("").name == "general"
    with pytest.raises(cdp_lanes.UnknownLane):
        cdp_lanes.get_lane("nope")


def test_validate_registry_detects_duplicates(tmp_path):
    a = cdp_lanes.Lane("a", 9300, tmp_path / "x", ("naver",))
    b = cdp_lanes.Lane("b", 9300, tmp_path / "x", ("naver",))
    errors = cdp_lanes.validate_registry({"a": a, "b": b})
    assert any("포트 9300" in e for e in errors)
    assert any("프로필 중복" in e for e in errors)
    assert any("'naver'" in e and "두 칸" in e for e in errors)


def test_can_start_enforces_active_lane_cap():
    alive = {"general", "naver", "groupware"}
    fn = lambda lane: lane.name in alive  # noqa: E731
    assert cdp_lanes.can_start("naver", fn) == (True, "이미 켜져 있음")
    assert cdp_lanes.MAX_ACTIVE_LANES == 3
    only_two = lambda lane: lane.name in {"general", "naver"}  # noqa: E731
    assert cdp_lanes.can_start("groupware", only_two)[0] is True
    extra = dict(cdp_lanes.LANES)
    extra["extra"] = cdp_lanes.Lane("extra", 9400, Path("x"), ())
    cdp_lanes.LANES["extra"] = extra["extra"]
    try:
        ok, why = cdp_lanes.can_start("extra", fn)
    finally:
        cdp_lanes.LANES.pop("extra")
    assert ok is False
    assert "상한" in why


def test_is_alive_uses_http_only():
    class R:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    lane = cdp_lanes.get_lane("general")
    assert cdp_lanes.is_alive(lane, opener=lambda *a, **k: R()) is True

    def boom(*a, **k):
        raise OSError("refused")

    assert cdp_lanes.is_alive(lane, opener=boom) is False


# ── 새 탭 안전 열기 ─────────────────────────────────────────────────────


def test_open_tab_navigates_immediately_and_records_ownership(chrome):
    fake = chrome("navigate")
    h = _open(fake)
    assert h.url == "https://developers.hiworks.com/"
    assert fake.tabs[h.tab_id] == "https://developers.hiworks.com/"
    assert not any(u == "about:blank" for u in fake.tabs.values())
    assert cdp_tabs.owned_count() == 1
    assert [t["owned_reason"] for t in cdp_tabs.list_tabs("fake") if t["id"] == h.tab_id] == ["test"]


def test_does_not_report_success_while_page_inside_tab_is_still_blank(chrome):
    """목록(/json/list)은 목표 주소를 미리 보여 주지만 탭 안은 아직 about:blank — 이때 성공을 돌려주면 '사이트가 안 열린' 상태가 된다."""
    fake = chrome("navigate", lag=4)
    h = _open(fake, wait_sec=5.0)
    listed = [t["url"] for t in cdp_tabs.list_tabs("fake") if t["id"] == h.tab_id]
    assert listed == ["https://developers.hiworks.com/"]  # 목록은 처음부터 목표 주소
    assert fake.probes[h.tab_id] == 5  # 탭 안 실제 상태를 4번 about:blank 로 본 뒤 5번째에 성공으로 판정
    assert h.url == "https://developers.hiworks.com/"


def test_loading_state_is_not_arrival_but_interactive_is(chrome):
    fake = chrome("navigate", ready="loading")
    with pytest.raises(cdp_tabs.CdpTabError):
        _open(fake, retries=0)
    fake2 = chrome("navigate", ready="interactive")
    assert _open(fake2).url == "https://developers.hiworks.com/"


def test_stuck_blank_tab_is_closed_retried_and_never_left_behind(chrome):
    fake = chrome("blank")
    with pytest.raises(cdp_tabs.CdpTabError, match="페이지가 뜨지 않음"):
        _open(fake, retries=1)
    assert fake.created == 2  # 1회 재시도
    assert len(fake.closed) == 2  # 만든 탭을 모두 닫음
    assert "about:blank" not in fake.tabs.values()
    assert set(fake.tabs) == {"USER01", "USER02"}  # 사용자 탭 불변
    assert cdp_tabs.owned_count() == 0


def test_error_page_fails_fast_without_waiting(chrome):
    fake = chrome("error")
    with pytest.raises(cdp_tabs.CdpTabError):
        _open(fake, retries=0)
    assert set(fake.tabs) == {"USER01", "USER02"}


def test_user_tabs_are_never_closed(chrome):
    fake = chrome("navigate")
    h = _open(fake)
    with pytest.raises(cdp_tabs.NotOwned):
        cdp_tabs.close_tab(cdp_tabs.TabHandle("USER01", "fake", "x", "t"))
    assert "USER01" in fake.tabs
    cdp_tabs.close_tab(h)
    assert h.tab_id not in fake.tabs
    assert cdp_tabs.close_owned() == 0


def test_close_owned_closes_only_my_tabs(chrome):
    fake = chrome("navigate")
    a = _open(fake)
    b = cdp_tabs.open_tab("https://example.com/", lane="fake", reason="other", wait_sec=0.6, probe=fake.probe, sleep=lambda _s: None)
    assert cdp_tabs.close_owned("fake", reason="test") == 1
    assert a.tab_id not in fake.tabs
    assert b.tab_id in fake.tabs
    assert {"USER01", "USER02"} <= set(fake.tabs)
    assert cdp_tabs.close_owned() == 1


def test_lane_down_is_reported_not_swallowed(monkeypatch, tmp_path):
    monkeypatch.setitem(cdp_lanes.LANES, "dead", cdp_lanes.Lane("dead", 1, tmp_path / "p", ()))
    with pytest.raises(cdp_tabs.LaneDown):
        cdp_tabs.open_tab("https://example.com/", lane="dead", reason="t", wait_sec=0.2, sleep=lambda _s: None)
    with pytest.raises(cdp_tabs.LaneDown):
        cdp_tabs.list_tabs("dead")


def test_input_validation(chrome):
    chrome("navigate")
    with pytest.raises(ValueError, match="reason"):
        cdp_tabs.open_tab("https://example.com/", lane="fake", reason=" ")
    with pytest.raises(ValueError, match="http"):
        cdp_tabs.open_tab("file:///C:/secret.txt", lane="fake", reason="t")
    with pytest.raises(cdp_lanes.UnknownLane):
        cdp_tabs.open_tab("https://example.com/", lane="nope", reason="t")


def test_url_with_query_and_hash_survives(chrome):
    fake = chrome("navigate")
    target = "https://example.com/a?x=1&y=한글#frag"
    h = cdp_tabs.open_tab(target, lane="fake", reason="t", wait_sec=0.6, probe=fake.probe, sleep=lambda _s: None)
    assert urllib.parse.unquote(fake.tabs[h.tab_id]) == target or fake.tabs[h.tab_id] == target


# ── 칸 시작 CLI ─────────────────────────────────────────────────────────


def test_apply_lane_sets_force_start_globals_for_that_lane(monkeypatch):
    base = cdp_lane_start.base
    for name in ("CDP_PORT", "PROFILE_DIR", "PID_FILE"):
        monkeypatch.setattr(base, name, getattr(base, name))  # 시험 뒤 원복
    lane = cdp_lanes.get_lane("naver")
    cdp_lane_start.apply_lane(lane)
    assert (base.CDP_PORT, base.PROFILE_DIR, base.PID_FILE) == (lane.port, lane.profile_dir, lane.pid_file)


def test_start_is_refused_when_cap_reached_and_unknown_lane_rejected(monkeypatch, capsys):
    monkeypatch.setattr(cdp_lanes, "can_start", lambda name, *a, **k: (False, "상한"))
    started = []
    monkeypatch.setattr(cdp_lane_start.base, "cmd_start", lambda url="": started.append(url) or 0)
    assert cdp_lane_start.run(["start", "--lane", "naver"]) == 3
    assert started == []
    assert cdp_lane_start.run(["start", "--lane", "nope"]) == 2
    assert "등록되지 않은" in capsys.readouterr().out


def test_start_general_delegates_to_existing_logic(monkeypatch):
    base = cdp_lane_start.base
    for name in ("CDP_PORT", "PROFILE_DIR", "PID_FILE"):
        monkeypatch.setattr(base, name, getattr(base, name))
    seen = {}
    monkeypatch.setattr(cdp_lanes, "can_start", lambda name, *a, **k: (True, "ok"))
    monkeypatch.setattr(base, "cmd_start", lambda url="": seen.update(port=base.CDP_PORT, url=url) or 0)
    assert cdp_lane_start.run(["start", "https://example.com/"]) == 0
    assert seen == {"port": 9222, "url": "https://example.com/"}


def test_list_reports_registry(monkeypatch, capsys):
    monkeypatch.setattr(cdp_lanes, "is_alive", lambda lane, *a, **k: lane.name == "general")
    assert cdp_lane_start.run(["list"]) == 0
    out = capsys.readouterr().out
    assert "general" in out
    assert "naver" in out
    assert "groupware" in out
    assert "켜짐" in out
    assert replace(cdp_lanes.get_lane("general")).port == 9222
