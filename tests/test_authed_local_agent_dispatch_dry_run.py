from tools.audits.agent import audit_authed_local_agent_dispatch_dry_run as audit


def test_authed_local_agent_dispatch_dry_run_passes_static_contract():
    result = audit.audit()
    assert result.verdict == "PASS_AUTHED_LOCAL_AGENT_DISPATCH_DRY_RUN_READY"
    assert result.passed is True


def test_dry_run_script_has_no_forbidden_execution_tokens():
    script = audit.Path(audit.__file__).read_text(encoding="utf-8", errors="replace").lower()
    forbidden = [token for token in audit.FORBIDDEN_SCRIPT_TOKENS if token in script]
    assert audit.FORBIDDEN_SCRIPT_TOKENS, "audit.FORBIDDEN_SCRIPT_TOKENS 이(가) 비어 있음 — 비교대상 0건이면 아래 assert 는 공허하게 통과한다"
    assert forbidden == []


_GOOD_REG = '''
registration_router = APIRouter()

@registration_router.post("/register")
def register_local_agent(
    body: X,
    user: dict = Depends(require_role("admin", "owner")),
):
    pass

@registration_router.post("/registration-codes")
def issue_registration_code(
    user: dict = Depends(require_role("admin", "owner")),
):
    pass

@registration_router.post("/register-with-code")
def register_with_code(body: R):
    pass
'''
_GOOD_ROUTER = "local_agent_router.include_router(_registration_router)\n"


def _run_router(registration, router=_GOOD_ROUTER):
    findings = []
    audit._audit_router(findings, router=router, registration=registration)
    return {f.item: f.status for f in findings}


def test_router_audit_passes_with_guards():
    assert set(_run_router(_GOOD_REG).values()) == {"PASS"}


def test_router_audit_fails_when_register_guard_removed():
    # 다른 엔드포인트의 가드가 register_local_agent 를 대신 통과시키면 안 된다.
    bad = _GOOD_REG.replace(
        'user: dict = Depends(require_role("admin", "owner")),\n):\n    pass\n\n@registration_router.post("/registration-codes")',
        'user: dict = Depends(get_user),\n):\n    pass\n\n@registration_router.post("/registration-codes")',
    )
    assert bad != _GOOD_REG
    res = _run_router(bad)
    assert res["register_endpoint_auth"] == "FAIL"
    assert res["registration_code_flow"] == "PASS"


def test_router_audit_fails_when_issue_guard_wrong_role_or_exchange_missing():
    wrong_role = _GOOD_REG.replace(
        'issue_registration_code(\n    user: dict = Depends(require_role("admin", "owner"))',
        'issue_registration_code(\n    user: dict = Depends(require_role("viewer"))',
    )
    assert wrong_role != _GOOD_REG
    assert _run_router(wrong_role)["registration_code_flow"] == "FAIL"
    no_exchange = _GOOD_REG.replace("/register-with-code", "/other")
    assert _run_router(no_exchange)["registration_code_flow"] == "FAIL"


def test_router_audit_fails_when_registration_router_not_included():
    assert _run_router(_GOOD_REG, router="x = 1\n")["registration_router_included"] == "FAIL"
