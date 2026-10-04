"""범용 팝업 인지(scripts/explorer/popup_probe.py + page_analysis.analyze_popups) 검사.

기준서: docs/specs/2026-09-30_page_analysis_layer.md §3-2 (v4).
- 순수 분석은 합성 데이터로 브라우저 없이 시험한다.
- 수집·안전 닫기·네이버티브 대화상자는 **로컬 HTML** 을 헤드리스 Chrome 에 띄워 시험한다(실제 사이트·계정 미접촉).
  Chrome 을 띄울 수 없는 환경에서는 해당 시험만 건너뛴다.
"""

from __future__ import annotations

import pytest

from scripts.explorer import page_analysis as pa
from scripts.explorer import popup_probe as pp

# ── 순수 분석 (브라우저 없음) ────────────────────────────────────────────


def _dlg(text="공지입니다", buttons=("닫기",), z=100, cover=0.3, role="dialog", visible=True):
    return {
        "role": role,
        "text": text,
        "z": z,
        "cover": cover,
        "visible": visible,
        "buttons": [{"text": b, "aria": "", "id": ""} for b in buttons],
    }


def _snap_with(*dialogs):
    return {
        "url": "https://example.com",
        "title": "",
        "frames": [
            {
                "idx": 0,
                "url": "u",
                "links": [],
                "inputs": [],
                "buttons": [],
                "forms": [],
                "headings": [],
                "dialogs": list(dialogs),
            }
        ],
    }


def test_popups_are_ordered_top_first_by_z_then_cover():
    snap = _snap_with(_dlg("아래", z=10), _dlg("맨 위", z=300), _dlg("중간", z=100))
    order = [p["text"] for p in pa.analyze_popups(snap)]
    assert order == ["맨 위", "중간", "아래"]


def test_hidden_popups_are_excluded():
    snap = _snap_with(_dlg("보임"), _dlg("숨김", visible=False))
    assert [p["text"] for p in pa.analyze_popups(snap)] == ["보임"]


@pytest.mark.parametrize(
    ("text", "buttons", "kind"),
    [
        ("쿠키 사용에 동의하시겠습니까", ("동의", "거부"), "consent"),
        ("이 항목을 삭제하시겠습니까", ("확인", "취소"), "confirm"),
        ("태그 불가 단어가 있습니다", ("확인",), "warning"),
        ("오류가 발생했습니다", ("확인",), "error"),
        ("이벤트 진행 중! 오늘 하루 보지 않기", ("닫기",), "ad"),
        ("새로운 기능 안내", ("닫기",), "notice"),
        ("", ("닫기",), "notice"),
    ],
)
def test_popup_kind_is_classified_from_structure_and_text(text, buttons, kind):
    popup = pa.analyze_popups(_snap_with(_dlg(text, buttons)))[0]
    assert popup["kind"] == kind


def test_safe_close_prefers_close_or_cancel_over_confirm():
    popup = pa.analyze_popups(_snap_with(_dlg("삭제할까요", ("확인", "취소"))))[0]
    assert popup["safe_close"]["label"] == "취소"
    assert popup["needs_review"] is False


def test_danger_button_is_never_chosen_as_safe_close():
    popup = pa.analyze_popups(_snap_with(_dlg("결제를 진행합니다", ("결제하기", "삭제"))))[0]
    assert popup["safe_close"] is None
    assert popup["needs_review"] is True


@pytest.mark.parametrize("buttons", [("삭제 확인",), ("확인 삭제",), ("결제 확인",), ("결제 확인", "발행 확인")])
def test_confirm_role_button_that_is_dangerous_is_never_the_safe_close(buttons):
    """역할은 confirm(확인) 이지만 위험한 버튼('삭제 확인' 등)은 안전 닫기로 고르면 안 된다 — 위험 필터의 유일한 방어선."""
    popup = pa.analyze_popups(_snap_with(_dlg("문구", buttons)))[0]
    assert popup["buttons"][0]["role"] == "confirm"
    assert popup["safe_close"] is None
    assert popup["needs_review"] is True


