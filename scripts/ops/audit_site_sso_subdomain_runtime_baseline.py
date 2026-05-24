"""Audit the shared SSO subdomain runtime baseline."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "docs" / "baseline" / "SITE_SSO_SUBDOMAIN_RUNTIME_BASELINE.md"

REQUIRED_PHRASES = (
    "Status: LOCKED",
    "Baseline ID: SITE-SSO-SUBDOMAIN-RUNTIME-BASELINE-01",
    "`google`",
    "`naver`",
    "user_present_sso_profile",
    "same local browser profile is reused",
    "navigation must use `web_open_url_readonly`",
    "execution location must be `local_agent`",
    "risk level must be `read`",
    "auto login must be false",
    "raw cookies, sessions, tokens, passwords, OTPs, Authorization headers",
    "automatic username/password entry",
    "cookie export",
    "session export",
)


def _missing(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def audit() -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not BASELINE.exists():
        return False, ["docs/baseline/SITE_SSO_SUBDOMAIN_RUNTIME_BASELINE.md missing"]

    text = BASELINE.read_text(encoding="utf-8", errors="replace")
    missing = _missing(text, REQUIRED_PHRASES)
    if missing:
        failures.append("SSO baseline missing phrase(s): " + ", ".join(missing))

    from scripts.sites.readonly_check import build_provider_readonly_check_plan
    from scripts.sites.sso_runtime import build_blocked_operation_result, build_login_entry_task
    from scripts.sites.subdomain_registry import get_provider, validate_registry

    registry_errors = validate_registry()
    if registry_errors:
        failures.extend(registry_errors)

    expected_counts = {"google": 12, "naver": 11}
    for provider_id, expected_count in expected_counts.items():
        provider = get_provider(provider_id)
        if len(provider.services) != expected_count:
            failures.append(f"{provider_id}: service count mismatch {len(provider.services)}")
        login_task = build_login_entry_task(provider_id)
        metadata = login_task.get("metadata", {})
        if metadata.get("auto_login") is not False:
            failures.append(f"{provider_id}: auto_login must be false")
        if metadata.get("user_present_required") is not True:
            failures.append(f"{provider_id}: user_present_required must be true")
        if metadata.get("shared_profile_required") is not True:
            failures.append(f"{provider_id}: shared_profile_required must be true")
        if metadata.get("secret_export_allowed") is not False:
            failures.append(f"{provider_id}: secret_export_allowed must be false")

        plan = build_provider_readonly_check_plan(provider_id)
        if plan.get("ok") is not True:
            failures.append(f"{provider_id}: read-only check plan dry-run failed")
        if plan.get("state_change") is not False:
            failures.append(f"{provider_id}: check plan state_change must be false")
        for service in plan.get("services", []):
            if service.get("contains_forbidden_field") is not False:
                failures.append(f"{provider_id}/{service.get('service_key')}: forbidden field present")
            task = service.get("local_agent_task", {})
            if task.get("action") != "web_open_url_readonly":
                failures.append(f"{provider_id}/{service.get('service_key')}: wrong action")
            if task.get("execution_location") != "local_agent":
                failures.append(f"{provider_id}/{service.get('service_key')}: wrong execution location")
            if task.get("risk_level") != "read":
                failures.append(f"{provider_id}/{service.get('service_key')}: wrong risk level")

    blocked = build_blocked_operation_result("google", "cloud_console", "deploy")
    if blocked.get("local_agent_task") is not None or blocked.get("state_change") is not False:
        failures.append("blocked operation created an unsafe task")

    return not failures, failures or [
        "SITE_SSO_SUBDOMAIN_RUNTIME_BASELINE exists and is locked",
        "Google and Naver share user-present SSO profile rules",
        "registered subdomain services convert to local read-only tasks",
        "write-like SSO operations remain blocked without local-agent tasks",
    ]


def main() -> int:
    ok, findings = audit()
    for finding in findings:
        print(f"[{'PASS' if ok else 'FAIL'}] {finding}")
    print(f"RESULT={'PASS_SITE_SSO_SUBDOMAIN_RUNTIME_BASELINE' if ok else 'FAIL_SITE_SSO_SUBDOMAIN_RUNTIME_BASELINE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
