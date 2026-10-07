"""NAVER-MAIL-CONSOLIDATED-BUSINESS-REPORT-CLOSEOUT-01 — 필수 15+ 테스트."""

from __future__ import annotations

import json

from scripts.naver.mail import business_report as br
from scripts.naver.mail.analysis import audit_naver_mail_business_report as audit


def _mk(
    sn="100", folder="받은메일함", subject="", sender="", date="", body="", has_attach=False, pii_n=0, link_domains=None
):
    return br.MailItem(
        sn=sn,
        folder_name=folder,
        subject_masked=subject,
        sender_masked=sender,
        date_text=date,
        body_redacted_short=body,
        link_domains=link_domains or {},
        has_attach=has_attach,
        pii_detected_count=pii_n,
    )


# ── 분류 규칙 ───────────────────────────────────────────────────────


def test_classify_fedex_phishing_suspect():
    it = _mk(subject="Re: Shipping Documents", sender='"FedEX Shipment"<fe***@global-gu.com>')
    cat, pri, ev = br.classify_mail(it)
    assert cat == br.CAT_SPAM_OR_PHISHING_SUSPECTED
    assert pri == br.PRIORITY_HIGH
    # shipping 키워드 + untrusted 도메인 marker 둘 중 하나라도 발견되면 PASS
    assert any(("fedex" in e) or ("shipping_keyword" in e) for e in ev), ev


def test_classify_gsc_indexing_review():
    it = _mk(
        subject="새로운 이유로 인해 haehan-ai.kr 사이트의 페이지에 대한 색인이 생성되지 않습니다",
        sender='"Google Search Console Team"<sc***@google.com>',
    )
    cat, pri, _ = br.classify_mail(it)
    assert cat == br.CAT_REVIEW
    assert pri == br.PRIORITY_MEDIUM


def test_classify_undelivered_mail_failure():
    it = _mk(subject="Undelivered Mail Returned to Sender", sender='"Mail Delivery System"<MA***@heatpipe.co.kr>')
    cat, pri, _ = br.classify_mail(it)
    assert cat == br.CAT_DELIVERY_FAILURE
    assert pri == br.PRIORITY_MEDIUM


def test_classify_security_notice_naver():
    it = _mk(subject="새로운 환경에서 로그인 되었습니다.", sender='"네이버"<ac***@navercorp.com>')
    cat, pri, _ = br.classify_mail(it)
    assert cat == br.CAT_SECURITY_NOTICE
    assert pri == br.PRIORITY_MEDIUM


def test_classify_security_notice_google():
    it = _mk(subject="보안 알림", sender='"Google"<no***@accounts.google.com>')
    cat, _, _ = br.classify_mail(it)
    assert cat == br.CAT_SECURITY_NOTICE


def test_classify_billing_kcp_payment():
    it = _mk(subject="NHN KCP - 쿠팡(쿠페이)의 결제 내역입니다.", sender='"NHN KCP 발신전용"<pg***@kcp.co.kr>')
    cat, _, _ = br.classify_mail(it)
    assert cat == br.CAT_BILLING


def test_classify_billing_kb_card():
    it = _mk(
        subject="(KB국민카드) 일부결제금액이월약정(리볼빙) 이용 안내", sender='"KB국민카드"<kb***@kbmail.kbcard.com>'
    )
    cat, _, _ = br.classify_mail(it)
    assert cat == br.CAT_BILLING


def test_classify_policy_notice_terms():
    it = _mk(subject="[하나카드]개인손님 할부수수료율 변경 사전안내", sender='"하나카드"<ha***@hanacard.co.kr>')
    cat, _, _ = br.classify_mail(it)
    assert cat == br.CAT_POLICY_NOTICE


def test_classify_attention_seller_listing_stop():
    it = _mk(
        subject="[쿠팡] 고객센터 문의 답변지연으로 인한 전체 상품 노출 정지 안내", sender='"Support"<sp***@coupang.com>'
    )
    cat, pri, _ = br.classify_mail(it)
    assert cat == br.CAT_ATTENTION
    assert pri == br.PRIORITY_HIGH


def test_classify_attention_smartstore_dormant():
    it = _mk(
        subject="[스마트스토어센터] 스마트스토어 판매자 계정이 휴면 상태로 전환될 예정입니다.",
        sender='"스마트스토어 센터"<sm***@navercorp.com>',
    )
    cat, pri, _ = br.classify_mail(it)
    assert cat == br.CAT_ATTENTION
    assert pri == br.PRIORITY_HIGH


def test_classify_low_priority_instagram():
    it = _mk(
        subject="11ggg162222님, Instagram에 새로 올라온 소식을 확인해보세요",
        sender='"Instagram"<po***@mail.instagram.com>',
    )
    cat, _, _ = br.classify_mail(it)
    assert cat == br.CAT_LOW_PRIORITY


