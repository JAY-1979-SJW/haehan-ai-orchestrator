"""SmartStore current-page function catalog.

This module develops the visible functions on the currently rendered
SmartStore page into explicit tool records. It is read-only: it classifies
controls and fields, but does not click final buttons or upload files.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scripts.naver.mail_read import cdp
from scripts.smartstore.live_probe import classify_probe, select_smartstore_session

ROOT = Path(__file__).resolve().parents[2]
LATEST_PAGE_FUNCTIONS_PATH = ROOT / "data" / "smartstore_page_functions_latest.json"
APPROVAL_CONFIRM_TEXT = "SMARTSTORE_APPROVED_SUBMIT"

APPROVAL_TOKENS = (
    "save",
    "submit",
    "send",
    "reply",
    "message",
    "delete",
    "cancel",
    "apply",
    "approve",
    "issue",
    "upload",
    "저장",
    "등록",
    "발송",
    "삭제",
    "취소",
    "신청",
    "승인",
    "발급",
    "업로드",
    "이미지 등록",
    "동영상 등록",
    "임시저장",
)

CUSTOMER_COMMUNICATION_TOKENS = (
    "reply",
    "message",
    "talk",
    "review",
    "inquiry",
    "답변",
    "댓글",
    "메시지",
    "톡톡",
    "리뷰",
    "문의",
    "상담",
)

READ_CONTROL_TOKENS = (
    "search",
    "filter",
    "view",
    "list",
    "detail",
    "help",
    "조회",
    "검색",
    "필터",
    "상세",
    "도움말",
    "가이드",
    "보기",
    "목록",
    "대기",
    "건",
)


@dataclass
class PageFunctionReport:
    ok: bool
    code: str
    port: int | None = None
    target_id: str = ""
    url: str = ""
    title: str = ""
    page_kind: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    functions: list[dict[str, Any]] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)
    fields: list[dict[str, Any]] = field(default_factory=list)
    controls: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PAGE_FUNCTIONS_EXPR = r"""JSON.stringify((() => {
  const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const rectOf = (el) => {
    const r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
  };
  const cssPath = (el) => {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const name = el.getAttribute('name');
    if (name) return `${el.tagName.toLowerCase()}[name="${name}"]`;
    const placeholder = el.getAttribute('placeholder');
    if (placeholder) return `${el.tagName.toLowerCase()}[placeholder*="${placeholder.slice(0, 24)}"]`;
    return el.tagName.toLowerCase();
  };
  const labelFor = (el) => {
    const id = el.getAttribute('id') || '';
    if (id) {
      const label = document.querySelector(`label[for="${CSS.escape(id)}"]`);
      if (label) return clean(label.innerText || label.textContent);
    }
    const aria = el.getAttribute('aria-label') || '';
    const placeholder = el.getAttribute('placeholder') || '';
    const wrapped = el.closest('label');
    const row = el.closest('tr,li,section,fieldset,[class*="form"],[class*="Form"],[class*="field"],[class*="Field"]');
    return clean(aria || placeholder || (wrapped && wrapped.innerText) || (row && row.innerText) || '').slice(0, 160);
  };
  const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,[role="heading"]'))
    .filter(visible).map((el) => ({text: clean(el.innerText || el.textContent), tag: el.tagName.toLowerCase(), rect: rectOf(el)}))
    .filter((item) => item.text).slice(0, 80);
  const fields = Array.from(document.querySelectorAll('input,textarea,select,[contenteditable="true"]'))
    .filter(visible)
    .map((el) => ({
      label: labelFor(el),
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || (el.isContentEditable ? 'contenteditable' : ''),
      name: el.getAttribute('name') || '',
      placeholder: el.getAttribute('placeholder') || '',
      value_present: !!(el.value || el.checked || el.innerText),
      selector: cssPath(el),
      rect: rectOf(el)
    })).slice(0, 240);
  const controls = Array.from(document.querySelectorAll('button,a,[role="button"],input[type="button"],input[type="submit"],summary'))
    .filter(visible)
    .map((el) => ({
      text: clean(el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || ''),
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      role: el.getAttribute('role') || '',
      href: el.href || '',
      selector: cssPath(el),
      rect: rectOf(el)
    }))
    .filter((item) => item.text || item.href)
    .slice(0, 260);
  const fileInputs = Array.from(document.querySelectorAll('input[type="file"]'))
    .map((el) => ({label: labelFor(el), tag: 'input', type: 'file', name: el.getAttribute('name') || '', selector: cssPath(el), rect: rectOf(el)}))
    .slice(0, 80);
  const tables = Array.from(document.querySelectorAll('table')).filter(visible).map((table) => ({
    headers: Array.from(table.querySelectorAll('thead th,thead td,tr:first-child th')).map((el) => clean(el.innerText || el.textContent)).filter(Boolean).slice(0, 30),
    rows: table.querySelectorAll('tbody tr,tr').length,
    rect: rectOf(table)
  })).slice(0, 30);
  const body = clean(document.body ? document.body.innerText : '');
  return {href: location.href, title: document.title || '', headings, fields, controls, fileInputs, tables,
    counts: {headings: headings.length, fields: fields.length, controls: controls.length, fileInputs: fileInputs.length, tables: tables.length, bodyTextLength: body.length},
    bodySample: body.slice(0, 1200)};
})())"""


def _slug(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in text.strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")[:64] or "unnamed"


def _page_kind(url: str, body_sample: str) -> str:
    text = f"{url} {body_sample}".lower()
    if "products/create" in text or "상품등록" in body_sample or "상품 등록" in body_sample:
        return "product_register"
    if "dashboard" in text:
        return "dashboard"
    return "smartstore_page"


def _control_risk(control: dict[str, Any]) -> str:
    label = f"{control.get('text') or ''} {control.get('href') or ''}".lower()
    control_type = str(control.get("type") or "").lower()
    if any(token.lower() in label for token in READ_CONTROL_TOKENS):
        return "read"
    if any(token.lower() in label for token in APPROVAL_TOKENS):
        return "approval"
    if control_type == "submit":
        return "approval"
    return "read"


def _control_policy(control: dict[str, Any]) -> str:
    label = f"{control.get('text') or ''} {control.get('href') or ''}".lower()
    if any(token.lower() in label for token in CUSTOMER_COMMUNICATION_TOKENS):
        return "customer_communication_approval_required"
    if _control_risk(control) == "approval":
        return "state_change_approval_required"
    return "read_or_navigation"


def _field_kind(field: dict[str, Any]) -> tuple[str, str]:
    field_type = str(field.get("type") or "").lower()
    tag = str(field.get("tag") or "").lower()
    if field_type in {"hidden", "password", "submit", "button", "reset"}:
        return "blocked", "unsafe_or_non_editable_field"
    if field_type == "file":
        return "approval", "file_upload_requires_explicit_approval"
    if field_type in {"checkbox", "radio"}:
        return "prepare_choice", "choice preparation only; no final submit"
    if tag == "select":
        return "prepare_select", "select preparation only; no final submit"
    return "prepare_text", "safe draft field; final submit remains blocked"


def build_page_functions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    page_kind = _page_kind(str(snapshot.get("href") or ""), str(snapshot.get("bodySample") or ""))
    functions: list[dict[str, Any]] = []
    for idx, heading in enumerate(snapshot.get("headings") or []):
        label = str(heading.get("text") or f"section_{idx}")
        functions.append({
            "tool_id": f"{page_kind}.section.{_slug(label)}",
            "label": label,
            "kind": "section",
            "risk": "read",
            "status": "implemented_read",
            "selector": "",
            "reason": "visible page section",
        })
    for field in snapshot.get("fields") or []:
        label = str(field.get("label") or field.get("placeholder") or field.get("name") or field.get("type") or field.get("tag") or "field")
        kind, reason = _field_kind(field)
        risk = "approval" if kind == "approval" else ("blocked" if kind == "blocked" else "prepare")
        functions.append({
            "tool_id": f"{page_kind}.field.{_slug(label)}",
            "label": label[:120],
            "kind": kind,
            "risk": risk,
            "status": "blocked" if risk == "blocked" else ("approval_required" if risk == "approval" else "implemented_prepare_only"),
            "selector": str(field.get("selector") or ""),
            "reason": reason,
        })
    for field in snapshot.get("fileInputs") or []:
        label = str(field.get("label") or field.get("name") or "file_upload")
        functions.append({
            "tool_id": f"{page_kind}.file_upload.{_slug(label)}",
            "label": label[:120],
            "kind": "file_upload",
            "risk": "approval",
            "status": "approval_required",
            "selector": str(field.get("selector") or ""),
            "reason": "file upload is not performed by page function catalog",
        })
    for control in snapshot.get("controls") or []:
        label = str(control.get("text") or control.get("href") or "control")
        risk = _control_risk(control)
        functions.append({
            "tool_id": f"{page_kind}.control.{_slug(label)}",
            "label": label[:120],
            "kind": "control",
            "risk": risk,
            "status": "approval_required" if risk == "approval" else "implemented_read_navigation",
            "selector": str(control.get("selector") or ""),
            "url": str(control.get("href") or ""),
            "reason": "state-changing control" if risk == "approval" else "read/navigation/help control",
            "policy": _control_policy(control),
        })
    for idx, table in enumerate(snapshot.get("tables") or []):
        label = ", ".join(str(item) for item in (table.get("headers") or [])) or f"table_{idx + 1}"
        functions.append({
            "tool_id": f"{page_kind}.table.{idx + 1}",
            "label": label[:120],
            "kind": "table",
            "risk": "read",
            "status": "implemented_read",
            "selector": "table",
            "reason": "visible table/list extraction",
        })
    deduped: dict[str, dict[str, Any]] = {}
    for item in functions:
        deduped.setdefault(str(item["tool_id"]), item)
    return list(deduped.values())


def _pick_current_smartstore_target(port: int) -> tuple[str, dict[str, Any]]:
    pages = cdp.list_pages(port)
    smartstore_pages = [page for page in pages if "sell.smartstore.naver.com" in str(page.get("url") or "")]
    preferred = sorted(
        smartstore_pages,
        key=lambda page: (
            0 if "products/create" in str(page.get("url") or "") else 1,
            0 if "standard-group-product/create" in str(page.get("url") or "") else 1,
        ),
    )
    for page in preferred:
        target_id = str(page.get("id") or "")
        if not target_id:
            continue
        raw = cdp.evaluate(target_id, r"""JSON.stringify((() => {
          const body = String(document.body ? document.body.innerText : '').replace(/\s+/g, ' ').trim();
          return {href: location.href, host: location.host, title: document.title || '', markers: {
            naverLogin: /nid\.naver\.com|로그인|sign in/i.test(`${location.href} ${document.title} ${body}`),
            logout: /로그아웃|logout|sign out/i.test(`${location.href} ${document.title} ${body}`),
            accountUser: /내정보|마이비즈|account/i.test(`${location.href} ${document.title} ${body}`),
            storeNavigation: /상품관리|판매관리|정산관리|문의\/리뷰관리|스토어관리/i.test(body),
            smartstore: /스마트스토어|스마트스토어센터|상품관리|판매관리/i.test(body),
            sellerCenter: /sell\.smartstore\.naver\.com|판매자센터/i.test(`${location.href} ${body}`),
            challenge: /보안|captcha|자동입력|로봇|인증번호|비정상|차단/i.test(body)
          }, bodyLength: body.length, bodySample: body.slice(0, 600)};
        })())""", timeout=6.0, port=port) or {}
        if isinstance(raw, dict) and (
            classify_probe(raw).get("logged_in")
            or (
                "sell.smartstore.naver.com" in str(raw.get("href") or "")
                and int(raw.get("bodyLength") or 0) > 100
                and bool((raw.get("markers") or {}).get("sellerCenter") or (raw.get("markers") or {}).get("smartstore"))
            )
        ):
            return target_id, raw
    return "", {}


def collect_current_page_functions(*, allow_mixed_readonly: bool = False) -> PageFunctionReport:
    session, selection = select_smartstore_session(allow_mixed_readonly=allow_mixed_readonly)
    if session is None:
        return PageFunctionReport(ok=False, code=selection.code, messages=list(selection.messages), selection=selection.to_dict())
    target_id, raw = _pick_current_smartstore_target(session.port)
    if not target_id:
        return PageFunctionReport(
            ok=False,
            code="no_logged_in_smartstore_page",
            port=session.port,
            messages=["No logged-in SmartStore page target was found."],
            selection=selection.to_dict(),
        )
    snapshot = cdp.evaluate(target_id, PAGE_FUNCTIONS_EXPR, timeout=10.0, port=session.port) or {}
    if not isinstance(snapshot, dict):
        snapshot = {}
    functions = build_page_functions(snapshot)
    return PageFunctionReport(
        ok=True,
        code="ok",
        port=session.port,
        target_id=target_id,
        url=str(snapshot.get("href") or raw.get("href") or ""),
        title=str(snapshot.get("title") or raw.get("title") or ""),
        page_kind=_page_kind(str(snapshot.get("href") or ""), str(snapshot.get("bodySample") or "")),
        counts={
            **dict(snapshot.get("counts") or {}),
            "functions": len(functions),
            "approval_functions": sum(1 for item in functions if item.get("risk") == "approval"),
            "prepare_functions": sum(1 for item in functions if item.get("risk") == "prepare"),
            "read_functions": sum(1 for item in functions if item.get("risk") == "read"),
            "blocked_functions": sum(1 for item in functions if item.get("risk") == "blocked"),
        },
        functions=functions,
        sections=list(snapshot.get("headings") or []),
        fields=list(snapshot.get("fields") or []) + list(snapshot.get("fileInputs") or []),
        controls=list(snapshot.get("controls") or []),
        messages=[
            "Developed visible SmartStore page functions into read/prepare/approval tool records.",
            "No save, temporary save, register, cancel, upload, send, delete, apply, or approve control was clicked.",
            "Review replies, inquiry replies, customer comments, and TalkTalk messages may be drafted by AI but final send/register remains approval-gated.",
            "Use UTF-8 JSON files for Korean product data; PowerShell stdin can corrupt Korean text in some shells.",
        ],
        selection=selection.to_dict(),
    )


def save_page_functions_report(report: PageFunctionReport, output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_PAGE_FUNCTIONS_PATH
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
