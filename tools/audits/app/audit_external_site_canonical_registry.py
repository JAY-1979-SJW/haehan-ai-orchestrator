"""External Site Canonical Registry Audit.

[ASSISTANT_EXTERNAL_SITE_MANAGEMENT_CANONICAL_REGISTRY_01]

실제 사이트 접속 없음. DNS 변경 없음. 쿠키 저장 없음.
정적 정책 검증만 수행한다.

성공 verdict: EXTERNAL_SITE_CANONICAL_REGISTRY_READY
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(REPO_ROOT))

VERDICT_READY = "EXTERNAL_SITE_CANONICAL_REGISTRY_READY"

REQUIRED_PROVIDERS = [
    "GABIA",
    "KAKAO",
    "NAVER",
    "NAVER_SMARTSTORE",
    "GOOGLE",
    "HIWORKS",
    "G2B_NARA",
    "HOMETAX",
    "WETAX",
    "GOVERNMENT24",
    "EMAIL_GENERIC",
    "BANK_GENERIC",
]

REQUIRED_GATES = [
    "DNS_RECORD_SAVE",
    "DOMAIN_TRANSFER",
    "NAMESERVER_CHANGE",
    "PAYMENT",
    "BID_SUBMIT",
    "CERTIFICATE_SIGN",
    "TAX_SUBMIT",
    "EMAIL_SEND",
    "SMARTSTORE_PRODUCT_UPDATE",
    "SMARTSTORE_ORDER_ACTION",
    "ACCOUNT_CHANGE",
    "FILE_UPLOAD_FINAL_SUBMIT",
    "DOCUMENT_FINAL_SUBMIT",
]

REQUIRED_PLAYBOOKS = ["GABIA", "NAVER", "GOOGLE", "HIWORKS", "G2B_NARA"]


def check_01_provider_count() -> list[str]:
    from ai_orchestrator.external_sites.provider_registry import PROVIDER_REGISTRY

    if len(PROVIDER_REGISTRY) < 12:
        return [f"provider 수 부족: {len(PROVIDER_REGISTRY)} < 12"]
    return []


def check_02_required_providers() -> list[str]:
    from ai_orchestrator.external_sites.provider_registry import get_provider

    errors = []
    for pid in REQUIRED_PROVIDERS:
        if get_provider(pid) is None:
            errors.append(f"provider 누락: {pid}")
    return errors


def check_03_unique_provider_ids() -> list[str]:
    from ai_orchestrator.external_sites.provider_registry import PROVIDER_REGISTRY

    seen, errors = set(), []
    for p in PROVIDER_REGISTRY:
        if p.provider_id in seen:
            errors.append(f"provider_id 중복: {p.provider_id}")
        seen.add(p.provider_id)
    return errors


def check_04_gabia_policy() -> list[str]:
    from ai_orchestrator.external_sites.provider_models import STATUS_CURRENT
    from ai_orchestrator.external_sites.provider_registry import get_provider

    p = get_provider("GABIA")
    errors = []
    if p is None:
        return ["GABIA provider 없음"]
    if p.current_status != STATUS_CURRENT:
        errors.append(f"GABIA current_status != CURRENT: {p.current_status}")
    if "dns.gabia.com" not in p.management_url:
        errors.append(f"GABIA management_url에 dns.gabia.com 없음: {p.management_url}")
    if p.guessed_url_allowed:
        errors.append("GABIA guessed_url_allowed=True 위반")
    if p.cookie_storage_allowed:
        errors.append("GABIA cookie_storage_allowed=True 위반")
    if not p.desktop_app_required:
        errors.append("GABIA desktop_app_required=False 위반")
    if p.server_remote_login_allowed:
        errors.append("GABIA server_remote_login_allowed=True 위반")
    return errors


def check_05_kakao_policy() -> list[str]:
    from ai_orchestrator.external_sites.provider_models import CAT_SOCIAL_LOGIN
    from ai_orchestrator.external_sites.provider_registry import get_provider

    p = get_provider("KAKAO")
    errors = []
    if p is None:
        return ["KAKAO provider 없음"]
    if p.category != CAT_SOCIAL_LOGIN:
        errors.append(f"KAKAO category != SOCIAL_LOGIN_PROVIDER: {p.category}")
    if p.server_remote_login_allowed:
        errors.append("KAKAO server_remote_login_allowed=True 위반")
    return errors


def check_06_google_api_preferred() -> list[str]:
    from ai_orchestrator.external_sites.provider_registry import get_provider

    p = get_provider("GOOGLE")
    if p is None:
        return ["GOOGLE provider 없음"]
    if not p.official_api_preferred:
        return ["GOOGLE official_api_preferred=False 위반"]
    return []


def check_07_critical_providers() -> list[str]:
    from ai_orchestrator.external_sites.provider_models import RISK_CRITICAL
    from ai_orchestrator.external_sites.provider_registry import get_provider

    errors = []
    critical_pids = ["G2B_NARA", "NAVER_SMARTSTORE", "HOMETAX", "WETAX", "GOVERNMENT24", "BANK_GENERIC"]
    for pid in critical_pids:
        p = get_provider(pid)
        if p is None:
            errors.append(f"{pid} 누락")
            continue
        if p.risk_level != RISK_CRITICAL:
            errors.append(f"{pid} risk_level != CRITICAL: {p.risk_level}")
        if not p.approval_gate_required:
            errors.append(f"{pid} approval_gate_required=False 위반")
    return errors


def check_08_no_cookie_storage() -> list[str]:
    from ai_orchestrator.external_sites.auth_policy_registry import assert_no_cookie_storage

    return assert_no_cookie_storage()


def check_09_no_server_remote_login() -> list[str]:
    from ai_orchestrator.external_sites.auth_policy_registry import assert_no_server_remote_login

    return assert_no_server_remote_login()


def check_10_no_headless_critical() -> list[str]:
    from ai_orchestrator.external_sites.auth_policy_registry import assert_no_headless_for_critical

    return assert_no_headless_for_critical()


def check_11_approval_gates() -> list[str]:
    from ai_orchestrator.external_sites.approval_gate_registry import get_gate

    errors = []
    for gid in REQUIRED_GATES:
        if get_gate(gid) is None:
            errors.append(f"gate 누락: {gid}")
    return errors


def check_12_critical_gates_blocked() -> list[str]:
    from ai_orchestrator.external_sites.approval_gate_registry import assert_all_critical_gates_blocked

    return assert_all_critical_gates_blocked()


def check_13_navigation_playbooks() -> list[str]:
    from ai_orchestrator.external_sites.navigation_playbook import get_playbook

    errors = []
    for pid in REQUIRED_PLAYBOOKS:
        if get_playbook(pid) is None:
            errors.append(f"playbook 누락: {pid}")
    return errors


def check_14_gabia_playbook_policy() -> list[str]:
    from ai_orchestrator.external_sites.navigation_playbook import get_playbook

    pb = get_playbook("GABIA")
    errors = []
    if pb is None:
        return ["GABIA playbook 없음"]
    if not pb.forbidden_url_guessing:
        errors.append("GABIA playbook forbidden_url_guessing=False 위반")
    if not pb.success_markers:
        errors.append("GABIA playbook success_markers 없음")
    if "dns.gabia.com" not in "".join(pb.known_management_urls):
        errors.append("GABIA playbook known_management_urls에 dns.gabia.com 없음")
    return errors


def get_overall_verdict(all_errors: list[str]) -> str:
    return VERDICT_READY if not all_errors else "FAIL"


def main():
    print("[EXTERNAL_SITE_CANONICAL_REGISTRY_AUDIT]")
    print()

    checks = [
        ("01_provider_count", check_01_provider_count),
        ("02_required_providers", check_02_required_providers),
        ("03_unique_ids", check_03_unique_provider_ids),
        ("04_gabia_policy", check_04_gabia_policy),
        ("05_kakao_policy", check_05_kakao_policy),
        ("06_google_api_preferred", check_06_google_api_preferred),
        ("07_critical_providers", check_07_critical_providers),
        ("08_no_cookie_storage", check_08_no_cookie_storage),
        ("09_no_server_remote", check_09_no_server_remote_login),
        ("10_no_headless_critical", check_10_no_headless_critical),
        ("11_approval_gates", check_11_approval_gates),
        ("12_critical_gates_blocked", check_12_critical_gates_blocked),
        ("13_navigation_playbooks", check_13_navigation_playbooks),
        ("14_gabia_playbook", check_14_gabia_playbook_policy),
    ]

    all_errors = []
    for label, fn in checks:
        e = fn()
        print(f"[{label:<28}] {'PASS' if not e else 'FAIL'}")
        for err in e:
            print(f"  ERROR: {err}")
        all_errors += e

    verdict = get_overall_verdict(all_errors)
    print()
    print(f"VERDICT: {verdict}")
    print("=" * 70)
    sys.exit(0 if verdict == VERDICT_READY else 1)


if __name__ == "__main__":
    main()
