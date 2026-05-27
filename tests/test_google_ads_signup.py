from __future__ import annotations

from scripts.google import ads_signup


def test_ads_signup_requires_google_work_mode() -> None:
    plan = ads_signup.build_ads_signup_plan()

    assert plan["status"] == "blocked"
    assert plan["blocked_reason"] == "google_work_mode_required"
    assert plan["paid_execution_allowed"] is False


def test_ads_signup_requires_explicit_signup_approval() -> None:
    plan = ads_signup.build_ads_signup_plan(google_work_mode="main")

    assert plan["status"] == "blocked"
    assert plan["blocked_reason"] == "ads_signup_requires_explicit_user_approval"
    assert "enter billing or payment information" in plan["agent_forbidden_steps"]


def test_ads_signup_plan_allows_no_paid_handoff_after_approval() -> None:
    plan = ads_signup.build_ads_signup_plan(
        google_work_mode="main",
        ads_signup_approved=True,
    )

    assert plan["status"] == "ready_for_no_paid_signup_handoff"
    assert plan["sequence"][0]["url"] == "https://www.google.com/"
    assert plan["keyword_planner_target_url"] == "https://ads.google.com/aw/keywordplanner/home?authuser=0"
    assert plan["billing_submit_allowed"] is False
    assert plan["budget_submit_allowed"] is False
    assert plan["campaign_publish_allowed"] is False


def test_ads_signup_blocks_unapproved_background_mode() -> None:
    plan = ads_signup.build_ads_signup_plan(
        google_work_mode="background",
        ads_signup_approved=True,
    )

    assert plan["status"] == "blocked"
    assert plan["blocked_reason"] == "background_mode_requires_explicit_user_approval"


def test_ads_signup_screen_classifier_stops_at_paid_boundaries() -> None:
    result = ads_signup.classify_ads_signup_screen("첫 번째 캠페인 만들기 3. 예산 설정 결제 정보")

    assert result["status"] == "blocked"
    assert result["reason"] == "paid_or_final_campaign_boundary_detected"
    assert result["agent_may_continue"] is False


def test_ads_signup_screen_classifier_requires_asset_scan_approval() -> None:
    result = ads_signup.classify_ads_signup_screen("웹페이지 URL 입력 이미지를 스캔 다운로드 및 보정 상업적 목적으로 사용")

    assert result["status"] == "needs_user_approval"
    assert result["reason"] == "website_asset_scan_consent_detected"
    assert result["agent_may_continue"] is False


def test_ads_signup_screen_classifier_allows_plain_account_selector() -> None:
    result = ads_signup.classify_ads_signup_screen("Google Ads 계정이 없습니다. 새 Google Ads 계정")

    assert result["status"] == "ok"
    assert result["agent_may_continue"] is True
