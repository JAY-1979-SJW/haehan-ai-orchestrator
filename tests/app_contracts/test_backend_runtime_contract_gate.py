from tools.audits.backend import audit_backend_runtime_contract as audit


def test_backend_runtime_route_count_is_locked():
    routes = audit.iter_runtime_routes()

    assert len(routes) == audit.EXPECTED_RUNTIME_ROUTES


def test_backend_runtime_required_routes_are_registered():
    route_keys = {(method, path) for method, path, _name in audit.iter_runtime_routes()}

    assert audit.REQUIRED_ROUTES.issubset(route_keys)


def test_backend_runtime_routes_have_no_duplicates():
    assert audit.find_duplicate_routes(audit.iter_runtime_routes()) == []


def test_backend_runtime_forbidden_security_patterns_absent():
    assert audit.scan_forbidden_backend_patterns() == []


def test_backend_runtime_auth_default_is_safe():
    assert audit.auth_default_is_safe() is True


def test_backend_runtime_contract_audit_passes():
    assert audit.main() == 0
