"""Action Item Dashboard — business_report.action_items 위에 status/riskType/
dueDateCandidate 를 부여하여 실제 처리 lane 단위 데이터 계층을 생성한다.

입력:
  action_items.json (business_report.ActionItem 리스트)
  category_summary.json (선택)
  consolidated_business_report_v2.json (선택, 메타데이터 hash 용)

출력:
  action_dashboard.json
  action_dashboard.md
  action_dashboard_summary.json

규칙:
  - 외부 AI/HTTP 호출 0
  - raw body 0 / 원문 이메일 local-part 0
  - status 기본 NEW (caller 가 state 파일 주입하면 override 가능)
  - HIGH 3건 (스마트스토어 휴면 / 쿠팡 노출 정지 / FedEx 사칭) 유지 필수
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from . import business_report as br

KST = timezone(timedelta(hours=9))
SCHEMA_VERSION = "dashboard-1.0"


# ── 상태 / 리스크 타입 ────────────────────────────────────────────

STATUS_NEW = "NEW"
STATUS_REVIEWING = "REVIEWING"
STATUS_DONE = "DONE"
STATUS_DISMISSED = "DISMISSED"
STATUS_SNOOZED = "SNOOZED"

ALL_STATUSES = (STATUS_NEW, STATUS_REVIEWING, STATUS_DONE,
                STATUS_DISMISSED, STATUS_SNOOZED)


RISK_ACCOUNT = "ACCOUNT_RISK"
RISK_SELLER_ACCOUNT = "SELLER_ACCOUNT_RISK"
RISK_PHISHING = "PHISHING_RISK"
RISK_SEO = "SEO_RISK"
RISK_DELIVERY_FAILURE = "DELIVERY_FAILURE_RISK"
RISK_BILLING_REVIEW = "BILLING_REVIEW"
RISK_POLICY_REVIEW = "POLICY_REVIEW"
RISK_SECURITY_REVIEW = "SECURITY_REVIEW"
RISK_SERVICE_NOTICE = "SERVICE_NOTICE"
RISK_UNKNOWN_REVIEW = "UNKNOWN_REVIEW"

ALL_RISK_TYPES = (
    RISK_ACCOUNT, RISK_SELLER_ACCOUNT, RISK_PHISHING, RISK_SEO,
    RISK_DELIVERY_FAILURE, RISK_BILLING_REVIEW, RISK_POLICY_REVIEW,
    RISK_SECURITY_REVIEW, RISK_SERVICE_NOTICE, RISK_UNKNOWN_REVIEW,
)


# ── riskType 추론 룰 ──────────────────────────────────────────────

_SELLER_KEYWORD_RE = re.compile(
    r"스마트스토어|smartstore|판매자|상품 ?노출|노출 ?정지|wing\.coupang"
    r"|coupangcorp|seller|확약서|미답변|답변지연", re.IGNORECASE,
)


def _is_seller_domain(domain: str) -> bool:
    """발신 도메인이 셀러 컨텍스트인지."""
    return any(s in (domain or "").lower()
               for s in ("coupang", "smartstore", "navercorp"))


def infer_risk_type(category: str, title_redacted: str,
                    sender_domain: str) -> str:
    """category + 제목/도메인으로 riskType 결정."""
    blob = f"{title_redacted} {sender_domain}"
    if category == br.CAT_SPAM_OR_PHISHING_SUSPECTED:
        return RISK_PHISHING
    if category == br.CAT_DELIVERY_FAILURE:
        return RISK_DELIVERY_FAILURE
    if category == br.CAT_REVIEW:
        # GSC / 색인 → SEO
        if re.search(r"색인|indexing|search ?console|haehan-ai\.kr",
                     title_redacted, re.IGNORECASE):
            return RISK_SEO
        return RISK_UNKNOWN_REVIEW
    if category == br.CAT_ATTENTION:
        if _SELLER_KEYWORD_RE.search(blob) or _is_seller_domain(sender_domain):
            return RISK_SELLER_ACCOUNT
        return RISK_ACCOUNT
    if category == br.CAT_BILLING:
        return RISK_BILLING_REVIEW
    if category == br.CAT_POLICY_NOTICE:
        return RISK_POLICY_REVIEW
    if category == br.CAT_SECURITY_NOTICE:
        return RISK_SECURITY_REVIEW
    if category == br.CAT_ACCOUNT_OR_SERVICE_NOTICE:
        return RISK_SERVICE_NOTICE
    if category == br.CAT_UNKNOWN_REVIEW_REQUIRED:
        return RISK_UNKNOWN_REVIEW
    return RISK_UNKNOWN_REVIEW


# ── dueDateCandidate 추출 ────────────────────────────────────────

# "2026년 6월 9일", "26년 6월 9일", "6월 2일", "06.02", "2026.06.02", "5/19까지", "6월 9일 시행"
_DATE_PATTERNS = [
    re.compile(r"(\d{4})\s*[년\.]\s*(\d{1,2})\s*[월\.]\s*(\d{1,2})\s*일?"),
    re.compile(r"(\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"),
    re.compile(r"\b(\d{1,2})\s*월\s*(\d{1,2})\s*일\b"),
    re.compile(r"\b(\d{1,2})\s*/\s*(\d{1,2})\s*까지\b"),
]


def infer_due_date(title: str, received_date: str,
                   *, ref_year: int = 2026) -> tuple[str, str]:
    """제목/날짜에서 마감 후보 추출.

    Returns:
        (iso_date_or_empty, confidence_level)
        confidence_level: 'HIGH' / 'MEDIUM' / 'LOW' / 'NONE'
    """
    if not title:
        return ("", "NONE")
    # 1) YYYY-MM-DD 풀 패턴 (HIGH confidence)
    m = _DATE_PATTERNS[0].search(title)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            iso = f"{y:04d}-{mo:02d}-{d:02d}"
            return (iso, "HIGH")
        except Exception:
            pass
    # 2) YY 년 M 월 D 일
    m = _DATE_PATTERNS[1].search(title)
    if m:
        y, mo, d = int(m.group(1)) + 2000, int(m.group(2)), int(m.group(3))
        return (f"{y:04d}-{mo:02d}-{d:02d}", "HIGH")
    # 3) M 월 D 일 — 연도 추정 (시행일 등 보통 미래)
    m = _DATE_PATTERNS[2].search(title)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        return (f"{ref_year:04d}-{mo:02d}-{d:02d}", "MEDIUM")
    # 4) MM/DD 까지
    m = _DATE_PATTERNS[3].search(title)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        return (f"{ref_year:04d}-{mo:02d}-{d:02d}", "MEDIUM")
    return ("", "NONE")


# ── DashboardItem ────────────────────────────────────────────────


@dataclass
class DashboardItem:
    actionId: str
    sourceCategory: str
    priority: str
    status: str
    title_redacted: str
    sender_domain: str
    received_date: str
    reason: str
    recommended_action: str
    evidence_markers: list[str]
    riskType: str
    dueDateCandidate: str
    dueDateConfidence: str = "NONE"
    pii_masked: bool = True
    raw_body_saved: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Dashboard:
    schema_version: str = SCHEMA_VERSION
    generated_at: str = ""
    input_report_hash: str = ""
    items: list[DashboardItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "input_report_hash": self.input_report_hash,
            "items": [i.to_dict() for i in self.items],
        }


@dataclass
class DashboardSummary:
    total_items: int
    high_count: int
    medium_count: int
    low_count: int
    unknown_review_count: int
    risk_type_counts: dict
    category_counts: dict
    due_date_candidate_count: int
    pii_masked_all: bool
    raw_body_saved_any: bool
    generated_at: str
    input_report_hash: str
    high_required_present: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ── 빌드 ───────────────────────────────────────────────────────────


def _action_dict_to_item(a: dict,
                         *, status_lookup: dict[str, str] | None = None
                         ) -> DashboardItem:
    title = a.get("title_redacted", "")
    sender_dom = a.get("sender_domain", "")
    risk = infer_risk_type(
        a.get("category", ""), title, sender_dom,
    )
    due_iso, due_conf = infer_due_date(title, a.get("received_date", ""))
    status = (status_lookup or {}).get(a.get("actionId", ""), STATUS_NEW)
    return DashboardItem(
        actionId=a.get("actionId", ""),
        sourceCategory=a.get("category", ""),
        priority=a.get("priority", ""),
        status=status,
        title_redacted=title,
        sender_domain=sender_dom,
        received_date=a.get("received_date", ""),
        reason=a.get("reason", ""),
        recommended_action=a.get("recommended_action", ""),
        evidence_markers=list(a.get("evidence_markers", [])),
        riskType=risk,
        dueDateCandidate=due_iso,
        dueDateConfidence=due_conf,
        pii_masked=bool(a.get("pii_masked", True)),
        raw_body_saved=bool(a.get("raw_body_saved", False)),
    )


def build_dashboard(action_items: Iterable[dict],
                    *, status_lookup: dict[str, str] | None = None,
                    input_report_text: str = "") -> Dashboard:
    items = [_action_dict_to_item(a, status_lookup=status_lookup)
             for a in action_items]
    # 정렬: priority HIGH → MEDIUM → LOW, 그 다음 dueDateCandidate, 그 다음 received_date desc
    pri_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    items.sort(key=lambda i: (pri_order.get(i.priority, 9),
                              # dueDateCandidate 있는 것 우선
                              0 if i.dueDateCandidate else 1,
                              i.dueDateCandidate or "9999-99-99",
                              # received_date 는 문자열로 그대로 (역순 비교 어려움 — best-effort)
                              i.received_date))
    return Dashboard(
        generated_at=datetime.now(KST).replace(microsecond=0).isoformat(),
        input_report_hash=hashlib.sha256(
            (input_report_text or "").encode("utf-8")
        ).hexdigest()[:16],
        items=items,
    )


HIGH_REQUIRED_KEYWORDS = {
    "smartstore_dormant": ("스마트스토어", "휴면"),
    "coupang_listing_stop": ("쿠팡", "노출", "정지"),
    "fedex_phishing": ("shipping", "documents"),  # fedex 사칭 핵심
}


def _high_required_check(items: list[DashboardItem]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for key, kws in HIGH_REQUIRED_KEYWORDS.items():
        out[key] = any(
            i.priority == "HIGH"
            and all(kw.lower() in (i.title_redacted or "").lower()
                    for kw in kws)
            for i in items
        )
    return out


def build_summary(dash: Dashboard) -> DashboardSummary:
    pri_c = Counter(i.priority for i in dash.items)
    risk_c = Counter(i.riskType for i in dash.items)
    cat_c = Counter(i.sourceCategory for i in dash.items)
    unknown = sum(1 for i in dash.items
                  if i.sourceCategory == br.CAT_UNKNOWN_REVIEW_REQUIRED)
    due_n = sum(1 for i in dash.items if i.dueDateCandidate)
    pii_all = all(i.pii_masked for i in dash.items) if dash.items else True
    raw_any = any(i.raw_body_saved for i in dash.items)
    return DashboardSummary(
        total_items=len(dash.items),
        high_count=pri_c.get("HIGH", 0),
        medium_count=pri_c.get("MEDIUM", 0),
        low_count=pri_c.get("LOW", 0),
        unknown_review_count=unknown,
        risk_type_counts=dict(risk_c),
        category_counts=dict(cat_c),
        due_date_candidate_count=due_n,
        pii_masked_all=pii_all,
        raw_body_saved_any=raw_any,
        generated_at=dash.generated_at,
        input_report_hash=dash.input_report_hash,
        high_required_present=_high_required_check(dash.items),
    )


# ── 렌더링 ────────────────────────────────────────────────────────


def render_markdown(dash: Dashboard, summary: DashboardSummary) -> str:
    by_pri: dict[str, list[DashboardItem]] = {"HIGH": [], "MEDIUM": [], "LOW": []}
    unknown_lane: list[DashboardItem] = []
    for it in dash.items:
        if it.sourceCategory == br.CAT_UNKNOWN_REVIEW_REQUIRED:
            unknown_lane.append(it)
        else:
            by_pri.setdefault(it.priority, []).append(it)

    lines = [
        f"# Action Item Dashboard",
        "",
        "## 개요",
        f"- 총 액션: **{summary.total_items}건**",
        f"- HIGH **{summary.high_count}** / MEDIUM {summary.medium_count} "
        f"/ LOW {summary.low_count}",
        f"- UNKNOWN review lane: {summary.unknown_review_count}건",
        f"- dueDate 후보: {summary.due_date_candidate_count}건",
        f"- 생성: {summary.generated_at}",
        f"- 입력 report hash: `{summary.input_report_hash}`",
        f"- HIGH 필수 존재 검증: `{summary.high_required_present}`",
        "",
        "## 안전 정책 준수",
        f"- pii_masked_all: **{summary.pii_masked_all}**",
        f"- raw_body_saved_any: **{summary.raw_body_saved_any}**",
        "- attachment download: 0  external AI call: 0",
        "",
        "## 🚨 HIGH 즉시 조치",
    ]
    for it in by_pri["HIGH"]:
        lines += _render_item(it)
    if not by_pri["HIGH"]:
        lines.append("- (없음)")

    lines += ["", "## 🟡 MEDIUM 검토 필요"]
    for it in by_pri["MEDIUM"][:50]:
        lines += _render_item(it)
    if len(by_pri["MEDIUM"]) > 50:
        lines.append(f"- … ({len(by_pri['MEDIUM']) - 50}건 더)")

    lines += ["", "## 🟢 LOW 검토"]
    for it in by_pri["LOW"][:50]:
        lines += _render_item(it)
    if len(by_pri["LOW"]) > 50:
        lines.append(f"- … ({len(by_pri['LOW']) - 50}건 더)")

    lines += ["", "## ❓ UNKNOWN review lane"]
    for it in unknown_lane[:50]:
        lines += _render_item(it)
    if len(unknown_lane) > 50:
        lines.append(f"- … ({len(unknown_lane) - 50}건 더)")

    lines += ["", "## 리스크 유형별 요약"]
    for k, v in sorted(summary.risk_type_counts.items(),
                       key=lambda x: -x[1]):
        lines.append(f"- {k}: {v}")
    lines += ["", "## 카테고리별 요약"]
    for k, v in sorted(summary.category_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {k}: {v}")
    lines += ["", "## due date 후보 (상위)"]
    due = [i for i in dash.items if i.dueDateCandidate]
    due.sort(key=lambda i: i.dueDateCandidate)
    for it in due[:20]:
        lines.append(
            f"- `{it.actionId}` {it.dueDateCandidate} "
            f"({it.dueDateConfidence}) — {it.title_redacted[:60]}"
        )
    lines += [
        "",
        "## 원문/PII 저장 여부",
        f"- raw_body_saved_any: **{summary.raw_body_saved_any}**",
        f"- pii_masked_all: **{summary.pii_masked_all}**",
        "",
        "> 본 dashboard 는 PII 마스킹된 데이터만 사용합니다. "
        "원문 본문/이메일 local-part 0건.",
    ]
    return "\n".join(lines)


def _render_item(it: DashboardItem) -> list[str]:
    due = ""
    if it.dueDateCandidate:
        due = f" 📅 {it.dueDateCandidate}({it.dueDateConfidence})"
    return [
        f"- `{it.actionId}` [{it.riskType}] **{it.title_redacted[:70]}**{due}  ",
        f"  status: `{it.status}` | priority: {it.priority} | "
        f"발신: {it.sender_domain} | 날짜: {it.received_date[:20]}  ",
        f"  → {it.recommended_action}",
    ]


# ── 입출력 ───────────────────────────────────────────────────────


def load_action_items(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_outputs(dash: Dashboard, summary: DashboardSummary,
                  out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    p1 = out_dir / "action_dashboard.json"
    p1.write_text(json.dumps(dash.to_dict(), ensure_ascii=False, indent=2),
                  encoding="utf-8")
    paths["dashboard"] = p1
    p2 = out_dir / "action_dashboard_summary.json"
    p2.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2),
                  encoding="utf-8")
    paths["summary"] = p2
    p3 = out_dir / "action_dashboard.md"
    p3.write_text(render_markdown(dash, summary), encoding="utf-8")
    paths["md"] = p3
    return paths


# ── PII leak self-check ──────────────────────────────────────────


def find_leaks(text: str) -> dict:
    return br.find_pii_leaks(text)
