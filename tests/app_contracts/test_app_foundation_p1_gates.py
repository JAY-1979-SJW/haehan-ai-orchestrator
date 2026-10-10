"""APP_FOUNDATION P1 게이트 테스트.

ROUTER_THINNESS, STORAGE_BOUNDARY, SERVER_BROWSER_GUARD 구조 게이트 검증.
기능 테스트 아님 — 구조/정책 위반 감지 테스트만 포함.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


# ── 공통 헬퍼 ────────────────────────────────────────────────────────────────

_REPORT_CACHE: dict | None = None


def _load_report() -> dict:
    """감사 리포트를 읽는다. 리포트는 .gitignore 대상 생성 산출물이라 깨끗한 체크아웃엔 없으므로,
    저장소 안 파일이 없으면 audit 를 임시 경로로 한 번 실행해 만든다(저장소 파일은 건드리지 않음)."""
    global _REPORT_CACHE
    if _REPORT_CACHE is not None:
        return _REPORT_CACHE
    report_path = ROOT / "data" / "codebase_layer_audit_latest.json"
    if not report_path.exists():
        report_path = Path(tempfile.mkdtemp(prefix="layer_audit_")) / "report.json"
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / "repo_gates" / "codebase_layer_audit.py"), "--output", str(report_path)],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
    assert report_path.exists(), "audit 리포트를 만들지 못함(tools/repo_gates/codebase_layer_audit.py 실행 실패)"
    _REPORT_CACHE = json.loads(report_path.read_text(encoding="utf-8"))
    return _REPORT_CACHE


def _audit_issues() -> list[dict]:
    return _load_report().get("issues", [])


def _gate_results() -> dict:
    return _load_report().get("gate_results", {})


# ── 1. ROUTER_THINNESS ───────────────────────────────────────────────────────

def test_router_thinness_check_function_exists():
    """check_router_thinness 함수가 audit 스크립트에 존재해야 한다."""
    import tools.repo_gates.codebase_layer_audit as m
    assert hasattr(m, "check_router_thinness")


def test_router_thinness_no_new_violations():
    """신규 ROUTER_THINNESS WARN 위반이 0이어야 한다 (known debt는 INFO)."""
    issues = _audit_issues()
    violations = [i for i in issues if i["code"] == "ROUTER_THINNESS" and i["severity"] == "warn"]
    assert len(violations) == 0, f"ROUTER_THINNESS 신규 위반: {violations}"


def test_router_thinness_known_debt_labeled():
    """known debt는 [KNOWN_DEBT] 레이블이 붙어야 한다."""
    issues = _audit_issues()
    debt = [i for i in issues if i["code"] == "ROUTER_THINNESS" and i["severity"] == "info"]
    for d in debt:
        assert "[KNOWN_DEBT]" in d["message"], f"known debt에 레이블 없음: {d}"


def test_router_thinness_gate_result_key_exists():
    """gate_results에 router_thinness 키가 존재해야 한다."""
    gr = _gate_results()
    assert "router_thinness" in gr, "gate_results에 router_thinness 없음"


def test_router_thinness_positive_detection():
    """실제 router 파일에 금지 패턴 없음을 확인 (site router)."""
    from tools.repo_gates.codebase_layer_audit import check_router_thinness, classify_files
    rows = classify_files(ROOT)
    issues = check_router_thinness(rows, ROOT)
    # 신규 warn 0
    new_violations = [i for i in issues if i.severity == "warn"]
    assert len(new_violations) == 0, f"ROUTER_THINNESS 신규 위반: {new_violations}"


def test_router_thinness_gabia_router_clean():
    """scripts/gabia/router.py는 ROUTER_THINNESS 위반이 없어야 한다."""
    from tools.repo_gates.codebase_layer_audit import check_router_thinness, classify_files
    rows = [r for r in classify_files(ROOT) if r.path == "scripts/gabia/router.py"]
    issues = check_router_thinness(rows, ROOT)
    violations = [i for i in issues if i.severity == "warn"]
    assert len(violations) == 0, f"gabia/router.py ROUTER_THINNESS 위반: {violations}"


def test_router_thinness_hiworks_router_clean():
    """scripts/hiworks/router.py는 ROUTER_THINNESS 위반이 없어야 한다."""
    from tools.repo_gates.codebase_layer_audit import check_router_thinness, classify_files
    rows = [r for r in classify_files(ROOT) if r.path == "scripts/hiworks/router.py"]
    issues = check_router_thinness(rows, ROOT)
    violations = [i for i in issues if i.severity == "warn"]
    assert len(violations) == 0, f"hiworks/router.py ROUTER_THINNESS 위반: {violations}"


# ── 2. STORAGE_BOUNDARY ──────────────────────────────────────────────────────

def test_storage_boundary_check_function_exists():
    """check_storage_boundary 함수가 audit 스크립트에 존재해야 한다."""
    import tools.repo_gates.codebase_layer_audit as m
    assert hasattr(m, "check_storage_boundary")


def test_storage_boundary_no_new_violations():
    """신규 STORAGE_BOUNDARY WARN 위반이 0이어야 한다."""
    issues = _audit_issues()
    violations = [i for i in issues if i["code"] == "STORAGE_BOUNDARY" and i["severity"] == "warn"]
    assert len(violations) == 0, f"STORAGE_BOUNDARY 신규 위반: {violations}"


def test_storage_boundary_known_debt_labeled():
    """known debt는 [KNOWN_DEBT] 레이블이 붙어야 한다."""
    issues = _audit_issues()
    debt = [i for i in issues if i["code"] == "STORAGE_BOUNDARY" and i["severity"] == "info"]
    for d in debt:
        assert "[KNOWN_DEBT]" in d["message"], f"known debt에 레이블 없음: {d}"


def test_storage_boundary_gate_result_key_exists():
    """gate_results에 storage_boundary 키가 존재해야 한다."""
    gr = _gate_results()
    assert "storage_boundary" in gr


def test_storage_boundary_gabia_scripts_clean():
    """scripts/gabia/ 내 파일은 STORAGE_BOUNDARY WARN 위반이 없어야 한다."""
    from tools.repo_gates.codebase_layer_audit import check_storage_boundary, classify_files
    rows = [r for r in classify_files(ROOT) if r.path.startswith("scripts/gabia/")]
    issues = check_storage_boundary(rows, ROOT)
    violations = [i for i in issues if i.severity == "warn"]
    assert len(violations) == 0, f"scripts/gabia/ STORAGE_BOUNDARY 위반: {violations}"


def test_storage_boundary_session_files_not_opened_in_site_modules():
    """site module에서 data/sessions/*.json open 코드가 없어야 한다."""
    import re
    pattern = re.compile(r"open\s*\(\s*['\"][^'\"]*data/sessions", re.IGNORECASE)
    for py_file in (ROOT / "scripts").rglob("*.py"):
        if "archive" in str(py_file):
            continue
        source = py_file.read_text(encoding="utf-8", errors="replace")
        if pattern.search(source):
            raise AssertionError(f"session 파일 open 발견: {py_file}")


def test_storage_boundary_domain_assist_no_session_access():
    """domain_assist.py는 session 파일을 열지 않아야 한다."""
    import re
    src = (ROOT / "scripts/gabia/domain_assist.py").read_text(encoding="utf-8")
    assert not re.search(r"open\s*\(\s*['\"][^'\"]*sessions", src), \
        "domain_assist.py에 session 파일 open 코드 발견"


# ── 3. SERVER_BROWSER_GUARD ──────────────────────────────────────────────────

def test_server_browser_guard_check_function_exists():
    """check_server_browser_guard 함수가 audit 스크립트에 존재해야 한다."""
    import tools.repo_gates.codebase_layer_audit as m
    assert hasattr(m, "check_server_browser_guard")


def test_server_browser_guard_no_violations():
    """SERVER_BROWSER_GUARD 위반이 0이어야 한다."""
    issues = _audit_issues()
    violations = [i for i in issues if i["code"] == "SERVER_BROWSER_GUARD" and i["severity"] == "warn"]
    assert len(violations) == 0, f"SERVER_BROWSER_GUARD 위반: {violations}"


def test_server_browser_guard_gate_result_key_exists():
    """gate_results에 server_browser_guard 키가 존재해야 한다."""
    gr = _gate_results()
    assert "server_browser_guard" in gr


def test_server_browser_guard_gabia_gate_is_blocked():
    """Gabia 로그인 gate는 BLOCKED여야 한다."""
    from scripts.gabia.gates import gate_gabia_login
    result = gate_gabia_login()
    assert result.is_blocked, "Gabia 로그인 gate가 BLOCKED가 아님"


def test_server_browser_guard_gabia_payment_blocked():
    """Gabia 결제 gate는 BLOCKED여야 한다."""
    from scripts.gabia.gates import gate_gabia_payment
    result = gate_gabia_payment()
    assert result.is_blocked, "Gabia 결제 gate가 BLOCKED가 아님"


def test_server_browser_guard_gabia_credential_blocked():
    """Gabia credential 추출 gate는 BLOCKED여야 한다."""
    from scripts.gabia.gates import gate_gabia_credential_extract
    result = gate_gabia_credential_extract()
    assert result.is_blocked, "Gabia credential 추출 gate가 BLOCKED가 아님"


def test_server_browser_guard_forbidden_sites_list_exists():
    """_SERVER_FORBIDDEN_SITES 목록이 정의되어야 한다."""
    from tools.repo_gates.codebase_layer_audit import _SERVER_FORBIDDEN_SITES
    assert len(_SERVER_FORBIDDEN_SITES) > 0
    assert any("gabia" in s for s in _SERVER_FORBIDDEN_SITES)
    assert any("g2b" in s for s in _SERVER_FORBIDDEN_SITES)


def test_server_browser_guard_execution_gate_has_server_forbidden():
    """execution_gate.py에 is_server_forbidden_site 기능이 존재해야 한다."""
    import scripts.site_engine.execution_gate as m
    assert hasattr(m, "ExecutionGateInput")
    import inspect

    from scripts.site_engine.execution_gate import ExecutionGateInput
    sig = inspect.signature(ExecutionGateInput.__init__)
    assert "is_server_forbidden_site" in sig.parameters, \
        "ExecutionGateInput에 is_server_forbidden_site 파라미터 없음"


def test_server_browser_guard_account_read_not_server_browser():
    """Gabia 계정 조회는 SERVER_BROWSER_ALLOWED가 아니어야 한다."""
    from scripts.gabia.gates import gate_gabia_account_read
    from scripts.site_engine.site_types import GateDecision
    result = gate_gabia_account_read()
    assert result.gate_decision != GateDecision.SERVER_BROWSER_ALLOWED


# ── 4. P1 게이트 전체 통합 확인 ──────────────────────────────────────────────

def test_p1_gates_all_zero_new_violations():
    """P1 게이트 3종 모두 신규 위반 0건이어야 한다."""
    issues = _audit_issues()
    p1_codes = {"ROUTER_THINNESS", "STORAGE_BOUNDARY", "SERVER_BROWSER_GUARD"}
    violations = [i for i in issues if i["code"] in p1_codes and i["severity"] == "warn"]
    assert len(violations) == 0, f"P1 신규 위반: {violations}"


def test_p1_gate_results_all_present():
    """gate_results에 P1 게이트 3종 키가 모두 있어야 한다."""
    gr = _gate_results()
    for key in ("router_thinness", "storage_boundary", "server_browser_guard"):
        assert key in gr, f"gate_results에 {key} 없음"


def test_governance_gate_matrix_p1_status_updated():
    """governance_gate_matrix.md에 P1 게이트가 구현됨/보강됨으로 표시되어야 한다."""
    doc = (ROOT / "docs/architecture/governance_gate_matrix.md").read_text(encoding="utf-8")
    assert "ROUTER_THINNESS" in doc
    assert "STORAGE_BOUNDARY" in doc
    assert "SERVER_BROWSER_GUARD" in doc


# ── 5. 기존 P0 게이트 regression ─────────────────────────────────────────────

def test_forbidden_import_still_zero():
    issues = _audit_issues()
    fi = [i for i in issues if i["code"] == "FORBIDDEN_IMPORT"]
    assert len(fi) == 0, f"FORBIDDEN_IMPORT 위반: {fi}"


def test_security_pattern_still_zero():
    issues = _audit_issues()
    sp = [i for i in issues if i["code"] == "SECURITY_PATTERN"]
    assert len(sp) == 0, f"SECURITY_PATTERN 위반: {sp}"
