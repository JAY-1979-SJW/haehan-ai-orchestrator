"""Google Ads signup gate.

The supported path is a no-paid-action signup handoff. The agent may prepare
and inspect the Google Ads onboarding flow after explicit user approval, but it
must stop before billing, budget, campaign publishing, or website asset-scan
consent.
"""
from __future__ import annotations

from typing import Any

from .managed_console import GOOGLE_HOME_URL
from scripts.common.gates.work_mode_gate import build_google_work_mode_policy


GOOGLE_ADS_HOME_URL = "https://ads.google.com/"
GOOGLE_ADS_ACCOUNT_SELECTOR_URL = (
    "https://ads.google.com/nav/selectaccount?dst=%2Faw%2Fcampaigns%2Fnew%2Fexpress&authuser=0"
)
GOOGLE_ADS_KEYWORD_PLANNER_URL = "https://ads.google.com/aw/keywordplanner/home?authuser=0"

PAID_OR_FINAL_STOP_KEYWORDS = (
    "예산 설정",
    "예산",
    "결제",
    "결제 정보",
    "payment",
    "billing",
    "campaign budget",
    "publish",
    "게시",
    "광고 시작",
    "campaign launch",
)
WEBSITE_ASSET_CONSENT_KEYWORDS = (
    "웹페이지 URL",
    "이미지를 스캔",
    "다운로드 및 보정",
    "상업적 목적으로 사용",
    "생성형 AI 정책",
)


def build_ads_signup_plan(
    *,
    google_work_mode: str | None = None,
    background_approved: bool = False,
    ads_signup_approved: bool = False,
    website_asset_scan_approved: bool = False,
) -> dict[str, Any]:
    """Return the locked Google Ads signup plan."""
    work_mode_policy = build_google_work_mode_policy(
        google_work_mode,
        background_approved=background_approved,
    )
    blocked_reason = ""
    if work_mode_policy["status"] == "blocked":
        blocked_reason = work_mode_policy["blocked_reason"]
    elif not ads_signup_approved:
        blocked_reason = "ads_signup_requires_explicit_user_approval"
    status = "blocked" if blocked_reason else "ready_for_no_paid_signup_handoff"

    return {
        "schema_version": 1,
        "workflow": "google_ads_no_paid_signup",
        "status": status,
        "blocked_reason": blocked_reason,
        "browser_runtime": "managed_local_agent_cdp_profile",
        "google_work_mode_policy": work_mode_policy,
        "google_work_mode": work_mode_policy["mode"],
        "ads_signup_approved": bool(ads_signup_approved),
        "website_asset_scan_approved": bool(website_asset_scan_approved),
        "default_browser_allowed": False,
        "google_home_required": True,
        "direct_accounts_login_allowed": False,
        "paid_execution_allowed": False,
        "billing_submit_allowed": False,
        "budget_submit_allowed": False,
        "campaign_publish_allowed": False,
        "keyword_planner_target_url": GOOGLE_ADS_KEYWORD_PLANNER_URL,
        "sequence": [
            {"step": 1, "stage": "google_home", "url": GOOGLE_HOME_URL},
            {"step": 2, "stage": "ads_home", "url": GOOGLE_ADS_HOME_URL},
            {"step": 3, "stage": "ads_account_selector", "url": GOOGLE_ADS_ACCOUNT_SELECTOR_URL},
            {
                "step": 4,
                "stage": "new_ads_account",
                "action": "click_new_google_ads_account_only_after_ads_signup_approved",
            },
            {
                "step": 5,
                "stage": "keyword_planner_access_check",
                "url": GOOGLE_ADS_KEYWORD_PLANNER_URL,
                "fallback": "stop_if_on_first_campaign_or_billing_or_budget_screen",
            },
        ],
        "agent_allowed_steps": [
            "open Google Home in the managed CDP profile",
            "open Google Ads account selector",
            "click the new Google Ads account entry only after explicit user approval",
            "read visible onboarding state and classify the next required step",
            "try Keyword Planner access after account creation",
            "write redacted status evidence",
        ],
        "agent_forbidden_steps": [
            "enter billing or payment information",
            "set or submit an advertising budget",
            "publish, enable, or launch a campaign",
            "click final campaign creation or ad start controls",
            "submit website URL asset-scan consent unless website_asset_scan_approved is true",
        ],
        "user_only_steps": [
            "approve Google Ads account creation",
            "approve any website URL asset scan/commercial asset use consent",
            "enter billing information if the user later chooses paid advertising",
            "approve any budget, campaign, publish, launch, or ad-spend action",
        ],
        "next_step": (
            "Select google_work_mode and approve ads_signup_approved=True."
            if blocked_reason
            else "Proceed until the first paid, billing, budget, campaign, or asset-consent boundary."
        ),
    }


def classify_ads_signup_screen(text: str) -> dict[str, Any]:
    """Classify a visible Ads onboarding page without taking action."""
    normalized = (text or "").lower()
    paid_matches = [item for item in PAID_OR_FINAL_STOP_KEYWORDS if item.lower() in normalized]
    asset_matches = [item for item in WEBSITE_ASSET_CONSENT_KEYWORDS if item.lower() in normalized]
    if paid_matches:
        return {
            "status": "blocked",
            "reason": "paid_or_final_campaign_boundary_detected",
            "matched_keywords": paid_matches,
            "agent_may_continue": False,
        }
    if asset_matches:
        return {
            "status": "needs_user_approval",
            "reason": "website_asset_scan_consent_detected",
            "matched_keywords": asset_matches,
            "agent_may_continue": False,
        }
    return {
        "status": "ok",
        "reason": "",
        "matched_keywords": [],
        "agent_may_continue": True,
    }


__all__ = [
    "GOOGLE_ADS_HOME_URL",
    "GOOGLE_ADS_ACCOUNT_SELECTOR_URL",
    "GOOGLE_ADS_KEYWORD_PLANNER_URL",
    "build_ads_signup_plan",
    "classify_ads_signup_screen",
]
