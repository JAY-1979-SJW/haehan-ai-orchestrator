"""메일함 비즈니스 보고서 — 정식 모듈.

입력: PII-마스킹된 메일 메타데이터 (subject_masked / sender_masked /
       date_text / body_redacted_short / link_domains / has_attach /
       folder_name / sn / pii_types).
출력: BusinessReport (categories, action_items, summary, markdown, json).

규칙:
  - 외부 AI/HTTP 호출 0 (로컬 키워드 + 도메인 신뢰 룰)
  - raw body / 원본 이메일 local-part 출력 금지 — input 이 이미 마스킹된 상태
  - 보고서 직렬화 후 자기검증 (assert_no_raw_pii)
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
SCHEMA_VERSION = "1.0"


# ── 카테고리 / 우선순위 ─────────────────────────────────────────────

CAT_ATTENTION = "ATTENTION"
CAT_REVIEW = "REVIEW"
CAT_SECURITY_NOTICE = "SECURITY_NOTICE"
CAT_BILLING = "BILLING"
CAT_POLICY_NOTICE = "POLICY_NOTICE"
CAT_PROMO = "PROMO"
CAT_SPAM_OR_PHISHING_SUSPECTED = "SPAM_OR_PHISHING_SUSPECTED"
CAT_DELIVERY_FAILURE = "DELIVERY_FAILURE"
CAT_ACCOUNT_OR_SERVICE_NOTICE = "ACCOUNT_OR_SERVICE_NOTICE"
CAT_LOW_PRIORITY = "LOW_PRIORITY"
CAT_UNKNOWN_REVIEW_REQUIRED = "UNKNOWN_REVIEW_REQUIRED"

ALL_CATEGORIES = (
    CAT_ATTENTION,
    CAT_REVIEW,
    CAT_SECURITY_NOTICE,
    CAT_BILLING,
    CAT_POLICY_NOTICE,
    CAT_PROMO,
    CAT_SPAM_OR_PHISHING_SUSPECTED,
    CAT_DELIVERY_FAILURE,
    CAT_ACCOUNT_OR_SERVICE_NOTICE,
    CAT_LOW_PRIORITY,
    CAT_UNKNOWN_REVIEW_REQUIRED,
)

PRIORITY_HIGH = "HIGH"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_LOW = "LOW"

# 카테고리 → 기본 우선순위 (개별 룰에서 override 가능)
_DEFAULT_PRIORITY_BY_CATEGORY = {
    CAT_ATTENTION: PRIORITY_HIGH,
    CAT_SPAM_OR_PHISHING_SUSPECTED: PRIORITY_HIGH,
    CAT_DELIVERY_FAILURE: PRIORITY_MEDIUM,
    CAT_REVIEW: PRIORITY_MEDIUM,
    CAT_SECURITY_NOTICE: PRIORITY_MEDIUM,
    CAT_POLICY_NOTICE: PRIORITY_MEDIUM,
    CAT_BILLING: PRIORITY_LOW,
    CAT_ACCOUNT_OR_SERVICE_NOTICE: PRIORITY_LOW,
    CAT_PROMO: PRIORITY_LOW,
    CAT_LOW_PRIORITY: PRIORITY_LOW,
    CAT_UNKNOWN_REVIEW_REQUIRED: PRIORITY_LOW,
}


# ── 추천 액션 ───────────────────────────────────────────────────────

_RECOMMENDED_ACTION_BY_CATEGORY = {
    CAT_ATTENTION: "즉시 본문 확인 + 운영 조치 (노출정지/휴면 해제 등)",
    CAT_SPAM_OR_PHISHING_SUSPECTED: "삭제 권장 — 발신 도메인 사칭 의심. 링크 클릭 금지",
    CAT_DELIVERY_FAILURE: "원본 메일 재발송 여부 확인 + 수신자 주소 정정",
    CAT_REVIEW: "관리 콘솔에서 사유 확인 + 사이트/계정 정상화",
    CAT_SECURITY_NOTICE: "본인 로그인/디바이스 일치 여부 확인. 미일치 시 비밀번호 변경",
    CAT_BILLING: "결제 내역 검토 + 부정 사용 없는지 확인",
    CAT_POLICY_NOTICE: "약관 변경 사항 확인 (영향도 평가)",
    CAT_PROMO: "관심 항목만 확인 후 일괄 정리",
    CAT_ACCOUNT_OR_SERVICE_NOTICE: "계정/서비스 상태 확인",
    CAT_LOW_PRIORITY: "확인 후 일괄 읽음 처리",
    CAT_UNKNOWN_REVIEW_REQUIRED: "수동 확인 — 분류 규칙 보강 필요",
}


# ── 도메인 신뢰 / 사칭 의심 ────────────────────────────────────────

# 도메인 별로 키워드 매칭이 있어야 정상 — fedex/dhl/ups 등 운송사 사칭 잡기용
_BRAND_DOMAIN_HINTS = {
    "fedex": ("fedex.com",),
    "dhl": ("dhl.com", "dhl.de"),
    "ups": ("ups.com",),
    "ems": ("epost.go.kr",),
    "korpost": ("epost.go.kr", "koreapost.go.kr"),
    "paypal": ("paypal.com",),
    "apple": ("apple.com", "icloud.com"),
    "microsoft": ("microsoft.com", "outlook.com", "live.com"),
}

# 의심 TLD
_SUSPICIOUS_TLD_RE = re.compile(r"\.(tk|gq|ml|ga|cf|top|xyz|click|loan|win|work|fit|rest)$")

# 신뢰 도메인 (사칭 의심 대상에서 제외)
_TRUSTED_DOMAINS = frozenset(
    {
        "fedex.com",
        "dhl.com",
        "ups.com",
        "epost.go.kr",
        "paypal.com",
        "apple.com",
        "icloud.com",
        "microsoft.com",
        "outlook.com",
        "live.com",
        "google.com",
        "accounts.google.com",
        "youtube.com",
        "navercorp.com",
        "naver.com",
        "smartstore.naver.com",
        "kbcard.com",
        "kbmail.kbcard.com",
        "hyundaicard.com",
        "shinhancard.com",
        "lottecardmailcenter.net",
        "hanacard.co.kr",
        "wooribank.com",
        "yes24.com",
        "miricanvas.co.kr",
        "coupang.com",
        "facebookmail.com",
        "mail.instagram.com",
        "nicepg.co.kr",
        "kcp.co.kr",
        "easypay.co.kr",
        "kgfinancial.co.kr",
        "x.com",
        "twitter.com",
        "github.com",
        "blackkiwi.net",
        "golfzon.com",
        "enclean.com",
        "style24.com",
        "emart.com",
        "heatpipe.co.kr",
    }
)


def _domain_of(sender_masked: str) -> str:
    m = re.search(r"@([A-Za-z0-9.\-]+)", sender_masked or "")
    return m.group(1).lower() if m else ""


_SHIPPING_KEYWORD_RE = re.compile(
    r"shipping\s+documents|delivery\s+confirmation|tracking\s+number"
    r"|package\s+delivery|customs\s+clearance"
    r"|배송\s*조회|운송장\s*번호|통관",
    re.IGNORECASE,
)


def _is_phishing_suspect(subject: str, sender_masked: str, link_domains: dict) -> tuple[bool, list[str]]:
    """발신 도메인 + 제목 키워드로 사칭 의심 판정."""
    dom = _domain_of(sender_masked)
    markers: list[str] = []
    if dom and dom not in _TRUSTED_DOMAINS:
        subj_low = (subject or "").lower()
        # 1) 운송사/결제 브랜드 키워드 + untrusted 도메인
        for brand, trusted in _BRAND_DOMAIN_HINTS.items():
            if brand in subj_low and not any(t in dom for t in trusted):
                markers.append(f"brand_keyword_in_subject_but_untrusted_domain:{brand}~{dom}")
        # 2) 운송 키워드 (shipping documents 등) + untrusted 도메인
        if _SHIPPING_KEYWORD_RE.search(subject or "") and not any(t in dom for t in ("fedex", "dhl", "ups", "epost")):
            markers.append(f"shipping_keyword_untrusted_domain:{dom}")
        # 3) 의심 TLD
        if _SUSPICIOUS_TLD_RE.search(dom):
            markers.append(f"suspicious_tld:{dom}")
    return (bool(markers), markers)


# ── 분류 규칙 ───────────────────────────────────────────────────────

# (카테고리, 키워드 정규식, 매칭 영역) — 영역: 'subject' | 'sender' | 'both'
_RULES = [
    # 1) DELIVERY_FAILURE
    (
        CAT_DELIVERY_FAILURE,
        re.compile(
            r"undelivered|returned to sender|mail delivery system"
            r"|반송|전달 실패|배달 실패",
            re.IGNORECASE,
        ),
        "both",
    ),
    # 2) ATTENTION — 노출 정지, 휴면, 답변 지연, 확약서
    (
        CAT_ATTENTION,
        re.compile(
            r"노출 ?정지|미답변|답변지연|확약서|휴면 ?상태로 ?전환"
            r"|계정 ?정지|복원\s*요청|상품 ?노출 ?재개"
        ),
        "subject",
    ),
    # 3) REVIEW — 색인 / 오류 / 권장 조치
    (
        CAT_REVIEW,
        re.compile(
            r"색인이 ?생성되지 ?않습니다|indexing|크롤링 오류"
            r"|조치 ?권장|검토 ?필요|수동 ?조치"
        ),
        "subject",
    ),
    # 4) SECURITY_NOTICE
    (
        CAT_SECURITY_NOTICE,
        re.compile(
            r"보안 ?알림|중요 ?보안 ?알림"
            r"|새로운 ?(환경|기기|위치)에서 ?로그인"
            r"|알림 ?없이 ?로그인|새로운 ?기기로 ?로그인"
            r"|간편 ?로그인 ?계정"
            r"|security alert|new or unusual.*login"
            r"|비밀번호 ?변경|2단계 ?인증"
            r"|로그인 ?기능이 ?해제",
            re.IGNORECASE,
        ),
        "subject",
    ),
    # 5) BILLING
    (
        CAT_BILLING,
        re.compile(
            r"결제 ?내역|영수증|매출실적|포인트리"
            r"|리볼빙|마일리지|payment|invoice"
            r"|쿠팡.{0,8}결제|배송달력|출고일 ?자동 ?조정"
            r"|google play.{0,8}주문|google play.{0,8}영수증"
            r"|kcp|nicepg|easypay|kgfinancial",
            re.IGNORECASE,
        ),
        "both",
    ),
    # 6) POLICY_NOTICE
    (
        CAT_POLICY_NOTICE,
        re.compile(
            r"약관 ?개정|이용약관|처리방침"
            r"|수수료율 ?변경|할부수수료율|개인정보 ?처리방침"
            r"|약관 ?변경"
        ),
        "subject",
    ),
    # 7) ACCOUNT_OR_SERVICE_NOTICE — 휴면/탈퇴/서비스 종료
    (
        CAT_ACCOUNT_OR_SERVICE_NOTICE,
        re.compile(
            r"서비스 ?종료|회원정보 ?삭제|휴면 ?정책"
            r"|회원 ?탈퇴|계정 ?등록|본인 ?인증 ?완료"
            r"|개인정보 ?이용내역|개인정보 ?수집"
            r"|개인정보 ?이용제공|등록되었습니다"
        ),
        "subject",
    ),
    # 8) LOW_PRIORITY 먼저 — Instagram/FB/Google Play 자동 추천 (PROMO 패턴이 광범위해 LOW를 가림)
    (
        CAT_LOW_PRIORITY,
        re.compile(
            r"instagram\.com|facebookmail"
            r"|google play.{0,10}추천|pc에서.{0,10}플레이"
            r"|새로 ?올라온 ?소식|🎮",
            re.IGNORECASE,
        ),
        "both",
    ),
    # 9) PROMO — 광고/이벤트/할인
    (
        CAT_PROMO,
        re.compile(
            r"이벤트|할인|쿠폰|프로모션|newsletter|뉴스레터"
            r"|특가|혜택|소식을 확인|업데이트를 전해드립니다"
            r"|월간 ?업데이트|drop의 ?새로운 ?소식"
            r"|출시할 ?준비|출시 ?여정|정책을 ?준비"
            r"|ai ?인사이트|product update|cloud product",
            re.IGNORECASE,
        ),
        "both",
    ),
]


@dataclass
class MailItem:
    """보고서 입력 — 모두 PII 마스킹된 데이터."""

    sn: str
    folder_name: str
    subject_masked: str
    sender_masked: str
    date_text: str = ""
    body_redacted_short: str = ""
    link_domains: dict = field(default_factory=dict)
    has_attach: bool = False
    pii_detected_count: int = 0


@dataclass
class ActionItem:
    actionId: str
    category: str
    priority: str
    title_redacted: str
    sender_domain: str
    received_date: str
    reason: str
    recommended_action: str
    evidence_markers: list[str]
    pii_masked: bool = True
    raw_body_saved: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CategoryGroup:
    category: str
    count: int
    items: list[dict] = field(default_factory=list)


@dataclass
class BusinessReport:
    schema_version: str = SCHEMA_VERSION
    run_id: str = ""
    generated_at_iso: str = ""
    total_mails: int = 0
    folder_distribution: dict = field(default_factory=dict)
    sender_domain_top: list[tuple[str, int]] = field(default_factory=list)
    categories: list[CategoryGroup] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    pii_detected_total: int = 0
    pii_types_summary: dict = field(default_factory=dict)
    raw_body_saved: bool = False
    attachment_download_count: int = 0
    external_ai_call_count: int = 0
    unread_restore_summary: dict = field(default_factory=dict)
    leak_self_check: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        # sender_domain_top tuple → list
        d["sender_domain_top"] = [list(t) for t in self.sender_domain_top]
        return d


# ── 분류 ────────────────────────────────────────────────────────────


def classify_mail(item: MailItem) -> tuple[str, str, list[str]]:
    """단일 메일 분류. returns (category, priority, evidence_markers)."""
    subj = item.subject_masked or ""
    sender = item.sender_masked or ""
    # 1) 피싱/사칭 최우선
    is_phish, ph_markers = _is_phishing_suspect(subj, sender, item.link_domains)
    if is_phish:
        return (CAT_SPAM_OR_PHISHING_SUSPECTED, PRIORITY_HIGH, ph_markers)

    # 2) 룰 순회 (첫 매칭 채택)
    for cat, pat, scope in _RULES:
        target = ""
        if scope == "subject":
            target = subj
        elif scope == "sender":
            target = sender
        else:
            target = subj + " " + sender
        m = pat.search(target)
        if m:
            return (cat, _DEFAULT_PRIORITY_BY_CATEGORY.get(cat, PRIORITY_LOW), [f"rule:{cat}:{m.group(0)[:40]}"])

    # 3) 미분류
    return (CAT_UNKNOWN_REVIEW_REQUIRED, PRIORITY_LOW, ["no_rule_matched"])


def _make_action_id(sn: str, category: str) -> str:
    h = hashlib.sha1(f"{sn}|{category}".encode()).hexdigest()[:10]
    return f"act_{h}"


def to_action_item(item: MailItem, *, category: str, priority: str, evidence: list[str]) -> ActionItem:
    return ActionItem(
        actionId=_make_action_id(item.sn, category),
        category=category,
        priority=priority,
        title_redacted=(item.subject_masked or "")[:200],
        sender_domain=_domain_of(item.sender_masked),
        received_date=item.date_text or "",
        reason="; ".join(evidence)[:200],
        recommended_action=_RECOMMENDED_ACTION_BY_CATEGORY.get(category, "수동 확인 필요"),
        evidence_markers=evidence,
        pii_masked=True,
        raw_body_saved=False,
    )


# ── 보고서 빌드 ────────────────────────────────────────────────────


def build_report(
    mails: Iterable[MailItem],
    *,
    run_id: str = "",
    unread_restore_summary: dict | None = None,
    attachment_download_count: int = 0,
    external_ai_call_count: int = 0,
    pii_detected_total: int = 0,
    pii_types_summary: dict | None = None,
) -> BusinessReport:
    items = list(mails)
    rep = BusinessReport(
        run_id=run_id,
        generated_at_iso=datetime.now(KST).replace(microsecond=0).isoformat(),
        total_mails=len(items),
        attachment_download_count=attachment_download_count,
        external_ai_call_count=external_ai_call_count,
        pii_detected_total=pii_detected_total,
        pii_types_summary=dict(pii_types_summary or {}),
        unread_restore_summary=dict(unread_restore_summary or {}),
    )

    # 폴더 / 도메인 분포
    folder_c = Counter(it.folder_name for it in items)
    rep.folder_distribution = dict(folder_c)
    dom_c = Counter(_domain_of(it.sender_masked) for it in items if _domain_of(it.sender_masked))
    rep.sender_domain_top = dom_c.most_common(15)

    # 분류
    grouped: dict[str, list[MailItem]] = defaultdict(list)
    classification_meta: list[tuple[MailItem, str, str, list[str]]] = []
    for it in items:
        cat, pri, ev = classify_mail(it)
        grouped[cat].append(it)
        classification_meta.append((it, cat, pri, ev))

    # categories — spec 순서대로
    for cat in ALL_CATEGORIES:
        lst = grouped.get(cat, [])
        cg = CategoryGroup(
            category=cat,
            count=len(lst),
            items=[
                {
                    "sn": it.sn,
                    "subject": it.subject_masked,
                    "sender": it.sender_masked,
                    "date": it.date_text,
                    "folder": it.folder_name,
                    "has_attach": it.has_attach,
                    "pii_n": it.pii_detected_count,
                }
                for it in lst[:50]  # 카테고리당 최대 50건
            ],
        )
        rep.categories.append(cg)

    # action items — HIGH/MEDIUM 모두 + UNKNOWN_REVIEW_REQUIRED 일부
    actions: list[ActionItem] = []
    for it, cat, pri, ev in classification_meta:
        if pri == PRIORITY_LOW and cat not in (
            CAT_UNKNOWN_REVIEW_REQUIRED,
            CAT_DELIVERY_FAILURE,
            CAT_SPAM_OR_PHISHING_SUSPECTED,
        ):
            continue
        actions.append(to_action_item(it, category=cat, priority=pri, evidence=ev))
    # 우선순위 정렬
    pri_order = {PRIORITY_HIGH: 0, PRIORITY_MEDIUM: 1, PRIORITY_LOW: 2}
    actions.sort(key=lambda a: (pri_order.get(a.priority, 9), a.category, a.received_date))
    rep.action_items = actions

    # leak self-check 는 caller 에서 추가 (renderer 호출 후)
    return rep


# ── 렌더링 ────────────────────────────────────────────────────────


def render_markdown(rep: BusinessReport) -> str:
    lines = [
        f"# 메일함 비즈니스 보고서 (closeout) — run `{rep.run_id}`",
        "",
        "## 개요",
        f"- 총 메일 수: **{rep.total_mails}건**",
        f"- 생성 시각: {rep.generated_at_iso}",
        f"- 액션 아이템: {len(rep.action_items)}건",
        "",
        "## 안전 정책 준수 결과",
        f"- raw body 저장: **{rep.raw_body_saved}**",
        f"- attachment download: **{rep.attachment_download_count}**",
        f"- external AI call: **{rep.external_ai_call_count}**",
        f"- PII 검출: {rep.pii_detected_total} (types: `{rep.pii_types_summary}`)",
        f"- unread 복구: `{rep.unread_restore_summary}`",
        "",
        "## 폴더별 분포",
    ]
    for f, n in sorted(rep.folder_distribution.items(), key=lambda x: -x[1]):
        lines.append(f"- {f}: {n}건")
    lines += ["", "## 발신자 도메인 TOP 15"]
    for dom, n in rep.sender_domain_top:
        lines.append(f"- `{dom}` — {n}건")

    # 카테고리별 섹션 (spec 명시 순서)
    SECTION_ORDER = [
        (CAT_ATTENTION, "🚨 긴급 액션 (ATTENTION)"),
        (CAT_REVIEW, "🔴 검토 필요 (REVIEW)"),
        (CAT_SPAM_OR_PHISHING_SUSPECTED, "⚠️ 피싱/스팸 의심"),
        (CAT_DELIVERY_FAILURE, "📭 전송 실패"),
        (CAT_SECURITY_NOTICE, "🛡 보안 알림"),
        (CAT_BILLING, "💳 결제/청구"),
        (CAT_POLICY_NOTICE, "📜 약관/정책"),
        (CAT_ACCOUNT_OR_SERVICE_NOTICE, "👤 계정/서비스 안내"),
        (CAT_PROMO, "📢 홍보/마케팅"),
        (CAT_LOW_PRIORITY, "📥 자동 알림 (낮은 우선순위)"),
        (CAT_UNKNOWN_REVIEW_REQUIRED, "❓ 미분류/검토 필요"),
    ]
    cat_by_name = {cg.category: cg for cg in rep.categories}
    for cat, header in SECTION_ORDER:
        cg = cat_by_name.get(cat)
        if not cg or not cg.count:
            continue
        lines += ["", f"## {header} — {cg.count}건"]
        for it in cg.items[:20]:
            mark = " 📎" if it.get("has_attach") else ""
            pii = f" pii={it['pii_n']}" if it.get("pii_n") else ""
            lines.append(
                f"- **{it['subject'][:80]}**{mark}{pii}  \n"
                f"  발신: {it['sender'][:60]}  |  날짜: {it['date'][:20]}  "
                f"|  폴더: {it['folder']}"
            )
        if cg.count > 20:
            lines.append(f"- … ({cg.count - 20}건 더)")

    # Action items
    lines += ["", "## 액션 아이템", ""]
    pri_groups: dict[str, list[ActionItem]] = defaultdict(list)
    for a in rep.action_items:
        pri_groups[a.priority].append(a)
    for pri in (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW):
        lst = pri_groups.get(pri, [])
        if not lst:
            continue
        lines += [f"### [{pri}] {len(lst)}건"]
        for a in lst[:30]:
            lines.append(
                f"- `{a.actionId}` [{a.category}] {a.title_redacted[:60]}  \n"
                f"  발신: {a.sender_domain}  날짜: {a.received_date[:20]}  \n"
                f"  → {a.recommended_action}"
            )
        if len(lst) > 30:
            lines.append(f"- … ({len(lst) - 30}건 더)")

    lines += [
        "",
        "## 원문/PII 저장 여부",
        f"- raw_body_saved: **{rep.raw_body_saved}**",
        f"- PII unmasked leak self-check: `{rep.leak_self_check}`",
    ]
    return "\n".join(lines)


def render_json(rep: BusinessReport) -> dict:
    return rep.to_dict()


# ── 자기검증 (PII leak) ─────────────────────────────────────────────


_RAW_EMAIL_RE = re.compile(r"\b[A-Za-z0-9_.+\-]{3,}@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_RAW_PHONE_RE = re.compile(r"\b01[016789]-\d{3,4}-\d{4}\b")
_RAW_RRN_RE = re.compile(r"\b\d{6}-[1-4]\d{6}\b")
_RAW_CARD_4x4_RE = re.compile(r"\b\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{4}\b")


def find_pii_leaks(text: str) -> dict:
    """렌더된 문서 안의 미마스킹 PII 패턴 검출."""
    return {
        "raw_emails": _RAW_EMAIL_RE.findall(text),
        "raw_phones": _RAW_PHONE_RE.findall(text),
        "raw_rrn": _RAW_RRN_RE.findall(text),
        "raw_card_4x4": _RAW_CARD_4x4_RE.findall(text),
    }


def attach_leak_check(rep: BusinessReport, *, md_text: str, json_text: str) -> BusinessReport:
    md_leaks = find_pii_leaks(md_text)
    json_leaks = find_pii_leaks(json_text)
    rep.leak_self_check = {
        "md": {k: len(v) for k, v in md_leaks.items()},
        "json": {k: len(v) for k, v in json_leaks.items()},
        "total_leak_count": (sum(len(v) for v in md_leaks.values()) + sum(len(v) for v in json_leaks.values())),
    }
    return rep