def test_dangerous_confirm_is_skipped_in_favor_of_a_safe_close_button():
    popup = pa.analyze_popups(_snap_with(_dlg("문구", ("삭제 확인", "닫기"))))[0]
    assert popup["safe_close"]["label"] == "닫기"


def test_popup_with_no_buttons_needs_review_but_can_use_escape():
    popup = pa.analyze_popups(_snap_with(_dlg("버튼 없는 안내", ())))[0]
    assert popup["safe_close"] is None
    assert popup["needs_review"] is False and popup["escape_ok"] is True


def test_popup_text_is_shortened_and_kept():
    popup = pa.analyze_popups(_snap_with(_dlg("가" * 500)))[0]
    assert 0 < len(popup["text"]) <= 200


def test_analyze_snapshot_reports_popup_count_and_state():
    snap = _snap_with(_dlg("A"), _dlg("B", z=200), _dlg("C", z=50))
    result = pa.analyze_snapshot(snap)
    assert result["summary"]["popups"] == 3
    assert result["page_state"]["state"] == "popup_blocking"
    assert [p["text"] for p in result["popups"]] == ["B", "A", "C"]


def test_no_popups_key_is_empty_not_error():
    assert pa.analyze_snapshot({"frames": []})["popups"] == []


# ── 실제 브라우저(로컬 HTML) ─────────────────────────────────────────────


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:  # noqa: BLE001 - Chrome 을 띄울 수 없는 환경(CI 등)에서는 브라우저 시험만 건너뛴다
            pytest.skip(f"헤드리스 Chrome 사용 불가: {type(exc).__name__}")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    pg = browser.new_page(viewport={"width": 1000, "height": 700})
    yield pg
    pg.close()


_BASE = "<body style='margin:0'><h1>본문</h1><button id='under'>본문 버튼</button>"


def _layer(idx, z, text, buttons, extra_style="", attrs=""):
    btns = "".join(f"<button>{b}</button>" for b in buttons)
    return (
        f"<div {attrs} style='position:fixed;left:{100 + idx * 30}px;top:{80 + idx * 30}px;width:400px;height:260px;"
        f"z-index:{z};background:#fff;border:1px solid #333;{extra_style}'><p>{text}</p>{btns}</div>"
    )


def test_probe_finds_three_stacked_popups_in_z_order(page):
    page.set_content(
        _BASE
        + _layer(0, 100, "첫번째 공지", ["닫기"], attrs="role='dialog'")
        + _layer(1, 300, "세번째 맨 위", ["확인", "취소"], attrs="role='dialog'")
        + _layer(2, 200, "두번째 경고", ["확인"], attrs="class='layer_popup'")
    )
    found = pp.probe_popups(page)
    assert [d["text"].startswith(x) for d, x in zip(found, ("세번째", "두번째", "첫번째"))] == [True, True, True]
    assert found[0]["z"] > found[1]["z"] > found[2]["z"]
    assert {b["text"] for b in found[0]["buttons"]} == {"확인", "취소"}


def test_same_z_index_uses_dom_order_later_drawn_is_on_top(page):
    """z-index 를 지정하지 않은(모두 같은) 팝업이 여러 개면 DOM 에서 나중에 그려진 것이 위에 보인다."""

    def box(i, text):
        return (
            f"<div role='dialog' style='position:fixed;left:{100 + i * 40}px;top:{80 + i * 40}px;width:300px;height:180px;"
            f"background:#fff;border:1px solid #333'><p>{text}</p><button>닫기</button></div>"
        )

    page.set_content(_BASE + box(0, "먼저 그려짐") + box(1, "중간") + box(2, "나중에 그려짐"))
    found = pp.probe_popups(page)
    assert [d["text"].split()[0] for d in found] == ["나중에", "중간", "먼저"]
    assert all("order" not in d for d in found)  # 내부 정렬용 값은 결과에 노출하지 않는다


