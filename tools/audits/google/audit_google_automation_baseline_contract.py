"""Read-only audit for the locked Google automation baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "docs" / "baseline" / "GOOGLE_AUTOMATION_BASELINE.md"

REQUIRED_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: GOOGLE-AUTOMATION-BASELINE-01",
    "Google tabs: 9",
    "Google surfaces: 50",
    "Google actions: 96",
    "Read actions: 50",
    "Approval actions: 46",
    "Live input supported approval actions: 46",
    "Prepare/open-only approval actions: 0",
    "Production final execution blocked: 46",
    "Host normalization warnings: 0",
    "Live logic surfaces: 50",
    "user_present_session",
    "host_warnings == []",
    "scripts/google/common/tab_registry.py",
    "scripts/google/common/subdomain_logic.py",
    "scripts/google/common/tab_logic.py",
    "scripts/google/live_surface_explorer.py",
    "scripts/google/cloud/live_console_explorer.py",
    "scripts/common/gates/secret_action_gate.py",
    "scripts/common/gates/work_mode_gate.py",
    "scripts/google/workspace_basic.py",
    "scripts/google/ads_signup.py",
    "scripts/google/domain_readiness_audit.py",
    "scripts/google/vision_usage_gate.py",
    "tools/audits/google/audit_google_home_login_gate.py",
    "python scripts/entry/cdp_cli.py google work undeveloped",
    "tests/test_google_tab_registry.py",
    "tests/test_google_domain_readiness_audit.py",
    "tests/test_google_secret_action_gate.py",
    "tests/test_google_work_mode_gate.py",
    "tests/test_google_workspace_basic.py",
    "tests/test_google_ads_signup.py",
    "tests/test_google_vision_usage_gate.py",
    "tests/test_google_home_login_gate.py",
    "scripts/ops/audit_google_home_login_gate.py",
    "python scripts/browser/cdp/cdp_client.py google work undeveloped",
    "tests/google/test_google_tab_registry.py",
    "tests/google/test_google_domain_readiness_audit.py",
    "tests/google/test_google_secret_action_gate.py",
    "tests/google/test_google_work_mode_gate.py",
    "tests/google/test_google_workspace_basic.py",
    "tests/google/test_google_ads_signup.py",
    "tests/google/test_google_vision_usage_gate.py",
    "tests/google/test_google_home_login_gate.py",
    "monthly_free_limit_units = 1000",
    "tools/audits/google/audit_google_prefill_maturity.py",
    "Strict final-approval-only prefill is a higher bar than live-input support.",
    "0 strict prefill",
    "tests/google/test_google_live_surface_explorer.py",
    "Do not split all Google modules in one change.",
)

REQUIRED_TABS = (
    "search",
    "identity",
    "workspace",
    "cloud",
    "ai",
    "youtube",
    "marketing",
    "developer",
    "media",
)


def _missing(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def _check_baseline_phrases() -> list[str]:
    text = BASELINE.read_text(encoding="utf-8", errors="replace")
    missing = _missing(text, REQUIRED_PHRASES)
    return ["Google baseline missing phrase(s): " + ", ".join(missing)] if missing else []


def _check_tab_registry() -> list[str]:
    from scripts.google.common.tab_registry import GOOGLE_TABS, build_google_tab_summary

    failures: list[str] = []
    tab_keys = tuple(tab.key for tab in GOOGLE_TABS)
    if tab_keys != REQUIRED_TABS:
        failures.append("Google tab order or keys changed: " + ", ".join(tab_keys))

    summary = build_google_tab_summary()
    counts = summary["counts"]
    expected_counts = {
        "tabs": 9,
        "surfaces": 50,
        "actions": 96,
        "read_actions": 50,
        "approval_actions": 46,
    }
    for key, expected in expected_counts.items():
        if counts.get(key) != expected:
            failures.append(f"Google count mismatch {key}: expected {expected}, got {counts.get(key)}")

    if summary["host_warnings"]:
        failures.append(f"Google host warnings must be zero, got {len(summary['host_warnings'])}")
    return failures


def _check_subdomain_and_tab_logic() -> list[str]:
    from scripts.google.common import subdomain_logic, tab_logic

    failures: list[str] = []
    subdomain_catalog = subdomain_logic.build_google_subdomain_logic_catalog()
    if subdomain_catalog.get("credential_replay_allowed") is not False:
        failures.append("Google subdomain logic must block credential replay")
    if subdomain_catalog.get("auto_login") is not False:
        failures.append("Google subdomain logic must block auto-login")

    tab_catalog = tab_logic.build_all_tab_logic_catalog()
    if tab_catalog.get("tab_count") != 9:
        failures.append("Google tab logic must expose 9 locked tabs")
    if not all(tab.get("user_guidance", {}).get("user_can_request") for tab in tab_catalog.get("tabs", [])):
        failures.append("Google tab logic must expose user guidance for every tab")
    return failures


def _check_live_surface() -> list[str]:
    from scripts.google import live_surface_explorer

    live_logic = live_surface_explorer.build_google_surface_live_logic()
    if live_logic.get("surface_count") != 50:
        return [f"Google live logic surface count mismatch: {live_logic.get('surface_count')}"]
    return []


def _check_undeveloped_report() -> list[str]:
    from scripts.google.common import workflows

    failures: list[str] = []
    undeveloped = workflows.build_undeveloped_report()
    expected_undeveloped_counts = {
        "actions": 96,
        "readonly_complete": 50,
        "approval_actions": 46,
        "live_input_supported": 46,
        "prepare_or_open_only": 0,
        "production_final_blocked": 46,
        "missing_adapter_profiles": 0,
    }
    for key, expected in expected_undeveloped_counts.items():
        actual = undeveloped["counts"].get(key)
        if actual != expected:
            failures.append(f"Google undeveloped lock mismatch {key}: expected {expected}, got {actual}")
    supported = {item["action_key"] for item in undeveloped["live_input_supported"]}
    prepare_only = {item["action_key"] for item in undeveloped["prepare_or_open_only"]}
    for key in ("gmail_send_email", "youtube_studio_upload_video", "cloud_create_api_credential"):
        if key not in supported:
            failures.append(f"Google live-input lock missing supported action: {key}")
    for key in ("drive_upload_share_file", "ads_campaign_budget_change", "vertex_ai_start_job_or_deploy"):
        if key not in supported:
            failures.append(f"Google generic live-input lock missing supported action: {key}")
    if prepare_only:
        failures.append("Google prepare/open-only backlog must be empty after generic handoff adapter lock")
    return failures


def _check_domain_readiness_and_secret_gate() -> list[str]:
    from scripts.common.gates import secret_action_gate
    from scripts.google import domain_readiness_audit

    failures: list[str] = []
    readiness = domain_readiness_audit.build_google_domain_readiness_audit()
    if readiness.get("ok") is not True:
        failures.append("Google domain readiness audit must pass")
    if readiness.get("counts", {}).get("surfaces") != 50:
        failures.append("Google domain readiness must cover all 50 surfaces")
    if readiness.get("global_policy", {}).get("browser_fallback") != "user_present_cdp_session_selection_required":
        failures.append("Google browser fallback must require CDP session selection")
    secret_policy = secret_action_gate.build_secret_action_policy("secret_issue_agent_click")
    if secret_policy.get("status") != "blocked":
        failures.append("Google agent secret issue click must require explicit approval")
    if secret_policy.get("raw_secret_output_allowed") is not False:
        failures.append("Google secret action gate must block raw secret output")
    return failures


def _check_vision_usage_gate() -> list[str]:
    from scripts.google import vision_usage_gate

    failures: list[str] = []
    if vision_usage_gate.MONTHLY_FREE_LIMIT_UNITS != 1000:
        failures.append("Google Vision monthly free-unit limit must stay 1000")
    if vision_usage_gate.WARNING_THRESHOLD_UNITS != 800:
        failures.append("Google Vision warning threshold must stay 800")
    vision_gate = vision_usage_gate.evaluate_vision_monthly_free_gate(
        current_month_units=999,
        image_count=2,
        features=["text_detection"],
    )
    if vision_gate.get("status") != "blocked":
        failures.append("Google Vision must block projected usage above free units")
    if vision_gate.get("secret_values_output") is not False:
        failures.append("Google Vision gate must not output raw secret values")
    return failures


def _check_prefill_maturity() -> list[str]:
    from tools.audits.google import audit_google_prefill_maturity

    failures: list[str] = []
    prefill_maturity = audit_google_prefill_maturity.build_report()
    expected_prefill_counts = {
        "approval_actions": 46,
        "live_input_supported": 46,
        "domain_specific_prefill": 46,
        "generic_handoff": 0,
        "partial_handoff": 0,
        "strict_prefill_gaps": 0,
    }
    for key, expected in expected_prefill_counts.items():
        actual = prefill_maturity["counts"].get(key)
        if actual != expected:
            failures.append(f"Google strict prefill maturity mismatch {key}: expected {expected}, got {actual}")
    priority_gaps = {item["action_key"] for item in prefill_maturity.get("priority_gaps", [])}
    if priority_gaps:
        failures.append("Google strict prefill priority gaps must be empty after API key issuance prefill readiness")
    priority_ready = {item["action_key"] for item in prefill_maturity.get("priority_ready", [])}
    if priority_ready != {"cloud_create_api_credential", "ai_studio_create_api_key"}:
        failures.append("Google API key issuance actions must be marked final-click-ready")
    return failures


def audit() -> tuple[bool, list[str]]:
    # 2026-09-29 STD-08(복잡도) 리팩터: 이 함수 하나(C901=32)에 있던 독립 체크 블록들을
    # 위 _check_*() 함수로 분리(순서·조건·문자열 그대로, 순수 추출) — #48 과 같은 패턴.
    failures: list[str] = []
    if not BASELINE.exists():
        return False, ["docs/baseline/GOOGLE_AUTOMATION_BASELINE.md missing"]

    failures.extend(_check_baseline_phrases())
    failures.extend(_check_tab_registry())
    failures.extend(_check_subdomain_and_tab_logic())
    failures.extend(_check_live_surface())
    failures.extend(_check_undeveloped_report())
    failures.extend(_check_domain_readiness_and_secret_gate())
    failures.extend(_check_vision_usage_gate())
    failures.extend(_check_prefill_maturity())

    return not failures, failures or [
        "GOOGLE_AUTOMATION_BASELINE exists and is locked",
        "9 Google tabs, 50 surfaces, and 96 actions are registered",
        "Google host warnings are zero",
        "Google subdomain, tab, and 50-surface live logic contracts are present",
        "Google domain readiness covers OAuth/API and browser fallback boundaries",
        "Google secret issuance modes are gated and raw secret output is blocked",
        "Google Vision monthly free-unit gate is locked",
        "Google strict prefill maturity gaps are explicit and tracked",
        "Google undeveloped work counts and backlog boundaries are locked",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "GOOGLE_AUTOMATION_BASELINE_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())
