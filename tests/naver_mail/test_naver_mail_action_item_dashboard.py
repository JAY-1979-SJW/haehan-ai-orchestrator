"""NAVER-MAIL-ACTION-ITEM-DASHBOARD-01 — 필수 12+ 테스트."""

from __future__ import annotations

import json

from scripts.naver.mail import action_item_dashboard as aid
from scripts.naver.mail import business_report as br
from scripts.naver.mail.analysis import audit_naver_mail_action_item_dashboard as audit

# ── 입력 헬퍼 ───────────────────────────────────────────────────────


def _action(cat, pri, title, sender="x.com", date="05-18", action_id=""):
    return {
        "actionId": action_id or f"act_{abs(hash(title)) % 1_000_000}",
        "category": cat,
        "priority": pri,
        "title_redacted": title,
        "sender_domain": sender,
        "received_date": date,
        "reason": "rule_matched",
        "recommended_action": "조치",
        "evidence_markers": ["mark1"],
        "pii_masked": True,
        "raw_body_saved": False,
    }


def _three_high_inputs():
    return [
        _action(
            br.CAT_ATTENTION,
            "HIGH",
            "[스마트스토어센터] 스마트스토어 판매자 계정이 휴면 상태로 전환될 예정입니다.",
            sender="navercorp.com",
            date="05-03",
            action_id="act_smart_dormant",
        ),
        _action(
            br.CAT_ATTENTION,
            "HIGH",
            "[쿠팡] 고객센터 문의 답변지연으로 인한 전체 상품 노출 정지 안내",
            sender="coupang.com",
            date="05-18",
            action_id="act_coupang_stop",
        ),
        _action(
            br.CAT_SPAM_OR_PHISHING_SUSPECTED,
            "HIGH",
            "Re: Shipping Documents",
            sender="global-gu.com",
            date="04-17",
            action_id="act_fedex_phish",
        ),
    ]


# ── 1) dashboard schema ─────────────────────────────────────────────


def test_dashboard_schema_complete():
    actions = _three_high_inputs()
    dash = aid.build_dashboard(actions)
    assert len(dash.items) == 3
    for it in dash.items:
        d = it.to_dict()
        for k in (
            "actionId",
            "sourceCategory",
            "priority",
            "status",
            "title_redacted",
            "sender_domain",
            "received_date",
            "reason",
            "recommended_action",
            "evidence_markers",
            "riskType",
            "dueDateCandidate",
            "pii_masked",
            "raw_body_saved",
        ):
            assert k in d, f"missing: {k}"


def test_dashboard_summary_schema():
    actions = _three_high_inputs()
    dash = aid.build_dashboard(actions)
    s = aid.build_summary(dash)
    d = s.to_dict()
    for k in (
        "total_items",
        "high_count",
        "medium_count",
        "low_count",
        "unknown_review_count",
        "risk_type_counts",
        "category_counts",
        "due_date_candidate_count",
        "pii_masked_all",
        "raw_body_saved_any",
        "generated_at",
        "input_report_hash",
        "high_required_present",
    ):
        assert k in d


# ── 2) HIGH 3건 유지 ────────────────────────────────────────────────


def test_high_three_required_present():
    dash = aid.build_dashboard(_three_high_inputs())
    hr = aid._high_required_check(dash.items)
    assert hr["smartstore_dormant"] is True
    assert hr["coupang_listing_stop"] is True
    assert hr["fedex_phishing"] is True


def test_audit_fail_high_missing():
    # 스마트스토어 빠짐
    actions = [a for a in _three_high_inputs() if "스마트스토어" not in a["title_redacted"]]
    dash = aid.build_dashboard(actions)
    s = aid.build_summary(dash)
    v = audit.judge_dashboard(dash, s)
    assert v.code == "FAIL_HIGH_ACTION_MISSING"


# ── 3) 우선순위 정렬 ────────────────────────────────────────────────


def test_priority_sort_high_first():
    actions = [
        _action(br.CAT_BILLING, "LOW", "결제 내역", action_id="L"),
        _action(br.CAT_ATTENTION, "HIGH", "쿠팡 노출 정지 안내", sender="coupang.com", action_id="H"),
        _action(br.CAT_REVIEW, "MEDIUM", "haehan-ai.kr 색인 오류", action_id="M"),
    ]
    dash = aid.build_dashboard(actions)
    priorities = [i.priority for i in dash.items]
    assert priorities[0] == "HIGH"
    # MEDIUM 이 LOW 보다 먼저
    assert priorities.index("MEDIUM") < priorities.index("LOW")


# ── 4) status 기본값 NEW ───────────────────────────────────────────


def test_default_status_new():
    dash = aid.build_dashboard(_three_high_inputs())
    for it in dash.items:
        assert it.status == aid.STATUS_NEW


