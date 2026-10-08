"""Google site_engine 연결 및 adapter boundary 테스트."""
from __future__ import annotations


# ── 1. profile 검증 ─────────────────────────────────────────────────────────

def test_google_profile_import():
    from scripts.google.site_profile import GOOGLE_PROFILE
    assert GOOGLE_PROFILE.key == "google"


def test_send_action_approval_required():
    from scripts.google.site_profile import GOOGLE_PROFILE
    from scripts.site_engine.site_types import SiteCapability
    policy = GOOGLE_PROFILE.action_policies.get(SiteCapability.SEND)
    assert policy is not None
    assert policy.requires_approval is True


def test_submit_action_approval_required():
    from scripts.google.site_profile import GOOGLE_PROFILE
    from scripts.site_engine.site_types import SiteCapability
    policy = GOOGLE_PROFILE.action_policies.get(SiteCapability.SUBMIT)
    assert policy is not None
    assert policy.requires_approval is True


def test_upload_action_approval_required():
    from scripts.google.site_profile import GOOGLE_PROFILE
    from scripts.site_engine.site_types import SiteCapability
    policy = GOOGLE_PROFILE.action_policies.get(SiteCapability.UPLOAD)
    assert policy is not None
    assert policy.requires_approval is True


def test_publish_action_approval_required():
    from scripts.google.site_profile import GOOGLE_PROFILE
    from scripts.site_engine.site_types import SiteCapability
    policy = GOOGLE_PROFILE.action_policies.get(SiteCapability.PUBLISH)
    assert policy is not None
    assert policy.requires_approval is True


def test_read_not_approval_required():
    from scripts.google.site_profile import GOOGLE_PROFILE
    from scripts.site_engine.site_types import SiteCapability
    policy = GOOGLE_PROFILE.action_policies.get(SiteCapability.READ)
    assert policy is None or policy.requires_approval is False


def test_oauth_is_user_direct():
    from scripts.google.site_profile import GOOGLE_PROFILE
    from scripts.site_engine.site_types import GateDecision, SiteCapability
    policy = GOOGLE_PROFILE.action_policies.get(SiteCapability.SIGN)
    assert policy is not None
    assert policy.gate == GateDecision.USER_DIRECT_REQUIRED


# ── 2. gate wrapper 검증 ─────────────────────────────────────────────────────

def test_gate_google_read_returns_result():
    from scripts.google.gates import gate_google_read
    from scripts.site_engine.execution_gate import ExecutionGateResult
    result = gate_google_read()
    assert isinstance(result, ExecutionGateResult)


def test_gate_google_send_plan_returns_result():
    from scripts.google.gates import gate_google_send_plan
    from scripts.site_engine.execution_gate import ExecutionGateResult
    result = gate_google_send_plan()
    assert isinstance(result, ExecutionGateResult)


def test_gate_google_submit_plan_returns_result():
    from scripts.google.gates import gate_google_submit_plan
    from scripts.site_engine.execution_gate import ExecutionGateResult
    result = gate_google_submit_plan()
    assert isinstance(result, ExecutionGateResult)


def test_gate_google_upload_plan_returns_result():
    from scripts.google.gates import gate_google_upload_plan
    from scripts.site_engine.execution_gate import ExecutionGateResult
    result = gate_google_upload_plan()
    assert isinstance(result, ExecutionGateResult)


def test_gate_google_oauth_required_returns_result():
    from scripts.google.gates import gate_google_oauth_required
    from scripts.site_engine.execution_gate import ExecutionGateResult
    result = gate_google_oauth_required()
    assert isinstance(result, ExecutionGateResult)


# ── 3. validator 검증 ────────────────────────────────────────────────────────

def test_validate_no_plain_secret_clean():
    from scripts.google.validators import validate_google_no_plain_secret
    result = validate_google_no_plain_secret({"subject": "회의", "to": "user@example.com"})
    assert result.is_valid is True


def test_validate_no_plain_secret_detects_token():
    from scripts.google.validators import validate_google_no_plain_secret
    result = validate_google_no_plain_secret({"token": "gho_abc123secret"})
    assert result.is_valid is False


# ── 4. router import smoke ───────────────────────────────────────────────────

def test_router_import_smoke():
    import scripts.google.router  # noqa: F401


# ── 5. cross-domain import 금지 검증 ────────────────────────────────────────

def test_google_does_not_import_hiworks():
    """scripts.google 모듈이 scripts.hiworks를 직접 import하지 않는다."""
    import ast
    from pathlib import Path
    google_dir = Path("scripts/google")
    for py_file in google_dir.glob("*.py"):
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
                    assert not name.startswith("scripts.hiworks"), (
                        f"{py_file}: imports scripts.hiworks (cross-domain forbidden)"
                    )


def test_google_does_not_import_eum():
    import ast
    from pathlib import Path
    google_dir = Path("scripts/google")
    for py_file in google_dir.glob("*.py"):
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
                    assert not name.startswith("scripts.eum"), (
                        f"{py_file}: imports scripts.eum (cross-domain forbidden)"
                    )


def test_google_does_not_import_g2b():
    import ast
    from pathlib import Path
    google_dir = Path("scripts/google")
    for py_file in google_dir.glob("*.py"):
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
                    assert not name.startswith("scripts.g2b"), (
                        f"{py_file}: imports scripts.g2b (cross-domain forbidden)"
                    )
