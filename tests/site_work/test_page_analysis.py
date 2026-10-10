"""페이지 구조 분석 계층(scripts/explorer/page_analysis.py) 검사.

브라우저 없이 합성 스냅샷으로 검증한다. 기준서: docs/specs/2026-09-30_page_analysis_layer.md
"""

from __future__ import annotations

import copy
import json

import pytest

from scripts.explorer import page_analysis as pa

# 2026-09-19 셀렉터 헬스체크에서 MISSING(깨짐)이던 실제 셀렉터 10개 (기준서 §5-1)
BROKEN_SELECTORS = [
    "button.publish_btn__m9KHH",
    'input[ng-model="vm.product.detailAttribute.purchaseQuantityInfo.minPurchaseQuantity"]',
    'input[ng-model="vm.product.detailAttribute.seoInfo.pageTitle"]',
    'input[ng-model="vm.viewData.isDirectInput"]',
    'select[ng-model="vm.viewData.originAreaInfo.originAreaExposureType"]',
    ".se-section-documentTitle",
    ".se-section-text",
    ".se-text-paragraph",
    'button:has-text("저장")',
    'button[data-name="image"]',
]


def _snap(url="https://example.com/write", title="", **frame) -> dict:
    base = {"idx": 0, "url": url, "links": [], "inputs": [], "buttons": [], "forms": [], "headings": []}
    base.update(frame)
    return {"url": url, "title": title, "captured_at": "2026-09-30T00:00:00", "frames": [base]}


# ── 셀렉터 안정성 점수 ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("selector", "low", "high"),
    [
        ("button.publish_btn__m9KHH", 0, 20),  # 빌드 해시 클래스
        ('input[ng-model="vm.viewData.isDirectInput"]', 30, 40),  # 프레임워크 내부 속성
        ('button:has-text("저장")', 45, 55),  # 문구 의존
        ("li:nth-child(3) > a", 15, 25),  # 위치 기반
        ('button[aria-label="저장"]', 70, 80),
        ('button[data-name="image"]', 65, 75),
        ('input[name="title"]', 75, 85),
        ("#login_button", 85, 95),
    ],
)
def test_score_selector_by_kind(selector, low, high):
    score, reason = pa.score_selector(selector)
    assert low <= score <= high, (selector, score, reason)
    assert reason


def test_hashed_id_is_not_treated_as_stable():
    stable, _ = pa.score_selector("#btnPublish")
    hashed, _ = pa.score_selector("#publish__x8Kq2Lm")
    assert hashed < stable


def test_combined_selector_takes_the_most_fragile_part():
    combined, _ = pa.score_selector('input[name="title"].field__aB3dE9x')
    assert combined <= 20  # 안정 속성(name)이 있어도 해시 클래스가 섞이면 취약


def test_broken_selectors_from_real_report_are_flagged_fragile():
    """기준서 §5-1: 실제로 깨진 셀렉터 10개 중 9개가 점수 50 이하."""
    scores = [pa.score_selector(s)[0] for s in BROKEN_SELECTORS]
    assert sum(1 for x in scores if x <= 50) >= 9
    assert pa.score_selector("button.publish_btn__m9KHH")[0] <= 20


# ── 역할 분류 ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("로그인", "login"),
        ("Sign in", "login"),
        ("검색", "search"),
        ("글쓰기", "write"),
        ("임시저장", "save"),
        ("저장", "save"),
        ("발행", "publish"),
        ("다음", "next"),
        ("닫기", "close"),
        ("아무 관계 없는 문구", "other"),
        ("", "other"),
    ],
)
def test_classify_button_role(text, expected):
    assert pa.classify_role("button", text) == expected


def test_password_input_is_password_role():
    assert pa.classify_role("input", "", input_type="password") == "password"


def test_search_input_role_from_placeholder():
    assert pa.classify_role("input", "검색어를 입력하세요") == "search"


# ── 위험 동작 ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("결제하기", "payment"),
        ("송금", "payment"),
        ("삭제", "destructive"),
        ("회원 탈퇴", "destructive"),
        ("발행", "publish"),
        ("메일 전송", "send"),
        ("입찰 참여", "legal"),
        ("전자서명", "legal"),
        ("저장", "safe"),
        ("", "safe"),
    ],
)
def test_classify_risk(text, expected):
    assert pa.classify_risk(text) == expected


