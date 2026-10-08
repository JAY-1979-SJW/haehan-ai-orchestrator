import pytest

from scripts.naver.common import live_safety


def test_detect_robot_signal_matches_korean_security_text():
    result = live_safety.detect_robot_signal("보안문자를 입력해 주세요", url="https://naver.com")

    assert result["ok"] is False
    assert result["detected"] is True
    assert result["reason"] == "robot_or_security_signal"


def test_detect_robot_signal_allows_normal_text():
    result = live_safety.detect_robot_signal("오늘의 카페 새글 목록", title="Naver Cafe")

    assert result["ok"] is True
    assert result["detected"] is False


def test_require_live_flag_blocks_without_explicit_flag():
    with pytest.raises(SystemExit):
        live_safety.require_live_flag([], workflow="content_explore")


def test_require_live_flag_blocks_multi_target_without_flag():
    with pytest.raises(SystemExit):
        live_safety.require_live_flag(["--live-ok"], workflow="content_explore", multi_target=True)


def test_require_live_flag_accepts_explicit_multi_target():
    live_safety.require_live_flag(
        ["--live-ok", "--allow-multi-target"],
        workflow="content_explore",
        multi_target=True,
    )


class _FakePage:
    url = "https://section.cafe.naver.com/"

    def __init__(self, text):
        self.text = text

    def evaluate(self, script):
        if "querySelector" in script:
            return False
        return {"url": self.url, "title": "Cafe", "text": self.text}


def test_ensure_page_safe_raises_on_robot_signal():
    with pytest.raises(live_safety.NaverLiveSafetyBlocked):
        live_safety.ensure_page_safe(_FakePage("비정상 접근이 감지되었습니다"))


def test_ensure_page_safe_allows_normal_page():
    result = live_safety.ensure_page_safe(_FakePage("카페 글 목록"))

    assert result["ok"] is True
