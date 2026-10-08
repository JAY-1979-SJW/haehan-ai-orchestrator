"""사이트가 정확히 열렸는지 판정하는 순수 로직 시험(실제 브라우저·네트워크 없음). 기준서 2026-10-02_app_agent_dispatch.md §9-8."""

from __future__ import annotations

import json
from typing import Any

from scripts.browser.cdp import cdp_verify as v


def _info(**over) -> v.PageInfo:
    base: dict[str, Any] = {
        "href": "https://developers.hiworks.com/",
        "ready": "complete",
        "title": "하이웍스 - 개발자 센터",
        "text_len": 987,
        "head_lower": "하이웍스 - 개발자 센터 전자결재 메신저 알림",
        "has_password": False,
        "shot_bytes": 90_000,
        "shot_colors": 800,
    }
    base.update(over)
    return v.PageInfo(**base)


URL = "https://developers.hiworks.com/"


def test_normal_site_is_ok():
    verdict = v.classify(_info(), URL)
    assert verdict.status == v.OK
    assert verdict.opened is True


def test_redirect_to_other_site_is_wrong_site():
    verdict = v.classify(_info(href="https://www.example.org/", head_lower="example domain"), URL)
    assert verdict.status == v.WRONG_SITE
    assert "example.org" in verdict.reason
    assert verdict.opened is False


def test_subdomain_and_two_level_tld_expectations():
    assert v.host_matches("mail.google.com", ("google.com",))
    assert not v.host_matches("evilgoogle.com", ("google.com",))
    assert v._registrable("eum.cw.or.kr") == "cw.or.kr"
    assert v._registrable("www.hiworks.com") == "hiworks.com"
    ok = v.classify(_info(href="https://eum.cw.or.kr/main", head_lower="건설근로자공제회"), "https://eum.cw.or.kr/main")
    assert ok.status == v.OK
    other = v.classify(_info(href="https://www.cw.or.kr/", head_lower="공제회"), "https://eum.cw.or.kr/main")
    assert other.status == v.OK  # 같은 등록 도메인(cw.or.kr)은 같은 사이트로 본다


def test_login_screen_counts_as_opened_not_failure():
    same_site = v.classify(_info(href="https://developers.hiworks.com/member/assemble_login", has_password=True), URL)
    assert same_site.status == v.LOGIN
    assert same_site.opened is True
    moved = v.classify(_info(href="https://accounts.gabia.com/", has_password=True, head_lower="로그인"), URL)
    assert moved.status == v.LOGIN
    assert "gabia" in moved.reason
    by_path = v.classify(
        _info(href="https://nid.naver.com/nidlogin.login", has_password=False, head_lower="네이버 로그인"),
        "https://www.naver.com/",
    )
    assert by_path.status == v.LOGIN


def test_blocked_and_error_pages_are_not_opened():
    blocked = v.classify(_info(head_lower="access denied you don't have permission"), URL)
    assert blocked.status == v.BLOCKED
    assert blocked.checks["block_hints"] == ["access denied"]
    korean = v.classify(_info(head_lower="접속이 원활하지 않습니다 잠시 후 다시"), URL)
    assert korean.status == v.BLOCKED
    chrome_err = v.classify(_info(href="chrome-error://chromewebdata/", head_lower=""), URL)
    assert chrome_err.status == v.ERROR
    nxdomain = v.classify(_info(head_lower="this site can’t be reached err_name_not_resolved"), URL)
    assert nxdomain.status == v.ERROR
    assert not (blocked.opened or chrome_err.opened or nxdomain.opened)


def test_blank_page_is_detected_but_small_real_page_is_not():
    blank = v.classify(_info(text_len=0, head_lower="", shot_bytes=4_800, shot_colors=1), URL)
    assert blank.status == v.BLANK
    unknown_visual = v.classify(_info(text_len=0, head_lower="", shot_colors=-1), URL)
    assert unknown_visual.status == v.BLANK  # 화면 통계를 못 구하면 본문이 없는 페이지는 빈 화면으로 본다
    image_page = v.classify(_info(text_len=5, head_lower="사진", shot_bytes=120_000, shot_colors=3000), URL)
    assert image_page.status == v.OK  # 글자는 적어도 화면에 내용이 있으면 정상


def test_expected_text_and_loading_state():
    missing = v.classify(_info(text_len=120), URL, expect_text=("전자결재", "없는문구"))
    assert missing.status == v.WRONG_SITE
    present = v.classify(_info(), URL, expect_text=("전자결재",))
    assert present.status == v.OK
    loading = v.classify(_info(ready="loading"), URL)
    assert loading.status == v.ERROR


def test_verdict_never_contains_page_text():
    verdict = v.classify(_info(head_lower="개인정보가 담긴 본문 123-4567"), URL)
    dumped = json.dumps(
        {"reason": verdict.reason, "title": verdict.title, "checks": verdict.checks}, ensure_ascii=False
    )
    assert "개인정보" not in dumped
    assert "123-4567" not in dumped


def test_verify_tab_reader_failure_is_not_success():
    def boom(_ws):
        raise TimeoutError("socket")

    verdict = v.verify_tab("ws://x", URL, reader=boom)
    assert verdict.status == v.ERROR
    assert "TimeoutError" in verdict.reason
    assert verdict.opened is False
    assert v.verify_tab("ws://x", URL, reader=lambda _ws: _info()).status == v.OK
