"""Gabia site_engine 연결 및 adapter boundary 테스트."""
from __future__ import annotations


# ── 1. profile 검증 ─────────────────────────────────────────────────────────

def test_gabia_profile_import():
    from scripts.gabia.site_profile import GABIA_PROFILE
    assert GABIA_PROFILE.key == "gabia"


def test_gabia_profile_display_name():
    from scripts.gabia.site_profile import GABIA_PROFILE
    assert "Gabia" in GABIA_PROFILE.display_name


def test_read_policy_is_read_only_allowed():
    from scripts.gabia.site_profile import GABIA_PROFILE
    from scripts.site_engine.site_types import GateDecision, SiteCapability
    policy = GABIA_PROFILE.action_policies.get(SiteCapability.READ)
    assert policy is not None
    assert policy.gate == GateDecision.READ_ONLY_ALLOWED
    assert policy.requires_approval is False


def test_submit_approval_required():
    from scripts.gabia.site_profile import GABIA_PROFILE
    from scripts.site_engine.site_types import SiteCapability
    policy = GABIA_PROFILE.action_policies.get(SiteCapability.SUBMIT)
    assert policy is not None
    assert policy.requires_approval is True
    assert policy.is_irreversible is True


def test_delete_approval_required():
    from scripts.gabia.site_profile import GABIA_PROFILE
    from scripts.site_engine.site_types import SiteCapability
    policy = GABIA_PROFILE.action_policies.get(SiteCapability.DELETE)
    assert policy is not None
    assert policy.requires_approval is True
    assert policy.is_irreversible is True


def test_sign_is_blocked():
    from scripts.gabia.site_profile import GABIA_PROFILE
    from scripts.site_engine.site_types import GateDecision, SiteCapability
    policy = GABIA_PROFILE.action_policies.get(SiteCapability.SIGN)
    assert policy is not None
    assert policy.gate == GateDecision.BLOCKED


# ── 2. gate 검증 ─────────────────────────────────────────────────────────────

def test_gate_public_read_allowed():
    from scripts.gabia.gates import gate_gabia_public_read
    from scripts.site_engine.execution_gate import ExecutionGateResult
    result = gate_gabia_public_read()
    assert isinstance(result, ExecutionGateResult)
    assert result.allowed is True


def test_gate_login_blocked():
    """로그인은 SIGN capability → BLOCKED."""
    from scripts.gabia.gates import gate_gabia_login
    result = gate_gabia_login()
    assert result.is_blocked is True


def test_gate_credential_extract_blocked():
    """비밀번호/세션/쿠키 추출 차단."""
    from scripts.gabia.gates import gate_gabia_credential_extract
    result = gate_gabia_credential_extract()
    assert result.is_blocked is True


def test_gate_payment_blocked():
    """결제/청구는 SIGN capability → BLOCKED."""
    from scripts.gabia.gates import gate_gabia_payment
    result = gate_gabia_payment()
    assert result.is_blocked is True


def test_gate_dns_change_approval_required():
    from scripts.gabia.gates import gate_gabia_dns_change
    from scripts.site_engine.site_types import GateDecision
    result = gate_gabia_dns_change()
    assert result.gate_decision == GateDecision.APPROVAL_REQUIRED
    assert result.requires_approval is True


def test_gate_dns_delete_approval_required():
    from scripts.gabia.gates import gate_gabia_dns_delete
    from scripts.site_engine.site_types import GateDecision
    result = gate_gabia_dns_delete()
    assert result.gate_decision == GateDecision.APPROVAL_REQUIRED
    assert result.requires_approval is True


def test_gate_domain_renew_approval_required():
    from scripts.gabia.gates import gate_gabia_domain_renew
    from scripts.site_engine.site_types import GateDecision
    result = gate_gabia_domain_renew()
    assert result.gate_decision == GateDecision.APPROVAL_REQUIRED
    assert result.requires_approval is True