def test_status_override_from_lookup():
    actions = _three_high_inputs()
    lookup = {"act_smart_dormant": aid.STATUS_REVIEWING}
    dash = aid.build_dashboard(actions, status_lookup=lookup)
    smart = next(i for i in dash.items if i.actionId == "act_smart_dormant")
    assert smart.status == aid.STATUS_REVIEWING


# ── 5) riskType 분류 ───────────────────────────────────────────────


def test_risk_type_smartstore_dormant():
    actions = [_three_high_inputs()[0]]
    dash = aid.build_dashboard(actions)
    assert dash.items[0].riskType in (aid.RISK_SELLER_ACCOUNT, aid.RISK_ACCOUNT)


def test_risk_type_coupang_listing_stop_is_seller():
    actions = [_three_high_inputs()[1]]
    dash = aid.build_dashboard(actions)
    assert dash.items[0].riskType == aid.RISK_SELLER_ACCOUNT


def test_risk_type_phishing():
    actions = [_three_high_inputs()[2]]
    dash = aid.build_dashboard(actions)
    assert dash.items[0].riskType == aid.RISK_PHISHING


def test_risk_type_seo_for_gsc_indexing():
    actions = [
        _action(
            br.CAT_REVIEW, "MEDIUM", "haehan-ai.kr 사이트의 페이지에 대한 색인이 생성되지 않습니다", sender="google.com"
        )
    ]
    dash = aid.build_dashboard(actions)
    assert dash.items[0].riskType == aid.RISK_SEO


def test_risk_type_delivery_failure():
    actions = [_action(br.CAT_DELIVERY_FAILURE, "MEDIUM", "Undelivered Mail Returned to Sender")]
    dash = aid.build_dashboard(actions)
    assert dash.items[0].riskType == aid.RISK_DELIVERY_FAILURE


def test_risk_type_billing_policy_security_service():
    cases = [
        (br.CAT_BILLING, "결제 내역", aid.RISK_BILLING_REVIEW),
        (br.CAT_POLICY_NOTICE, "약관 개정 안내", aid.RISK_POLICY_REVIEW),
        (br.CAT_SECURITY_NOTICE, "보안 알림", aid.RISK_SECURITY_REVIEW),
        (br.CAT_ACCOUNT_OR_SERVICE_NOTICE, "휴면 정책 변경 사전 안내", aid.RISK_SERVICE_NOTICE),
    ]
    for cat, title, expected in cases:
        a = [_action(cat, "MEDIUM", title)]
        d = aid.build_dashboard(a)
        assert d.items[0].riskType == expected, f"{cat}→{expected}"


# ── 6) UNKNOWN review lane ─────────────────────────────────────────


def test_unknown_review_lane_preserved():
    actions = [
        _action(br.CAT_UNKNOWN_REVIEW_REQUIRED, "LOW", "임의 제목 1"),
        _action(br.CAT_UNKNOWN_REVIEW_REQUIRED, "LOW", "임의 제목 2"),
    ]
    dash = aid.build_dashboard(actions)
    s = aid.build_summary(dash)
    assert s.unknown_review_count == 2
    # riskType 도 UNKNOWN_REVIEW 로 유지
    for it in dash.items:
        assert it.riskType == aid.RISK_UNKNOWN_REVIEW


def test_audit_warn_unknown_review_items_present():
    actions = _three_high_inputs() + [  # noqa: RUF005
        _action(br.CAT_UNKNOWN_REVIEW_REQUIRED, "LOW", "임의 제목"),
    ]
    dash = aid.build_dashboard(actions)
    s = aid.build_summary(dash)
    md = aid.render_markdown(dash, s)
    js = json.dumps(dash.to_dict(), ensure_ascii=False)
    v = audit.judge_dashboard(dash, s, md_text=md, json_text=js)
    assert v.code == "WARN_UNKNOWN_REVIEW_ITEMS_PRESENT"


# ── 7) dueDateCandidate 추출 ───────────────────────────────────────


def test_due_date_full_yyyy_mm_dd():
    iso, conf = aid.infer_due_date(
        "2026.06.02 시행",
        received_date="05-03",
    )
    assert iso == "2026-06-02"
    assert conf == "HIGH"


def test_due_date_yy_year_format():
    iso, conf = aid.infer_due_date(
        "[안내] 26년 6월 9일 시행",
        received_date="05-09",
    )
    assert iso == "2026-06-09"
    assert conf == "HIGH"


def test_due_date_month_day_only_medium():
    iso, conf = aid.infer_due_date("스마트스토어 휴면 6월 2일", received_date="05-03")
    assert iso.endswith("-06-02")
    assert conf == "MEDIUM"


