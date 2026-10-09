from tools.repo_gates import audit_api_contract_frontend_backend as audit
from tools.repo_gates import audit_r1_api_contract_gate as gate


def test_r1_backend_routes_scan_runs():
    routes = audit.scan_backend_routes()
    assert len(routes) > 100  # 런타임 라우트가 비정상적으로 적게 잡히면 스캔 자체가 고장


def test_r1_frontend_calls_scan_finds_known_files():
    calls = audit.scan_frontend_calls()
    files = {c.file for c in calls}
    assert any("assistant/api.ts" in f for f in files)


def test_r1_baseline_file_exists_and_matches_schema():
    baseline = audit.load_baseline()
    assert isinstance(baseline, set)


def test_r1_no_new_broken_calls_beyond_baseline():
    """기존 부채(허용목록)는 통과, 새로 끊긴 호출만 차단."""
    assert gate.main() == 0
