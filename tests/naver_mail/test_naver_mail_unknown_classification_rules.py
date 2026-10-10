"""NAVER-MAIL-UNKNOWN-CLASSIFICATION-RULES-01 — 12+ 테스트."""

from __future__ import annotations

from scripts.naver.mail import (
    business_report as br,
)
from scripts.naver.mail import (
    unknown_classification_rules as ur,
)
from scripts.naver.mail.analysis import audit_naver_mail_unknown_classification_rules as audit


def _mk(action_id, category, title, sender_domain, priority="LOW"):
    return {
        "actionId": action_id,
        "category": category,
        "priority": priority,
        "title_redacted": title,
        "sender_domain": sender_domain,
        "received_date": "05-18",
        "reason": "x",
        "recommended_action": "x",
        "evidence_markers": ["m1"],
        "pii_masked": True,
        "raw_body_saved": False,
    }


def _three_high():
    """HIGH 3건 (변경되면 안 됨)."""
    return [
        {
            "actionId": "high_smart",
            "category": br.CAT_ATTENTION,
            "priority": "HIGH",
            "title_redacted": "[스마트스토어센터] 스마트스토어 판매자 계정이 휴면 상태로 전환될 예정입니다.",
            "sender_domain": "navercorp.com",
            "received_date": "05-03",
            "reason": "r",
            "recommended_action": "a",
            "evidence_markers": [],
            "pii_masked": True,
            "raw_body_saved": False,
        },
        {
            "actionId": "high_coupang",
            "category": br.CAT_ATTENTION,
            "priority": "HIGH",
            "title_redacted": "[쿠팡] 고객센터 문의 답변지연으로 인한 전체 상품 노출 정지 안내",
            "sender_domain": "coupang.com",
            "received_date": "05-18",
            "reason": "r",
            "recommended_action": "a",
            "evidence_markers": [],
            "pii_masked": True,
            "raw_body_saved": False,
        },
        {
            "actionId": "high_fedex",
            "category": br.CAT_SPAM_OR_PHISHING_SUSPECTED,
            "priority": "HIGH",
            "title_redacted": "Re: Shipping Documents",
            "sender_domain": "global-gu.com",
            "received_date": "04-17",
            "reason": "r",
            "recommended_action": "a",
            "evidence_markers": [],
            "pii_masked": True,
            "raw_body_saved": False,
        },
    ]


# ── 1) UNKNOWN 20건 입력 감지 ──────────────────────────────────────


def test_reclassify_only_unknown_actions():
    actions = _three_high() + [  # noqa: RUF005
        _mk(
            "u1",
            br.CAT_UNKNOWN_REVIEW_REQUIRED,
            "[하나카드]신*우님의 2026년05월20일 이용대금명세서입니다.",
            "hanacard.co.kr",
        ),
    ]
    rep = ur.reclassify(actions)
    assert rep.previous_unknown_count == 1
    assert rep.resolved_unknown_count == 1


# ── 2) 카드 명세서 / 와우 멤버십 / 구독 ─────────────────────────────


def test_promote_hana_card_statement_to_billing():
    a = _mk(
        "u1",
        br.CAT_UNKNOWN_REVIEW_REQUIRED,
        "[하나카드]신*우님의 2026년05월20일 이용대금명세서입니다.",
        "hanacard.co.kr",
    )
    d = ur.reclassify_one(a)
    assert d.promoted is True
    assert d.promoted_category == br.CAT_BILLING
    assert d.confidence == ur.CONF_HIGH


def test_promote_kb_check_card_statement():
    a = _mk(
        "u1", br.CAT_UNKNOWN_REVIEW_REQUIRED, "(KB국민카드) 신*우님 2026년04월 KB국민체크카드 내역서", "bill.kbcard.com"
    )
    d = ur.reclassify_one(a)
    assert d.promoted is True
    assert d.promoted_category == br.CAT_BILLING


def test_promote_coupang_wow_membership():
    a = _mk("u1", br.CAT_UNKNOWN_REVIEW_REQUIRED, "[쿠팡] 신*우님, 와우 멤버십 월회비가 결제되었습니다.", "coupang.com")
    d = ur.reclassify_one(a)
    assert d.promoted is True
    assert d.promoted_category == br.CAT_BILLING
    assert d.confidence == ur.CONF_HIGH


def test_promote_subscription_update_to_billing():
    a = _mk("u1", br.CAT_UNKNOWN_REVIEW_REQUIRED, "OpenAI OpCo, LLC 구독을 업데이트했습니다.", "google.com")
    d = ur.reclassify_one(a)
    assert d.promoted is True
    assert d.promoted_category == br.CAT_BILLING


# ── 3) 약관 개정 (loosened pattern) ────────────────────────────────