def test_classify_promo_event():
    it = _mk(subject="[BLACKKIWI] 블랙키위 AI 인사이트 기능 베타 오픈 안내", sender='"BLACKKIWI"<no***@blackkiwi.net>')
    cat, _, _ = br.classify_mail(it)
    assert cat == br.CAT_PROMO


def test_classify_unknown_when_no_rule():
    it = _mk(subject="아무 키워드도 매칭 안되는 임의 제목입니다", sender='"임의"<so***@unknown-x.example>')
    cat, _, ev = br.classify_mail(it)
    assert cat == br.CAT_UNKNOWN_REVIEW_REQUIRED
    assert "no_rule_matched" in ev


# ── ActionItem schema ──────────────────────────────────────────────


def test_action_item_schema_complete():
    it = _mk(sn="999", subject="노출 정지 안내", sender='"X"<x@coupang.com>', date="05-18")
    cat, pri, ev = br.classify_mail(it)
    a = br.to_action_item(it, category=cat, priority=pri, evidence=ev)
    d = a.to_dict()
    for k in (
        "actionId",
        "category",
        "priority",
        "title_redacted",
        "sender_domain",
        "received_date",
        "reason",
        "recommended_action",
        "evidence_markers",
        "pii_masked",
        "raw_body_saved",
    ):
        assert k in d, f"missing field: {k}"
    assert d["pii_masked"] is True
    assert d["raw_body_saved"] is False
    assert d["actionId"].startswith("act_")


# ── 보고서 빌드 + 렌더링 ──────────────────────────────────────────


def test_build_report_categorizes_mails():
    items = [
        _mk(sn="1", subject="노출 정지 안내", sender="<sp***@coupang.com>"),
        _mk(sn="2", subject="보안 알림", sender="<no***@accounts.google.com>"),
        _mk(sn="3", subject="NHN KCP - 쿠팡(쿠페이)의 결제 내역입니다.", sender="<pg***@kcp.co.kr>"),
        _mk(sn="4", subject="이용약관 개정 안내", sender="<no***@x.com>"),
        _mk(sn="5", subject="Re: Shipping Documents", sender="<fe***@global-gu.com>"),
    ]
    rep = br.build_report(items, run_id="t1")
    cats = {cg.category: cg.count for cg in rep.categories}
    assert cats[br.CAT_ATTENTION] == 1
    assert cats[br.CAT_SECURITY_NOTICE] == 1
    assert cats[br.CAT_BILLING] == 1
    assert cats[br.CAT_POLICY_NOTICE] == 1
    assert cats[br.CAT_SPAM_OR_PHISHING_SUSPECTED] == 1
    assert rep.total_mails == 5


def test_render_markdown_and_json():
    items = [_mk(sn="1", subject="노출 정지", sender="<sp***@coupang.com>")]
    rep = br.build_report(items, run_id="t1")
    md = br.render_markdown(rep)
    j = json.dumps(br.render_json(rep), ensure_ascii=False)
    rep = br.attach_leak_check(rep, md_text=md, json_text=j)
    # 마크다운 구조 확인
    for sec in ("개요", "안전 정책 준수 결과", "폴더별 분포", "발신자 도메인 TOP", "긴급 액션", "액션 아이템"):
        assert sec in md


# ── PII leak self-check ────────────────────────────────────────────


def test_find_pii_leaks_detects_raw_patterns():
    text = "raw user@example.com and 010-1234-5678 and 123456-1234567"
    leaks = br.find_pii_leaks(text)
    assert leaks["raw_emails"] == ["user@example.com"]
    assert leaks["raw_phones"] == ["010-1234-5678"]
    assert leaks["raw_rrn"] == ["123456-1234567"]


def test_render_with_masked_input_yields_zero_leak():
    items = [_mk(sn="1", subject="보안 알림", sender='"Google"<no***@accounts.google.com>')]
    rep = br.build_report(items, run_id="t1")
    md = br.render_markdown(rep)
    j = json.dumps(br.render_json(rep), ensure_ascii=False)
    rep = br.attach_leak_check(rep, md_text=md, json_text=j)
    assert rep.leak_self_check["total_leak_count"] == 0


# ── audit ────────────────────────────────────────────────────────


def test_audit_pass_when_clean():
    items = [
        _mk(sn="1", subject="보안 알림", sender="<no***@accounts.google.com>"),
        _mk(sn="2", subject="결제 내역", sender="<pg***@kcp.co.kr>"),
    ]
    rep = br.build_report(items, run_id="t1")
    md = br.render_markdown(rep)
    j = json.dumps(br.render_json(rep), ensure_ascii=False)
    rep = br.attach_leak_check(rep, md_text=md, json_text=j)
    v = audit.judge_report(rep, md_text=md, json_text=j)
    assert v.code == "PASS_NAVER_MAIL_BUSINESS_REPORT", v.reasons


