"""카페 글쓰기 라우터(cafe/cli_router._cmd_cafe write/publish)가 새 write_post 시그니처로 호출하는지 검사."""

from __future__ import annotations

import json

import pytest

from scripts.naver.cafe import cli_router as router


class _FakeCafe:
    calls: list[dict] = []
    result: dict = {"ok": True, "mode": "awaiting_approval"}

    def __init__(self, page):
        self.page = page

    def write_post(self, **kwargs):
        _FakeCafe.calls.append(kwargs)
        return _FakeCafe.result


@pytest.fixture
def fake_cafe(monkeypatch, tmp_path):
    import scripts.naver.cafe as cafe_pkg
    import scripts.browser.cdp.connection as wc

    _FakeCafe.calls = []
    _FakeCafe.result = {"ok": True, "mode": "awaiting_approval"}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(router, "gate_check", lambda *a, **k: None)
    monkeypatch.setattr(wc, "get_page", lambda: object())
    monkeypatch.setattr(cafe_pkg, "NaverCafe", _FakeCafe)
    return _FakeCafe


def _run(sub, *extra):
    router._cmd_cafe(sub, ["--cafe-url=testcafe", "--board-name=자유게시판", "--title=제목", "--body=본문", *extra])


def test_write_saves_draft_with_approval_required(fake_cafe, capsys):
    _run("write")
    call = fake_cafe.calls[0]
    assert call["board_name"] == "자유게시판"
    assert call["require_approval"] is True  # 발행 요청이 없으면 임시저장(승인 대기)
    assert "board_no" not in call and "send" not in call
    record = json.loads(capsys.readouterr().out.split("saved:")[0])
    assert record["ok"] is True and record["published"] is False


def test_publish_requires_approval_flags(fake_cafe):
    with pytest.raises(SystemExit):
        _run("publish")  # --approved 와 확인 문구가 없으면 게시 전에 막힘
    assert fake_cafe.calls == []


def test_publish_with_approval_publishes_directly(fake_cafe, capsys):
    from scripts.naver.common.content import APPROVAL_CONFIRM_TEXT

    fake_cafe.result = {"ok": True, "url": "https://cafe.naver.com/testcafe/1"}
    _run("publish", "--approved", f"--confirm={APPROVAL_CONFIRM_TEXT}")
    assert fake_cafe.calls[0]["require_approval"] is False
    record = json.loads(capsys.readouterr().out.split("saved:")[0])
    assert record["published"] is True


def test_live_write_without_board_name_fails_before_browser(fake_cafe):
    with pytest.raises(SystemExit):
        router._cmd_cafe("write", ["--cafe-url=testcafe", "--board-no=12", "--title=제목"])
    assert fake_cafe.calls == []


def test_dry_run_with_board_no_still_works(fake_cafe):
    router._cmd_cafe("write", ["--cafe-url=testcafe", "--board-no=12", "--title=제목", "--dry-run"])
    assert fake_cafe.calls == []
