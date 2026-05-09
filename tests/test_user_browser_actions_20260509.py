"""user_browser_actions 단위 테스트 (Playwright 실제 연결 없이 mock 사용)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from ai_orchestrator.local_agent.user_browser_actions import (
    navigate, click, type_text, upload_file, select_option,
    scroll, get_text, wait_for_selector, fill_form,
    GateBlockedError, GateApprovalRequired, ActionResult,
)
from ai_orchestrator.local_agent.user_browser_intent_token import create_intent


def _make_page(url="https://developer.hancom.com/"):
    page = MagicMock()
    page.url = url
    page.inner_text.return_value = "sample text"
    page.get_attribute.return_value = "attr_value"
    return page


def _make_intent(origins=("developer.hancom.com",)):
    return create_intent(natural_language="SDK 가격 확인", allowed_origins=origins)


# ── navigate ─────────────────────────────────────────────────────────────────

def test_navigate_auto(tmp_path):
    page = _make_page()
    intent = _make_intent()
    r = navigate(page, "https://developer.hancom.com/sdk",
                 intent=intent, audit_path=tmp_path / "log.jsonl")
    assert r.ok is True
    assert r.verdict == "AUTO"
    page.goto.assert_called_once()


def test_navigate_notify_no_intent(tmp_path):
    page = _make_page()
    r = navigate(page, "https://developer.hancom.com/",
                 intent=None, audit_path=tmp_path / "log.jsonl")
    assert r.verdict == "NOTIFY"
    assert r.ok is True


def test_navigate_approve_raises(tmp_path):
    page = _make_page(url="https://shop.com/purchase")
    intent = _make_intent(origins=("shop.com",))
    with pytest.raises(GateApprovalRequired):
        navigate(page, "https://shop.com/purchase",
                 intent=intent, audit_path=tmp_path / "log.jsonl")


def test_navigate_approve_force(tmp_path):
    page = _make_page(url="https://shop.com/purchase")
    intent = _make_intent(origins=("shop.com",))
    r = navigate(page, "https://shop.com/purchase",
                 intent=intent, audit_path=tmp_path / "log.jsonl", force=True)
    assert r.ok is True
    assert r.verdict == "APPROVE"


def test_navigate_error_returns_false(tmp_path):
    page = _make_page()
    page.goto.side_effect = Exception("연결 실패")
    intent = _make_intent()
    r = navigate(page, "https://developer.hancom.com/",
                 intent=intent, audit_path=tmp_path / "log.jsonl")
    assert r.ok is False
    assert "연결 실패" in r.error


# ── click ────────────────────────────────────────────────────────────────────

def test_click_auto(tmp_path):
    page = _make_page()
    intent = _make_intent()
    r = click(page, "button.next", label="다음",
              intent=intent, audit_path=tmp_path / "log.jsonl")
    assert r.ok is True
    page.click.assert_called_once_with("button.next", timeout=10000)


def test_click_approve_keyword(tmp_path):
    page = _make_page()
    intent = _make_intent()
    with pytest.raises(GateApprovalRequired) as exc:
        click(page, "button.pay", label="결제하기",
              intent=intent, audit_path=tmp_path / "log.jsonl")
    assert "결제" in exc.value.approval_prompt()


# ── type_text ─────────────────────────────────────────────────────────────────

def test_type_text_blocked_password(tmp_path):
    page = _make_page()
    intent = _make_intent()
    with pytest.raises(GateBlockedError) as exc:
        type_text(page, "input[name='password']", "s3cret",
                  label="password", intent=intent,
                  audit_path=tmp_path / "log.jsonl")
    assert exc.value.field_name != ""


def test_type_text_auto(tmp_path):
    page = _make_page()
    intent = _make_intent()
    r = type_text(page, "input#search", "SDK",
                  label="검색어", intent=intent,
                  audit_path=tmp_path / "log.jsonl")
    assert r.ok is True
    page.type.assert_called()


# ── upload_file ───────────────────────────────────────────────────────────────

def test_upload_file_notify_no_force(tmp_path):
    page = _make_page()
    intent = _make_intent()
    dummy = tmp_path / "doc.pdf"
    dummy.write_bytes(b"dummy")
    # NOTIFY → force 없으면 통과 (NOTIFY는 예외 없음, AUTO처럼 진행)
    r = upload_file(page, "input[type='file']", dummy,
                    intent=intent, audit_path=tmp_path / "log.jsonl")
    assert r.verdict == "NOTIFY"
    assert r.ok is True


def test_upload_file_force(tmp_path):
    page = _make_page()
    intent = _make_intent()
    dummy = tmp_path / "doc.pdf"
    dummy.write_bytes(b"data")
    r = upload_file(page, "input[type='file']", dummy,
                    intent=intent, audit_path=tmp_path / "log.jsonl", force=True)
    assert r.ok is True
    page.set_input_files.assert_called_once()


# ── select_option ─────────────────────────────────────────────────────────────

def test_select_option_auto(tmp_path):
    page = _make_page()
    intent = _make_intent()
    r = select_option(page, "select#category", "option1",
                      label="카테고리", intent=intent,
                      audit_path=tmp_path / "log.jsonl")
    assert r.ok is True
    assert r.value == "option1"


# ── scroll ───────────────────────────────────────────────────────────────────

def test_scroll_down(tmp_path):
    page = _make_page()
    intent = _make_intent()
    r = scroll(page, direction="down", amount=500,
               intent=intent, audit_path=tmp_path / "log.jsonl")
    assert r.ok is True
    page.evaluate.assert_called_with("window.scrollBy(0, 500)")


def test_scroll_up(tmp_path):
    page = _make_page()
    intent = _make_intent()
    r = scroll(page, direction="up", amount=300,
               intent=intent, audit_path=tmp_path / "log.jsonl")
    assert r.ok is True
    page.evaluate.assert_called_with("window.scrollBy(0, -300)")


# ── get_text ─────────────────────────────────────────────────────────────────

def test_get_text_returns_value(tmp_path):
    page = _make_page()
    page.inner_text.return_value = "SDK 가격: 50만원"
    intent = _make_intent()
    r = get_text(page, "div.price",
                 intent=intent, audit_path=tmp_path / "log.jsonl")
    assert r.ok is True
    assert r.value == "SDK 가격: 50만원"


# ── wait_for_selector ─────────────────────────────────────────────────────────

def test_wait_for_selector_ok(tmp_path):
    page = _make_page()
    intent = _make_intent()
    r = wait_for_selector(page, "div.result",
                          intent=intent, audit_path=tmp_path / "log.jsonl")
    assert r.ok is True


def test_wait_for_selector_timeout(tmp_path):
    page = _make_page()
    page.wait_for_selector.side_effect = Exception("Timeout")
    intent = _make_intent()
    r = wait_for_selector(page, "div.result",
                          intent=intent, audit_path=tmp_path / "log.jsonl")
    assert r.ok is False
    assert "Timeout" in r.error


# ── fill_form ─────────────────────────────────────────────────────────────────

def test_fill_form_multi_fields(tmp_path):
    page = _make_page()
    intent = _make_intent()
    results = fill_form(page, {
        "input#name": "홍길동",
        "input#address": "서울시",
        "input#phone": "010-1234-5678",
    }, intent=intent, audit_path=tmp_path / "log.jsonl")
    assert len(results) == 3
    assert all(r.ok for r in results)


def test_fill_form_blocked_stops(tmp_path):
    page = _make_page()
    intent = _make_intent()
    with pytest.raises(GateBlockedError):
        fill_form(page, {
            "input#name": "홍길동",
            "input#password": "s3cret",
        }, intent=intent, audit_path=tmp_path / "log.jsonl")


# ── audit log 기록 확인 ───────────────────────────────────────────────────────

def test_navigate_writes_audit_log(tmp_path):
    page = _make_page()
    intent = _make_intent()
    audit = tmp_path / "audit.jsonl"
    navigate(page, "https://developer.hancom.com/",
             intent=intent, audit_path=audit)
    assert audit.exists()
    content = audit.read_text(encoding="utf-8")
    assert "navigate" in content
    assert "developer.hancom.com" in content
