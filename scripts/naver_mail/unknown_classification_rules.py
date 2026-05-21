"""UNKNOWN_REVIEW_REQUIRED 재분류 룰 + confidence 정책.

기존 business_report 분류 후 남은 UNKNOWN 항목만 대상으로 재시도.
HIGH/MEDIUM confidence 매칭만 자동 승격, LOW 는 UNKNOWN 유지.

설계:
  - 입력: business_report.action_items (dict 리스트) 중 UNKNOWN
  - 출력: ReclassifyResult (per-item promotion plan)
  - 부작용 없음 (순수 함수). caller 가 결과를 적용 여부 결정.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Iterable

from . import business_report as br


# ── confidence 상수 ────────────────────────────────────────────────

CONF_HIGH = "HIGH"
CONF_MEDIUM = "MEDIUM"
CONF_LOW = "LOW"
ALL_CONFIDENCE = (CONF_HIGH, CONF_MEDIUM, CONF_LOW)


# ── 도메인 신뢰 매핑 (브랜드 → 도메인) ─────────────────────────────

_DOMAIN_BRAND = {
    "kbcard": ("kbcard", "bill.kbcard.com", "kbmail.kbcard.com"),
    "hanacard": ("hanacard.co.kr",),
    "shinhancard": ("shinhancard.com", "mail3.shinhancard.com"),
    "wooribank": ("wooribank.com",),
    "coupang_seller": ("coupang.com",),
    "navercorp_cloud": ("navercorp.com",),
    "google_account": ("accounts.google.com", "google.com"),
    "enclean": ("enclean.com",),
}


def _domain_match(sender_domain: str, brand_key: str) -> bool:
    doms = _DOMAIN_BRAND.get(brand_key, ())
    return any(d in (sender_domain or "").lower() for d in doms)


# ── 룰 정의 ───────────────────────────────────────────────────────
#
# 각 룰: (target_category, confidence, subject_pattern, sender_brand_required_or_None,
#         evidence_marker)
# 우선순위는 리스트 순서. 첫 매칭 채택.

_ENHANCED_RULES = [
    # ── HIGH confidence: 도메인 + 명확한 제목 marker ──
    # 카드/은행 명세서/이용대금 → BILLING
    (br.CAT_BILLING, CONF_HIGH,
     re.compile(r"이용대금명세서|월\s*명세서|체크카드 ?내역서"
                r"|이용대금 ?내역|카드 ?이용\s?내역서", re.IGNORECASE),
     ("kbcard", "hanacard", "shinhancard"),
     "card_statement_high"),
    # 쿠팡 와우 월회비 결제 → BILLING
    (br.CAT_BILLING, CONF_HIGH,
     re.compile(r"와우.{0,4}멤버십.{0,8}월회비|월회비가? ?결제",
                re.IGNORECASE),
     ("coupang_seller",),
     "coupang_wow_membership"),
    # 구독 업데이트 → BILLING
    (br.CAT_BILLING, CONF_HIGH,
     re.compile(r"구독을 ?업데이트|subscription updated", re.IGNORECASE),
     ("google_account",),
     "subscription_update"),
    # 약관 개정/변경 (loosened pattern — 사이에 단어 허용)
    (br.CAT_POLICY_NOTICE, CONF_HIGH,
     re.compile(r"약관.{0,20}(개정|변경)|개정.{0,10}안내"
                r"|기본약관.{0,15}(개정|변경)",
                re.IGNORECASE),
     None,
     "terms_revision"),

    # ── MEDIUM confidence: 도메인 + 키워드 ──
    # 카드 발급/신청 안내
    (br.CAT_ACCOUNT_OR_SERVICE_NOTICE, CONF_MEDIUM,
     re.compile(r"카드 ?신청 ?안내|발급 ?신청|발급 ?안내", re.IGNORECASE),
     ("kbcard",),
     "card_application_notice"),
    # 회원 정보 삭제 예정 / 장기 미사용 정지
    (br.CAT_ACCOUNT_OR_SERVICE_NOTICE, CONF_MEDIUM,
     re.compile(r"회원 ?정보 ?삭제|장기 ?미사용.{0,10}정지"
                r"|데이터 ?보관처리", re.IGNORECASE),
     None,
     "account_inactive_notice"),
    # 본인 인증 완료
    (br.CAT_ACCOUNT_OR_SERVICE_NOTICE, CONF_MEDIUM,
     re.compile(r"본인 ?인증.{0,8}(완료|되었)", re.IGNORECASE),
     None,
     "identity_verification_done"),
    # 우대서비스등급 / VIP 등급 적용
    (br.CAT_ACCOUNT_OR_SERVICE_NOTICE, CONF_MEDIUM,
     re.compile(r"우대 ?서비스 ?등급|등급 ?적용|등급 ?안내",
                re.IGNORECASE),
     ("wooribank",),
     "tier_grade_applied"),
    # 클라우드 정기 점검/출시 안내
    (br.CAT_ACCOUNT_OR_SERVICE_NOTICE, CONF_MEDIUM,
     re.compile(r"정기 ?상품 ?출시|점검 ?안내|cloud product"
                r"|product update", re.IGNORECASE),
     ("navercorp_cloud", "google_account"),
     "cloud_release_notice"),
    # 판매자 기능 안내 (쿠팡 등)
    (br.CAT_ACCOUNT_OR_SERVICE_NOTICE, CONF_MEDIUM,
     re.compile(r"판매자.{0,15}(기능|가이드|업데이트|중요)"
                r"|아이템 ?위너|판매자 ?자동", re.IGNORECASE),
     ("coupang_seller",),
     "seller_feature_notice"),

    # Gemini / Google Play 마케팅
    (br.CAT_PROMO, CONF_MEDIUM,
     re.compile(r"gemini|ai ?메모리|채팅 ?기록을? ?gemini"
                r"|간편한 ?로그인.{0,10}팁|gemini drop"
                r"|google play.{0,15}(앱|게임).{0,15}(출시|확인|준비)"
                r"|생산적인 ?하루", re.IGNORECASE),
     ("google_account",),
     "google_marketing"),
]


# ── 결과 모델 ─────────────────────────────────────────────────────


@dataclass
class ReclassifyDecision:
    actionId: str
    original_category: str
    promoted_category: str = ""
    confidence: str = ""
    evidence_markers: list[str] = field(default_factory=list)
    promoted: bool = False
    kept_unknown: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReclassifyReport:
    previous_unknown_count: int = 0
    new_unknown_count: int = 0
    resolved_unknown_count: int = 0
    unresolved_unknown_count: int = 0
    promoted_by_category: dict = field(default_factory=dict)
    low_confidence_kept_unknown: int = 0
    decisions: list[ReclassifyDecision] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "previous_unknown_count": self.previous_unknown_count,
            "new_unknown_count": self.new_unknown_count,
            "resolved_unknown_count": self.resolved_unknown_count,
            "unresolved_unknown_count": self.unresolved_unknown_count,
            "promoted_by_category": dict(self.promoted_by_category),
            "low_confidence_kept_unknown": self.low_confidence_kept_unknown,
            "decisions": [d.to_dict() for d in self.decisions],
        }


# ── 핵심 로직 ─────────────────────────────────────────────────────


def reclassify_one(action: dict) -> ReclassifyDecision:
    """단일 UNKNOWN action 재분류. promoted=True 이면 적용 가능.

    승격 정책: HIGH/MEDIUM 만 승격, LOW 는 UNKNOWN 유지.
    """
    aid = action.get("actionId", "")
    original = action.get("category", "")
    title = action.get("title_redacted", "")
    sender_domain = action.get("sender_domain", "")

    dec = ReclassifyDecision(actionId=aid, original_category=original)

    if original != br.CAT_UNKNOWN_REVIEW_REQUIRED:
        dec.kept_unknown = False
        dec.confidence = "NONE"
        dec.evidence_markers = ["not_unknown_source"]
        return dec

    for target_cat, conf, pat, brands, marker in _ENHANCED_RULES:
        if not pat.search(title or ""):
            continue
        # 도메인 매칭 — brands None 이면 도메인 무관 룰
        if brands is not None:
            if not any(_domain_match(sender_domain, b) for b in brands):
                continue
        # 룰 매칭 — confidence 정책 적용
        dec.evidence_markers = [
            f"rule:{marker}",
            f"confidence:{conf}",
        ]
        dec.confidence = conf
        if conf in (CONF_HIGH, CONF_MEDIUM):
            dec.promoted_category = target_cat
            dec.promoted = True
            dec.kept_unknown = False
        else:
            # LOW — 승격 안 함
            dec.promoted_category = ""
            dec.promoted = False
            dec.kept_unknown = True
        return dec

    # 어떤 룰도 매칭 안 됨 — UNKNOWN 유지
    dec.kept_unknown = True
    dec.confidence = "NONE"
    dec.evidence_markers = ["no_enhanced_rule_matched"]
    return dec


def reclassify(actions: Iterable[dict]) -> ReclassifyReport:
    actions_list = list(actions)
    unknown_actions = [a for a in actions_list
                       if a.get("category") == br.CAT_UNKNOWN_REVIEW_REQUIRED]
    report = ReclassifyReport(previous_unknown_count=len(unknown_actions))
    promoted_counter: Counter[str] = Counter()
    for a in unknown_actions:
        dec = reclassify_one(a)
        report.decisions.append(dec)
        if dec.promoted:
            promoted_counter[dec.promoted_category] += 1
        elif dec.kept_unknown:
            if dec.confidence == CONF_LOW:
                report.low_confidence_kept_unknown += 1
    report.promoted_by_category = dict(promoted_counter)
    report.resolved_unknown_count = sum(promoted_counter.values())
    report.new_unknown_count = (
        report.previous_unknown_count - report.resolved_unknown_count
    )
    report.unresolved_unknown_count = report.new_unknown_count
    return report


def apply_promotions(actions: list[dict],
                     report: ReclassifyReport) -> list[dict]:
    """ReclassifyReport 결정대로 actions 의 category 를 in-place 업데이트한 새 리스트 반환.

    원본 actions 는 변경하지 않는다.
    """
    aid_to_dec = {d.actionId: d for d in report.decisions}
    out: list[dict] = []
    for a in actions:
        new_a = dict(a)
        dec = aid_to_dec.get(a.get("actionId", ""))
        if dec and dec.promoted and dec.promoted_category:
            new_a["category"] = dec.promoted_category
            # priority 는 기존 LOW 유지 (자동 승격이 우선순위까지 끌어올리지 않음)
            # 기존 evidence_markers + 신규 결합
            new_a["evidence_markers"] = list(
                a.get("evidence_markers", [])
            ) + list(dec.evidence_markers)
        out.append(new_a)
    return out


# ── HIGH 액션 보존 검증 ────────────────────────────────────────────

HIGH_REQUIRED_MARKERS = {
    "smartstore_dormant": ("스마트스토어", "휴면"),
    "coupang_listing_stop": ("쿠팡", "노출", "정지"),
    "fedex_phishing": ("shipping", "documents"),
}


def assert_high_preserved(actions_before: list[dict],
                          actions_after: list[dict]) -> dict[str, bool]:
    """HIGH 액션 3건이 분류 변경 없이 유지되는지 검증."""
    def _has_high_with_keywords(actions, keywords):
        for a in actions:
            if a.get("priority") != "HIGH":
                continue
            t = (a.get("title_redacted") or "").lower()
            if all(k.lower() in t for k in keywords):
                # 추가로 category 가 ATTENTION 또는 SPAM_OR_PHISHING_SUSPECTED 인지
                cat = a.get("category", "")
                if cat in (br.CAT_ATTENTION, br.CAT_SPAM_OR_PHISHING_SUSPECTED):
                    return True
        return False

    out: dict[str, bool] = {}
    for key, kws in HIGH_REQUIRED_MARKERS.items():
        before_ok = _has_high_with_keywords(actions_before, kws)
        after_ok = _has_high_with_keywords(actions_after, kws)
        out[key] = (before_ok == after_ok and after_ok is True)
    return out


# ── 렌더링 ────────────────────────────────────────────────────────


def render_unknown_classification_markdown(
    report: ReclassifyReport,
) -> str:
    lines = [
        "# UNKNOWN 재분류 보고서",
        "",
        f"- previous_unknown_count: **{report.previous_unknown_count}**",
        f"- resolved_unknown_count: **{report.resolved_unknown_count}**",
        f"- new_unknown_count: **{report.new_unknown_count}**",
        f"- low_confidence_kept_unknown: {report.low_confidence_kept_unknown}",
        "",
        "## promoted_by_category",
    ]
    for cat, n in sorted(report.promoted_by_category.items(),
                         key=lambda x: -x[1]):
        lines.append(f"- {cat}: {n}건")
    lines += ["", "## per-item decisions"]
    for d in report.decisions:
        if d.promoted:
            lines.append(
                f"- `{d.actionId}` UNKNOWN → **{d.promoted_category}** "
                f"({d.confidence}) | evidence: {d.evidence_markers}"
            )
        else:
            lines.append(
                f"- `{d.actionId}` UNKNOWN _kept_ "
                f"({d.confidence}) | evidence: {d.evidence_markers}"
            )
    return "\n".join(lines)
