"""Approval-gated SmartStore product publish/cleanup workflow.

This module is intentionally narrow. It can click final product save only when
the caller passes explicit approval flags, and it only permits cleanup for
obvious test products.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import websocket  # type: ignore

from scripts.naver.mail_read import cdp
from scripts.smartstore.live_probe import _target_ws_url, classify_probe, select_smartstore_session
from scripts.smartstore.draft_fill import (
    PRODUCT_REGISTER_URL,
    _fill_product_expr,
    _navigate_to_best_product_page,
    _wait_for_product_page,
    create_test_image,
    sample_test_product_data,
    select_test_category,
    upload_first_product_image,
)

ROOT = Path(__file__).resolve().parents[2]
LATEST_APPROVED_PRODUCT_PATH = ROOT / "data" / "smartstore_approved_product_latest.json"

APPROVAL_CONFIRM_TEXT = "SMARTSTORE_APPROVED_SUBMIT"
PRODUCT_LIST_URL = "https://sell.smartstore.naver.com/#/products/origin-list"


@dataclass
class ApprovedProductWorkflowReport:
    ok: bool
    code: str
    action: str
    port: int | None = None
    target_id: str = ""
    before_url: str = ""
    after_url: str = ""
    product_name: str = ""
    clicked: list[dict[str, Any]] = field(default_factory=list)
    detected_messages: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    saved_detected: bool = False
    cleanup_attempted: bool = False
    cleanup_result: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_safe_test_name(name: str) -> bool:
    text = name.lower()
    return any(token in text for token in ("테스트", "test", "저장 금지", "삭제"))


def _current_target(allow_mixed_readonly: bool) -> tuple[int | None, str, dict[str, Any], dict[str, Any]]:
    session, selection = select_smartstore_session(allow_mixed_readonly=allow_mixed_readonly)
    if session is None:
        return None, "", {}, selection.to_dict()
    pages = [page for page in cdp.list_pages(session.port) if "sell.smartstore.naver.com" in str(page.get("url") or "")]
    pages = sorted(
        pages,
        key=lambda page: (
            0 if "products/create" in str(page.get("url") or "") else 1,
            0 if "standard-group-product/create" in str(page.get("url") or "") else 1,
            0 if "dashboard" not in str(page.get("url") or "") else 1,
        ),
    )
    for page in pages:
        target_id = str(page.get("id") or "")
        if not target_id:
            continue
        raw = cdp.evaluate(target_id, _page_status_expr(), timeout=6.0, port=session.port) or {}
        if isinstance(raw, dict):
            raw["href"] = raw.get("href") or page.get("url") or ""
            raw["host"] = "sell.smartstore.naver.com"
            raw["markers"] = {
                "sellerCenter": True,
                "smartstore": True,
                "storeNavigation": True,
                "logout": True,
                "naverLogin": False,
                "challenge": False,
            }
            raw["bodyLength"] = len(str(raw.get("bodySample") or ""))
            return session.port, target_id, raw, selection.to_dict()
    return session.port, "", {}, selection.to_dict()


def _extract_product_name_expr() -> str:
    return r"""JSON.stringify((() => {
      const input = document.querySelector('input[name="product.name"],input[name*="product.name"]');
      return {value: input ? String(input.value || '').trim() : '', href: location.href, title: document.title || ''};
    })())"""


def _click_button_expr(tokens: list[str]) -> str:
    encoded = json.dumps(tokens, ensure_ascii=False)
    return f"""JSON.stringify((() => {{
      const tokens = {encoded};
      const visible = (el) => {{
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      }};
      const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
      const candidates = Array.from(document.querySelectorAll('button,a,[role="button"],input[type="button"],input[type="submit"]'))
        .filter(visible)
        .map((el) => ({{el, text: clean(el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || ''), tag: el.tagName.toLowerCase(), type: el.getAttribute('type') || ''}}))
        .filter((item) => tokens.some((token) => item.text.includes(token)))
        .sort((a, b) => a.text.length - b.text.length);
      if (!candidates.length) return {{ok: false, reason: 'button_not_found', tokens}};
      const item = candidates[0];
      item.el.scrollIntoView({{block: 'center', inline: 'nearest'}});
      item.el.click();
      return {{ok: true, text: item.text, tag: item.tag, type: item.type}};
    }})())"""


def _prepare_required_defaults_expr() -> str:
    return r"""JSON.stringify((() => {
      const visible = (el) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      };
      const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
      const setValue = (el, value) => {
        el.scrollIntoView({block: 'center', inline: 'nearest'});
        el.focus();
        const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
        if (descriptor && descriptor.set) descriptor.set.call(el, String(value));
        else el.value = String(value);
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        el.dispatchEvent(new Event('blur', {bubbles: true}));
      };
      const clicked = [];
      for (const control of Array.from(document.querySelectorAll('button,a,[role="button"],label')).filter(visible)) {
        const text = clean(control.innerText || control.textContent || control.value || control.getAttribute('aria-label'));
        if (text === '설정안함') {
          control.click();
          clicked.push({kind: 'force_no_setting', text});
        }
        if (/상품상세 참조로 전체 입력|상품상세 참조|해당사항 없음/.test(text)) {
          control.click();
          clicked.push({kind: 'detail_reference', text: text.slice(0, 80)});
        }
      }
      const groups = new Map();
      for (const radio of Array.from(document.querySelectorAll('input[type="radio"]')).filter(visible)) {
        const name = radio.name || `anon-${clicked.length}`;
        if (!groups.has(name)) groups.set(name, []);
        groups.get(name).push(radio);
      }
      for (const [name, radios] of groups) {
        if (!radios.some((radio) => radio.checked)) {
          const preferred = radios.find((radio) => /false|N|NONE|NO/i.test(String(radio.value || '')) || String(radio.className || '').includes('r-no-set')) || radios[0];
          preferred.click();
          clicked.push({kind: 'radio_default', name});
        }
      }
      for (const control of Array.from(document.querySelectorAll('button,a,[role="button"],label,span')).filter(visible)) {
        const text = clean(control.innerText || control.textContent || control.value || control.getAttribute('aria-label'));
        if (text === '상품상세 참조' || text === '해당사항 없음') {
          control.click();
          clicked.push({kind: 'post_radio_detail_reference', text});
        }
      }
      const today = new Date().toISOString().slice(0, 10);
      for (const input of Array.from(document.querySelectorAll('input')).filter(visible)) {
        const hint = `${input.name || ''} ${input.placeholder || ''} ${input.getAttribute('aria-label') || ''}`;
        if (/manufactureDate|제조일|제조일자/i.test(hint) && !input.value) {
          input.value = today;
          input.dispatchEvent(new Event('input', {bubbles: true}));
          input.dispatchEvent(new Event('change', {bubbles: true}));
          clicked.push({kind: 'date_default', name: input.name || input.placeholder || 'manufactureDate', value: today});
        }
      }
      for (const select of Array.from(document.querySelectorAll('select')).filter(visible)) {
        if (select.value) continue;
        const option = Array.from(select.options || []).find((item) => item.value && !item.disabled);
        if (option) {
          select.value = option.value;
          select.dispatchEvent(new Event('change', {bubbles: true}));
          clicked.push({kind: 'select_default', name: select.name || select.getAttribute('aria-label') || '', value: option.value});
        }
      }
      for (const input of Array.from(document.querySelectorAll('input,textarea')).filter(visible)) {
        if (input.value || ['hidden','file','password','checkbox','radio','submit','button','reset'].includes(String(input.type || '').toLowerCase())) continue;
        const hint = clean(`${input.name || ''} ${input.placeholder || ''} ${input.getAttribute('aria-label') || ''}`);
        const type = String(input.type || '').toLowerCase();
        if (/origin|\uc6d0\uc0b0\uc9c0/i.test(hint)) {
          setValue(input, '\uad6d\uc0b0');
          clicked.push({kind: 'text_default', name: input.name || input.placeholder || 'origin', value: '\uad6d\uc0b0'});
        } else if (/delivery|shipping|\ubc30\uc1a1|\ucd9c\ubc1c|\ubc18\ud488|\uad50\ud658/i.test(hint)) {
          setValue(input, type === 'number' || type === 'tel' ? '0' : '\ud14c\uc2a4\ud2b8 \ubc30\uc1a1\uc815\ubcf4');
          clicked.push({kind: 'shipping_default', name: input.name || input.placeholder || 'shipping'});
        } else if (/review|\ub9ac\ubdf0|\ud3ec\uc778\ud2b8|\uc801\ub9bd/i.test(hint)) {
          setValue(input, '0');
          clicked.push({kind: 'review_reward_default', name: input.name || input.placeholder || 'review'});
        } else if (input.tagName.toLowerCase() === 'textarea') {
          setValue(input, '상품상세 참조');
          clicked.push({kind: 'textarea_default', name: input.name || input.placeholder || 'textarea'});
        }
      }
      return {ok: true, defaults: clicked};
    })())"""


def _dismiss_known_modal_expr() -> str:
    return r"""JSON.stringify((() => {
      const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
      const visible = (el) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      };
      const body = clean(document.body ? document.body.innerText : '');
      const overlays = Array.from(document.querySelectorAll('.modal,.modal-dialog,[role="dialog"],.seller-layer,.popover')).filter(visible);
      const buttons = Array.from(document.querySelectorAll('button,a,[role="button"]')).filter(visible);
      const allowedNotice = /청약철회|법률에 근거하지 않은 판매자의 임의적인|내 사진 불러오기|최대 20MB|사진보관함/.test(body);
      if (!allowedNotice) return {ok: true, clicked: false, reason: 'no_known_modal'};
      const confirm = buttons.find((el) => clean(el.innerText || el.textContent || el.value || el.getAttribute('aria-label')) === '확인');
      if (confirm && /청약철회|법률에 근거하지 않은 판매자의 임의적인/.test(body)) {
        confirm.click();
        return {ok: true, clicked: true, text: '확인', modal_count: overlays.length};
      }
      return {ok: true, clicked: false, modal_count: overlays.length, reason: 'known_modal_without_confirm'};
    })())"""


def _stabilize_required_fields_expr(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, ensure_ascii=False)
    return f"""JSON.stringify((() => {{
      const data = {encoded};
      const out = [];
      const detailText = data.description || 'SmartStore automation test product. Delete after validation. This is a temporary product description for live workflow verification.';
      const set = (selector, value, key) => {{
        const el = document.querySelector(selector);
        if (!el || value === undefined || value === null || value === '') return false;
        el.scrollIntoView({{block: 'center', inline: 'nearest'}});
        el.focus();
        const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
        if (descriptor && descriptor.set) descriptor.set.call(el, String(value));
        else el.value = String(value);
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        el.dispatchEvent(new Event('blur', {{bubbles: true}}));
        try {{
          const jq = window.jQuery || window.$;
          const scope = jq && jq(el).scope && jq(el).scope();
          const model = el.getAttribute('ng-model') || '';
          if (scope && model === 'vm.product.salePrice') scope.vm.product.salePrice = Number(value);
          if (scope && model === 'vm.product.stockQuantity') scope.vm.product.stockQuantity = Number(value);
          if (scope && model === 'vm.product.name') scope.vm.product.name = String(value);
          if (scope && scope.$applyAsync) scope.$applyAsync();
        }} catch (error) {{}}
        out.push({{key, value: String(value).slice(0, 80), actual: el.value}});
        return true;
      }};
      const setElement = (el, value, key) => {{
        if (!el || value === undefined || value === null || value === '') return false;
        el.scrollIntoView({{block: 'center', inline: 'nearest'}});
        el.focus && el.focus();
        const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
        if (descriptor && descriptor.set) descriptor.set.call(el, String(value));
        else el.value = String(value);
        el.setAttribute && el.setAttribute('value', String(value));
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        el.dispatchEvent(new Event('blur', {{bubbles: true}}));
        el.classList && el.classList.remove('ng-empty', 'ng-invalid', 'ng-invalid-required', 'ng-invalid-min', 'ng-invalid-pattern', 'ng-invalid-date-time-input');
        el.classList && el.classList.add('ng-not-empty', 'ng-valid', 'ng-valid-required');
        out.push({{key, value: String(value).slice(0, 80), actual: el.value || ''}});
        return true;
      }};
      set('input[name="product.name"]', data.name, 'name');
      set('input[name="product.salePrice"]', data.price, 'price');
      set('input[name="product.stockQuantity"]', data.stock, 'stock');
      set('input[placeholder*="제조사"]', data.manufacturer || 'Haehan AI Lab', 'manufacturer');
      set('textarea[name="editorContent"]', detailText, 'detail_hidden_editor');
      const htmlDetail = Array.from(document.querySelectorAll('textarea'))
        .find((el) => {{
          const rect = el.getBoundingClientRect();
          return rect.width > 200 && rect.height > 100;
        }});
      setElement(htmlDetail, detailText, 'detail_html_textarea');
      for (const el of Array.from(document.querySelectorAll('input')).filter((node) => String(node.getAttribute('ng-model') || '').includes('afterServiceDirector'))) {{
        setElement(el, 'Haehan AI Lab 025626652', 'after_service_director');
      }}
      for (const el of Array.from(document.querySelectorAll('input')).filter((node) => String(node.getAttribute('ng-model') || '').includes('customerServicePhoneNumber'))) {{
        setElement(el, '025626652', 'customer_service_phone');
      }}
      for (const radio of Array.from(document.querySelectorAll('input[name="as_customer"]')).filter((node) => String(node.value) === 'false')) {{
        radio.click();
        radio.checked = true;
        radio.dispatchEvent(new Event('input', {{bubbles: true}}));
        radio.dispatchEvent(new Event('change', {{bubbles: true}}));
        out.push({{key: 'as_customer', value: 'false', actual: String(radio.checked)}});
      }}
      for (const el of Array.from(document.querySelectorAll('input[name^="product.customerBenefit.reviewPointPolicy"]'))) {{
        const name = String(el.name || '');
        if (name.endsWith('startDate')) setElement(el, '2026-05-27', 'review_point_start_date');
        else if (name.endsWith('endDate')) setElement(el, '2026-06-27', 'review_point_end_date');
        else if (String(el.type || '').toLowerCase() === 'tel') setElement(el, '10', 'review_point_amount');
      }}
      for (const textarea of Array.from(document.querySelectorAll('textarea')).filter((el) => !el.value)) {{
        textarea.scrollIntoView({{block: 'center', inline: 'nearest'}});
        textarea.focus();
        textarea.value = '상품상세 참조';
        textarea.dispatchEvent(new Event('input', {{bubbles: true}}));
        textarea.dispatchEvent(new Event('change', {{bubbles: true}}));
        textarea.dispatchEvent(new Event('blur', {{bubbles: true}}));
        out.push({{key: 'textarea', value: '상품상세 참조', actual: textarea.value}});
      }}
      return {{ok: true, fields: out}};
    }})())"""


def _type_field_with_cdp(target_id: str, *, port: int, selector: str, text: str) -> dict[str, Any]:
    focus = cdp.evaluate(
        target_id,
        f"""JSON.stringify((() => {{
          const el = document.querySelector({json.dumps(selector)});
          if (!el) return {{ok: false, reason: 'field_missing', selector: {json.dumps(selector)}}};
          el.scrollIntoView({{block: 'center', inline: 'nearest'}});
          el.focus();
          el.select && el.select();
          return {{ok: true, before: el.value || '', selector: {json.dumps(selector)}}};
        }})())""",
        timeout=8.0,
        port=port,
    ) or {}
    if not focus.get("ok"):
        return focus
    ws_url = _target_ws_url(target_id, port=port)
    if not ws_url:
        return {"ok": False, "reason": "target_websocket_url_missing", "selector": selector}
    ws = websocket.create_connection(ws_url, timeout=10)
    try:
        event = cdp._send(ws, 9301, "Input.insertText", {"text": str(text)}, timeout=8.0)
    finally:
        ws.close()
    after = cdp.evaluate(
        target_id,
        f"""JSON.stringify((() => {{
          const el = document.querySelector({json.dumps(selector)});
          return {{value: el ? el.value : '', className: el ? String(el.className || '') : ''}};
        }})())""",
        timeout=8.0,
        port=port,
    ) or {}
    return {"ok": "error" not in event, "selector": selector, "text": str(text), "event": event.get("error"), "after": after}


def _type_final_fields_with_cdp(target_id: str, *, port: int, data: dict[str, Any]) -> dict[str, Any]:
    results = [
        _type_field_with_cdp(target_id, port=port, selector='input[name="product.name"]', text=str(data.get("name") or "")),
        _type_field_with_cdp(target_id, port=port, selector='input[name="product.salePrice"]', text=str(data.get("price") or "")),
        _type_field_with_cdp(target_id, port=port, selector='input[name="product.stockQuantity"]', text=str(data.get("stock") or "")),
        _type_field_with_cdp(target_id, port=port, selector='input[placeholder*="제조사"]', text=str(data.get("manufacturer") or "Haehan AI Lab")),
        _type_field_with_cdp(
            target_id,
            port=port,
            selector='input[ng-model*="afterServiceDirector"]',
            text="Haehan AI Lab 025626652",
        ),
    ]
    return {"ok": all(item.get("ok") for item in results), "results": results}


def _page_status_expr() -> str:
    return r"""JSON.stringify((() => {
      const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
      const body = clean(document.body ? document.body.innerText : '');
      const alerts = Array.from(document.querySelectorAll('[role="alert"],.toast,.Toast,[class*="toast"],[class*="Toast"],[class*="error"],[class*="Error"],.invalid-feedback'))
        .map((el) => clean(el.innerText || el.textContent)).filter(Boolean).slice(0, 50);
      const validation = Array.from(document.querySelectorAll('.invalid-feedback,[class*="error"],[class*="Error"],[aria-invalid="true"]'))
        .map((el) => clean(el.innerText || el.textContent || el.getAttribute('aria-label'))).filter(Boolean).slice(0, 50);
      return {
        href: location.href,
        title: document.title || '',
        alerts,
        validation,
        bodySample: body.slice(0, 1600),
        successLike: /저장되었습니다|상품저장이 완료되었습니다|등록되었습니다|완료|success/i.test(body),
        validationLike: /필수|입력|선택|확인|오류|실패|error|required/i.test(body)
      };
    })())"""


def approved_save_product(
    *,
    approved: bool,
    confirm: str,
    allow_mixed_readonly: bool = False,
    cleanup: bool = False,
    wait_seconds: float = 10.0,
) -> ApprovedProductWorkflowReport:
    if not approved or confirm != APPROVAL_CONFIRM_TEXT:
        return ApprovedProductWorkflowReport(
            ok=False,
            code="approval_required",
            action="product_save",
            messages=[f"Requires --approved --confirm={APPROVAL_CONFIRM_TEXT}"],
        )
    port, target_id, raw, selection = _current_target(allow_mixed_readonly)
    if not port or not target_id:
        return ApprovedProductWorkflowReport(
            ok=False,
            code="no_smartstore_target",
            action="product_save",
            port=port,
            target_id=target_id,
            selection=selection,
        )
    name_payload = cdp.evaluate(target_id, _extract_product_name_expr(), timeout=5.0, port=port) or {}
    product_name = str((name_payload or {}).get("value") or "")
    before_url = str((name_payload or {}).get("href") or raw.get("href") or "")
    if not _is_safe_test_name(product_name):
        return ApprovedProductWorkflowReport(
            ok=False,
            code="unsafe_product_name",
            action="product_save",
            port=port,
            target_id=target_id,
            before_url=before_url,
            product_name=product_name,
            messages=["Approved save is limited to obvious test products containing 테스트/test/저장 금지/삭제."],
            selection=selection,
        )

    clicked = cdp.evaluate(target_id, _click_button_expr(["저장하기"]), timeout=8.0, port=port) or {}
    time.sleep(max(2.0, wait_seconds))
    status = cdp.evaluate(target_id, _page_status_expr(), timeout=8.0, port=port) or {}
    detected = list((status or {}).get("alerts") or [])
    validation = list((status or {}).get("validation") or [])
    saved_detected = bool((status or {}).get("successLike")) and not bool(validation)
    report = ApprovedProductWorkflowReport(
        ok=bool(clicked.get("ok")) and saved_detected,
        code=("saved" if saved_detected else "validation_blocked") if clicked.get("ok") else str(clicked.get("reason") or "save_click_failed"),
        action="product_save",
        port=port,
        target_id=target_id,
        before_url=before_url,
        after_url=str((status or {}).get("href") or ""),
        product_name=product_name,
        clicked=[clicked] if isinstance(clicked, dict) else [],
        detected_messages=detected,
        validation_errors=validation,
        saved_detected=saved_detected,
        messages=[
            "Clicked final product save under explicit approval.",
            "If validation errors are present, product publication likely did not complete.",
        ],
        selection=selection,
    )
    if cleanup and saved_detected:
        cleanup_result = approved_cleanup_product(
            product_name=product_name,
            approved=approved,
            confirm=confirm,
            allow_mixed_readonly=allow_mixed_readonly,
            wait_seconds=wait_seconds,
        )
        report.cleanup_attempted = True
        report.cleanup_result = cleanup_result.to_dict()
    return report


def approved_cleanup_product(
    *,
    product_name: str,
    approved: bool,
    confirm: str,
    allow_mixed_readonly: bool = False,
    wait_seconds: float = 8.0,
) -> ApprovedProductWorkflowReport:
    if not approved or confirm != APPROVAL_CONFIRM_TEXT:
        return ApprovedProductWorkflowReport(ok=False, code="approval_required", action="product_cleanup")
    if not _is_safe_test_name(product_name):
        return ApprovedProductWorkflowReport(
            ok=False,
            code="unsafe_product_name",
            action="product_cleanup",
            product_name=product_name,
            messages=["Cleanup is limited to obvious test products."],
        )
    port, target_id, _raw, selection = _current_target(allow_mixed_readonly)
    if not port or not target_id:
        return ApprovedProductWorkflowReport(ok=False, code="no_smartstore_target", action="product_cleanup", selection=selection)
    cdp.navigate(target_id, PRODUCT_LIST_URL, port=port)
    time.sleep(max(3.0, wait_seconds))
    search_and_delete = f"""JSON.stringify((() => {{
      const productName = {json.dumps(product_name, ensure_ascii=False)};
      const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
      const visible = (el) => {{
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      }};
      const fields = Array.from(document.querySelectorAll('input')).filter(visible);
      const search = fields.find((el) => /상품|검색|product|search/i.test(`${{el.placeholder}} ${{el.name}} ${{el.getAttribute('aria-label') || ''}}`)) || fields[0];
      if (search) {{
        search.focus();
        search.value = productName;
        search.dispatchEvent(new Event('input', {{bubbles: true}}));
        search.dispatchEvent(new Event('change', {{bubbles: true}}));
      }}
      const searchButton = Array.from(document.querySelectorAll('button,a,[role="button"]')).filter(visible)
        .find((el) => /검색|조회|search/i.test(clean(el.innerText || el.textContent || el.getAttribute('aria-label'))));
      if (searchButton) searchButton.click();
      return {{ok: true, searched: !!search, clicked_search: !!searchButton, href: location.href}};
    }})())"""
    search_result = cdp.evaluate(target_id, search_and_delete, timeout=8.0, port=port) or {}
    time.sleep(max(3.0, wait_seconds))
    delete_expr = f"""JSON.stringify((() => {{
      const productName = {json.dumps(product_name, ensure_ascii=False)};
      const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
      const visible = (el) => {{
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      }};
      const body = clean(document.body ? document.body.innerText : '');
      if (!body.includes(productName)) return {{ok: false, reason: 'product_not_found', href: location.href}};
      const row = Array.from(document.querySelectorAll('tr,li,div')).filter(visible)
        .find((el) => clean(el.innerText || el.textContent).includes(productName));
      if (row) {{
        const checkbox = row.querySelector('input[type="checkbox"]');
        if (checkbox && !checkbox.checked) checkbox.click();
      }}
      const deleteButton = Array.from(document.querySelectorAll('button,a,[role="button"]')).filter(visible)
        .find((el) => /삭제|delete/i.test(clean(el.innerText || el.textContent || el.getAttribute('aria-label'))));
      if (!deleteButton) return {{ok: false, reason: 'delete_button_not_found', href: location.href}};
      deleteButton.click();
      return {{ok: true, clicked_delete: true, href: location.href}};
    }})())"""
    delete_result = cdp.evaluate(target_id, delete_expr, timeout=8.0, port=port) or {}
    time.sleep(1.5)
    confirm_result = cdp.evaluate(target_id, _click_button_expr(["확인", "삭제"]), timeout=5.0, port=port) or {}
    time.sleep(max(2.0, wait_seconds))
    status = cdp.evaluate(target_id, _page_status_expr(), timeout=8.0, port=port) or {}
    return ApprovedProductWorkflowReport(
        ok=bool(delete_result.get("ok")),
        code="cleanup_clicked" if delete_result.get("ok") else str(delete_result.get("reason") or "cleanup_failed"),
        action="product_cleanup",
        port=port,
        target_id=target_id,
        after_url=str((status or {}).get("href") or PRODUCT_LIST_URL),
        product_name=product_name,
        clicked=[{"search": search_result}, {"delete": delete_result}, {"confirm": confirm_result}],
        detected_messages=list((status or {}).get("alerts") or []),
        validation_errors=list((status or {}).get("validation") or []),
        messages=["Attempted approved cleanup for a test product only."],
        selection=selection,
    )


def approved_test_product_cycle(
    *,
    product_type: str,
    approved: bool,
    confirm: str,
    allow_mixed_readonly: bool = False,
    cleanup: bool = True,
    wait_seconds: float = 10.0,
) -> ApprovedProductWorkflowReport:
    if product_type not in {"individual", "group"}:
        return ApprovedProductWorkflowReport(ok=False, code="unsupported_product_type", action="test_product_cycle")
    if not approved or confirm != APPROVAL_CONFIRM_TEXT:
        return ApprovedProductWorkflowReport(
            ok=False,
            code="approval_required",
            action=f"{product_type}_test_product_cycle",
            messages=[f"Requires --approved --confirm={APPROVAL_CONFIRM_TEXT}"],
        )
    port, target_id, _raw, selection = _current_target(allow_mixed_readonly)
    if not port or not target_id:
        return ApprovedProductWorkflowReport(ok=False, code="no_smartstore_target", action=f"{product_type}_test_product_cycle", selection=selection)

    data = sample_test_product_data(product_type)
    image_path = create_test_image(label=f"{product_type.upper()} TEST")
    before_status = cdp.evaluate(target_id, _page_status_expr(), timeout=6.0, port=port) or {}
    before_url = str((before_status or {}).get("href") or "")

    if product_type == "individual":
        page_choice = _navigate_to_best_product_page(target_id, port=port, wants_price_stock=True, wait_seconds=wait_seconds)
    else:
        cdp.navigate(target_id, PRODUCT_REGISTER_URL, port=port)
        _wait_for_product_page(target_id, port=port, wait_seconds=wait_seconds)
        page_choice = {"url": PRODUCT_REGISTER_URL, "probe": {}}

    category = select_test_category(target_id, port=port)
    time.sleep(2.0)
    fill_data = {key: value for key, value in data.items() if key != "category"}
    fill_payload = cdp.evaluate(target_id, _fill_product_expr(fill_data), timeout=15.0, port=port) or {}
    defaults = cdp.evaluate(target_id, _prepare_required_defaults_expr(), timeout=10.0, port=port) or {}
    first_dismiss = cdp.evaluate(target_id, _dismiss_known_modal_expr(), timeout=8.0, port=port) or {}
    time.sleep(1.0)
    upload = upload_first_product_image(target_id, port=port, image_path=image_path)
    second_dismiss = cdp.evaluate(target_id, _dismiss_known_modal_expr(), timeout=8.0, port=port) or {}
    final_fields = cdp.evaluate(target_id, _stabilize_required_fields_expr(data), timeout=10.0, port=port) or {}
    typed_final_fields = _type_final_fields_with_cdp(target_id, port=port, data=data)
    time.sleep(max(2.0, wait_seconds / 2))
    clicked = cdp.evaluate(target_id, _click_button_expr(["저장하기"]), timeout=8.0, port=port) or {}
    time.sleep(max(4.0, wait_seconds))
    status = cdp.evaluate(target_id, _page_status_expr(), timeout=10.0, port=port) or {}
    detected = list((status or {}).get("alerts") or [])
    validation = list((status or {}).get("validation") or [])
    saved_detected = bool((status or {}).get("successLike")) and not bool(validation)
    report = ApprovedProductWorkflowReport(
        ok=bool(clicked.get("ok")) and saved_detected,
        code=("saved" if saved_detected else "validation_blocked") if clicked.get("ok") else str(clicked.get("reason") or "save_click_failed"),
        action=f"{product_type}_test_product_cycle",
        port=port,
        target_id=target_id,
        before_url=before_url,
        after_url=str((status or {}).get("href") or ""),
        product_name=str(data.get("name") or ""),
        clicked=[
            {"page_choice": page_choice},
            {"category": category},
            {"filled": fill_payload},
            {"defaults": defaults},
            {"dismiss_before_upload": first_dismiss},
            {"upload": upload},
            {"dismiss_after_upload": second_dismiss},
            {"final_fields": final_fields},
            {"typed_final_fields": typed_final_fields},
            {"save": clicked},
        ],
        detected_messages=detected,
        validation_errors=validation,
        saved_detected=saved_detected,
        messages=[
            f"Ran approved {product_type} test product cycle.",
            "Generated and uploaded a local PNG test image when a file input was available.",
            "Cleanup runs only if save success is detected.",
        ],
        selection=selection,
    )
    if cleanup and saved_detected:
        cleanup_result = approved_cleanup_product(
            product_name=str(data.get("name") or ""),
            approved=approved,
            confirm=confirm,
            allow_mixed_readonly=allow_mixed_readonly,
            wait_seconds=wait_seconds,
        )
        report.cleanup_attempted = True
        report.cleanup_result = cleanup_result.to_dict()
    return report


def approved_both_test_product_cycle(
    *,
    approved: bool,
    confirm: str,
    allow_mixed_readonly: bool = False,
    cleanup: bool = True,
    wait_seconds: float = 10.0,
) -> dict[str, Any]:
    individual = approved_test_product_cycle(
        product_type="individual",
        approved=approved,
        confirm=confirm,
        allow_mixed_readonly=allow_mixed_readonly,
        cleanup=cleanup,
        wait_seconds=wait_seconds,
    )
    group = approved_test_product_cycle(
        product_type="group",
        approved=approved,
        confirm=confirm,
        allow_mixed_readonly=allow_mixed_readonly,
        cleanup=cleanup,
        wait_seconds=wait_seconds,
    )
    return {
        "ok": bool(individual.ok and group.ok),
        "code": "both_saved" if individual.saved_detected and group.saved_detected else "both_attempted_validation_blocked",
        "individual": individual.to_dict(),
        "group": group.to_dict(),
    }


def save_approved_product_report(report: ApprovedProductWorkflowReport, output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_APPROVED_PRODUCT_PATH
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