def test_risk_reuses_existing_keyword_table():
    from core.agent_runtime.runtime.universal.generic_selector_discovery import _RISK_BUTTON_KEYWORDS

    assert pa.RISK_KEYWORD_SOURCE is _RISK_BUTTON_KEYWORDS


# ── 페이지 상태 ───────────────────────────────────────────────────────


def test_login_page_by_url():
    snap = _snap(url="https://nid.naver.com/nidlogin.login?mode=form")
    assert pa.classify_page_state(snap)["state"] == "login_required"


def test_login_page_by_password_input():
    snap = _snap(
        inputs=[
            {"tag": "INPUT", "type": "password", "name": "pw", "id": "", "placeholder": "", "aria": "", "visible": True}
        ],
        buttons=[{"text": "로그인", "id": "", "aria": "", "cls": "", "visible": True}],
    )
    assert pa.classify_page_state(snap)["state"] == "login_required"


def test_captcha_detected_and_wins_over_login():
    snap = _snap(
        url="https://nid.naver.com/nidlogin.login",
        headings=[{"level": "H2", "text": "자동입력 방지 문자를 입력해 주세요"}],
    )
    assert pa.classify_page_state(snap)["state"] == "captcha"


def test_permission_denied_by_text():
    snap = _snap(headings=[{"level": "H1", "text": "접근 권한이 없습니다"}])
    assert pa.classify_page_state(snap)["state"] == "permission_denied"


def test_popup_blocking_uses_dialogs_when_present():
    snap = _snap(dialogs=[{"role": "dialog", "text": "공지", "visible": True}])
    assert pa.classify_page_state(snap)["state"] == "popup_blocking"


def test_normal_page_is_ok_and_empty_page_is_unknown():
    ok = _snap(buttons=[{"text": "저장", "id": "", "aria": "", "cls": "", "visible": True}])
    assert pa.classify_page_state(ok)["state"] == "ok"
    assert pa.classify_page_state(_snap())["state"] == "unknown"


def test_evidence_contains_rule_names_not_page_text():
    snap = _snap(headings=[{"level": "H1", "text": "접근 권한이 없습니다 고객명 홍길동 010-1234-5678"}])
    evidence = " ".join(pa.classify_page_state(snap)["evidence"])
    assert "홍길동" not in evidence and "010" not in evidence


# ── 후보 셀렉터 ───────────────────────────────────────────────────────


def _button(text="저장", **kw):
    return {"text": text, "id": "", "aria": "", "cls": "", "visible": True, **kw}


def test_role_based_candidate_comes_first_for_unique_named_button():
    result = pa.analyze_snapshot(_snap(buttons=[_button("저장", cls="btn__aB3dE9x")]))
    cands = result["elements"][0]["selectors"]
    assert cands[0]["kind"] == "role"
    assert cands[0]["locator"] == 'get_by_role("button", name="저장")'
    assert cands[0]["stability"] >= max(c["stability"] for c in cands[1:])


def test_duplicate_names_are_downgraded_and_marked():
    result = pa.analyze_snapshot(_snap(buttons=[_button("확인"), _button("확인")]))
    for el in result["elements"]:
        first = el["selectors"][0]
        assert first["kind"] == "role" and first["stability"] < 60
        assert "중복" in first["reason"]


def test_quotes_in_labels_are_escaped():
    result = pa.analyze_snapshot(_snap(buttons=[_button('말 "따옴표" 버튼')]))
    assert '\\"따옴표\\"' in result["elements"][0]["selectors"][0]["locator"]


def test_hashed_class_candidate_is_scored_low():
    result = pa.analyze_snapshot(_snap(buttons=[_button("발행", cls="publish_btn__m9KHH")]))
    css = [c for c in result["elements"][0]["selectors"] if c["kind"] == "css"]
    assert css and min(c["stability"] for c in css) <= 20


# ── 통합 ──────────────────────────────────────────────────────────────


def test_analyze_snapshot_structure_and_roles_and_risk():
    snap = _snap(
        buttons=[_button("로그인"), _button("삭제"), _button("발행")],
        inputs=[
            {
                "tag": "INPUT",
                "type": "text",
                "name": "title",
                "id": "title",
                "placeholder": "제목",
                "aria": "",
                "visible": True,
            }
        ],
    )
    result = pa.analyze_snapshot(snap)
    by_label = {e["label"]: e for e in result["elements"]}
    assert by_label["로그인"]["role"] == "login"
    assert by_label["삭제"]["risk"] == "destructive"
    assert by_label["발행"]["risk"] == "publish"
    assert result["summary"]["elements"] == 4
    assert result["summary"]["risky"] == 2
    json.dumps(result, ensure_ascii=False)  # 직렬화 가능


