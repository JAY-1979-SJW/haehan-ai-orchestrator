"""Audit the shared SSO subdomain runtime baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
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
    "scripts/google/common/subdomain_logic.py",
    "scripts/google/common/tab_logic.py",
    "unknown Google subdomains fail closed before execution",
    "hosts outside the requested Google tab must fail closed",
    "auto-login and credential replay stay false",
    "Occasional Site Login Handoff",
    "developed site module is not required",
    "user enters credentials directly",
    "read-only session check",
)


def _missing(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase not in text]


def _check_baseline_phrases() -> list[str]:
    text = BASELINE.read_text(encoding="utf-8", errors="replace")
    missing = _missing(text, REQUIRED_PHRASES)
    return ["SSO baseline missing phrase(s): " + ", ".join(missing)] if missing else []


def _check_provider_metadata(provider_id: str, metadata: dict) -> list[str]:
    failures: list[str] = []
    if metadata.get("auto_login") is not False:
        failures.append(f"{provider_id}: auto_login must be false")
    if metadata.get("user_present_required") is not True:
        failures.append(f"{provider_id}: user_present_required must be true")
    if metadata.get("shared_profile_required") is not True:
        failures.append(f"{provider_id}: shared_profile_required must be true")
    if metadata.get("secret_export_allowed") is not False:
        failures.append(f"{provider_id}: secret_export_allowed must be false")
    return failures


def _check_provider_service(provider_id: str, service: dict) -> list[str]:
    failures: list[str] = []
    if service.get("contains_forbidden_field") is not False:
        failures.append(f"{provider_id}/{service.get('service_key')}: forbidden field present")
    task = service.get("local_agent_task", {})
    if task.get("action") != "web_open_url_readonly":
        failures.append(f"{provider_id}/{service.get('service_key')}: wrong action")
    if task.get("execution_location") != "local_agent":
        failures.append(f"{provider_id}/{service.get('service_key')}: wrong execution location")
    if task.get("risk_level") != "read":
        failures.append(f"{provider_id}/{service.get('service_key')}: wrong risk level")
    return failures


def _check_provider(provider_id: str, expected_count: int) -> list[str]:
    from scripts.site_engine.readonly_check import build_provider_readonly_check_plan
    from scripts.site_engine.sso_runtime import build_login_entry_task
    from scripts.site_engine.subdomain_registry import get_provider

    failures: list[str] = []
    provider = get_provider(provider_id)
    if len(provider.services) != expected_count:
        failures.append(f"{provider_id}: service count mismatch {len(provider.services)}")
    login_task = build_login_entry_task(provider_id)
    failures.extend(_check_provider_metadata(provider_id, login_task.get("metadata", {})))

    plan = build_provider_readonly_check_plan(provider_id)
    if plan.get("ok") is not True:
        failures.append(f"{provider_id}: read-only check plan dry-run failed")
    if plan.get("state_change") is not False:
        failures.append(f"{provider_id}: check plan state_change must be false")
    for service in plan.get("services", []):
        failures.extend(_check_provider_service(provider_id, service))
    return failures


def _check_blocked_operation() -> list[str]:
    from scripts.site_engine.sso_runtime import build_blocked_operation_result

    blocked = build_blocked_operation_result("google", "cloud_console", "deploy")
    if blocked.get("local_agent_task") is not None or blocked.get("state_change") is not False:
        return ["blocked operation created an unsafe task"]
    return []


def _check_occasional_site_login() -> list[str]:
    from scripts.site_engine.sso_runtime import dry_run_occasional_site_login_task

    failures: list[str] = []
    occasional = dry_run_occasional_site_login_task("https://example.com/", site_label="example")
    occasional_task = occasional.get("local_agent_task", {})
    occasional_meta = occasional_task.get("metadata", {})
    if occasional.get("ok") is not True or occasional.get("state_change") is not False:
        failures.append("occasional site login dry-run failed")
    if occasional.get("contains_forbidden_field") is not False:
        failures.append("occasional site login contains forbidden field")
    if occasional_meta.get("auto_login") is not False:
        failures.append("occasional site login: auto_login must be false")
    if occasional_meta.get("developed_site_required") is not False:
        failures.append("occasional site login: developed_site_required must be false")
    policy = occasional_meta.get("occasional_site_login_policy", {})
    if policy.get("user_enters_credentials") is not True:
        failures.append("occasional site login: user must enter credentials")
    if policy.get("state_change_allowed") is not False:
        failures.append("occasional site login: state changes must be false")
    return failures


def _check_google_subdomain_logic() -> list[str]:
    from scripts.google.common import subdomain_logic

    failures: list[str] = []
    google_catalog = subdomain_logic.build_google_subdomain_logic_catalog()
    if google_catalog.get("auto_login") is not False:
        failures.append("google subdomain logic: auto_login must be false")
    if google_catalog.get("credential_replay_allowed") is not False:
        failures.append("google subdomain logic: credential replay must be false")
    gmail_read = subdomain_logic.classify_google_subdomain_operation("gmail", "read")
    if gmail_read.get("ok") is not True or gmail_read.get("state_change") is not False:
        failures.append("google subdomain logic: gmail read must build read-only task")
    gmail_send = subdomain_logic.classify_google_subdomain_operation("mail.google.com", "send")
    if gmail_send.get("approval_required") is not True or gmail_send.get("local_agent_task") is not None:
        failures.append("google subdomain logic: gmail send must be approval-gated without task")
    unknown = subdomain_logic.classify_google_subdomain_operation("unknown.google.example", "read")
    if unknown.get("reason") != "unknown_google_subdomain_fail_closed":
        failures.append("google subdomain logic: unknown hosts must fail closed")
    return failures


def _check_google_tab_logic() -> list[str]:
    from scripts.google.common import tab_logic

    failures: list[str] = []
    tab_catalog = tab_logic.build_all_tab_logic_catalog()
    if tab_catalog.get("tab_count") != 9:
        failures.append("google tab logic: expected 9 locked tabs")
    tab_read = tab_logic.classify_tab_operation("workspace", "gmail", "read")
    if tab_read.get("ok") is not True or tab_read.get("tab_key") != "workspace":
        failures.append("google tab logic: workspace gmail read must pass")
    tab_send = tab_logic.classify_tab_operation("workspace", "mail.google.com", "send")
    if tab_send.get("approval_required") is not True or tab_send.get("local_agent_task") is not None:
        failures.append("google tab logic: workspace gmail send must be approval-gated")
    out_of_tab = tab_logic.classify_tab_operation("search", "mail.google.com", "read")
    if out_of_tab.get("reason") != "google_subdomain_not_in_tab_fail_closed":
        failures.append("google tab logic: out-of-tab host must fail closed")
    return failures


def audit() -> tuple[bool, list[str]]:
    # 2026-09-29 STD-08(복잡도) 리팩터: 이 함수 하나(C901=33)에 있던 독립적인 체크 블록들을
    # 위 _check_*() 함수들로 분리했다. 각 체크는 서로 상태를 공유하지 않고 failures 리스트에
    # 추가만 하는 구조라, 순서·조건·문자열을 그대로 유지한 채 나누는 것이 안전했다.
    failures: list[str] = []
    if not BASELINE.exists():
        return False, ["docs/baseline/SITE_SSO_SUBDOMAIN_RUNTIME_BASELINE.md missing"]

    failures.extend(_check_baseline_phrases())

    from scripts.site_engine.subdomain_registry import validate_registry

    registry_errors = validate_registry()
    if registry_errors:
        failures.extend(registry_errors)

    expected_counts = {"google": 12, "naver": 11}
    for provider_id, expected_count in expected_counts.items():
        failures.extend(_check_provider(provider_id, expected_count))

    failures.extend(_check_blocked_operation())
    failures.extend(_check_occasional_site_login())
    failures.extend(_check_google_subdomain_logic())
    failures.extend(_check_google_tab_logic())

    return not failures, failures or [
        "SITE_SSO_SUBDOMAIN_RUNTIME_BASELINE exists and is locked",
        "Google and Naver share user-present SSO profile rules",
        "registered subdomain services convert to local read-only tasks",
        "occasional site login handoff stays user-present and read-only",
        "Google subdomain feature logic preserves login/read/approval boundaries",
        "Google tab feature logic exposes all locked tabs with fail-closed host boundaries",
        "write-like SSO operations remain blocked without local-agent tasks",
    ]


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "SITE_SSO_SUBDOMAIN_RUNTIME_BASELINE")


if __name__ == "__main__":
    raise SystemExit(main())
