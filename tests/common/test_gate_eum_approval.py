import pytest

from scripts.common.gate import GateBlocked, check, get_risk
from scripts.common.schemas import RiskLevel


def test_eum_mutation_gates_are_approval():
    assert get_risk("eum_register_device") == RiskLevel.APPROVE
    assert get_risk("eum_deregister_device") == RiskLevel.APPROVE


def test_eum_mutation_gate_blocks_without_force():
    with pytest.raises(GateBlocked):
        check("eum_register_device")
