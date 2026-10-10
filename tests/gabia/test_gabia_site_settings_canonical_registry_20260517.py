"""Gabia Site Settings Canonical Registry Tests (2026-05-17).

[GABIA_SITE_SETTINGS_CANONICAL_REGISTRY_AUDIT_01]
DNS 저장/변경 없음. 서버 접속 없음. 쿠키 저장 없음.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_registry():
    import ai_orchestrator.connectors.gabia.site_settings_registry as m

    return m


def load_audit():
    import scripts.gabia.ops.audit_gabia_site_settings_canonical_registry as m

    return m


# ── 1~3. import ──────────────────────────────────────────────────────────────


def test_01_registry_importable():
    assert load_registry() is not None


def test_02_audit_importable():
    assert load_audit() is not None


def test_03_canonical_site_settings_not_empty():
    m = load_registry()
    assert len(m.CANONICAL_SITE_SETTINGS) > 0


# ── 4~9. canonical primary (autowork) ────────────────────────────────────────


def test_04_primary_fqdn():
    m = load_registry()
    e = m.get_canonical_primary()
    assert e.fqdn == "autowork.haehan-ai.kr"


def test_05_primary_target_ip():
    m = load_registry()
    e = m.get_canonical_primary()
    assert e.target_ip == "1.201.176.236"


def test_06_primary_status_current():
    m = load_registry()
    e = m.get_canonical_primary()
    assert e.status == m.STATUS_CURRENT


def test_07_primary_ssl_issued():
    m = load_registry()
    e = m.get_canonical_primary()
    assert e.ssl_status == "issued"


def test_08_primary_nginx_active():
    m = load_registry()
    e = m.get_canonical_primary()
    assert e.nginx_status == "active"


def test_09_primary_no_pending_ip():
    m = load_registry()
    e = m.get_canonical_primary()
    assert "PENDING" not in e.target_ip


# ── 10~15. HOLD 항목 (assistant / assistant-api) ──────────────────────────────


def test_10_assistant_entry_exists():
    m = load_registry()
    assert m.get_entry("assistant_haehan_ai_kr") is not None


def test_11_assistant_status_hold():
    m = load_registry()
    e = m.get_entry("assistant_haehan_ai_kr")
    assert e.status == m.STATUS_HOLD


def test_12_assistant_ssl_not_issued():
    m = load_registry()
    e = m.get_entry("assistant_haehan_ai_kr")
    assert e.ssl_status != "issued"


def test_13_assistant_api_entry_exists():
    m = load_registry()
    assert m.get_entry("assistant_api_haehan_ai_kr") is not None


def test_14_assistant_api_status_hold():
    m = load_registry()
    e = m.get_entry("assistant_api_haehan_ai_kr")
    assert e.status == m.STATUS_HOLD


def test_15_assistant_api_ssl_not_issued():
    m = load_registry()
    e = m.get_entry("assistant_api_haehan_ai_kr")
    assert e.ssl_status != "issued"


# ── 16~19. LEGACY 항목 (/orchestrator 경로) ───────────────────────────────────


def test_16_orchestrator_path_exists():
    m = load_registry()
    assert m.get_entry("orchestrator_path") is not None


def test_17_orchestrator_path_status_legacy():
    m = load_registry()
    e = m.get_entry("orchestrator_path")
    assert e.status == m.STATUS_LEGACY


def test_18_orchestrator_api_path_exists():
    m = load_registry()
    assert m.get_entry("orchestrator_api_path") is not None


def test_19_orchestrator_api_path_status_legacy():
    m = load_registry()
    e = m.get_entry("orchestrator_api_path")
    assert e.status == m.STATUS_LEGACY


# ── 20~22. PENDING 잔존 없음 (CURRENT 항목 기준) ─────────────────────────────


def test_20_no_pending_in_current_entries():
    m = load_registry()
    for e in m.list_by_status(m.STATUS_CURRENT):
        assert "PENDING" not in e.target_ip, f"{e.entry_id}에 PENDING IP 잔존"


def test_21_current_entries_have_real_ip():
    m = load_registry()
    for e in m.list_by_status(m.STATUS_CURRENT):
        parts = e.target_ip.split(".")
        assert len(parts) == 4, f"{e.entry_id} IP 형식 불일치: {e.target_ip}"


def test_22_list_by_status_current_not_empty():
    m = load_registry()
    assert len(m.list_by_status(m.STATUS_CURRENT)) >= 1


# ── 23~25. 기존 가비아 모듈 무결성 유지 ───────────────────────────────────────


def test_23_gabia_dns_models_intact():
    from ai_orchestrator.connectors.gabia.dns_models import make_assistant_subdomain_drafts

    d1, d2 = make_assistant_subdomain_drafts("1.2.3.4")
    assert d1.host == "assistant"
    assert d2.host == "assistant-api"


def test_24_gabia_browser_task_intact():
    from ai_orchestrator.connectors.gabia.browser_task import make_autowork_dns_task

    t = make_autowork_dns_task()
    assert t.target_domain == "haehan-ai.kr"
    assert t.safe_to_click_final_button is False


def test_25_gabia_work_registry_intact():
    from ai_orchestrator.connectors.gabia.dns_work_registry import GABIA_DNS_FINAL_SAVE

    assert GABIA_DNS_FINAL_SAVE.approval_required is True


# ── 26~28. audit 스크립트 통과 ───────────────────────────────────────────────


def test_26_audit_import_check_pass():
    m = load_audit()
    assert m.check_import() == []


def test_27_audit_canonical_primary_pass():
    m = load_audit()
    assert m.check_canonical_primary() == []


def test_28_audit_overall_verdict_ready():
    m = load_audit()
    all_errors = (
        m.check_import()
        + m.check_canonical_primary()
        + m.check_hold_entries()
        + m.check_legacy_entries()
        + m.check_no_pending_in_current()
        + m.check_old_models_not_broken()
    )
    verdict = m.get_overall_verdict(all_errors)
    assert verdict == m.VERDICT_READY, f"errors={all_errors}"
