"""SmartStore page-derived tool inventory.

The collector is attach-only and read-only. It creates an isolated SmartStore
tab, inspects visible page controls, and converts them into conservative tool
development candidates.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.browser_cdp_selection_gate import create_isolated_target  # noqa: E402
from scripts.naver.mail_read import cdp  # noqa: E402
from scripts.smartstore.live_probe import (  # noqa: E402
    DASHBOARD_URL,
    _send_target_cdp,
    classify_probe,
    find_rendered_smartstore_target,
    select_smartstore_session,
)

LATEST_PAGE_TOOLS_PATH = ROOT / "data" / "smartstore_page_tools_latest.json"
LATEST_DASHBOARD_PATH = ROOT / "data" / "smartstore_dashboard_latest.json"


@dataclass
class PageToolCandidate:
    action_id: str
    label: str
    kind: str
    risk: str
    status: str
    selector_hint: str = ""
    url: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SmartStorePageToolsReport:
    ok: bool
    code: str
    port: int | None = None
    target_id: str = ""
    url: str = ""
    title: str = ""
    logged_in: bool = False
    counts: dict[str, int] = field(default_factory=dict)
    headings: list[str] = field(default_factory=list)
    menus: list[dict[str, Any]] = field(default_factory=list)
    buttons: list[dict[str, Any]] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    tool_candidates: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)
    isolation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SmartStoreDashboardReport:
    ok: bool
    code: str
    port: int | None = None
    target_id: str = ""
    url: str = ""
    title: str = ""
    logged_in: bool = False
    store_name: str = ""
    user_label: str = ""
    primary_menus: list[str] = field(default_factory=list)
    utility_buttons: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    search_inputs: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PAGE_TOOLS_EXPR = r"""JSON.stringify((() => {
  const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const shortText = (el) => clean(el.innerText || el.textContent || el.getAttribute('aria-label') || '').slice(0, 80);
  const rectOf = (el) => {
    const r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
  };
  const selectorHint = (el) => {
    if (el.id) return `#${el.id}`;
    const name = el.getAttribute('name');
    if (name) return `${el.tagName.toLowerCase()}[name="${name}"]`;
    const aria = el.getAttribute('aria-label');
    if (aria) return `${el.tagName.toLowerCase()}[aria-label="${aria.slice(0, 40)}"]`;
    return el.tagName.toLowerCase();
  };
  const uniqBy = (items, keyFn, limit) => {
    const seen = new Set();
    const out = [];
    for (const item of items) {
      const key = keyFn(item);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(item);
      if (out.length >= limit) break;
    }
    return out;
  };

  const headings = Array.from(document.querySelectorAll('h1,h2,h3,[role="heading"]'))
    .filter(visible).map(shortText).filter(Boolean).slice(0, 30);

  const controls = Array.from(document.querySelectorAll('a,button,[role="button"],[role="menuitem"],li'));
  const menus = uniqBy(
    controls.filter(visible).map((el) => ({text: shortText(el), tag: el.tagName.toLowerCase(), rect: rectOf(el), selector: selectorHint(el), href: el.href || ''}))
      .filter((item) => item.text && item.rect.x < 360 && item.text.length <= 50)
      .sort((a, b) => a.rect.y - b.rect.y),
    (item) => item.text,
    80
  );
  const buttons = uniqBy(
    Array.from(document.querySelectorAll('button,[role="button"],input[type="button"],input[type="submit"]'))
      .filter(visible).map((el) => ({text: shortText(el) || clean(el.value), tag: el.tagName.toLowerCase(), rect: rectOf(el), selector: selectorHint(el)}))
      .filter((item) => item.text),
    (item) => `${item.text}:${item.selector}`,
    80
  );
  const links = uniqBy(
    Array.from(document.querySelectorAll('a[href]')).filter(visible)
      .map((el) => ({text: shortText(el), href: el.href || '', rect: rectOf(el), selector: selectorHint(el)}))
      .filter((item) => item.text || item.href),
    (item) => `${item.text}:${item.href}`,
    100
  );
  const inputs = Array.from(document.querySelectorAll('input,textarea,select')).filter(visible)
    .map((el) => ({
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      name: el.getAttribute('name') || '',
      placeholder: el.getAttribute('placeholder') || '',
      aria: el.getAttribute('aria-label') || '',
      label: clean((el.closest('label') || {}).innerText || ''),
      selector: selectorHint(el),
      rect: rectOf(el)
    })).slice(0, 120);
  const tables = Array.from(document.querySelectorAll('table')).filter(visible);
  const body = clean(document.body ? document.body.innerText : '');
  return {
    href: location.href,
    host: location.host,
    title: document.title || '',
    readyState: document.readyState,
    headings,
    menus,
    buttons,
    links,
    inputs,
    counts: {
      menus: menus.length,
      buttons: buttons.length,
      links: links.length,
      inputs: inputs.length,
      tables: tables.length,
      bodyTextLength: body.length
    },
    loginRaw: {
      href: location.href,
      host: location.host,
      title: document.title || '',
      markers: {
        naverLogin: /nid\.naver\.com|로그인|아이디|비밀번호|sign in/i.test(`${location.href} ${document.title} ${body}`),
        logout: /로그아웃|logout|sign out/i.test(`${location.href} ${document.title} ${body}`),
        accountUser: /[A-Za-z0-9_.-]{2,}\s*님|내정보|마이비즈/i.test(`${location.href} ${document.title} ${body}`),
        storeNavigation: /상품관리|판매관리|정산관리|문의\/리뷰관리|스토어관리/i.test(`${location.href} ${document.title} ${body}`),
        smartstore: /스마트스토어|스마트스토어센터|상품관리|판매관리|정산관리|문의\/리뷰관리|스토어/i.test(body),
        sellerCenter: /sell\.smartstore\.naver\.com|판매자|센터/i.test(`${location.href} ${body}`),
        challenge: /보안|captcha|자동입력|로봇|인증번호|비정상|차단/i.test(body)
      },
      bodyLength: body.length,
      hasVisibleBody: body.length > 20,
      bodySample: body.slice(0, 500)
    }
  };
})())"""


def _slug(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in text.strip())
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_")[:48] or "unnamed"


def _risk_for_label(label: str, kind: str) -> tuple[str, str]:
    text = label.lower()
    if any(token in label for token in ("삭제", "발송", "저장", "등록", "수정", "취소", "반품", "교환", "정산요청", "구매확정")):
        return "approval", "state-changing SmartStore action"
    if any(token in label for token in ("검색", "조회", "필터", "다운로드", "목록", "상세", "통계", "분석")):
        return "read", "read-only page action"
    if kind == "input" or any(token in text for token in ("input", "textarea", "select")):
        return "prepare", "field preparation only; submit/save remains gated"
    return "read", "default to read until a submit/save control is identified"


def build_tool_candidates(snapshot: dict[str, Any]) -> list[PageToolCandidate]:
    candidates: list[PageToolCandidate] = []
    for item in snapshot.get("menus") or []:
        label = str(item.get("text") or "").strip()
        if not label:
            continue
        risk, reason = _risk_for_label(label, "menu")
        candidates.append(
            PageToolCandidate(
                action_id=f"page.menu.{_slug(label)}",
                label=label,
                kind="menu",
                risk=risk,
                status="observed",
                selector_hint=str(item.get("selector") or ""),
                url=str(item.get("href") or ""),
                reason=reason,
            )
        )
    for item in snapshot.get("buttons") or []:
        label = str(item.get("text") or "").strip()
        if not label:
            continue
        risk, reason = _risk_for_label(label, "button")
        candidates.append(
            PageToolCandidate(
                action_id=f"page.button.{_slug(label)}",
                label=label,
                kind="button",
                risk=risk,
                status="observed_approval_required" if risk == "approval" else "observed",
                selector_hint=str(item.get("selector") or ""),
                reason=reason,
            )
        )
    for item in snapshot.get("inputs") or []:
        label = str(item.get("label") or item.get("placeholder") or item.get("name") or item.get("aria") or "").strip()
        if not label:
            continue
        risk, reason = _risk_for_label(label, "input")
        candidates.append(
            PageToolCandidate(
                action_id=f"page.input.{_slug(label)}",
                label=label[:80],
                kind="input",
                risk=risk,
                status="observed_prepare_only",
                selector_hint=str(item.get("selector") or ""),
                reason=reason,
            )
        )
    deduped: dict[str, PageToolCandidate] = {}
    for candidate in candidates:
        deduped.setdefault(candidate.action_id, candidate)
    return list(deduped.values())


def _ax_name(node: dict[str, Any]) -> str:
    raw = node.get("name")
    if isinstance(raw, dict):
        return str(raw.get("value") or "").strip()
    return str(raw or "").strip()


def _ax_role(node: dict[str, Any]) -> str:
    raw = node.get("role")
    if isinstance(raw, dict):
        return str(raw.get("value") or "").strip()
    return str(raw or "").strip()


def extract_accessibility_controls(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract page controls from Chrome's accessibility tree."""
    headings: list[str] = []
    menus: list[dict[str, Any]] = []
    buttons: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(bucket: list[dict[str, Any]], role: str, name: str) -> None:
        clean = " ".join(name.split())[:100]
        if not clean:
            return
        key = (role, clean)
        if key in seen:
            return
        seen.add(key)
        bucket.append({"text": clean, "role": role, "selector": f"ax:{role}"})

    for node in nodes:
        role = _ax_role(node)
        name = _ax_name(node)
        if not name:
            continue
        if role in {"heading"}:
            if name not in headings:
                headings.append(name[:100])
        elif role in {"button", "toggle button"}:
            add(buttons, role, name)
        elif role == "link":
            add(links, role, name)
        elif role in {"menu item", "menuitem", "list item", "tree item", "tab"}:
            add(menus, role, name)
        elif role in {"textbox", "searchbox", "combobox", "checkbox", "radio button", "spinbutton"}:
            item = {"label": name[:100], "role": role, "selector": f"ax:{role}"}
            key = (role, item["label"])
            if key not in seen:
                seen.add(key)
                inputs.append(item)

    return {
        "headings": headings[:40],
        "menus": menus[:100],
        "buttons": buttons[:100],
        "links": links[:120],
        "inputs": inputs[:120],
        "counts": {
            "axNodes": len(nodes),
            "menus": len(menus[:100]),
            "buttons": len(buttons[:100]),
            "links": len(links[:120]),
            "inputs": len(inputs[:120]),
        },
    }


