"""Gabia Site Settings Canonical Registry Audit.

[GABIA_SITE_SETTINGS_CANONICAL_REGISTRY_AUDIT_01]

실제 운영 상태와 코드 registry가 일치하는지 정적으로 검증한다.
DNS 저장/변경 없음. 서버 접속 없음. 쿠키 저장 없음.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

VERDICT_READY = "GABIA_SITE_SETTINGS_CANONICAL_REGISTRY_READY"

# 확정 기준값
CANONICAL_PRIMARY_FQDN = "autowork.haehan-ai.kr"
CANONICAL_TARGET_IP = "1.201.176.236"
CANONICAL_SSL_STATUS = "issued"
CANONICAL_NGINX_STATUS = "active"
CANONICAL_STATUS = "CURRENT"

HOLD_ENTRIES = ["assistant_haehan_ai_kr", "assistant_api_haehan_ai_kr"]
LEGACY_ENTRIES = ["orchestrator_path", "orchestrator_api_path"]

FORBIDDEN_PENDING_IN_CURRENT = "PENDING_USER_CONFIRMATION"


def check_import() -> list[str]:
    errors = []
    try:
        import ai_orchestrator.connectors.gabia.site_settings_registry as m

        _ = m.CANONICAL_SITE_SETTINGS
        _ = m.get_canonical_primary
    except Exception as e:  # noqa: BLE001 - 가비아 도메인 정본 레지스트리 import/조회 자체검증 스크립트 - 실패를 errors 목록에 추가(감사 리포트, 런타임 게이트 아님)
        errors.append(f"import 실패: {e}")
    return errors


def check_canonical_primary() -> list[str]:
    errors = []
    from ai_orchestrator.connectors.gabia.site_settings_registry import get_canonical_primary

    try:
        entry = get_canonical_primary()
    except Exception as e:  # noqa: BLE001 - 가비아 도메인 정본 레지스트리 import/조회 자체검증 스크립트 - 실패를 errors 목록에 추가(감사 리포트, 런타임 게이트 아님)
        errors.append(f"get_canonical_primary 오류: {e}")
        return errors

    if entry.fqdn != CANONICAL_PRIMARY_FQDN:
        errors.append(f"primary fqdn 불일치: {entry.fqdn} != {CANONICAL_PRIMARY_FQDN}")
    if entry.target_ip != CANONICAL_TARGET_IP:
        errors.append(f"target_ip 불일치: {entry.target_ip} != {CANONICAL_TARGET_IP}")
    if entry.ssl_status != CANONICAL_SSL_STATUS:
        errors.append(f"ssl_status 불일치: {entry.ssl_status} != {CANONICAL_SSL_STATUS}")
    if entry.nginx_status != CANONICAL_NGINX_STATUS:
        errors.append(f"nginx_status 불일치: {entry.nginx_status} != {CANONICAL_NGINX_STATUS}")
    if entry.status != CANONICAL_STATUS:
        errors.append(f"status 불일치: {entry.status} != {CANONICAL_STATUS}")
    if FORBIDDEN_PENDING_IN_CURRENT in entry.target_ip:
        errors.append(f"CURRENT 항목에 PENDING 값 잔존: {entry.target_ip}")
    return errors


def check_hold_entries() -> list[str]:
    errors = []
    from ai_orchestrator.connectors.gabia.site_settings_registry import STATUS_HOLD, get_entry

    for eid in HOLD_ENTRIES:
        e = get_entry(eid)
        if e is None:
            errors.append(f"HOLD 항목 누락: {eid}")
            continue
        if e.status != STATUS_HOLD:
            errors.append(f"{eid} status가 HOLD 아님: {e.status}")
        if e.ssl_status == "issued":
            errors.append(f"{eid} HOLD인데 ssl_status=issued — 불일치")
    return errors


def check_legacy_entries() -> list[str]:
    errors = []
    from ai_orchestrator.connectors.gabia.site_settings_registry import STATUS_LEGACY, get_entry

    for eid in LEGACY_ENTRIES:
        e = get_entry(eid)
        if e is None:
            errors.append(f"LEGACY 항목 누락: {eid}")
            continue
        if e.status != STATUS_LEGACY:
            errors.append(f"{eid} status가 LEGACY 아님: {e.status}")
    return errors


def check_no_pending_in_current() -> list[str]:
    errors = []
    from ai_orchestrator.connectors.gabia.site_settings_registry import STATUS_CURRENT, list_by_status

    for e in list_by_status(STATUS_CURRENT):
        if FORBIDDEN_PENDING_IN_CURRENT in e.target_ip:
            errors.append(f"CURRENT 항목 {e.entry_id}에 PENDING IP 잔존")
    return errors


def check_old_models_not_broken() -> list[str]:
    errors = []
    try:
        import ai_orchestrator.connectors.gabia.dns_models as m

        _ = m.GabiaDnsRecordDraft
        _ = m.make_assistant_subdomain_drafts
    except Exception as e:  # noqa: BLE001 - 가비아 도메인 정본 레지스트리 import/조회 자체검증 스크립트 - 실패를 errors 목록에 추가(감사 리포트, 런타임 게이트 아님)
        errors.append(f"gabia_dns_models import 실패: {e}")
    try:
        import ai_orchestrator.connectors.gabia.browser_task as m_task

        _ = m_task.GabiaBrowserTask  # type: ignore[attr-defined]  # 이 스크립트 자체가 "실제 있는지" 검증 대상 — 없으면 위 except 가 errors 에 기록
        _ = m_task.make_autowork_dns_task  # type: ignore[attr-defined]
    except Exception as e:  # noqa: BLE001 - 가비아 도메인 정본 레지스트리 import/조회 자체검증 스크립트 - 실패를 errors 목록에 추가(감사 리포트, 런타임 게이트 아님)
        errors.append(f"gabia_browser_task import 실패: {e}")
    try:
        import ai_orchestrator.connectors.gabia.dns_work_registry as m_work

        _ = m_work.GABIA_DNS_WORK_TRADE  # type: ignore[attr-defined]  # 이 스크립트 자체가 "실제 있는지" 검증 대상 — 없으면 위 except 가 errors 에 기록
    except Exception as e:  # noqa: BLE001 - 가비아 도메인 정본 레지스트리 import/조회 자체검증 스크립트 - 실패를 errors 목록에 추가(감사 리포트, 런타임 게이트 아님)
        errors.append(f"gabia_dns_work_registry import 실패: {e}")
    return errors


def get_overall_verdict(all_errors: list[str]) -> str:
    return VERDICT_READY if not all_errors else "FAIL"


def main():
    print("[GABIA_SITE_SETTINGS_CANONICAL_REGISTRY_AUDIT]")
    print()
    all_errors = []

    checks = [
        ("import", check_import),
        ("canonical_primary", check_canonical_primary),
        ("hold_entries", check_hold_entries),
        ("legacy_entries", check_legacy_entries),
        ("no_pending_current", check_no_pending_in_current),
        ("old_models_intact", check_old_models_not_broken),
    ]

    for label, fn in checks:
        e = fn()
        status = "PASS" if not e else "FAIL"
        print(f"[{label:<22}] {status}")
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