def test_audit_warn_unknown_review_required():
    # ratio 가 40% 이하가 되도록 알려진 카테고리 9건 + 미분류 1건
    items = [_mk(sn=str(i), subject="보안 알림", sender="<no***@accounts.google.com>") for i in range(9)]
    items.append(_mk(sn="x", subject="아무 키워드도 없는 임의 제목", sender="<x@unknown-x.example>"))
    rep = br.build_report(items, run_id="t1")
    md = br.render_markdown(rep)
    j = json.dumps(br.render_json(rep))
    rep = br.attach_leak_check(rep, md_text=md, json_text=j)
    v = audit.judge_report(rep, md_text=md, json_text=j)
    assert v.code == "WARN_UNKNOWN_REVIEW_REQUIRED"


def test_audit_warn_low_confidence_when_ratio_high():
    items = [_mk(sn=str(i), subject="아무것도 매칭 안됨", sender="<x@u.example>") for i in range(10)]
    rep = br.build_report(items, run_id="t1")
    md = br.render_markdown(rep)
    j = json.dumps(br.render_json(rep))
    rep = br.attach_leak_check(rep, md_text=md, json_text=j)
    v = audit.judge_report(rep, md_text=md, json_text=j)
    assert v.code == "WARN_LOW_CONFIDENCE_CLASSIFICATION"


def test_audit_fail_raw_body_leak():
    rep = br.BusinessReport(raw_body_saved=True)
    v = audit.judge_report(rep)
    assert v.code == "FAIL_RAW_BODY_LEAK"


def test_audit_fail_pii_unmasked_in_md():
    rep = br.BusinessReport()
    rep.leak_self_check = {"md": {"raw_emails": 1}, "json": {}, "total_leak_count": 1}
    v = audit.judge_report(rep)
    assert v.code == "FAIL_PII_UNMASKED"


def test_audit_fail_attachment_downloaded():
    rep = br.BusinessReport(attachment_download_count=1)
    v = audit.judge_report(rep)
    assert v.code == "FAIL_ATTACHMENT_DOWNLOADED"


def test_audit_fail_external_ai_via_network_log():
    rep = br.BusinessReport()
    v = audit.judge_report(rep, network_log=["POST https://api.anthropic.com/v1"])
    assert v.code == "FAIL_EXTERNAL_AI_CALL_USED"


def test_audit_fail_unread_restore_regression():
    rep = br.BusinessReport()
    rep.unread_restore_summary = {
        "restore_attempted": 60,
        "restore_succeeded": 50,
        "restore_failed": 10,
        "state_changed": 60,
    }
    prior = {"restore_attempted": 60, "restore_succeeded": 60, "restore_failed": 0, "state_changed": 60}
    v = audit.judge_report(rep, prior_unread_restore=prior)
    assert v.code == "FAIL_UNREAD_RESTORE_REGRESSION"


# ── 회귀 가드 ───────────────────────────────────────────────────────


def test_regression_batch_runner_imports():
    from scripts.naver.mail import batch_runner as bt

    assert hasattr(bt, "run_batch")


def test_regression_body_pipeline_v2_imports():
    from scripts.naver.mail import body_pipeline_v2 as bp

    assert hasattr(bp, "run")


def test_regression_folder_discovery_imports():
    from scripts.naver.mail import folder_discovery as fd
    from scripts.naver.mail import folder_profile as fpr

    assert hasattr(fd, "discover_folders")
    assert hasattr(fpr, "build_snapshot")


# ── 정렬 / domain 추출 ────────────────────────────────────────────


def test_domain_of_extracts_correctly():
    assert br._domain_of('"X"<sp***@coupang.com>') == "coupang.com"
    assert br._domain_of("<a@b.example>") == "b.example"
    assert br._domain_of("") == ""


def test_action_items_sorted_by_priority():
    items = [
        _mk(sn="1", subject="이용약관 개정 안내", sender="<x@x.com>"),  # MEDIUM
        _mk(sn="2", subject="노출 정지", sender="<x@coupang.com>"),  # HIGH
        _mk(sn="3", subject="Undelivered Mail", sender="<x@x.com>"),  # MEDIUM
    ]
    rep = br.build_report(items, run_id="t1")
    priorities = [a.priority for a in rep.action_items]
    # HIGH 가 먼저
    assert priorities.index(br.PRIORITY_HIGH) < priorities.index(br.PRIORITY_MEDIUM)
