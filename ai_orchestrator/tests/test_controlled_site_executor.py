"""F-4G-1 — local_agent.controlled_site_executor 단위 테스트.

검증 항목 (지시문 6단계):
  1)  "전자세금계산서 조회" → read_only allowed
  2)  "매입세금계산서 조회" → read_only allowed
  3)  "엑셀 다운로드" → download requires_approval
  4)  "PDF 저장" → download requires_approval
  5)  "신고서 제출" → blocked
  6)  "납부하기" → blocked
  7)  "전자세금계산서 발행" → blocked
  8)  "사업자정보 변경" → blocked
  9)  "이체" → blocked
  10) login_required page_state면 manual_action_required
  11) security_program_required면 manual_action_required
  12) captcha_or_bot_check면 manual_action_required
  13) observer_result의 links/buttons/forms를 모두 분석
  14) href query/fragment 제거 유지
  15) input value 출력 없음
  16) page.click/fill/type 없음 (AST 회귀)
  17) cookie/session/storage 접근 없음 (AST 회귀)
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from local_agent import controlled_site_executor as cse  # noqa: E402


# ─── 헬퍼 ────────────────────────────────────────────────────────────────

def _observer_result(**overrides):
    base = {
        "success": True,
        "error_code": "",
        "warnings": [],
        "target_url": "https://www.hometax.go.kr/",
        "final_url_host_path": "www.hometax.go.kr/",
        "title": "국세청 홈택스 - 메인",
        "status_code": 200,
        "page_state": "public_page",
        "text_excerpt": "",
        "text_length": 0,
        "links_count": 0,
        "buttons_count": 0,
        "forms_count": 0,
        "inputs_count": 0,
        "links": [],
        "buttons": [],
        "forms": [],
        "input_types": [],
        "screenshot_path": None,
    }
    base.update(overrides)
    return base


# ═════════════════════════════════════════════════════════════════════════
# 1~9) classify_site_action_candidate — 단일 후보 분류
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("text", [
    "전자세금계산서 조회",
    "매입세금계산서 조회",
    "발급내역 조회",
    "현금영수증 내역",
    "상세 보기",
    "미리보기",
])
def test_read_only_tokens_allowed(text):
    """1, 2 — 조회/내역/상세/보기/미리보기 등은 read_only allowed."""
    out = cse.classify_site_action_candidate({"text": text})
    assert out["allowed"] is True
    assert out["risk_level"] == "read_only"
    assert out["requires_approval"] is False


@pytest.mark.parametrize("text", [
    "엑셀 다운로드",
    "PDF 저장",
    "내려받기",
    "엑셀로 저장",
    "PDF",
    "Excel 다운로드",
    "인쇄",
])
def test_download_tokens_require_approval(text):
    """3, 4 — 다운로드/엑셀/PDF/저장/인쇄는 download / requires_approval."""
    out = cse.classify_site_action_candidate({"text": text})
    assert out["allowed"] is True
    assert out["risk_level"] == "download"
    assert out["requires_approval"] is True


@pytest.mark.parametrize("text", [
    "신고서 제출",         # 5
    "최종 제출",
    "납부하기",            # 6
    "전자세금계산서 발행",  # 7
    "사업자정보 변경",      # 8
    "이체",                # 9
    "결제하기",
    "발행하기",
    "최종전송",
    "전송하기",
    "위임",
    "수임",
    "해지",
    "삭제",
    "취소",
    "정정신고",
    "신고하기",
    "신청하기",
])
def test_blocked_tokens_classified_blocked(text):
    out = cse.classify_site_action_candidate({"text": text})
    assert out["allowed"] is False
    assert out["risk_level"] == "blocked"
    assert out["requires_approval"] is False
    assert out["matched_blocked_tokens"], (
        f"expected matched_blocked_tokens for {text!r}"
    )


def test_blocked_priority_over_read_and_download():
    """blocked + read + download 토큰이 함께 있으면 blocked 가 최우선."""
    out = cse.classify_site_action_candidate(
        {"text": "신고서 제출 후 내역 조회 엑셀 다운로드"},
    )
    assert out["risk_level"] == "blocked"
    assert out["allowed"] is False


def test_download_priority_over_read_when_both():
    """blocked 없을 때 download + read 가 함께면 download (승인 후 실행)."""
    out = cse.classify_site_action_candidate(
        {"text": "조회 결과 엑셀 다운로드"},
    )
    assert out["risk_level"] == "download"
    assert out["requires_approval"] is True


def test_unknown_when_no_tokens():
    """명시적 신호 없으면 unknown / not allowed — 임의 실행 금지."""
    out = cse.classify_site_action_candidate(
        {"text": "공지사항", "href": "/notice"},
    )
    assert out["risk_level"] == "unknown"
    assert out["allowed"] is False


def test_password_form_is_dangerous():
    out = cse.classify_site_action_candidate(
        {"action": "/login", "has_password": True},
    )
    assert out["risk_level"] == "dangerous"
    assert out["allowed"] is False


def test_non_dict_input_safe():
    for v in (None, "조회", 42, ["a"]):
        out = cse.classify_site_action_candidate(v)
        assert out["risk_level"] == "unknown"
        assert out["allowed"] is False


# ═════════════════════════════════════════════════════════════════════════
# 10~13) build_controlled_action_plan — page_state 가드 + links/buttons/forms
# ═════════════════════════════════════════════════════════════════════════

def test_login_required_page_state_marks_manual_action_required():
    """10) login_required → manual_action_required."""
    plan = cse.build_controlled_action_plan(
        _observer_result(page_state="login_required"),
        site_key="hometax",
    )
    assert plan["manual_action_required"] is True
    assert any(
        w.startswith("manual_action_required:login_required")
        for w in plan["warnings"]
    )


@pytest.mark.parametrize("ps", [
    "security_program_required",
    "keyboard_security_required",
    "certificate_plugin_required",
    "browser_not_supported",
    "manual_install_required",
])
def test_security_program_states_mark_manual_action_required(ps):
    """11) 보안프로그램/인증서/키보드보안/브라우저 비호환/수동 설치
    page_state 는 manual_action_required."""
    plan = cse.build_controlled_action_plan(
        _observer_result(page_state=ps),
        site_key="hometax",
    )
    assert plan["manual_action_required"] is True


def test_captcha_state_marks_manual_action_required():
    """12) captcha_or_bot_check → manual_action_required."""
    plan = cse.build_controlled_action_plan(
        _observer_result(page_state="captcha_or_bot_check"),
        site_key="hometax",
    )
    assert plan["manual_action_required"] is True


@pytest.mark.parametrize("ps", ["access_denied", "not_found", "server_error"])
def test_unrecoverable_states_clear_candidates(ps):
    """access_denied / not_found / server_error → unrecoverable, 후보 빈 리스트."""
    plan = cse.build_controlled_action_plan(
        _observer_result(
            page_state=ps,
            links=[{"text": "조회", "href": "/x"}],
            buttons=[{"text": "엑셀 다운로드"}],
        ),
        site_key="hometax",
    )
    assert plan["unrecoverable"] is True
    assert plan["safe_read_candidates"] == []
    assert plan["download_candidates"] == []
    assert plan["blocked_candidates"] == []
    assert any(w.startswith("page_state_unrecoverable:") for w in plan["warnings"])


def test_plan_analyzes_links_buttons_forms_all():
    """13) links / buttons / forms 모두 분석되어 각 카테고리에 라우팅."""
    plan = cse.build_controlled_action_plan(
        _observer_result(
            page_state="public_page",
            links=[
                {"text": "전자세금계산서 조회", "href": "/issued"},
                {"text": "엑셀 다운로드", "href": "/excel"},
                {"text": "신고서 제출", "href": "/submit"},
                {"text": "공지사항", "href": "/notice"},  # unknown — 어디에도 분류 안 됨
            ],
            buttons=[
                {"text": "내려받기", "type": "button"},
                {"text": "납부하기", "type": "submit"},
            ],
            forms=[
                {
                    "action": "/login", "method": "POST",
                    "has_password": True, "input_count": 2,
                },
                {
                    "action": "/lookup",
                    "method": "GET",
                    "has_password": False,
                    "input_count": 1,
                    # action 자체에는 매칭 토큰 없지만 기본은 unknown 처리.
                },
            ],
        ),
        site_key="hometax",
    )

    read_texts = [c["text"] for c in plan["safe_read_candidates"]]
    assert "전자세금계산서 조회" in read_texts

    download_texts = [c["text"] for c in plan["download_candidates"]]
    assert "엑셀 다운로드" in download_texts
    assert "내려받기" in download_texts

    blocked_texts = [c["text"] for c in plan["blocked_candidates"]]
    assert "신고서 제출" in blocked_texts
    assert "납부하기" in blocked_texts

    # password 폼은 dangerous 로 분리.
    assert len(plan["dangerous_candidates"]) == 1
    assert plan["dangerous_candidates"][0]["kind"] == "form"
    assert plan["dangerous_candidates"][0]["has_password"] is True


# ═════════════════════════════════════════════════════════════════════════
# 14) href query/fragment 제거 유지
# ═════════════════════════════════════════════════════════════════════════

def test_query_fragment_stripped_from_candidate_href():
    out = cse.classify_site_action_candidate(
        {
            "text": "엑셀 다운로드",
            "href": "https://hometax.go.kr/excel?token=SECRET&user=me#frag",
        },
    )
    assert out["risk_level"] == "download"

    plan = cse.build_controlled_action_plan(
        _observer_result(
            links=[{
                "text": "엑셀 다운로드",
                "href": "https://hometax.go.kr/excel?token=SECRET#frag",
            }],
        ),
        site_key="hometax",
    )
    href = plan["download_candidates"][0]["href"]
    for sensitive in ("?", "#", "token=", "SECRET", "user=", "#frag"):
        assert sensitive not in href, href


def test_query_fragment_stripped_from_form_action_in_plan():
    plan = cse.build_controlled_action_plan(
        _observer_result(
            forms=[{
                "action": "/auth/submit?session=ABCDEF",
                "method": "POST",
                "has_password": True,
                "input_count": 2,
            }],
        ),
        site_key="hometax",
    )
    form_entry = plan["dangerous_candidates"][0]
    href = form_entry["href"]
    for sensitive in ("?", "session=", "ABCDEF"):
        assert sensitive not in href, href


# ═════════════════════════════════════════════════════════════════════════
# 15) input value / password 출력 누설 없음
# ═════════════════════════════════════════════════════════════════════════

def test_no_input_values_leak_in_classify():
    out = cse.classify_site_action_candidate(
        {
            "text": "조회",
            "href": "/x",
            "value": "USER_INPUT_LEAKED",
            "password": "PW_LEAKED",
            "cookie": "SESS_LEAKED",
        },
    )
    serialized = repr(out)
    for s in ("USER_INPUT_LEAKED", "PW_LEAKED", "SESS_LEAKED"):
        assert s not in serialized, s
    for k in ("value", "password", "cookie"):
        assert k not in out


def test_no_input_values_leak_in_plan():
    plan = cse.build_controlled_action_plan(
        _observer_result(
            links=[{
                "text": "엑셀 다운로드",
                "href": "/x",
                "value": "LINK_VALUE_LEAK",
                "password": "LINK_PW_LEAK",
            }],
            forms=[{
                "action": "/auth", "method": "POST",
                "has_password": True, "input_count": 2,
                "value": "FORM_VALUE_LEAK", "password": "FORM_PW_LEAK",
                "cookie": "FORM_COOKIE_LEAK",
            }],
        ),
        site_key="hometax",
    )
    serialized = repr(plan)
    for s in (
        "LINK_VALUE_LEAK", "LINK_PW_LEAK",
        "FORM_VALUE_LEAK", "FORM_PW_LEAK", "FORM_COOKIE_LEAK",
    ):
        assert s not in serialized, s
    for entry in (
        plan["download_candidates"]
        + plan["safe_read_candidates"]
        + plan["blocked_candidates"]
        + plan["dangerous_candidates"]
    ):
        for k in ("value", "password", "cookie"):
            assert k not in entry, (entry, k)


def test_non_dict_observer_result_safe():
    plan = cse.build_controlled_action_plan("not a dict", site_key="hometax")
    assert plan["safe_read_candidates"] == []
    assert plan["download_candidates"] == []
    assert plan["blocked_candidates"] == []
    assert "observer_result_not_dict" in plan["warnings"]


def test_non_list_links_buttons_forms_warns():
    res = _observer_result()
    res["links"] = "not_a_list"
    res["buttons"] = 123
    res["forms"] = {"oops": True}
    plan = cse.build_controlled_action_plan(res, site_key="hometax")
    assert "links_not_list" in plan["warnings"]
    assert "buttons_not_list" in plan["warnings"]
    assert "forms_not_list" in plan["warnings"]


# ═════════════════════════════════════════════════════════════════════════
# validate / dry-run
# ═════════════════════════════════════════════════════════════════════════

def test_validate_read_only_action_ok():
    out = cse.validate_controlled_action(
        {"kind": "link", "text": "전자세금계산서 조회", "href": "/issued"},
    )
    assert out["ok"] is True
    assert out["error_code"] == ""


def test_validate_download_action_warns_approval():
    out = cse.validate_controlled_action(
        {"kind": "button", "text": "엑셀 다운로드"},
    )
    assert out["ok"] is True
    assert "approval_required" in out["warnings"]


def test_validate_blocked_action_rejected():
    out = cse.validate_controlled_action(
        {"kind": "button", "text": "신고서 제출"},
    )
    assert out["ok"] is False
    assert out["error_code"] == "ACTION_BLOCKED"


def test_validate_javascript_href_blocked():
    out = cse.validate_controlled_action(
        {"kind": "link", "text": "조회", "href": "javascript:alert(1)"},
    )
    assert out["ok"] is False
    assert out["error_code"] == "ACTION_HREF_SCHEME_BLOCKED"


@pytest.mark.parametrize("scheme", ["data:text/html,x", "file:///etc/passwd",
                                     "vbscript:x"])
def test_validate_dangerous_schemes_blocked(scheme):
    out = cse.validate_controlled_action(
        {"kind": "link", "text": "조회", "href": scheme},
    )
    assert out["ok"] is False


def test_validate_relative_href_ok():
    out = cse.validate_controlled_action(
        {"kind": "link", "text": "조회", "href": "/issued"},
    )
    assert out["ok"] is True


def test_validate_unknown_action_rejected():
    out = cse.validate_controlled_action(
        {"kind": "link", "text": "공지사항", "href": "/notice"},
    )
    assert out["ok"] is False
    assert out["error_code"] == "ACTION_UNKNOWN"


def test_validate_invalid_kind():
    out = cse.validate_controlled_action(
        {"kind": "iframe", "text": "조회"},
    )
    assert out["ok"] is False
    assert out["error_code"] == "ACTION_KIND_INVALID"


def test_validate_empty_action():
    out = cse.validate_controlled_action({"kind": "link"})
    assert out["ok"] is False
    assert out["error_code"] == "ACTION_EMPTY"


def test_validate_non_dict_action():
    out = cse.validate_controlled_action(None)
    assert out["ok"] is False
    assert out["error_code"] == "ACTION_NOT_DICT"


def test_dry_run_never_executes_even_when_valid():
    out = cse.execute_controlled_action_dry_run(
        {"kind": "link", "text": "전자세금계산서 조회", "href": "/issued"},
    )
    assert out["executed"] is False
    assert out["would_execute"] is True
    assert out["ok"] is True
    assert out["risk_level"] == "read_only"


def test_dry_run_blocks_dangerous_action():
    out = cse.execute_controlled_action_dry_run(
        {"kind": "button", "text": "신고서 제출"},
    )
    assert out["executed"] is False
    assert out["would_execute"] is False
    assert out["ok"] is False
    assert out["error_code"] == "ACTION_BLOCKED"


def test_dry_run_marks_download_as_requires_approval():
    out = cse.execute_controlled_action_dry_run(
        {"kind": "button", "text": "엑셀 다운로드"},
    )
    assert out["would_execute"] is True
    assert out["risk_level"] == "download"
    assert out["requires_approval"] is True


# ═════════════════════════════════════════════════════════════════════════
# 16~17) AST 보안 회귀 — page.click/fill/type/cookie/storage 미사용
# ═════════════════════════════════════════════════════════════════════════

_FORBIDDEN_CALL_ATTRS = {
    "fill", "press", "click", "type", "select_option", "set_input_files",
    "cookies", "add_cookies", "storage_state",
    "evaluate", "evaluate_handle",
    "goto", "screenshot",  # 본 모듈은 브라우저 미접촉
    "launch", "new_context", "new_page",
}
_FORBIDDEN_ATTR_USAGE = {"keyboard", "mouse"}
_FORBIDDEN_NAMES = {"localStorage", "sessionStorage"}
_FORBIDDEN_STRING_LITERALS = (
    "--remote-debugging-port",
    "--headless",
    "GOOGLE_PASSWORD",
    "GOOGLE_LOGIN_PASSWORD",
    "GOOGLE_COOKIE",
    "GOOGLE_SESSION",
    "GOOGLE_STORAGE_STATE",
    "GOOGLE_OTP_SECRET",
)


def _scan_forbidden_apis(src: str) -> list[tuple[str, int]]:
    tree = ast.parse(src)
    offenders: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _FORBIDDEN_CALL_ATTRS:
                offenders.append((f"call:.{node.func.attr}(", node.lineno))
        if isinstance(node, ast.Attribute) and \
                node.attr in _FORBIDDEN_ATTR_USAGE:
            offenders.append((f"attr:.{node.attr}", node.lineno))
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            offenders.append((f"name:{node.id}", node.lineno))
    return offenders


def test_module_has_no_forbidden_browser_apis():
    src = Path(cse.__file__).read_text(encoding="utf-8")
    offenders = _scan_forbidden_apis(src)
    assert offenders == [], (
        f"forbidden API patterns in controlled_site_executor: {offenders}"
    )


def test_module_does_not_import_playwright():
    src = Path(cse.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "playwright" not in alias.name.lower(), alias.name
        if isinstance(node, ast.ImportFrom):
            assert "playwright" not in (node.module or "").lower(), node.module


def test_module_has_no_forbidden_string_literals():
    src = Path(cse.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for forbidden in _FORBIDDEN_STRING_LITERALS:
                assert forbidden not in node.value, (
                    f"forbidden literal {forbidden!r} at line {node.lineno}"
                )
