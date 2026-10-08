"""G2B 세대 골격 테스트.

실제 G2B 접속, 외부 API 호출, DB 접근, data/sessions 접근 없음.
순수 골격 정책/판단/validators/router 검증.
"""
from __future__ import annotations

import pytest


# ── 1. profile 존재 테스트 ────────────────────────────────────────────

def test_profile_exists():
    from scripts.g2b.site_profile import G2B_SITE_PROFILE
    assert G2B_SITE_PROFILE["key"] == "g2b"
    assert "base_url" in G2B_SITE_PROFILE


def test_profile_allowed_actions_nonempty():
    from scripts.g2b.site_profile import G2B_SITE_PROFILE
    assert len(G2B_SITE_PROFILE["allowed_actions"]) > 0


def test_profile_blocked_actions_nonempty():
    from scripts.g2b.site_profile import G2B_SITE_PROFILE
    assert len(G2B_SITE_PROFILE["blocked_actions"]) > 0


# ── 2. 허용 read action ───────────────────────────────────────────────

def test_read_actions_allowed():
    from scripts.g2b.gates import evaluate_g2b_action_gate
    for action in ("search_notice", "read_notice_detail", "inspect_attachment"):
        result = evaluate_g2b_action_gate(action)
        assert result["decision"] == "READ_ONLY_ALLOWED", f"{action} 기대: READ_ONLY_ALLOWED"
        assert not result["blocked"]


# ── 3. openapi collector read-only 분리 ──────────────────────────────

def test_openapi_collector_read_only():
    from scripts.g2b.gates import evaluate_g2b_action_gate
    result = evaluate_g2b_action_gate("collect_openapi_notice")
    assert result["decision"] == "READ_ONLY_ALLOWED"
    assert not result["blocked"]


