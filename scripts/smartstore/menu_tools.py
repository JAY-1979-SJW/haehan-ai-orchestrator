"""SmartStore primary menu tools.

This module turns the observed SmartStore left navigation into explicit,
read-oriented tools. Opening a menu is treated as navigation only; save,
submit, send, delete, cancel, settlement request, and other state-changing
controls remain approval-gated elsewhere.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scripts.naver.mail_read import cdp
from scripts.smartstore.live_probe import classify_probe, find_rendered_smartstore_target, select_smartstore_session
from scripts.smartstore.page_tools import _read_page_tools_snapshot

ROOT = Path(__file__).resolve().parents[2]
LATEST_MENU_CATALOG_PATH = ROOT / "data" / "smartstore_menu_catalog_latest.json"
LATEST_MENU_REPORT_PATH = ROOT / "data" / "smartstore_menu_snapshot_latest.json"
LATEST_ALL_MENU_REPORT_PATH = ROOT / "data" / "smartstore_menu_snapshots_latest.json"

APPROVAL_CONFIRM_TEXT = "SMARTSTORE_APPROVED_SUBMIT"


@dataclass(frozen=True)
class SmartStoreMenuSpec:
    menu_id: str
    label: str
    route_hint: str
    purpose: str
    read_tools: list[str]
    prepare_tools: list[str] = field(default_factory=list)
    approval_tools: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    status: str = "implemented_read_snapshot"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["risk_contract"] = {
            "read": "allowed",
            "prepare": "allowed only without final save/submit",
            "approval": f"requires --approved --confirm={APPROVAL_CONFIRM_TEXT}",
        }
        return data


@dataclass
class SmartStoreMenuSnapshotReport:
    ok: bool
    code: str
    menu_id: str = ""
    label: str = ""
    port: int | None = None
    target_id: str = ""
    before_url: str = ""
    after_url: str = ""
    title: str = ""
    logged_in: bool = False
    counts: dict[str, int] = field(default_factory=dict)
    headings: list[str] = field(default_factory=list)
    visible_menus: list[dict[str, Any]] = field(default_factory=list)
    buttons: list[dict[str, Any]] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    tables: int = 0
    tool_candidates: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    selection: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MENU_SPECS: tuple[SmartStoreMenuSpec, ...] = (
    SmartStoreMenuSpec(
        "product",
        "상품관리",
        "#/products",
        "상품 조회, 상품 등록 준비, 상품 상태/노출 관리",
        ["product.list", "product.detail.read", "product.page.snapshot"],
        ["product.general.prepare", "product.group.prepare", "product.bulk.prepare"],
        ["product.general.save", "product.group.save", "product.bulk.save", "product.delete", "product.status.change"],
        ["products", "상품"],
    ),
    SmartStoreMenuSpec(
        "sales",
        "판매관리",
        "#/orders",
        "주문, 발송, 배송, 취소/반품/교환 현황 조회",
        ["order.list", "order.detail.read", "delivery.status.read", "sales.page.snapshot"],
        ["delivery.prepare", "claim.memo.prepare"],
        ["delivery.send", "order.cancel.approve", "return.approve", "exchange.approve"],
        ["order", "orders", "판매", "주문"],
    ),
    SmartStoreMenuSpec(
        "settlement",
        "정산관리",
        "#/settlement",
        "정산 예정/완료, 수수료, 지급 내역 조회",
        ["settlement.list", "settlement.summary.read", "settlement.page.snapshot"],
        [],
        ["settlement.request", "settlement.export_confirmed"],
        ["settlements", "정산"],
    ),
    SmartStoreMenuSpec(
        "inquiry_review",
        "문의/리뷰관리",
        "#/customer",
        "고객 문의와 리뷰 조회, 답변 초안 준비",
        ["inquiry.list", "review.list", "customer.voice.snapshot"],
        ["inquiry.reply.prepare", "review.reply.prepare"],
        ["inquiry.reply.send", "review.reply.send"],
        ["review", "reviews", "inquiry", "문의", "리뷰"],
    ),
    SmartStoreMenuSpec(
        "store",
        "스토어관리",
        "#/store",
        "스토어 정보, 전시, 운영 설정 조회와 변경 준비",
        ["store.info", "store.display.read", "store.page.snapshot"],
        ["store.info.prepare", "store.display.prepare"],
        ["store.info.save", "store.display.save", "store.policy.save"],
        ["store-management", "스토어"],
    ),
    SmartStoreMenuSpec(
        "benefit_marketing",
        "혜택/마케팅",
        "#/benefit",
        "쿠폰, 포인트, 프로모션성 혜택 현황 조회",
        ["benefit.list", "coupon.list", "marketing.page.snapshot"],
        ["coupon.prepare", "benefit.prepare"],
        ["coupon.issue", "benefit.save", "campaign.start"],
        ["benefit", "marketing", "혜택", "마케팅"],
    ),
    SmartStoreMenuSpec(
        "n_delivery",
        "N배송 관리",
        "#/n-delivery",
        "N배송 설정과 처리 현황 조회",
        ["n_delivery.status.read", "n_delivery.page.snapshot"],
        ["n_delivery.setting.prepare"],
        ["n_delivery.setting.save", "n_delivery.shipment.request"],
        ["delivery", "n-delivery", "N배송"],
    ),
    SmartStoreMenuSpec(
        "commerce_solution",
        "커머스솔루션",
        "#/solution",
        "솔루션 설치/사용 현황 조회",
        ["solution.list", "solution.usage.read", "solution.page.snapshot"],
        ["solution.config.prepare"],
        ["solution.install", "solution.uninstall", "solution.config.save"],
        ["solution", "솔루션"],
    ),
    SmartStoreMenuSpec(
        "data_analysis",
        "데이터분석",
        "#/analytics",
        "매출, 유입, 상품, 고객 데이터 조회",
        ["analytics.today", "analytics.traffic.read", "analytics.product.read", "analytics.page.snapshot"],
        [],
        [],
        ["analytics", "stats", "데이터", "분석"],
    ),
    SmartStoreMenuSpec(
        "ads",
        "광고관리",
        "#/advertise",
        "광고 성과와 캠페인 현황 조회",
        ["ads.list", "ads.performance.read", "ads.page.snapshot"],
        ["ads.campaign.prepare"],
        ["ads.campaign.start", "ads.campaign.stop", "ads.budget.save"],
        ["advertising", "ad", "광고"],
    ),
    SmartStoreMenuSpec(
        "promotion",
        "프로모션 관리",
        "#/promotion",
        "프로모션 참여, 노출, 진행 상태 조회",
        ["promotion.list", "promotion.status.read", "promotion.page.snapshot"],
        ["promotion.apply.prepare"],
        ["promotion.apply.submit", "promotion.cancel"],
        ["promo", "promotion", "프로모션"],
    ),
    SmartStoreMenuSpec(
        "shopping_connect",
        "쇼핑 커넥트",
        "#/shopping-connect",
        "쇼핑 커넥트 연동/채널 상태 조회",
        ["shopping_connect.status.read", "shopping_connect.page.snapshot"],
        ["shopping_connect.config.prepare"],
        ["shopping_connect.config.save", "shopping_connect.disconnect"],
        ["connect", "shopping-connect", "커넥트"],
    ),
    SmartStoreMenuSpec(
        "seller_info",
        "판매자 정보",
        "#/seller-info",
        "판매자 계정, 사업자, 권한 정보 조회",
        ["seller.info", "seller.permission.read", "seller.page.snapshot"],
        ["seller.info.prepare"],
        ["seller.info.save", "seller.permission.change"],
        ["seller", "seller-info", "판매자"],
    ),
)


def list_menu_specs() -> list[SmartStoreMenuSpec]:
    return list(MENU_SPECS)


def build_menu_catalog() -> dict[str, Any]:
    specs = [spec.to_dict() for spec in MENU_SPECS]
    return {
        "site_id": "smartstore",
        "menu_count": len(specs),
        "menus": specs,
        "summary": {
            "read_tools": sum(len(spec.read_tools) for spec in MENU_SPECS),
            "prepare_tools": sum(len(spec.prepare_tools) for spec in MENU_SPECS),
            "approval_tools": sum(len(spec.approval_tools) for spec in MENU_SPECS),
        },
        "contract": {
            "menu_open": "read-only navigation in an already approved SmartStore CDP session",
            "read_and_prepare": "allowed",
            "state_change": f"blocked unless --approved --confirm={APPROVAL_CONFIRM_TEXT}",
        },
    }


def menu_tool_records(spec: SmartStoreMenuSpec) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for tool_id in spec.read_tools:
        records.append({"tool_id": tool_id, "risk": "read", "approval_required": False})
    for tool_id in spec.prepare_tools:
        records.append({"tool_id": tool_id, "risk": "prepare", "approval_required": False, "final_submit_blocked": True})
    for tool_id in spec.approval_tools:
        records.append({"tool_id": tool_id, "risk": "approval", "approval_required": True, "confirm": APPROVAL_CONFIRM_TEXT})
    return records


def save_menu_catalog(catalog: dict[str, Any] | None = None, output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_MENU_CATALOG_PATH
    path.write_text(json.dumps(catalog or build_menu_catalog(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def resolve_menu_spec(menu_id_or_label: str) -> SmartStoreMenuSpec:
    key = menu_id_or_label.strip().lower()
    for spec in MENU_SPECS:
        if key in {spec.menu_id.lower(), spec.label.lower(), *(alias.lower() for alias in spec.aliases)}:
            return spec
    raise KeyError(f"unknown SmartStore menu: {menu_id_or_label}")


def _click_menu_expr(label: str) -> str:
    encoded = json.dumps(label, ensure_ascii=False)
    return f"""JSON.stringify((() => {{
      const label = {encoded};
      const visible = (el) => {{
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      }};
      const textOf = (el) => String(el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
      const candidates = Array.from(document.querySelectorAll('a,button,[role="button"],[role="menuitem"],li,span,div'))
        .filter(visible)
        .map((el) => {{
          const rect = el.getBoundingClientRect();
          return {{el, text: textOf(el), x: rect.x, y: rect.y, w: rect.width, h: rect.height}};
        }})
        .filter((item) => item.text === label && item.x < 380)
        .sort((a, b) => a.x - b.x || a.y - b.y);
      if (!candidates.length) return {{ok: false, reason: 'menu_not_found', label}};
      const item = candidates[0];
      item.el.click();
      return {{ok: true, label, x: Math.round(item.x), y: Math.round(item.y), text: item.text}};
    }})())"""


def _wait_after_click(target_id: str, *, port: int, before_url: str, wait_seconds: float) -> dict[str, Any]:
    deadline = time.time() + max(1.0, wait_seconds)
    snapshot: dict[str, Any] = {}
    while time.time() < deadline:
        snapshot = _read_page_tools_snapshot(target_id, port=port)
        counts = snapshot.get("counts") if isinstance(snapshot.get("counts"), dict) else {}
        has_controls = sum(int(counts.get(key) or 0) for key in ("menus", "buttons", "links", "inputs")) > 0
        if snapshot.get("href") != before_url and has_controls:
            break
        if has_controls and snapshot.get("readyState") == "complete":
            break
        time.sleep(0.5)
    return snapshot


def collect_menu_snapshot(
    menu_id_or_label: str,
    *,
    allow_mixed_readonly: bool = False,
    wait_seconds: float = 6.0,
) -> SmartStoreMenuSnapshotReport:
    spec = resolve_menu_spec(menu_id_or_label)
    session, selection = select_smartstore_session(allow_mixed_readonly=allow_mixed_readonly)
    if session is None:
        return SmartStoreMenuSnapshotReport(
            ok=False,
            code=selection.code,
            menu_id=spec.menu_id,
            label=spec.label,
            messages=list(selection.messages),
            selection=selection.to_dict(),
        )

    target_id, raw = find_rendered_smartstore_target(port=session.port)
    if not target_id or not raw:
        return SmartStoreMenuSnapshotReport(
            ok=False,
            code="no_rendered_smartstore_tab",
            menu_id=spec.menu_id,
            label=spec.label,
            port=session.port,
            messages=["No rendered SmartStore tab was found. Open/login SmartStore first, then run login-watch."],
            selection=selection.to_dict(),
        )
    verdict = classify_probe(raw)
    if not verdict.get("logged_in"):
        return SmartStoreMenuSnapshotReport(
            ok=False,
            code=str(verdict.get("code") or "login_required"),
            menu_id=spec.menu_id,
            label=spec.label,
            port=session.port,
            target_id=target_id,
            before_url=str(verdict.get("url") or ""),
            logged_in=False,
            messages=["SmartStore tab is not logged in or not fully rendered."],
            selection=selection.to_dict(),
        )

    before_url = str(verdict.get("url") or "")
    clicked = cdp.evaluate(target_id, _click_menu_expr(spec.label), timeout=8.0, port=session.port)
    if not isinstance(clicked, dict) or not clicked.get("ok"):
        return SmartStoreMenuSnapshotReport(
            ok=False,
            code=str((clicked or {}).get("reason") if isinstance(clicked, dict) else "menu_click_failed"),
            menu_id=spec.menu_id,
            label=spec.label,
            port=session.port,
            target_id=target_id,
            before_url=before_url,
            logged_in=True,
            messages=[f"Could not open SmartStore menu: {spec.label}"],
            selection=selection.to_dict(),
        )

    snapshot = _wait_after_click(target_id, port=session.port, before_url=before_url, wait_seconds=wait_seconds)
    counts = dict(snapshot.get("counts") or {})
    return SmartStoreMenuSnapshotReport(
        ok=True,
        code="ok",
        menu_id=spec.menu_id,
        label=spec.label,
        port=session.port,
        target_id=target_id,
        before_url=before_url,
        after_url=str(snapshot.get("href") or before_url),
        title=str(snapshot.get("title") or verdict.get("title") or ""),
        logged_in=True,
        counts=counts,
        headings=[str(item) for item in (snapshot.get("headings") or [])],
        visible_menus=list(snapshot.get("menus") or [])[:120],
        buttons=list(snapshot.get("buttons") or [])[:80],
        links=list(snapshot.get("links") or [])[:120],
        inputs=list(snapshot.get("inputs") or [])[:120],
        tables=int(counts.get("tables") or 0),
        tool_candidates=menu_tool_records(spec),
        messages=[
            "Opened SmartStore primary menu and collected visible controls.",
            "No save, submit, send, delete, cancel, settlement request, or other write action was executed.",
        ],
        selection=selection.to_dict(),
    )


def save_menu_snapshot(report: SmartStoreMenuSnapshotReport, output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_MENU_REPORT_PATH
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def collect_all_menu_snapshots(
    *,
    allow_mixed_readonly: bool = False,
    wait_seconds: float = 4.0,
) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    for spec in MENU_SPECS:
        report = collect_menu_snapshot(
            spec.menu_id,
            allow_mixed_readonly=allow_mixed_readonly,
            wait_seconds=wait_seconds,
        )
        reports.append(report.to_dict())
    return {
        "site_id": "smartstore",
        "menu_count": len(MENU_SPECS),
        "ok_count": sum(1 for report in reports if report.get("ok")),
        "reports": reports,
        "contract": {
            "read_only": True,
            "write_actions_executed": False,
            "state_change_requires": f"--approved --confirm={APPROVAL_CONFIRM_TEXT}",
        },
    }


def save_all_menu_snapshots(payload: dict[str, Any], output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_ALL_MENU_REPORT_PATH
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
