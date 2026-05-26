"""Advanced SmartStore menu analyzers.

The analyzers are read-only. They open a SmartStore menu through the common
menu gate, then normalize the visible page into business-oriented records:
tables, metric cards, forms, filters, and approval-sensitive controls.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scripts.naver.mail_read import cdp
from scripts.smartstore.menu_tools import (
    APPROVAL_CONFIRM_TEXT,
    MENU_SPECS,
    SmartStoreMenuSnapshotReport,
    collect_menu_snapshot,
    resolve_menu_spec,
)

ROOT = Path(__file__).resolve().parents[2]
LATEST_ADVANCED_REPORT_PATH = ROOT / "data" / "smartstore_advanced_report_latest.json"
LATEST_ADVANCED_ALL_PATH = ROOT / "data" / "smartstore_advanced_all_latest.json"

APPROVAL_TOKENS = (
    "save",
    "submit",
    "send",
    "delete",
    "cancel",
    "approve",
    "reject",
    "start",
    "stop",
    "issue",
    "install",
    "uninstall",
    "disconnect",
    "저장",
    "등록",
    "발송",
    "삭제",
    "취소",
    "승인",
    "거절",
    "반려",
    "시작",
    "중지",
    "발급",
    "설치",
    "해지",
    "정산요청",
)


@dataclass(frozen=True)
class AdvancedMenuProfile:
    menu_id: str
    domain: str
    supported_tools: list[str]
    key_entities: list[str]
    recommended_next_tools: list[str]
    high_value: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AdvancedMenuReport:
    ok: bool
    code: str
    menu_id: str
    label: str = ""
    profile: dict[str, Any] = field(default_factory=dict)
    snapshot: dict[str, Any] = field(default_factory=dict)
    normalized: dict[str, Any] = field(default_factory=dict)
    menu_insights: dict[str, Any] = field(default_factory=dict)
    approval_controls: list[dict[str, Any]] = field(default_factory=list)
    read_controls: list[dict[str, Any]] = field(default_factory=list)
    prepare_fields: list[dict[str, Any]] = field(default_factory=list)
    automation_plan: list[dict[str, Any]] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ADVANCED_PROFILES: dict[str, AdvancedMenuProfile] = {
    "product": AdvancedMenuProfile(
        "product",
        "상품 운영",
        ["product.list.normalized", "product.filter.prepare", "product.bulk.prepare", "product.approval.guard"],
        ["product", "price", "stock", "sale_status", "exposure_status"],
        ["상품 목록 정규화", "검색/필터 조건 저장", "재고/가격 이상치 탐지", "등록/삭제 승인 게이트"],
        True,
    ),
    "sales": AdvancedMenuProfile(
        "sales",
        "주문/배송",
        ["order.list.normalized", "delivery.queue.read", "claim.status.read", "delivery.approval.guard"],
        ["order", "buyer", "payment", "delivery", "claim"],
        ["신규 주문 수집", "배송 지연 탐지", "취소/반품/교환 분류", "발송 승인 게이트"],
        True,
    ),
    "settlement": AdvancedMenuProfile(
        "settlement",
        "정산",
        ["settlement.summary.normalized", "settlement.table.read", "settlement.export.guard"],
        ["settlement_amount", "fee", "payable", "payout_date"],
        ["정산 요약 수집", "수수료 항목 분류", "지급 예정/완료 비교"],
        True,
    ),
    "inquiry_review": AdvancedMenuProfile(
        "inquiry_review",
        "고객 응대",
        ["inquiry.list.normalized", "review.list.normalized", "reply.draft.prepare", "reply.send.guard"],
        ["inquiry", "review", "rating", "reply_status"],
        ["미답변 문의 수집", "리뷰 답변 초안", "감성/불만 키워드 분류", "답변 발송 승인 게이트"],
        True,
    ),
    "data_analysis": AdvancedMenuProfile(
        "data_analysis",
        "성과 분석",
        ["analytics.metric.cards", "analytics.table.read", "analytics.trend.summary"],
        ["sales", "traffic", "conversion", "product_performance"],
        ["매출/방문/전환 지표 수집", "상품별 성과 요약", "이상 변동 탐지"],
        True,
    ),
}

for spec in MENU_SPECS:
    ADVANCED_PROFILES.setdefault(
        spec.menu_id,
        AdvancedMenuProfile(
            spec.menu_id,
            spec.purpose,
            [f"{spec.menu_id}.snapshot.normalized", f"{spec.menu_id}.approval.guard"],
            [spec.menu_id],
            ["가시 컨트롤 수집", "입력 필드 분류", "승인 필요 버튼 분리"],
            False,
        ),
    )


ADVANCED_PAGE_EXPR = r"""JSON.stringify((() => {
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
  const textOf = (el) => clean(el.innerText || el.textContent || el.getAttribute('aria-label') || el.value || '');
  const tables = Array.from(document.querySelectorAll('table')).filter(visible).map((table) => {
    const headers = Array.from(table.querySelectorAll('thead th, thead td, tr:first-child th'))
      .map(textOf).filter(Boolean).slice(0, 30);
    const rows = Array.from(table.querySelectorAll('tbody tr, tr')).slice(0, 25).map((tr) =>
      Array.from(tr.querySelectorAll('td, th')).map(textOf).filter(Boolean).slice(0, 20)
    ).filter((row) => row.length > 0);
    return {headers, rows, row_count: rows.length, rect: rectOf(table)};
  }).slice(0, 10);
  const cards = Array.from(document.querySelectorAll('[class*="card"],[class*="summary"],[class*="Summary"],[class*="metric"],[class*="Metric"],li,section'))
    .filter(visible)
    .map((el) => ({text: textOf(el).slice(0, 240), rect: rectOf(el)}))
    .filter((item) => item.text && /\d/.test(item.text))
    .slice(0, 40);
  const fields = Array.from(document.querySelectorAll('input,textarea,select')).filter(visible).map((el) => ({
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type') || '',
    name: el.getAttribute('name') || '',
    placeholder: el.getAttribute('placeholder') || '',
    aria: el.getAttribute('aria-label') || '',
    value_present: !!(el.value || el.checked),
    rect: rectOf(el)
  })).slice(0, 120);
  const controls = Array.from(document.querySelectorAll('button,a,[role="button"],input[type="button"],input[type="submit"]'))
    .filter(visible)
    .map((el) => ({
      text: textOf(el).slice(0, 80),
      tag: el.tagName.toLowerCase(),
      href: el.href || '',
      role: el.getAttribute('role') || '',
      rect: rectOf(el)
    }))
    .filter((item) => item.text || item.href)
    .slice(0, 160);
  const body = clean(document.body ? document.body.innerText : '');
  return {
    href: location.href,
    title: document.title || '',
    headings: Array.from(document.querySelectorAll('h1,h2,h3,[role="heading"]')).filter(visible).map(textOf).filter(Boolean).slice(0, 40),
    tables,
    cards,
    fields,
    controls,
    body_sample: body.slice(0, 2000),
    counts: {tables: tables.length, cards: cards.length, fields: fields.length, controls: controls.length, bodyTextLength: body.length}
  };
})())"""


def build_advanced_catalog() -> dict[str, Any]:
    profiles = [ADVANCED_PROFILES[spec.menu_id].to_dict() for spec in MENU_SPECS]
    return {
        "site_id": "smartstore",
        "profile_count": len(profiles),
        "high_value_profiles": [profile["menu_id"] for profile in profiles if profile.get("high_value")],
        "profiles": profiles,
        "contract": {
            "read": "collect visible tables, metric cards, fields, and controls",
            "prepare": "build drafts/filters without final save",
            "approval": f"state-changing controls require --approved --confirm={APPROVAL_CONFIRM_TEXT}",
        },
    }


def _control_risk(control: dict[str, Any]) -> str:
    text = str(control.get("text") or "").lower()
    href = str(control.get("href") or "").lower()
    haystack = f"{text} {href}"
    return "approval" if any(token.lower() in haystack for token in APPROVAL_TOKENS) else "read"


def _field_label(field: dict[str, Any]) -> str:
    return str(field.get("placeholder") or field.get("aria") or field.get("name") or field.get("type") or field.get("tag") or "")


def _normalize_payload(menu_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    tables = payload.get("tables") if isinstance(payload.get("tables"), list) else []
    cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
    body = str(payload.get("body_sample") or "")
    numbers = re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?%?", body)
    return {
        "menu_id": menu_id,
        "url": str(payload.get("href") or ""),
        "title": str(payload.get("title") or ""),
        "headings": [str(item) for item in (payload.get("headings") or [])],
        "table_count": len(tables),
        "tables": tables,
        "metric_card_count": len(cards),
        "metric_cards": cards[:30],
        "numeric_tokens": numbers[:80],
        "field_count": len(payload.get("fields") or []),
        "control_count": len(payload.get("controls") or []),
        "counts": dict(payload.get("counts") or {}),
    }


def _texts(payload: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for key in ("headings",):
        texts.extend(str(item) for item in (payload.get(key) or []))
    for key in ("cards", "controls"):
        for item in payload.get(key) or []:
            if isinstance(item, dict):
                texts.append(str(item.get("text") or ""))
    for table in payload.get("tables") or []:
        if not isinstance(table, dict):
            continue
        texts.extend(str(item) for item in (table.get("headers") or []))
        for row in table.get("rows") or []:
            texts.extend(str(cell) for cell in row)
    texts.append(str(payload.get("body_sample") or ""))
    return [text for text in texts if text]


def _contains_any(texts: list[str], tokens: tuple[str, ...]) -> bool:
    haystack = "\n".join(texts).lower()
    return any(token.lower() in haystack for token in tokens)


def _matching_controls(controls: list[dict[str, Any]], tokens: tuple[str, ...]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for control in controls:
        text = str(control.get("text") or "")
        href = str(control.get("href") or "")
        haystack = f"{text} {href}".lower()
        if any(token.lower() in haystack for token in tokens):
            out.append(control)
    return out[:30]


def _matching_fields(fields: list[dict[str, Any]], tokens: tuple[str, ...]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for field in fields:
        label = _field_label(field)
        if any(token.lower() in label.lower() for token in tokens):
            out.append({**field, "label": label})
    return out[:30]


def _table_headers(normalized: dict[str, Any]) -> list[str]:
    headers: list[str] = []
    for table in normalized.get("tables") or []:
        if isinstance(table, dict):
            headers.extend(str(item) for item in (table.get("headers") or []))
    return headers


def _menu_specific_insights(
    menu_id: str,
    payload: dict[str, Any],
    normalized: dict[str, Any],
    controls: list[dict[str, Any]],
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    texts = _texts(payload)
    headers = _table_headers(normalized)
    base = {
        "menu_id": menu_id,
        "entity_columns": headers[:40],
        "has_table_data": bool(normalized.get("table_count")),
        "has_metrics": bool(normalized.get("metric_card_count")),
        "numeric_sample": list(normalized.get("numeric_tokens") or [])[:20],
    }
    specs: dict[str, dict[str, Any]] = {
        "product": {
            "entity": "product",
            "read_models": ["product_list", "inventory_status", "sale_status", "exposure_status"],
            "detectors": {
                "price_visible": _contains_any(texts, ("price", "sale price", "판매가", "가격")),
                "stock_visible": _contains_any(texts, ("stock", "재고")),
                "status_visible": _contains_any(texts, ("status", "상태", "판매중", "품절", "노출")),
            },
            "prepare_fields": _matching_fields(fields, ("상품", "product", "price", "stock", "재고", "가격")),
            "approval_actions": _matching_controls(controls, ("등록", "저장", "삭제", "delete", "save")),
        },
        "sales": {
            "entity": "order",
            "read_models": ["order_list", "delivery_queue", "claim_status"],
            "detectors": {
                "order_visible": _contains_any(texts, ("order", "주문")),
                "delivery_visible": _contains_any(texts, ("delivery", "배송", "발송")),
                "claim_visible": _contains_any(texts, ("cancel", "return", "exchange", "취소", "반품", "교환")),
            },
            "prepare_fields": _matching_fields(fields, ("주문", "order", "배송", "delivery", "claim")),
            "approval_actions": _matching_controls(controls, ("발송", "취소", "승인", "send", "cancel", "approve")),
        },
        "settlement": {
            "entity": "settlement",
            "read_models": ["settlement_summary", "fee_breakdown", "payout_schedule"],
            "detectors": {
                "amount_visible": _contains_any(texts, ("amount", "금액", "정산", "지급")),
                "fee_visible": _contains_any(texts, ("fee", "수수료")),
                "date_visible": _contains_any(texts, ("date", "일자", "예정", "완료")),
            },
            "prepare_fields": _matching_fields(fields, ("정산", "settlement", "기간", "date")),
            "approval_actions": _matching_controls(controls, ("정산요청", "export", "download", "요청")),
        },
        "inquiry_review": {
            "entity": "customer_message",
            "read_models": ["inquiry_list", "review_list", "reply_status"],
            "detectors": {
                "inquiry_visible": _contains_any(texts, ("inquiry", "문의")),
                "review_visible": _contains_any(texts, ("review", "리뷰", "평점")),
                "reply_visible": _contains_any(texts, ("reply", "답변", "미답변")),
            },
            "prepare_fields": _matching_fields(fields, ("답변", "reply", "문의", "리뷰")),
            "approval_actions": _matching_controls(controls, ("답변등록", "발송", "send", "submit")),
        },
        "store": {
            "entity": "store_profile",
            "read_models": ["store_info", "display_settings", "policy_settings"],
            "detectors": {
                "profile_visible": _contains_any(texts, ("store", "스토어", "상점")),
                "display_visible": _contains_any(texts, ("display", "전시", "노출")),
                "policy_visible": _contains_any(texts, ("policy", "정책", "약관")),
            },
            "prepare_fields": _matching_fields(fields, ("스토어", "store", "상호", "대표", "display")),
            "approval_actions": _matching_controls(controls, ("저장", "변경", "save", "change")),
        },
        "benefit_marketing": {
            "entity": "benefit_campaign",
            "read_models": ["coupon_list", "benefit_status", "campaign_status"],
            "detectors": {
                "coupon_visible": _contains_any(texts, ("coupon", "쿠폰")),
                "benefit_visible": _contains_any(texts, ("benefit", "혜택", "포인트")),
                "campaign_visible": _contains_any(texts, ("campaign", "캠페인", "마케팅")),
            },
            "prepare_fields": _matching_fields(fields, ("쿠폰", "coupon", "혜택", "benefit", "campaign")),
            "approval_actions": _matching_controls(controls, ("발급", "시작", "저장", "issue", "start", "save")),
        },
        "n_delivery": {
            "entity": "n_delivery",
            "read_models": ["n_delivery_status", "shipping_policy"],
            "detectors": {
                "shipping_visible": _contains_any(texts, ("shipping", "delivery", "배송", "발송")),
                "policy_visible": _contains_any(texts, ("policy", "설정", "정책")),
            },
            "prepare_fields": _matching_fields(fields, ("배송", "delivery", "shipping", "N배송")),
            "approval_actions": _matching_controls(controls, ("저장", "요청", "발송", "save", "request", "send")),
        },
        "commerce_solution": {
            "entity": "solution",
            "read_models": ["solution_list", "solution_usage"],
            "detectors": {
                "solution_visible": _contains_any(texts, ("solution", "솔루션")),
                "install_visible": _contains_any(texts, ("install", "설치", "사용")),
            },
            "prepare_fields": _matching_fields(fields, ("solution", "솔루션", "설정")),
            "approval_actions": _matching_controls(controls, ("설치", "해지", "저장", "install", "uninstall", "save")),
        },
        "data_analysis": {
            "entity": "analytics_metric",
            "read_models": ["sales_metrics", "traffic_metrics", "conversion_metrics", "product_metrics"],
            "detectors": {
                "sales_visible": _contains_any(texts, ("sales", "매출")),
                "traffic_visible": _contains_any(texts, ("traffic", "방문", "유입")),
                "conversion_visible": _contains_any(texts, ("conversion", "전환")),
            },
            "prepare_fields": _matching_fields(fields, ("기간", "date", "상품", "product")),
            "approval_actions": [],
        },
        "ads": {
            "entity": "ad_campaign",
            "read_models": ["ad_campaign_list", "ad_performance", "budget_status"],
            "detectors": {
                "campaign_visible": _contains_any(texts, ("campaign", "캠페인", "광고")),
                "budget_visible": _contains_any(texts, ("budget", "예산", "비용")),
                "performance_visible": _contains_any(texts, ("click", "클릭", "노출", "전환")),
            },
            "prepare_fields": _matching_fields(fields, ("광고", "ad", "campaign", "예산")),
            "approval_actions": _matching_controls(controls, ("시작", "중지", "저장", "start", "stop", "save")),
        },
        "promotion": {
            "entity": "promotion",
            "read_models": ["promotion_list", "promotion_status"],
            "detectors": {
                "promotion_visible": _contains_any(texts, ("promotion", "프로모션")),
                "apply_visible": _contains_any(texts, ("apply", "신청", "참여")),
            },
            "prepare_fields": _matching_fields(fields, ("promotion", "프로모션", "신청")),
            "approval_actions": _matching_controls(controls, ("신청", "취소", "submit", "apply", "cancel")),
        },
        "shopping_connect": {
            "entity": "shopping_connect",
            "read_models": ["connect_status", "channel_status"],
            "detectors": {
                "connect_visible": _contains_any(texts, ("connect", "커넥트", "연동")),
                "channel_visible": _contains_any(texts, ("channel", "채널")),
            },
            "prepare_fields": _matching_fields(fields, ("connect", "커넥트", "channel", "채널")),
            "approval_actions": _matching_controls(controls, ("연동", "해제", "저장", "connect", "disconnect", "save")),
        },
        "seller_info": {
            "entity": "seller_account",
            "read_models": ["seller_profile", "business_info", "permission_status"],
            "detectors": {
                "seller_visible": _contains_any(texts, ("seller", "판매자")),
                "business_visible": _contains_any(texts, ("business", "사업자")),
                "permission_visible": _contains_any(texts, ("permission", "권한")),
            },
            "prepare_fields": _matching_fields(fields, ("판매자", "seller", "사업자", "business", "권한")),
            "approval_actions": _matching_controls(controls, ("저장", "변경", "save", "change")),
        },
    }
    specific = specs.get(menu_id, {"entity": menu_id, "read_models": [f"{menu_id}_snapshot"], "detectors": {}})
    return {**base, **specific}


def _automation_plan(profile: AdvancedMenuProfile, report: SmartStoreMenuSnapshotReport, normalized: dict[str, Any]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    plan.append({
        "step": "collect",
        "tool": profile.supported_tools[0] if profile.supported_tools else f"{profile.menu_id}.snapshot.normalized",
        "risk": "read",
        "status": "implemented",
    })
    if normalized.get("table_count"):
        plan.append({"step": "table_normalize", "tool": f"{profile.menu_id}.table.read", "risk": "read", "status": "implemented"})
    if normalized.get("field_count"):
        plan.append({"step": "prepare_filters", "tool": f"{profile.menu_id}.filter.prepare", "risk": "prepare", "status": "implemented_prepare_only"})
    if any(item.get("risk") == "approval" for item in report.tool_candidates):
        plan.append({
            "step": "approval_guard",
            "tool": f"{profile.menu_id}.approval.guard",
            "risk": "approval",
            "status": "blocked_without_approval",
            "requires": ["--approved", f"--confirm={APPROVAL_CONFIRM_TEXT}"],
        })
    return plan


def analyze_menu(
    menu_id_or_label: str,
    *,
    allow_mixed_readonly: bool = False,
    wait_seconds: float = 6.0,
) -> AdvancedMenuReport:
    spec = resolve_menu_spec(menu_id_or_label)
    profile = ADVANCED_PROFILES[spec.menu_id]
    snapshot = collect_menu_snapshot(
        spec.menu_id,
        allow_mixed_readonly=allow_mixed_readonly,
        wait_seconds=wait_seconds,
    )
    if not snapshot.ok:
        return AdvancedMenuReport(
            ok=False,
            code=snapshot.code,
            menu_id=spec.menu_id,
            label=spec.label,
            profile=profile.to_dict(),
            snapshot=snapshot.to_dict(),
            messages=list(snapshot.messages),
        )

    payload = cdp.evaluate(snapshot.target_id, ADVANCED_PAGE_EXPR, timeout=10.0, port=int(snapshot.port or 0)) or {}
    if not isinstance(payload, dict):
        payload = {}
    normalized = _normalize_payload(spec.menu_id, payload)
    controls = list(payload.get("controls") or [])
    fields = list(payload.get("fields") or [])
    approval_controls = [control | {"risk": "approval"} for control in controls if _control_risk(control) == "approval"]
    read_controls = [control | {"risk": "read"} for control in controls if _control_risk(control) == "read"]
    prepare_fields = [
        {**field, "label": _field_label(field), "risk": "prepare", "final_submit_blocked": True}
        for field in fields
    ]
    menu_insights = _menu_specific_insights(spec.menu_id, payload, normalized, controls, fields)
    return AdvancedMenuReport(
        ok=True,
        code="ok",
        menu_id=spec.menu_id,
        label=spec.label,
        profile=profile.to_dict(),
        snapshot=snapshot.to_dict(),
        normalized=normalized,
        menu_insights=menu_insights,
        approval_controls=approval_controls[:80],
        read_controls=read_controls[:80],
        prepare_fields=prepare_fields[:80],
        automation_plan=_automation_plan(profile, snapshot, normalized),
        messages=[
            "Advanced SmartStore menu analysis completed as read-only collection.",
            "No save, submit, send, delete, cancel, approve, reject, issue, install, stop, or settlement request was executed.",
        ],
    )


def analyze_all_menus(*, allow_mixed_readonly: bool = False, wait_seconds: float = 4.0) -> dict[str, Any]:
    reports = [
        analyze_menu(spec.menu_id, allow_mixed_readonly=allow_mixed_readonly, wait_seconds=wait_seconds).to_dict()
        for spec in MENU_SPECS
    ]
    return {
        "site_id": "smartstore",
        "menu_count": len(MENU_SPECS),
        "ok_count": sum(1 for report in reports if report.get("ok")),
        "high_value_ok": [report["menu_id"] for report in reports if report.get("ok") and report.get("profile", {}).get("high_value")],
        "reports": reports,
    }


def save_advanced_report(report: AdvancedMenuReport, output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_ADVANCED_REPORT_PATH
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_advanced_all(payload: dict[str, Any], output: str | Path | None = None) -> Path:
    path = Path(output) if output else LATEST_ADVANCED_ALL_PATH
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