def test_due_date_no_match():
    iso, conf = aid.infer_due_date("아무 날짜도 없는 제목", received_date="05-01")
    assert iso == ""
    assert conf == "NONE"


def test_due_date_summary_count():
    actions = [
        _action(br.CAT_POLICY_NOTICE, "MEDIUM", "[안내] 26년 6월 9일 시행 약관"),
        _action(br.CAT_BILLING, "LOW", "날짜 없는 결제"),
    ]
    dash = aid.build_dashboard(actions)
    s = aid.build_summary(dash)
    assert s.due_date_candidate_count == 1


# ── 8) raw body 저장 금지 ───────────────────────────────────────────


def test_raw_body_saved_false_in_all_items():
    actions = _three_high_inputs()
    dash = aid.build_dashboard(actions)
    for it in dash.items:
        assert it.raw_body_saved is False
    s = aid.build_summary(dash)
    assert s.raw_body_saved_any is False


def test_audit_fail_raw_body_leak():
    actions = _three_high_inputs()
    # 강제로 한 건 raw_body_saved=True
    actions[0]["raw_body_saved"] = True
    dash = aid.build_dashboard(actions)
    s = aid.build_summary(dash)
    v = audit.judge_dashboard(dash, s)
    assert v.code == "FAIL_RAW_BODY_LEAK"


# ── 9) PII leak 방지 ───────────────────────────────────────────────


def test_audit_fail_pii_unmasked_when_raw_email_in_md():
    actions = _three_high_inputs()
    dash = aid.build_dashboard(actions)
    s = aid.build_summary(dash)
    # 일부러 raw email 이 들어간 md 시뮬레이션
    fake_md = "raw user@example.com 누출"
    js = json.dumps(dash.to_dict(), ensure_ascii=False)
    v = audit.judge_dashboard(dash, s, md_text=fake_md, json_text=js)
    assert v.code == "FAIL_PII_UNMASKED"


def test_render_with_masked_input_yields_zero_leak():
    actions = _three_high_inputs()
    dash = aid.build_dashboard(actions)
    s = aid.build_summary(dash)
    md = aid.render_markdown(dash, s)
    js = json.dumps(dash.to_dict(), ensure_ascii=False)
    leaks_md = aid.find_leaks(md)
    leaks_js = aid.find_leaks(js)
    total = sum(len(v) for v in leaks_md.values()) + sum(len(v) for v in leaks_js.values())
    assert total == 0


# ── 10) external AI call 금지 ──────────────────────────────────────


def test_audit_fail_external_ai_call_in_network_log():
    actions = _three_high_inputs()
    dash = aid.build_dashboard(actions)
    s = aid.build_summary(dash)
    v = audit.judge_dashboard(dash, s, network_log=["POST https://api.anthropic.com/v1"])
    assert v.code == "FAIL_EXTERNAL_AI_CALL_USED"


# ── 11) audit PASS ────────────────────────────────────────────────


def test_audit_pass_when_clean_with_high3_only():
    actions = _three_high_inputs()
    dash = aid.build_dashboard(actions)
    s = aid.build_summary(dash)
    md = aid.render_markdown(dash, s)
    js = json.dumps(dash.to_dict(), ensure_ascii=False)
    v = audit.judge_dashboard(dash, s, md_text=md, json_text=js)
    assert v.code == "PASS_NAVER_MAIL_ACTION_ITEM_DASHBOARD", v.reasons


# ── 12) 회귀 가드 ──────────────────────────────────────────────────


def test_regression_business_report_imports():
    from scripts.naver.mail import business_report as br

    assert hasattr(br, "build_report")
    assert hasattr(br, "ActionItem")


def test_regression_batch_runner_imports():
    from scripts.naver.mail import batch_runner as bt

    assert hasattr(bt, "run_batch")


def test_regression_body_pipeline_v2_imports():
    from scripts.naver.mail import body_pipeline_v2 as bp

    assert hasattr(bp, "run")


# ── markdown 섹션 ──────────────────────────────────────────────────


def test_markdown_has_required_sections():
    actions = _three_high_inputs() + [  # noqa: RUF005
        _action(br.CAT_UNKNOWN_REVIEW_REQUIRED, "LOW", "임의 제목"),
    ]
    dash = aid.build_dashboard(actions)
    s = aid.build_summary(dash)
    md = aid.render_markdown(dash, s)
    for sec in (
        "개요",
        "안전 정책 준수",
        "HIGH 즉시 조치",
        "MEDIUM 검토 필요",
        "LOW",
        "UNKNOWN",
        "리스크 유형별",
        "카테고리별",
        "due date 후보",
        "원문/PII 저장 여부",
    ):
        assert sec in md, f"missing section: {sec}"