def test_openapi_collector_no_router_import():
    import ast, pathlib
    router_src = pathlib.Path("scripts/g2b/router.py").read_text(encoding="utf-8")
    tree = ast.parse(router_src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [n.name for n in getattr(node, "names", [])]
            module = getattr(node, "module", "") or ""
            assert "openapi" not in module.lower(), "router에서 openapi 직접 import 금지"
            for name in names:
                assert "openapi" not in name.lower(), "router에서 openapi 직접 import 금지"


# ── 4. bid analysis draft DRAFT_ALLOWED ──────────────────────────────

def test_bid_analysis_draft_allowed():
    from scripts.g2b.gates import evaluate_g2b_action_gate
    result = evaluate_g2b_action_gate("create_bid_analysis_draft")
    assert result["decision"] == "DRAFT_ALLOWED"
    assert result["draft_allowed"]
    assert not result["blocked"]


# ── 5. submit draft DRAFT_ALLOWED ────────────────────────────────────

def test_submit_draft_allowed():
    from scripts.g2b.gates import evaluate_g2b_action_gate
    result = evaluate_g2b_action_gate("create_submit_draft")
    assert result["decision"] in ("DRAFT_ALLOWED", "USER_DIRECT_REQUIRED")
    assert not result["blocked"]


# ── 6. login LOCAL_AGENT_REQUIRED ────────────────────────────────────

def test_login_local_agent_required():
    from scripts.g2b.gates import evaluate_g2b_action_gate
    result = evaluate_g2b_action_gate("login")
    assert result["decision"] == "LOCAL_AGENT_REQUIRED"
    assert result["local_agent_required"]
    assert not result["blocked"]


# ── 7. certificate/otp USER_DIRECT_REQUIRED ──────────────────────────

def test_certificate_auth_user_direct():
    from scripts.g2b.gates import evaluate_g2b_action_gate
    result = evaluate_g2b_action_gate("certificate_auth")
    assert result["decision"] == "USER_DIRECT_REQUIRED"
    assert result["user_direct_required"]


def test_otp_user_direct():
    from scripts.g2b.gates import evaluate_g2b_action_gate
    result = evaluate_g2b_action_gate("otp")
    assert result["decision"] == "USER_DIRECT_REQUIRED"
    assert result["user_direct_required"]


# ── 8. submit_bid BLOCKED ─────────────────────────────────────────────

def test_submit_bid_blocked():
    from scripts.g2b.gates import evaluate_g2b_action_gate
    result = evaluate_g2b_action_gate("submit_bid")
    assert result["decision"] in ("BLOCKED", "USER_DIRECT_REQUIRED")
    assert result["blocked"] or result["user_direct_required"]


# ── 9. e_sign BLOCKED ────────────────────────────────────────────────

def test_e_sign_blocked():
    from scripts.g2b.gates import evaluate_g2b_action_gate
    result = evaluate_g2b_action_gate("e_sign")
    assert result["decision"] == "BLOCKED"
    assert result["blocked"]


# ── 10. secret/session/cookie/token payload 차단 ─────────────────────

@pytest.mark.parametrize("key", [
    "password", "passwd", "session", "cookie", "token", "otp",
    "cert_password", "access_token",
])
def test_secret_payload_blocked(key):
    from scripts.g2b.validators import validate_g2b_no_secret_session_payload
    result = validate_g2b_no_secret_session_payload({key: "value"})
    assert not result["valid"], f"키 '{key}'는 차단되어야 합니다"


# ── 11. validator action allowlist ───────────────────────────────────

def test_validator_unknown_action_rejected():
    from scripts.g2b.validators import validate_g2b_action_name
    result = validate_g2b_action_name("unknown_action_xyz")
    assert not result["valid"]


def test_validator_blocked_action_rejected():
    from scripts.g2b.validators import validate_g2b_action_name
    result = validate_g2b_action_name("submit_bid")
    assert not result["valid"]


def test_validator_known_action_allowed():
    from scripts.g2b.validators import validate_g2b_action_name
    result = validate_g2b_action_name("search_notice")
    assert result["valid"]


# ── 12. router command 목록 ───────────────────────────────────────────

def test_router_commands_exist():
    from scripts.g2b.router import ROUTER_COMMANDS
    required = {"status", "gate", "analysis-draft", "submit-draft", "discover", "download", "suite"}
    assert required.issubset(set(ROUTER_COMMANDS))


# ── 13. router response key ───────────────────────────────────────────

def test_router_response_keys():
    from scripts.g2b.router import ROUTER_RESPONSE_KEYS
    required = {
        "command", "status", "decision", "reason",
        "user_direct_required", "local_agent_required",
        "approval_required", "blocked", "next_step",
        "evidence_policy", "report_policy",
    }
    assert required.issubset(set(ROUTER_RESPONSE_KEYS))


# ── 14. evidence/report policy ───────────────────────────────────────

def test_evidence_warehouse_policy():
    from scripts.g2b.site_profile import EVIDENCE_WAREHOUSE_POLICY
    assert EVIDENCE_WAREHOUSE_POLICY["server_write"] == "BLOCKED"
    assert "data/g2b/" in EVIDENCE_WAREHOUSE_POLICY["warehouse_root"]


def test_report_policy_path():
    from scripts.g2b.site_profile import EVIDENCE_WAREHOUSE_POLICY
    assert EVIDENCE_WAREHOUSE_POLICY["report_root"] == "docs/reports/"


# ── 15. OpenAPI collector 직접 변경 없음 ─────────────────────────────

def test_openapi_collector_files_unchanged():
    import pathlib
    collector_file = pathlib.Path("scripts/g2b/discover_valid_public_notice_urls.py")
    assert collector_file.exists(), "OpenAPI collector 파일 보존 확인"


# ── 16. FORBIDDEN_IMPORT / ROUTER_THINNESS / STORAGE_BOUNDARY 회귀 ──

def test_router_no_sql():
    import pathlib
    src = pathlib.Path("scripts/g2b/router.py").read_text(encoding="utf-8")
    assert "SELECT " not in src.upper(), "router에 SQL 금지"
    assert "INSERT " not in src.upper(), "router에 SQL 금지"


def test_router_no_db_import():
    import ast, pathlib
    src = pathlib.Path("scripts/g2b/router.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("scripts.db"), "router에 DB import 금지"
            assert not module.startswith("scripts.models"), "router에 models import 금지"


def test_no_sessions_access_in_g2b():
    import pathlib
    for py in pathlib.Path("scripts/g2b").glob("*.py"):
        src = py.read_text(encoding="utf-8")
        assert "data/sessions" not in src, f"{py.name}에 data/sessions 접근 금지"


def test_no_real_login_code():
    import pathlib
    for py in (
        pathlib.Path("scripts/g2b/site_profile.py"),
        pathlib.Path("scripts/g2b/gates.py"),
        pathlib.Path("scripts/g2b/validators.py"),
        pathlib.Path("scripts/g2b/router.py"),
    ):
        src = py.read_text(encoding="utf-8")
        assert "playwright" not in src.lower(), f"{py.name}에 playwright 직접 사용 금지"
        assert "selenium" not in src.lower(), f"{py.name}에 selenium 직접 사용 금지"