def test_gate_hosting_change_approval_required():
    from scripts.gabia.gates import gate_gabia_hosting_change
    from scripts.site_engine.site_types import GateDecision
    result = gate_gabia_hosting_change()
    assert result.gate_decision == GateDecision.APPROVAL_REQUIRED
    assert result.requires_approval is True


def test_gate_account_read_not_plain_allowed():
    """로그인 후 계정 조회는 서버 사이드 브라우저 금지."""
    from scripts.gabia.gates import gate_gabia_account_read
    result = gate_gabia_account_read()
    # is_server_forbidden_site=True 이므로 SERVER_BROWSER_ALLOWED 아님
    from scripts.site_engine.site_types import GateDecision
    assert result.gate_decision != GateDecision.SERVER_BROWSER_ALLOWED


# ── 3. validator 검증 ────────────────────────────────────────────────────────

def test_validate_no_plain_secret_clean():
    from scripts.gabia.validators import validate_gabia_no_plain_secret
    result = validate_gabia_no_plain_secret({"domain": "haehan-ai.kr", "status": "active"})
    assert result.is_valid is True


def test_validate_no_plain_secret_detects_secret():
    from scripts.gabia.validators import validate_gabia_no_plain_secret
    result = validate_gabia_no_plain_secret({"secret": "abc123"})
    assert result.is_valid is False


# ── 4. router import smoke ───────────────────────────────────────────────────

def test_router_import_smoke():
    import scripts.gabia.router  # noqa: F401


def test_router_status_keys():
    from scripts.gabia.router import __status__
    tasks = __status__["tasks"]
    assert "status" in tasks
    assert "dns" in tasks
    assert "login" in tasks
    assert "domain" in tasks
    assert "payment" in tasks


# ── 5. cross-domain import 금지 검증 ────────────────────────────────────────

def _check_no_cross_import(forbidden_prefix: str) -> None:
    import ast
    from pathlib import Path
    gabia_dir = Path("scripts/gabia")
    if not gabia_dir.exists():
        return
    for py_file in gabia_dir.glob("*.py"):
        source = py_file.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif node.module:
                    names = [node.module]
                for name in names:
                    assert not name.startswith(forbidden_prefix), (
                        f"{py_file}: cross-domain import '{name}' forbidden"
                    )


def test_gabia_does_not_import_hiworks():
    _check_no_cross_import("scripts.hiworks")


def test_gabia_does_not_import_eum():
    _check_no_cross_import("scripts.eum")


def test_gabia_does_not_import_google():
    _check_no_cross_import("scripts.google")


def test_gabia_does_not_import_g2b():
    _check_no_cross_import("scripts.g2b")


def test_gabia_does_not_import_youtube():
    _check_no_cross_import("scripts.youtube")


# ── 6. gate/audit regression ────────────────────────────────────────────────

def test_forbidden_import_gate_zero():
    """FORBIDDEN_IMPORT 게이트가 0을 유지해야 한다."""
    import json
    from pathlib import Path
    report_path = Path("data/codebase_layer_audit_latest.json")
    if not report_path.exists():
        return  # audit 미실행 환경에서는 스킵
    d = json.loads(report_path.read_text(encoding="utf-8"))
    fi = [i for i in d.get("issues", []) if i["code"] == "FORBIDDEN_IMPORT"]
    assert len(fi) == 0, f"FORBIDDEN_IMPORT violations: {fi}"


def test_security_pattern_gate_zero():
    """SECURITY_PATTERN 게이트가 0을 유지해야 한다."""
    import json
    from pathlib import Path
    report_path = Path("data/codebase_layer_audit_latest.json")
    if not report_path.exists():
        return
    d = json.loads(report_path.read_text(encoding="utf-8"))
    sp = [i for i in d.get("issues", []) if i["code"] == "SECURITY_PATTERN"]
    assert len(sp) == 0, f"SECURITY_PATTERN violations: {sp}"