def test_probe_finds_overlay_without_any_dialog_markup(page):
    """role·클래스 이름 없이 고정 위치 + 큰 z-index 로 화면을 덮는 요소도 팝업으로 본다."""
    page.set_content(
        _BASE
        + "<div style='position:fixed;left:0;top:0;width:100%;height:100%;z-index:9999;background:rgba(0,0,0,.5)'>"
        "<div style='margin:100px auto;width:300px;background:#fff'><p>이름 없는 오버레이</p><button>닫기</button></div></div>"
    )
    found = pp.probe_popups(page)
    assert len(found) == 1 and "이름 없는 오버레이" in found[0]["text"]
    assert found[0]["cover"] >= 0.9


def test_probe_ignores_hidden_and_normal_page_content(page):
    page.set_content(
        _BASE
        + "<div role='dialog' style='display:none'>숨김 다이얼로그</div>"
        + "<div class='modal' style='position:fixed;visibility:hidden;width:300px;height:200px'>보이지 않음</div>"
        + "<div class='popup-notes'>일반 본문 안의 문구(고정 위치 아님)</div>"
    )
    assert pp.probe_popups(page) == []


def test_small_floating_widgets_named_layer_are_not_popups(page):
    """실제 네이버 메인(2026-09-30): 클래스에 'layer' 가 든 92x40 '최상단으로 이동/홈 설정' 플로팅 버튼이 팝업으로 오탐됐다.
    이름만으로는 팝업이 아니다 — 의미 있는 크기(화면 5% 이상)로 화면을 덮어야 한다."""
    page.set_content(
        _BASE
        + "<div class='SettingView-module__layer_setting___zk2O' style='position:fixed;right:20px;bottom:20px;width:92px;height:40px;z-index:50'>"
        "<button>최상단으로 이동</button><button id='viewSetting'>홈 설정</button></div>"
        + "<div class='chat-popup-launcher' style='position:fixed;right:20px;bottom:80px;width:60px;height:60px;z-index:999'><button>채팅</button></div>"
        + "<div class='top-bar layer' style='position:sticky;top:0;width:100%;height:30px;z-index:20'><a href='/'>홈</a></div>"
    )
    assert pp.probe_popups(page) == []


def test_named_popup_that_really_covers_the_screen_is_still_found(page):
    page.set_content(
        _BASE
        + "<div class='layer_popup' style='position:fixed;left:200px;top:100px;width:500px;height:300px;z-index:50;background:#fff'>"
        "<p>충분히 큰 팝업</p><button>닫기</button></div>"
    )
    found = pp.probe_popups(page)
    assert len(found) == 1 and found[0]["cover"] >= 0.05


def test_explicit_dialog_role_is_found_even_when_small(page):
    """role=dialog 는 이름이 아니라 명시적 표식이므로 작아도 팝업이다(작은 토스트/알림창)."""
    page.set_content(
        _BASE
        + "<div role='alertdialog' style='position:fixed;right:10px;top:10px;width:180px;height:60px;z-index:5'><p>저장됨</p><button>확인</button></div>"
    )
    found = pp.probe_popups(page)
    assert len(found) == 1 and found[0]["role"] == "alertdialog"


def test_probe_finds_open_dialog_element_and_cookie_banner(page):
    page.set_content(
        _BASE
        + "<dialog open><p>네이티브 다이얼로그</p><button>닫기</button></dialog>"
        + "<div style='position:fixed;bottom:0;left:0;width:100%;height:220px;z-index:500;background:#eee'>"
        "<span>쿠키 사용에 동의하시겠습니까</span><button>동의</button><button>거부</button></div>"
    )
    texts = " ".join(d["text"] for d in pp.probe_popups(page))
    assert "네이티브 다이얼로그" in texts and "쿠키" in texts


def test_probe_returns_each_popup_once_not_its_nested_children(page):
    page.set_content(
        _BASE
        + _layer(0, 100, "바깥", ["닫기"], attrs="role='dialog'")
        .replace("<p>", "<div class='modal'><p>")
        .replace("</p>", "</p></div>")
    )
    assert len(pp.probe_popups(page)) == 1


def test_probe_does_not_change_the_page(page):
    page.set_content(_BASE + _layer(0, 100, "공지", ["닫기"], attrs="role='dialog'"))
    before = page.content()
    pp.probe_popups(page)
    assert page.content() == before


