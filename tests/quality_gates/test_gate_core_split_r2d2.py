"""R2d-2 P0a — 게이트 핵심 이전(scripts/common/gate.py → tools/gates/gate_core.py) 시험.

목적: ① 핵심이 `scripts` 를 import 하지 않는다(순환 해소의 구조 보장) ② 기존 `scripts.common.gate` 호출자 동작이 같다(shim)
③ 감사 기록(op_log)이 싱크 주입으로 그대로 남는다 ④ `__file__` 기준 경로가 저장소 루트를 가리킨다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import scripts.common.gate as shim
import scripts.common.schemas as schemas
import tools.gates.gate_core as core
import tools.gates.gate_types as gtypes

ROOT = Path(__file__).resolve().parents[2]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("name", ["gate_core.py", "gate_types.py"])
def test_gate_core_modules_do_not_import_scripts(name):
    """게이트 핵심은 scripts 패키지를 import 하지 않는다(함수 안쪽 import 포함 — 의존을 숨기지 않는다)."""
    imports = _imports(ROOT / "tools" / "gates" / name)
    assert imports, f"{name} 의 import 목록이 비어 있음(검사 대상 없음)"
    bad = {m for m in imports if m == "scripts" or m.startswith("scripts.")}
    assert not bad, f"{name} 이 scripts 를 import 함: {sorted(bad)}"


def test_send_approval_adapter_uses_core_not_scripts():
    imports = _imports(ROOT / "tools" / "gates" / "send_approval.py")
    assert imports and "tools.gates.gate_core" in imports
    scripts_imports = {m for m in imports if m.startswith("scripts")}
    assert not scripts_imports, f"send_approval 이 scripts 를 import 함: {sorted(scripts_imports)}"


def test_shim_is_same_module_object():
    assert shim is core
    assert shim.check is core.check and shim.GateBlocked is core.GateBlocked


def test_schemas_reexport_same_types():
    assert schemas.GateResult is gtypes.GateResult
    assert schemas.GateVerdict is gtypes.GateVerdict
    assert schemas.RiskLevel is gtypes.RiskLevel


def test_registry_and_force_state_shared_through_shim():
    shim.register("r2d2_probe_op", "approve")
    assert core.get_risk("r2d2_probe_op") == schemas.RiskLevel.APPROVE
    with pytest.raises(core.GateBlocked):
        shim.check("r2d2_probe_op")
    with shim.force_approved():
        assert core.check("r2d2_probe_op").allowed
    with pytest.raises(shim.GateBlocked):
        core.check("r2d2_probe_op")


def test_default_state_dir_is_repo_root(monkeypatch):
    """__file__ 기준 경로 보정: gate_core 는 ai_orchestrator/gates 안에 있으므로 parents[2](저장소 루트)여야 한다."""
    monkeypatch.delenv("GATE_DATA_DIR", raising=False)
    assert core._opt_out_path() == ROOT / "data" / "gate" / "opt_out.json"


# ── 감사 기록 싱크 ──


@pytest.fixture
def restore_sink():
    saved = core._audit_sink
    yield
    core.set_audit_sink(saved)


def test_audit_sink_receives_gate_verdicts(restore_sink):
    seen: list[tuple[str, dict]] = []
    core.set_audit_sink(lambda name, **f: seen.append((name, f)))
    core.check("scan_page")
    with pytest.raises(core.GateBlocked):
        core.check("mail_send")
    assert [n for n, _ in seen] == ["gate.allowed", "gate.blocked"]
    assert seen[1][1]["op"] == "mail_send" and seen[1][1]["ok"] is False and seen[1][1]["risk"] == "approve"


def test_audit_sink_failure_never_changes_verdict(restore_sink):
    def boom(*a, **k):
        raise RuntimeError("sink down")

    core.set_audit_sink(boom)
    assert core.check("scan_page").allowed
    with pytest.raises(core.GateBlocked):
        core.check("mail_send")


def test_no_sink_is_safe(restore_sink):
    core.set_audit_sink(None)
    assert core.check("scan_page").allowed


def test_shim_registers_op_log_sink(monkeypatch):
    """scripts.common.gate(shim)를 import 한 경로는 op_log 로 감사 기록을 남긴다(기존 동작과 동일)."""
    import scripts.common.op_log as op_log

    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(op_log, "log_op", lambda name, **f: calls.append((name, f)))
    saved = core._audit_sink
    try:
        # shim 이 등록한 싱크가 지연 import 한 log_op 로 전달해야 한다
        sink = saved
        assert sink is not None
        sink("gate.allowed", ok=True, op="x")
    finally:
        core.set_audit_sink(saved)
    assert calls == [("gate.allowed", {"ok": True, "op": "x"})]


def test_asgi_composition_root_connects_audit_sink(monkeypatch):
    import scripts.common.op_log as op_log
    from ai_orchestrator import asgi

    calls: list[str] = []
    monkeypatch.setattr(op_log, "log_op", lambda name, **f: calls.append(name))
    saved = core._audit_sink
    try:
        core.set_audit_sink(None)
        asgi._connect_gate_audit()
        with pytest.raises(core.GateBlocked):
            core.check("mail_send")
    finally:
        core.set_audit_sink(saved)
    assert calls == ["gate.blocked"]