def _merge_ax_fallback(snapshot: dict[str, Any], ax_payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(snapshot)
    if not merged.get("headings"):
        merged["headings"] = ax_payload.get("headings") or []
    for key in ("menus", "buttons", "links", "inputs"):
        if not merged.get(key):
            merged[key] = ax_payload.get(key) or []
    counts = dict(merged.get("counts") or {})
    for key, value in (ax_payload.get("counts") or {}).items():
        counts[f"accessibility_{key}" if key != "axNodes" else "accessibility_nodes"] = value
        if counts.get(key, 0) == 0 and key in {"menus", "buttons", "links", "inputs"}:
            counts[key] = value
    merged["counts"] = counts
    return merged


def collect_page_tools(
    *,
    allow_mixed_readonly: bool = False,
    wait_seconds: float = 8.0,
) -> SmartStorePageToolsReport:
    session, selection = select_smartstore_session(allow_mixed_readonly=allow_mixed_readonly)
    if session is None:
        return SmartStorePageToolsReport(
            ok=False,
            code=selection.code,
            messages=list(selection.messages),
            selection=selection.to_dict(),
        )

    existing_target_id, existing_raw = find_rendered_smartstore_target(port=session.port)
    if existing_target_id and existing_raw:
        existing_verdict = classify_probe(existing_raw)
        if existing_verdict.get("logged_in"):
            snapshot = _read_page_tools_snapshot(existing_target_id, port=session.port)
            snapshot.setdefault("href", existing_verdict.get("url") or "")
            snapshot.setdefault("title", existing_verdict.get("title") or "")
            snapshot["loginRaw"] = existing_raw
            return _build_page_tools_report(
                snapshot,
                login_verdict=existing_verdict,
                port=session.port,
                target_id=existing_target_id,
                selection=selection.to_dict(),
                isolation={},
                messages=[
                    "Collected SmartStore page controls from an existing rendered CDP tab; no browser launch, restart, close, submit, save, or write action.",
                    "Session storage remains SmartStore-specific: data/sessions/sell.smartstore.naver.com.json.",
                ],
            )

    isolation = create_isolated_target(
        task="smartstore",
        work="smartstore:page_tools",
        port=session.port,
        start_url=DASHBOARD_URL,
    )
    if not isolation.ok or not isolation.target_id:
        return SmartStorePageToolsReport(
            ok=False,
            code=isolation.code,
            port=session.port,
            messages=list(isolation.messages),
            selection=selection.to_dict(),
            isolation=isolation.to_dict(),
        )

    cdp.navigate(isolation.target_id, DASHBOARD_URL, port=session.port)
    snapshot = _wait_page_tools_snapshot(isolation.target_id, port=session.port, wait_seconds=wait_seconds)

    login_verdict = classify_probe(snapshot.get("loginRaw") or {})
    return _build_page_tools_report(
        snapshot,
        login_verdict=login_verdict,
        port=session.port,
        target_id=isolation.target_id,
        selection=selection.to_dict(),
        isolation=isolation.to_dict(),
        messages=[
            "Collected SmartStore page controls from an isolated CDP tab; no browser launch, restart, close, submit, save, or write action.",
            "Session storage remains SmartStore-specific: data/sessions/sell.smartstore.naver.com.json.",
        ],
    )


def _read_page_tools_snapshot(target_id: str, *, port: int) -> dict[str, Any]:
    snapshot = cdp.evaluate(target_id, PAGE_TOOLS_EXPR, timeout=8.0, port=port) or {}
    if not isinstance(snapshot, dict):
        snapshot = {}
    counts = snapshot.get("counts") if isinstance(snapshot.get("counts"), dict) else {}
    if sum(int(counts.get(key) or 0) for key in ("menus", "buttons", "links", "inputs")) == 0:
        try:
            ax_event = _send_target_cdp(target_id, "Accessibility.getFullAXTree", {}, port=port)
            nodes = ((ax_event.get("result") or {}).get("nodes") or [])
            if isinstance(nodes, list):
                snapshot = _merge_ax_fallback(snapshot, extract_accessibility_controls(nodes))
        except Exception:
            pass
    return snapshot


def _wait_page_tools_snapshot(target_id: str, *, port: int, wait_seconds: float) -> dict[str, Any]:
    deadline = time.time() + max(1.0, wait_seconds)
    snapshot: dict[str, Any] = {}
    while time.time() < deadline:
        snapshot = _read_page_tools_snapshot(target_id, port=port)
        if snapshot.get("readyState") == "complete" and snapshot.get("href") != "about:blank":
            break
        time.sleep(0.5)
    return snapshot


def _build_page_tools_report(
    snapshot: dict[str, Any],
    *,
    login_verdict: dict[str, Any],
    port: int,
    target_id: str,
    selection: dict[str, Any],
    isolation: dict[str, Any],
    messages: list[str],
) -> SmartStorePageToolsReport:
    candidates = build_tool_candidates(snapshot)
    return SmartStorePageToolsReport(
        ok=bool(login_verdict.get("logged_in")),
        code="ok" if login_verdict.get("logged_in") else str(login_verdict.get("code") or "login_required"),
        port=port,
        target_id=target_id,
        url=str(snapshot.get("href") or ""),
        title=str(snapshot.get("title") or ""),
        logged_in=bool(login_verdict.get("logged_in")),
        counts=dict(snapshot.get("counts") or {}),
        headings=[str(item) for item in (snapshot.get("headings") or [])],
        menus=list(snapshot.get("menus") or []),
        buttons=list(snapshot.get("buttons") or []),
        links=list(snapshot.get("links") or []),
        inputs=list(snapshot.get("inputs") or []),
        tool_candidates=[candidate.to_dict() for candidate in candidates],
        messages=messages,
        selection=selection,
        isolation=isolation,
    )


def save_page_tools_report(report: SmartStorePageToolsReport, output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_PAGE_TOOLS_PATH
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def collect_dashboard_summary(*, allow_mixed_readonly: bool = False) -> SmartStoreDashboardReport:
    session, selection = select_smartstore_session(allow_mixed_readonly=allow_mixed_readonly)
    if session is None:
        return SmartStoreDashboardReport(
            ok=False,
            code=selection.code,
            messages=list(selection.messages),
            selection=selection.to_dict(),
        )
    target_id, raw = find_rendered_smartstore_target(port=session.port)
    if not target_id or not raw:
        return SmartStoreDashboardReport(
            ok=False,
            code="no_rendered_smartstore_tab",
            port=session.port,
            messages=["No rendered SmartStore tab was found. Run smartstore login-watch after opening the browser."],
            selection=selection.to_dict(),
        )
    verdict = classify_probe(raw)
    if not verdict.get("logged_in"):
        return SmartStoreDashboardReport(
            ok=False,
            code=str(verdict.get("code") or "login_required"),
            port=session.port,
            target_id=target_id,
            url=str(verdict.get("url") or ""),
            title=str(verdict.get("title") or ""),
            logged_in=False,
            messages=["SmartStore dashboard is not logged in or not fully rendered."],
            selection=selection.to_dict(),
        )

    snapshot = _read_page_tools_snapshot(target_id, port=session.port)
    body = str(verdict.get("body_sample") or "")
    menus = [str(item.get("text") or "") for item in snapshot.get("menus") or [] if item.get("text")]
    buttons = [str(item.get("text") or "") for item in snapshot.get("buttons") or [] if item.get("text")]
    inputs = [
        str(item.get("label") or item.get("placeholder") or item.get("name") or item.get("aria") or "")
        for item in snapshot.get("inputs") or []
    ]
    primary_names = [
        "상품관리",
        "판매관리",
        "정산관리",
        "문의/리뷰관리",
        "스토어관리",
        "혜택/마케팅",
        "N배송 관리",
        "커머스솔루션",
        "데이터분석",
        "광고관리",
        "프로모션 관리",
        "쇼핑 커넥트",
        "판매자 정보",
    ]
    primary_menus = [name for name in primary_names if name in menus or name in body]
    notices = [text for text in menus if any(token in text for token in ("공지", "정책", "안내", "변경"))][:20]
    store_name = next((text for text in menus if text and text not in primary_names and "아뜰리에" in text), "")
    user_label = "logged_in_user_detected" if verdict.get("markers", {}).get("accountUser") else ""
    return SmartStoreDashboardReport(
        ok=True,
        code="ok",
        port=session.port,
        target_id=target_id,
        url=str(verdict.get("url") or snapshot.get("href") or ""),
        title=str(verdict.get("title") or snapshot.get("title") or ""),
        logged_in=True,
        store_name=store_name,
        user_label=user_label,
        primary_menus=primary_menus,
        utility_buttons=buttons[:30],
        notices=notices,
        search_inputs=[text for text in inputs if text][:20],
        messages=["Collected SmartStore dashboard summary from the rendered logged-in tab."],
        selection=selection.to_dict(),
    )


def save_dashboard_report(report: SmartStoreDashboardReport, output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_DASHBOARD_PATH
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