def test_dismiss_closes_three_stacked_popups_top_first_and_keeps_their_text(page):
    def layer(i, z, text):
        return (
            f"<div id='p{i}' role='dialog' style='position:fixed;left:{100 + i * 20}px;top:{80 + i * 20}px;width:400px;height:200px;"
            f"z-index:{z};background:#fff;border:1px solid #333'><p>{text}</p>"
            f"<button onclick=\"document.getElementById('p{i}').remove()\">닫기</button></div>"
        )

    page.set_content(_BASE + layer(0, 100, "공지 하나") + layer(1, 200, "공지 둘") + layer(2, 300, "공지 셋"))
    result = pp.dismiss_popups_safely(page, max_rounds=10)
    # 맨 위부터 닫히고, 팝업 문구가 결과에 그대로 남는다(본문에 이어진 버튼 글자 포함 — 원문 그대로 보존)
    assert [c["text"].split()[0:2] for c in result["closed"]] == [["공지", "셋"], ["공지", "둘"], ["공지", "하나"]]
    assert result["remaining"] == [] and result["clean"] is True
    assert pp.probe_popups(page) == []


def test_dismiss_does_not_press_dangerous_button_and_reports_it(page):
    page.set_content(
        _BASE
        + "<div role='dialog' style='position:fixed;left:100px;top:100px;width:400px;height:200px;z-index:100;background:#fff'>"
        "<p>결제를 진행하시겠습니까</p><button id='pay' onclick=\"window.paid=true\">결제하기</button></div>"
    )
    result = pp.dismiss_popups_safely(page, max_rounds=5)
    assert page.evaluate("window.paid === true") is False  # 위험 버튼은 누르지 않았다
    assert result["closed"] == [] and result["clean"] is False
    assert result["remaining"][0]["needs_review"] is True and "결제" in result["remaining"][0]["text"]


def test_dismiss_stops_after_max_rounds_when_popup_keeps_coming_back(page):
    page.set_content(
        _BASE
        + "<div id='p' role='dialog' style='position:fixed;left:100px;top:100px;width:300px;height:150px;z-index:100;background:#fff'>"
        "<p>계속 나타남</p><button onclick=\"this.parentNode.style.display='none';setTimeout(()=>this.parentNode.style.display='block',10)\">닫기</button></div>"
    )
    result = pp.dismiss_popups_safely(page, max_rounds=3)
    assert len(result["closed"]) <= 3 and result["clean"] is False


def test_dismiss_uses_escape_for_popup_without_buttons(page):
    page.set_content(
        _BASE
        + "<div id='p' role='dialog' style='position:fixed;left:100px;top:100px;width:300px;height:150px;z-index:100;background:#fff'><p>버튼 없음</p></div>"
        "<script>document.addEventListener('keydown',e=>{if(e.key==='Escape')document.getElementById('p').remove()})</script>"
    )
    result = pp.dismiss_popups_safely(page, max_rounds=3)
    assert result["clean"] is True and result["closed"][0]["how"] == "escape"


# ── 네이티브 alert / confirm / prompt ───────────────────────────────────


def test_native_dialogs_are_recorded_with_safe_policy(page):
    rec = pp.install_dialog_recorder(page)
    page.set_content(
        "<button id='a' onclick=\"alert('알림 메시지')\">a</button>"
        "<button id='c' onclick=\"window.r = confirm('삭제할까요?')\">c</button>"
        "<button id='p' onclick=\"window.q = prompt('이름?','기본')\">p</button>"
    )
    page.click("#a")
    page.click("#c")
    page.click("#p")
    kinds = [(e["type"], e["handled"]) for e in rec.events]
    assert kinds == [("alert", "accept"), ("confirm", "dismiss"), ("prompt", "dismiss")]
    assert page.evaluate("window.r") is False  # confirm 은 취소(안전)
    assert page.evaluate("window.q") is None  # prompt 도 취소
    assert rec.events[0]["message"] == "알림 메시지"


def test_dialog_recorder_truncates_long_messages(page):
    rec = pp.install_dialog_recorder(page)
    page.set_content("<button id='a' onclick=\"alert('가'.repeat(900))\">a</button>")
    page.click("#a")
    assert len(rec.events[0]["message"]) <= 200