def test_promote_kb_terms_revision():
    a = _mk(
        "u1",
        br.CAT_UNKNOWN_REVIEW_REQUIRED,
        "(KB국민카드, 기타안내) 표준 전자금융거래 기본약관 외 약관 1종 개정 안내",
        "kbmail.kbcard.com",
    )
    d = ur.reclassify_one(a)
    assert d.promoted is True
    assert d.promoted_category == br.CAT_POLICY_NOTICE


# ── 4) ACCOUNT_OR_SERVICE_NOTICE 그룹 ─────────────────────────────


def test_promote_kb_card_application_notice():
    a = _mk(
        "u1", br.CAT_UNKNOWN_REVIEW_REQUIRED, "(KB국민카드) KB국민카드 발급 신청에 대한 발급 안내", "kbmail.kbcard.com"
    )
    d = ur.reclassify_one(a)
    assert d.promoted is True
    assert d.promoted_category == br.CAT_ACCOUNT_OR_SERVICE_NOTICE


def test_promote_account_inactive_notice():
    a = _mk("u1", br.CAT_UNKNOWN_REVIEW_REQUIRED, "[엔크린] 회원 정보 삭제 예정 사전 안내", "enclean.com")
    d = ur.reclassify_one(a)
    assert d.promoted is True
    assert d.promoted_category == br.CAT_ACCOUNT_OR_SERVICE_NOTICE


def test_promote_google_data_retention_notice():
    a = _mk("u1", br.CAT_UNKNOWN_REVIEW_REQUIRED, "Google 데이터 보관처리 요청됨", "accounts.google.com")
    d = ur.reclassify_one(a)
    assert d.promoted is True


def test_promote_naver_cloud_release_notice():
    a = _mk(
        "u1",
        br.CAT_UNKNOWN_REVIEW_REQUIRED,
        "[네이버 클라우드 플랫폼] 4월 정기 상품 출시 및 점검 안내(2026.4.23)",
        "navercorp.com",
    )
    d = ur.reclassify_one(a)
    assert d.promoted is True


def test_promote_coupang_seller_feature_notice():
    a = _mk(
        "u1",
        br.CAT_UNKNOWN_REVIEW_REQUIRED,
        "[쿠팡] (중요 업데이트) 판매자 자동 가격 조정 기능으로 아이템 위너를 더 쉽게 확보하세요",
        "coupang.com",
    )
    d = ur.reclassify_one(a)
    assert d.promoted is True
    assert d.promoted_category == br.CAT_ACCOUNT_OR_SERVICE_NOTICE


# ── 5) PROMO: Gemini / Google Play 마케팅 ──────────────────────────


def test_promote_gemini_marketing_to_promo():
    a = _mk("u1", br.CAT_UNKNOWN_REVIEW_REQUIRED, "재우님, AI 메모리와 채팅 기록을 Gemini로 가져오세요", "google.com")
    d = ur.reclassify_one(a)
    assert d.promoted is True
    assert d.promoted_category == br.CAT_PROMO


def test_promote_google_play_marketing():
    a = _mk(
        "u1",
        br.CAT_UNKNOWN_REVIEW_REQUIRED,
        "신재우님, Google Play에서 앱 또는 게임을 자신 있게 출시하세요",
        "google.com",
    )
    d = ur.reclassify_one(a)
    assert d.promoted is True
    assert d.promoted_category == br.CAT_PROMO


# ── 6) LOW confidence 는 UNKNOWN 유지 (overclassification 방지) ────


def test_no_promotion_when_no_rule_matches():
    a = _mk("u1", br.CAT_UNKNOWN_REVIEW_REQUIRED, "완전히 새로운 임의 제목 — 어떤 키워드도 없는", "unknown.example")
    d = ur.reclassify_one(a)
    assert d.promoted is False
    assert d.kept_unknown is True


def test_no_promotion_when_domain_mismatch():
    """카드 명세서 키워드 + 카드 도메인이 아닌 경우 → 매칭 안 됨."""
    a = _mk(
        "u1",
        br.CAT_UNKNOWN_REVIEW_REQUIRED,
        "이용대금명세서",  # 카드 도메인 아님
        "unknown.example",
    )
    d = ur.reclassify_one(a)
    # 도메인 매칭 실패 — 룰 미적용 → kept
    assert d.promoted is False
    assert d.kept_unknown is True


# ── 7) HIGH 3건 보존 ──────────────────────────────────────────────


def test_high_actions_preserved_after_reclassify():
    before = _three_high() + [  # noqa: RUF005
        _mk("u1", br.CAT_UNKNOWN_REVIEW_REQUIRED, "[하나카드] 이용대금명세서", "hanacard.co.kr"),
    ]
    rep = ur.reclassify(before)
    after = ur.apply_promotions(before, rep)
    preserved = ur.assert_high_preserved(before, after)
    assert preserved["smartstore_dormant"] is True
    assert preserved["coupang_listing_stop"] is True
    assert preserved["fedex_phishing"] is True