def test_input_is_not_mutated():
    snap = _snap(buttons=[_button("저장")])
    before = copy.deepcopy(snap)
    pa.analyze_snapshot(snap)
    assert snap == before


def test_frames_with_errors_are_skipped_not_fatal():
    snap = _snap(buttons=[_button("저장")])
    snap["frames"].append({"idx": 1, "url": "https://x", "error": "boom"})
    assert pa.analyze_snapshot(snap)["summary"]["elements"] == 1


def test_missing_or_bad_snapshot_returns_unknown_not_exception():
    assert pa.analyze_snapshot({})["page_state"]["state"] == "unknown"
    assert pa.analyze_snapshot({"frames": None})["summary"]["elements"] == 0


def test_icon_only_button_with_aria_label_is_included():
    result = pa.analyze_snapshot(_snap(buttons=[_button("", aria="닫기")]))
    assert result["elements"][0]["role"] == "close"


# ── CLI ───────────────────────────────────────────────────────────────


def test_cli_prints_summary_and_returns_zero(tmp_path, capsys):
    p = tmp_path / "snap.json"
    p.write_text(json.dumps(_snap(buttons=[_button("발행")]), ensure_ascii=False), encoding="utf-8")
    assert pa.main([str(p)]) == 0
    out = capsys.readouterr().out
    assert "publish" in out and "page_state" in out


