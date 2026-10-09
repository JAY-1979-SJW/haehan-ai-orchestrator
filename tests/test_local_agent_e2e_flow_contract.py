from tools.audits.agent import audit_local_agent_e2e_flow_contract as audit


def test_local_agent_e2e_flow_contract_passes():
    ok, findings = audit.audit()

    assert ok, findings


def test_local_agent_e2e_forbidden_key_detector_is_recursive():
    payload = {"task": {"params": {"nested": {"device_token": "hidden"}}}}

    assert audit._contains_forbidden_key(payload) == ["device_token"]
