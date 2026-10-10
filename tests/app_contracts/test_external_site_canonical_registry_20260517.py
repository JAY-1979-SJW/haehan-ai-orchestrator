"""External Site Canonical Registry Tests (2026-05-17).

[ASSISTANT_EXTERNAL_SITE_MANAGEMENT_CANONICAL_REGISTRY_01]
실제 사이트 접속 없음. DNS 변경 없음. 쿠키 저장 없음.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def reg():
    import ai_orchestrator.external_sites.provider_registry as m

    return m


def models():
    import ai_orchestrator.external_sites.provider_models as m

    return m


def playbook():
    import ai_orchestrator.external_sites.navigation_playbook as m

    return m


def auth():
    import ai_orchestrator.external_sites.auth_policy_registry as m

    return m


def gates():
    import ai_orchestrator.external_sites.approval_gate_registry as m

    return m


def audit():
    import tools.audits.app.audit_external_site_canonical_registry as m

    return m


# ── 1~4. import / provider 수 / 필수 provider / unique ───────────────────────


def test_01_provider_registry_importable():
    assert reg() is not None


def test_02_provider_count_gte_12():
    assert len(reg().PROVIDER_REGISTRY) >= 12


def test_03_required_providers_exist():
    r = reg()
    for pid in [
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
    ]:
        assert r.get_provider(pid) is not None, f"{pid} 없음"


def test_04_provider_ids_unique():
    r = reg()
    ids = [p.provider_id for p in r.PROVIDER_REGISTRY]
    assert len(ids) == len(set(ids))


# ── 5~9. GABIA ────────────────────────────────────────────────────────────────


def test_05_gabia_status_current():
    p = reg().get_provider("GABIA")
    assert p.current_status == models().STATUS_CURRENT


def test_06_gabia_management_url_dns():
    p = reg().get_provider("GABIA")
    assert "dns.gabia.com" in p.management_url


def test_07_gabia_guessed_url_false():
    p = reg().get_provider("GABIA")
    assert p.guessed_url_allowed is False


def test_08_gabia_cookie_storage_false():
    p = reg().get_provider("GABIA")
    assert p.cookie_storage_allowed is False


def test_09_gabia_desktop_app_required():
    p = reg().get_provider("GABIA")
    assert p.desktop_app_required is True


# ── 10~11. KAKAO ──────────────────────────────────────────────────────────────


def test_10_kakao_category_social_login():
    p = reg().get_provider("KAKAO")
    assert p.category == models().CAT_SOCIAL_LOGIN


def test_11_kakao_server_remote_login_false():
    p = reg().get_provider("KAKAO")
    assert p.server_remote_login_allowed is False


# ── 12~13. NAVER / SMARTSTORE ────────────────────────────────────────────────


def test_12_naver_exists():
    assert reg().get_provider("NAVER") is not None


def test_13_naver_smartstore_exists():
    assert reg().get_provider("NAVER_SMARTSTORE") is not None


# ── 14. GOOGLE ───────────────────────────────────────────────────────────────


def test_14_google_official_api_preferred():
    p = reg().get_provider("GOOGLE")
    assert p.official_api_preferred is True


# ── 15~19. HIWORKS / G2B / 공공행정 ─────────────────────────────────────────


def test_15_hiworks_exists():
    assert reg().get_provider("HIWORKS") is not None


def test_16_g2b_nara_risk_critical():
    p = reg().get_provider("G2B_NARA")
    assert p.risk_level == models().RISK_CRITICAL


def test_17_hometax_exists():
    assert reg().get_provider("HOMETAX") is not None


def test_18_wetax_exists():
    assert reg().get_provider("WETAX") is not None


def test_19_government24_exists():
    assert reg().get_provider("GOVERNMENT24") is not None


# ── 20~22. 전체 provider 공통 정책 ───────────────────────────────────────────


def test_20_all_providers_cookie_storage_false():
    r = reg()
    for p in r.PROVIDER_REGISTRY:
        assert p.cookie_storage_allowed is False, f"{p.provider_id} cookie_storage_allowed=True"


def test_21_all_providers_server_remote_login_false():
    r = reg()
    for p in r.PROVIDER_REGISTRY:
        assert p.server_remote_login_allowed is False, f"{p.provider_id} server_remote_login_allowed=True"


def test_22_critical_providers_approval_gate_required():
    r = reg()
    m = models()
    for p in r.PROVIDER_REGISTRY:
        if p.risk_level == m.RISK_CRITICAL:
            assert p.approval_gate_required is True, f"{p.provider_id} CRITICAL인데 approval_gate_required=False"


# ── 23~25. navigation playbook ───────────────────────────────────────────────


def test_23_navigation_playbook_importable():
    assert playbook() is not None


def test_24_gabia_playbook_no_url_guessing():
    pb = playbook().get_playbook("GABIA")
    assert pb is not None
    assert pb.forbidden_url_guessing is True


def test_25_gabia_playbook_success_markers_exist():
    pb = playbook().get_playbook("GABIA")
    assert len(pb.success_markers) > 0


# ── 26. auth policy ──────────────────────────────────────────────────────────


def test_26_auth_policy_registry_importable():
    assert auth() is not None


# ── 27~31. approval gates ────────────────────────────────────────────────────


def test_27_approval_gate_registry_importable():
    assert gates() is not None


def test_28_dns_record_save_gate_exists():
    assert gates().get_gate("DNS_RECORD_SAVE") is not None


def test_29_bid_submit_gate_exists():
    assert gates().get_gate("BID_SUBMIT") is not None


def test_30_certificate_sign_gate_exists():
    assert gates().get_gate("CERTIFICATE_SIGN") is not None


def test_31_payment_gate_exists():
    assert gates().get_gate("PAYMENT") is not None


# ── 32. critical gate auto_execute=False ────────────────────────────────────


def test_32_all_critical_gates_auto_execute_false():
    g = gates()
    violations = g.assert_all_critical_gates_blocked()
    assert violations == [], f"CRITICAL gate 위반: {violations}"


# ── 33~35. 전역 정책 검사 ────────────────────────────────────────────────────


def test_33_no_github_actions_dependency():
    src_files = [
        REPO_ROOT / "ai_orchestrator/external_sites/provider_registry.py",
        REPO_ROOT / "ai_orchestrator/external_sites/approval_gate_registry.py",
        REPO_ROOT / "tools/audits/app/audit_external_site_canonical_registry.py",
    ]
    for f in src_files:
        content = f.read_text(encoding="utf-8")
        assert "github.com/workflows" not in content.lower(), f"{f.name}에 GitHub Actions 의존"
        assert "uses: actions/" not in content.lower(), f"{f.name}에 GitHub Actions 의존"


def test_34_no_cookie_storage_allowed_provider():
    r = reg()
    bad = [p.provider_id for p in r.PROVIDER_REGISTRY if p.cookie_storage_allowed]
    assert r.PROVIDER_REGISTRY, "r.PROVIDER_REGISTRY 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert bad == [], f"쿠키 저장 허용 provider: {bad}"


def test_35_no_server_remote_login_allowed_provider():
    r = reg()
    bad = [p.provider_id for p in r.PROVIDER_REGISTRY if p.server_remote_login_allowed]
    assert r.PROVIDER_REGISTRY, "r.PROVIDER_REGISTRY 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert bad == [], f"서버 원격 로그인 허용 provider: {bad}"


# ── 36. audit 최종 verdict ───────────────────────────────────────────────────


def test_36_audit_verdict_ready():
    a = audit()
    all_errors = (
        a.check_01_provider_count()
        + a.check_02_required_providers()
        + a.check_03_unique_provider_ids()
        + a.check_04_gabia_policy()
        + a.check_05_kakao_policy()
        + a.check_06_google_api_preferred()
        + a.check_07_critical_providers()
        + a.check_08_no_cookie_storage()
        + a.check_09_no_server_remote_login()
        + a.check_10_no_headless_critical()
        + a.check_11_approval_gates()
        + a.check_12_critical_gates_blocked()
        + a.check_13_navigation_playbooks()
        + a.check_14_gabia_playbook_policy()
    )
    verdict = a.get_overall_verdict(all_errors)
    assert verdict == a.VERDICT_READY, f"errors={all_errors}"