def test_audit_fail_high_action_changed():
    before = _three_high()
    # after 에서 쿠팡 HIGH 가 사라지면 FAIL
    after = [a for a in before if "쿠팡" not in a["title_redacted"]]
    rep = ur.ReclassifyReport(previous_unknown_count=0)
    v = audit.judge_rules(rep, actions_before=before, actions_after=after)
    assert v.code == "FAIL_HIGH_ACTION_CHANGED"


# ── 8) apply_promotions 정확성 ────────────────────────────────────


def test_apply_promotions_updates_category_only():
    actions = [_mk("u1", br.CAT_UNKNOWN_REVIEW_REQUIRED, "[하나카드] 이용대금명세서", "hanacard.co.kr")]
    rep = ur.reclassify(actions)
    new = ur.apply_promotions(actions, rep)
    assert new[0]["category"] == br.CAT_BILLING
    # priority 변경 안 됨 (LOW 유지)
    assert new[0]["priority"] == actions[0]["priority"]
    # original action 은 변경 안 됨
    assert actions[0]["category"] == br.CAT_UNKNOWN_REVIEW_REQUIRED


# ── 9) evidence_markers ──────────────────────────────────────────


def test_evidence_markers_present():
    a = _mk("u1", br.CAT_UNKNOWN_REVIEW_REQUIRED, "[하나카드] 이용대금명세서", "hanacard.co.kr")
    d = ur.reclassify_one(a)
    assert len(d.evidence_markers) >= 1
    assert any("rule:" in m for m in d.evidence_markers)
    assert any("confidence:" in m for m in d.evidence_markers)


# ── 10) raw body / PII / external AI 금지 ─────────────────────────


def test_audit_fail_raw_body_leak():
    rep = ur.ReclassifyReport(previous_unknown_count=1)
    v = audit.judge_rules(rep, raw_body_saved=True)
    assert v.code == "FAIL_RAW_BODY_LEAK"


def test_audit_fail_pii_unmasked():
    rep = ur.ReclassifyReport(previous_unknown_count=0)
    v = audit.judge_rules(rep, md_text="raw user@example.com leaked")
    assert v.code == "FAIL_PII_UNMASKED"


def test_audit_fail_external_ai_call():
    rep = ur.ReclassifyReport(previous_unknown_count=0)
    v = audit.judge_rules(rep, network_log=["POST https://api.anthropic.com/v1"])
    assert v.code == "FAIL_EXTERNAL_AI_CALL_USED"


def test_audit_fail_attachment_download():
    rep = ur.ReclassifyReport(previous_unknown_count=0)
    v = audit.judge_rules(rep, attachment_download_count=2)
    assert v.code == "FAIL_ATTACHMENT_DOWNLOADED"


# ── 11) overclassification 방지 ──────────────────────────────────


def test_audit_fail_overclassified_low_confidence():
    rep = ur.ReclassifyReport(previous_unknown_count=1)
    # LOW confidence 인데 promoted=True 강제 주입
    rep.decisions.append(
        ur.ReclassifyDecision(
            actionId="x",
            original_category=br.CAT_UNKNOWN_REVIEW_REQUIRED,
            promoted_category=br.CAT_PROMO,
            confidence=ur.CONF_LOW,
            promoted=True,
            kept_unknown=False,
        )
    )
    v = audit.judge_rules(rep)
    assert v.code == "FAIL_OVERCLASSIFIED_LOW_CONFIDENCE"


# ── 12) audit PASS / WARN ────────────────────────────────────────


def test_audit_pass_when_clean():
    # UNKNOWN 0 + 위반 0 → PASS
    rep = ur.ReclassifyReport(
        previous_unknown_count=5,
        resolved_unknown_count=5,
        new_unknown_count=0,
    )
    v = audit.judge_rules(rep)
    assert v.code == "PASS_NAVER_MAIL_UNKNOWN_CLASSIFICATION_RULES", v.reasons


def test_audit_warn_unknown_items_remain():
    rep = ur.ReclassifyReport(
        previous_unknown_count=5,
        resolved_unknown_count=2,
        new_unknown_count=3,
    )
    v = audit.judge_rules(rep)
    assert v.code == "WARN_UNKNOWN_ITEMS_REMAIN"


def test_audit_warn_low_confidence_kept():
    rep = ur.ReclassifyReport(
        previous_unknown_count=5,
        resolved_unknown_count=2,
        new_unknown_count=3,
        low_confidence_kept_unknown=2,
    )
    v = audit.judge_rules(rep)
    assert v.code == "WARN_LOW_CONFIDENCE_ITEMS_KEPT"


# ── 13) 회귀 가드 ───────────────────────────────────────────────


def test_regression_action_dashboard_imports():
    from scripts.naver.mail import action_item_dashboard as aid

    assert hasattr(aid, "build_dashboard")


def test_regression_business_report_imports():
    from scripts.naver.mail import business_report as br

    assert hasattr(br, "build_report")