def test_cli_json_flag_outputs_valid_json(tmp_path, capsys):
    p = tmp_path / "snap.json"
    p.write_text(json.dumps(_snap(buttons=[_button("발행")]), ensure_ascii=False), encoding="utf-8")
    assert pa.main([str(p), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["elements"] == 1


def test_cli_missing_file_returns_error_code(tmp_path):
    assert pa.main([str(tmp_path / "nope.json")]) == 2


def test_script_runs_directly_from_other_working_directory(tmp_path):
    """pytest 가 루트를 sys.path 에 넣어 주기 때문에 못 잡던 결함 — 실제로 스크립트를 직접 실행한다(2026-09-30 실측 재현)."""
    import subprocess
    import sys
    from pathlib import Path

    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps(_snap(buttons=[_button("발행")]), ensure_ascii=False), encoding="utf-8")
    script = Path(pa.__file__).resolve()
    proc = subprocess.run(
        [sys.executable, str(script), str(snap), "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-300:]
    assert json.loads(proc.stdout)["summary"]["elements"] == 1


# ── 실제 네이버 페이지 검증(2026-09-30)에서 드러난 빈틈 ──────────────────────


def _link(text="", href="", **kw):
    return {"text": text, "href": href, "target": "", **kw}


def test_nameless_link_gets_href_candidate():
    result = pa.analyze_snapshot(_snap(links=[_link("", "/news/today")]))
    cands = result["elements"][0]["selectors"]
    assert [c["css"] for c in cands] == ['a[href="/news/today"]']
    assert cands[0]["stability"] == 60 and "href" in cands[0]["reason"]


def test_href_with_query_uses_prefix_match_on_path():
    result = pa.analyze_snapshot(_snap(links=[_link("", "/search?q=abc&t=xyz")]))
    assert result["elements"][0]["selectors"][0]["css"] == 'a[href^="/search"]'


@pytest.mark.parametrize(
    "href", ["", "#", "#top", "javascript:void(0)", "/articles/8f3a9c2d7e1b", "/n/123456789", "/" + "a" * 150]
)
def test_unstable_or_useless_href_is_skipped(href):
    result = pa.analyze_snapshot(_snap(links=[_link("", href)]))
    assert result["elements"][0]["selectors"] == []


def test_long_named_link_still_gets_a_css_candidate_but_no_role_candidate():
    result = pa.analyze_snapshot(_snap(links=[_link("가" * 45, "/topic/economy")]))
    kinds = [c["kind"] for c in result["elements"][0]["selectors"]]
    assert kinds == ["css"]


def test_href_candidate_is_only_for_links():
    result = pa.analyze_snapshot(_snap(buttons=[_button("저장", href="/x")]))
    assert not any("href" in c.get("css", "") for c in result["elements"][0]["selectors"])


def test_hidden_risky_elements_are_counted_separately():
    snap = _snap(buttons=[_button("결제하기", visible=False), _button("삭제"), _button("저장")])
    summary = pa.analyze_snapshot(snap)["summary"]
    assert summary["risky"] == 1  # 화면에 보이는 위험 요소만
    assert summary["risky_hidden"] == 1
    hidden = next(e for e in pa.analyze_snapshot(snap)["elements"] if e["label"] == "결제하기")
    assert hidden["risk"] == "payment" and hidden["visible"] is False  # 개별 표시는 유지


@pytest.mark.parametrize("word", ["economy", "search", "decade", "facade", "feedback", "community"])
def test_ordinary_words_are_not_mistaken_for_hashes(word):
    assert pa.looks_hashed(word) is False


@pytest.mark.parametrize("token", ["deadbeef", "facecafe", "decafbad"])
def test_hex_rule_requires_a_digit(token):
    """a~f 로만 이뤄진 8자 이상 토큰은 숫자가 없으면 해시로 보지 않는다(정상 식별자 오탐 방지).
    16진수 규칙에서 '숫자 필수' 조건이 빠지면 이 시험이 잡는다."""
    assert pa.looks_hashed(token) is False


@pytest.mark.parametrize("token", ["8f3a9c2d7e1b", "a1b2c3d4e5f6"])
def test_hex_hash_tokens_are_detected(token):
    assert pa.looks_hashed(token) is True


# ── 실제 네이버 로그인 화면 검증(2026-09-30)에서 드러난 캡차 오탐 ─────────────────


def test_login_page_with_alternative_login_link_is_not_captcha():
    """로그인 화면의 '일회용 로그인' 같은 대체 수단 링크 하나로 화면 전체를 캡차로 보면 안 된다."""
    snap = _snap(
        url="https://nid.naver.com/nidlogin.login?mode=form",
        links=[
            {"text": "일회용 번호", "href": "/otp", "target": ""},
            {"text": "비밀번호 찾기", "href": "/find", "target": ""},
        ],
        inputs=[
            {"tag": "INPUT", "type": "text", "name": "id", "id": "id", "placeholder": "", "aria": "", "visible": True},
            {
                "tag": "INPUT",
                "type": "password",
                "name": "pw",
                "id": "pw",
                "placeholder": "",
                "aria": "",
                "visible": True,
            },
        ],
        buttons=[{"text": "로그인", "id": "log.login", "aria": "", "cls": "", "visible": True}],
    )
    assert pa.classify_page_state(snap)["state"] == "login_required"


def test_captcha_needs_a_blocking_signal_not_a_lone_link():
    only_link = _snap(links=[{"text": "일회용 번호로 로그인", "href": "/otp", "target": ""}], buttons=[_button("확인")])
    assert pa.classify_page_state(only_link)["state"] != "captcha"


def test_captcha_from_visible_heading_still_detected():
    snap = _snap(headings=[{"level": "H2", "text": "보안문자를 입력해 주세요"}])
    assert pa.classify_page_state(snap)["state"] == "captcha"


def test_captcha_from_visible_dialog_text_still_detected():
    snap = _snap(dialogs=[{"role": "dialog", "text": "자동입력 방지 문자를 입력하세요", "visible": True}])
    assert pa.classify_page_state(snap)["state"] == "captcha"


def test_captcha_from_captcha_input_or_image_still_detected():
    snap = _snap(
        inputs=[
            {
                "tag": "INPUT",
                "type": "text",
                "name": "captcha",
                "id": "captchaInput",
                "placeholder": "",
                "aria": "",
                "visible": True,
            }
        ]
    )
    assert pa.classify_page_state(snap)["state"] == "captcha"


def test_hidden_captcha_text_does_not_trigger():
    snap = _snap(
        dialogs=[{"role": "dialog", "text": "자동입력 방지 문자", "visible": False}], buttons=[_button("저장")]
    )
    assert pa.classify_page_state(snap)["state"] == "ok"


def test_hidden_captcha_input_does_not_trigger():
    """화면에 보이지 않는 캡차 입력칸(미리 렌더링된 숨김 요소)은 캡차 상태가 아니다."""
    snap = _snap(
        inputs=[
            {
                "tag": "INPUT",
                "type": "text",
                "name": "captcha",
                "id": "captchaInput",
                "placeholder": "",
                "aria": "",
                "visible": False,
            }
        ],
        buttons=[_button("저장")],
    )
    assert pa.classify_page_state(snap)["state"] == "ok"
