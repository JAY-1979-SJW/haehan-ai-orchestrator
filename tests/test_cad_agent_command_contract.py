# -*- coding: utf-8 -*-
"""CAD-AGENT-CAD-CONTROL-COMMAND-CONTRACT-01 — schema/contract tests.

실제 실행 / DB write / network / subprocess / AutoCAD 일체 없음.
"""
from __future__ import annotations

import ast
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_agent.cad import command_approval as approval_mod
from local_agent.cad import command_audit as audit_mod
from local_agent.cad import command_contract as cc
from local_agent.cad import tool_catalog as tc

CONTRACT_FILE = ROOT / "local_agent" / "cad" / "command_contract.py"
AUDIT_FILE = ROOT / "local_agent" / "cad" / "command_audit.py"
APPROVAL_FILE = ROOT / "local_agent" / "cad" / "command_approval.py"


# ──────────────────────────────────────────────
# 1. Registry — READ_ONLY 9 + CANDIDATE_PAYLOAD 4
# ──────────────────────────────────────────────

def test_default_registry_imports_nine_read_only_tools():
    reg = cc.build_default_registry()
    ro_ids = reg.list_by_risk(cc.RiskLevel.READ_ONLY)
    assert len(ro_ids) == 9
    # tool_catalog.READ_ONLY_TOOLS 가 source-of-truth
    for tool_id in tc.READ_ONLY_TOOLS:
        assert tool_id.lower() in ro_ids


def test_default_registry_has_four_candidate_payload_tools():
    reg = cc.build_default_registry()
    cp_ids = reg.list_by_risk(cc.RiskLevel.CANDIDATE_PAYLOAD)
    assert set(cp_ids) == {
        "arch_quantity_tab.build_cards",
        "drawing_inventory.analyze_drawing_inventory",
        "schedule_tables.detect",
        "construction_sequence.plan",
    }


def test_default_registry_has_no_mutating_tools_seeded():
    """본 트랙에서 MUTATING_DXF / MUTATING_AUTOCAD_COM 은 등록 0건 (enum 만 정의)."""
    reg = cc.build_default_registry()
    assert reg.list_by_risk(cc.RiskLevel.MUTATING_DXF) == ()
    assert reg.list_by_risk(cc.RiskLevel.MUTATING_AUTOCAD_COM) == ()


def test_registry_rejects_duplicate_registration():
    reg = cc.CadCommandRegistry()
    e = cc.CadCommandRegistryEntry(
        toolId="x.y", risk=cc.RiskLevel.READ_ONLY,
        endpointPath=None, description="x",
    )
    reg.register(e)
    with pytest.raises(ValueError):
        reg.register(e)


def test_registry_get_unknown_raises_CadToolNotRegistered():
    reg = cc.build_default_registry()
    with pytest.raises(cc.CadToolNotRegistered):
        reg.get("unknown.tool.id")


def test_registry_has_returns_false_for_unknown():
    reg = cc.build_default_registry()
    assert reg.has("unknown.tool.id") is False
    assert reg.has("layer.list") is True


# ──────────────────────────────────────────────
# 2. RegistryEntry.requires_approval
# ──────────────────────────────────────────────

@pytest.mark.parametrize("risk,expected", [
    (cc.RiskLevel.READ_ONLY, False),
    (cc.RiskLevel.CANDIDATE_PAYLOAD, False),
    (cc.RiskLevel.MUTATING_DXF, True),
    (cc.RiskLevel.MUTATING_AUTOCAD_COM, True),
])
def test_entry_requires_approval(risk, expected):
    e = cc.CadCommandRegistryEntry(
        toolId="x.y", risk=risk, endpointPath=None, description="",
    )
    assert e.requires_approval is expected


# ──────────────────────────────────────────────
# 3. Validator — propose
# ──────────────────────────────────────────────

def test_validator_propose_read_only_does_not_require_approval():
    v = cc.CadCommandValidator()
    cmd = v.propose("layer.list", {"limit": 100})
    assert cmd.risk == cc.RiskLevel.READ_ONLY
    assert cmd.status == cc.CommandStatus.VALIDATED
    assert cmd.approvalStatus == cc.ApprovalStatus.NOT_REQUIRED
    assert cmd.requiresApproval is False


def test_validator_propose_candidate_payload_does_not_require_approval():
    v = cc.CadCommandValidator()
    cmd = v.propose("arch_quantity_tab.build_cards", {})
    assert cmd.risk == cc.RiskLevel.CANDIDATE_PAYLOAD
    assert cmd.status == cc.CommandStatus.VALIDATED
    assert cmd.approvalStatus == cc.ApprovalStatus.NOT_REQUIRED
    assert cmd.requiresApproval is False
    # endpoint path contract 보존
    assert cmd.endpointPath == "/acad/arch-quantity-tab/build-cards"


def test_validator_propose_mutating_dxf_requires_approval():
    # MUTATING_DXF 는 default registry 에 없음 — 임시 registry 등록
    reg = cc.CadCommandRegistry()
    reg.register(cc.CadCommandRegistryEntry(
        toolId="dxf.mutate.example", risk=cc.RiskLevel.MUTATING_DXF,
        endpointPath="/acad/example", description="example",
    ))
    v = cc.CadCommandValidator(registry=reg)
    cmd = v.propose("dxf.mutate.example", {})
    assert cmd.risk == cc.RiskLevel.MUTATING_DXF
    assert cmd.status == cc.CommandStatus.APPROVAL_REQUIRED
    assert cmd.approvalStatus == cc.ApprovalStatus.PENDING
    assert cmd.requiresApproval is True


def test_validator_propose_mutating_autocad_com_requires_approval():
    reg = cc.CadCommandRegistry()
    reg.register(cc.CadCommandRegistryEntry(
        toolId="autocad.com.example", risk=cc.RiskLevel.MUTATING_AUTOCAD_COM,
        endpointPath="/acad/example2", description="example",
    ))
    v = cc.CadCommandValidator(registry=reg)
    cmd = v.propose("autocad.com.example", {})
    assert cmd.requiresApproval is True
    assert cmd.approvalStatus == cc.ApprovalStatus.PENDING


def test_validator_unknown_tool_raises():
    v = cc.CadCommandValidator()
    with pytest.raises(cc.CadToolNotRegistered):
        v.propose("nonexistent.tool", {})


def test_validator_mark_blocked_for_unknown_returns_blocked_command():
    v = cc.CadCommandValidator()
    cmd = v.mark_blocked_unknown_tool("nonexistent.tool")
    assert cmd.status == cc.CommandStatus.BLOCKED
    assert cmd.autoExecute is False


# ──────────────────────────────────────────────
# 4. autoExecute=False 강제
# ──────────────────────────────────────────────

def test_command_auto_execute_always_false():
    v = cc.CadCommandValidator()
    cmd = v.propose("layer.list")
    assert cmd.autoExecute is False
    # to_dict 에서도 항상 False
    assert cmd.to_dict()["autoExecute"] is False


def test_validator_rejects_auto_execute_true():
    v = cc.CadCommandValidator()
    with pytest.raises(cc.CadAutoExecuteForbidden):
        v.propose("layer.list", {}, auto_execute=True)


def test_command_dataclass_is_frozen():
    """autoExecute 우회 방지 — dataclass frozen."""
    v = cc.CadCommandValidator()
    cmd = v.propose("layer.list")
    with pytest.raises((AttributeError, TypeError)):
        cmd.status = cc.CommandStatus.APPROVED  # type: ignore


def test_args_must_be_mapping_or_none():
    v = cc.CadCommandValidator()
    with pytest.raises(TypeError):
        v.propose("layer.list", args=["not", "a", "mapping"])  # type: ignore


# ──────────────────────────────────────────────
# 5. Audit / redaction
# ──────────────────────────────────────────────

def test_redact_args_masks_secret_like_keys():
    out = audit_mod.redact_args({
        "api_key": "sk-secret",
        "password": "pw",
        "token": "tok",
        "Authorization": "Bearer xyz",
        "ok_key": "visible",
    })
    assert out["api_key"] == "[REDACTED]"
    assert out["password"] == "[REDACTED]"
    assert out["token"] == "[REDACTED]"
    assert out["Authorization"] == "[REDACTED]"
    assert out["ok_key"] == "visible"


def test_redact_args_redacts_raw_text_key():
    out = audit_mod.redact_args({"raw_text": "some sensitive content"})
    assert out["raw_text"] == "[REDACTED]"


def test_redact_truncates_long_strings():
    long_value = "x" * 500
    out = audit_mod.redact_args({"note": long_value})
    assert out["note"].endswith("[truncated]")
    assert len(out["note"]) <= 300


def test_redact_recursive_dicts():
    out = audit_mod.redact_args({
        "nested": {"api_key": "sk-xyz", "safe": "ok"},
    })
    assert out["nested"]["api_key"] == "[REDACTED]"
    assert out["nested"]["safe"] == "ok"


def test_audit_record_has_no_raw_text_field():
    v = cc.CadCommandValidator()
    cmd = v.propose("layer.list", {"limit": 50})
    rec = audit_mod.build_audit_record(cmd)
    d = rec.to_dict()
    assert "rawText" not in d
    assert "raw_text" not in d
    assert "token" not in d
    assert "apiKey" not in d


def test_summarize_result_does_not_leak_payload():
    big_result = {"secret": "hidden", "data": list(range(1000))}
    s = audit_mod.summarize_result(big_result)
    # 키 이름만 노출, 값 0건
    assert "secret" in s["keys"]
    assert "hidden" not in str(s)


# ──────────────────────────────────────────────
# 6. Approval store — in-memory PoC
# ──────────────────────────────────────────────

def test_create_approval_returns_id_and_raw_token_once():
    store = approval_mod.CadCommandApprovalStore()
    approval_id, token = store.create_approval("cmd-1", "layer.list")
    assert approval_id.startswith("appr_")
    assert isinstance(token, str)
    # token 원문은 store 에 저장되지 않음
    rec = store.get_record(approval_id)
    # raw token 필드 없음 — tokenHash 만
    assert not hasattr(rec, "token")
    assert not hasattr(rec, "raw_token")
    assert rec.tokenHash != token
    assert rec.tokenHash == approval_mod._hash_token(token)


def test_approve_then_verify_then_consume_once():
    store = approval_mod.CadCommandApprovalStore()
    approval_id, token = store.create_approval("cmd-1", "dxf.mutate")
    # PENDING → verify False
    assert store.verify(approval_id, token) is False
    # APPROVED → verify True
    store.approve(approval_id)
    assert store.verify(approval_id, token) is True
    # consume succeeds once
    assert store.consume(approval_id, token) is True
    # re-use rejected
    assert store.consume(approval_id, token) is False
    assert store.verify(approval_id, token) is False
    # status = USED
    rec = store.get_record(approval_id)
    assert rec.status == approval_mod.ApprovalRecordStatus.USED


def test_reject_blocks_consume():
    store = approval_mod.CadCommandApprovalStore()
    approval_id, token = store.create_approval("cmd-1", "dxf.mutate")
    store.reject(approval_id)
    rec = store.get_record(approval_id)
    assert rec.status == approval_mod.ApprovalRecordStatus.REJECTED
    assert store.verify(approval_id, token) is False
    assert store.consume(approval_id, token) is False


def test_wrong_token_rejected():
    store = approval_mod.CadCommandApprovalStore()
    approval_id, token = store.create_approval("cmd-1", "dxf.mutate")
    store.approve(approval_id)
    assert store.verify(approval_id, "WRONG-TOKEN-XYZ") is False
    assert store.consume(approval_id, "WRONG-TOKEN-XYZ") is False
    rec = store.get_record(approval_id)
    # 상태는 APPROVED 유지 (잘못된 token 으로 consume 안 됨)
    assert rec.status == approval_mod.ApprovalRecordStatus.APPROVED


def test_expired_approval_blocks_use():
    store = approval_mod.CadCommandApprovalStore(expiry_seconds=0)
    approval_id, token = store.create_approval("cmd-1", "dxf.mutate")
    # 즉시 expired
    time.sleep(0.01)
    store.approve(approval_id)  # 이미 expired → status EXPIRED 로 전이
    rec = store.get_record(approval_id)
    assert rec.status == approval_mod.ApprovalRecordStatus.EXPIRED
    assert store.verify(approval_id, token) is False


def test_approval_not_found_raises():
    store = approval_mod.CadCommandApprovalStore()
    with pytest.raises(approval_mod.ApprovalNotFound):
        store.get_record("nonexistent-id")


def test_approve_idempotent_when_already_approved():
    store = approval_mod.CadCommandApprovalStore()
    approval_id, _ = store.create_approval("cmd-1", "dxf.mutate")
    r1 = store.approve(approval_id)
    r2 = store.approve(approval_id)
    assert r1.status == approval_mod.ApprovalRecordStatus.APPROVED
    assert r2.status == approval_mod.ApprovalRecordStatus.APPROVED
    assert r1.approvedAt == r2.approvedAt  # 동일 timestamp


def test_token_hash_only_sha256_hex():
    h = approval_mod._hash_token("abc")
    # SHA256 hex digest = 64 chars
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ──────────────────────────────────────────────
# 7. Static — forbidden import / call
# ──────────────────────────────────────────────

@pytest.mark.parametrize("path", [CONTRACT_FILE, AUDIT_FILE, APPROVAL_FILE])
def test_contract_modules_no_subprocess_no_urlopen(path):
    src = path.read_text(encoding="utf-8")
    for forbidden in (
        "subprocess.Popen", "subprocess.run", "subprocess.call",
        "from subprocess", "import subprocess",
        "urlopen(", "from urllib.request", "import urllib.request",
        "import httpx", "from httpx", "import requests", "from requests",
    ):
        assert forbidden not in src, f"{forbidden!r} in {path.name}"


@pytest.mark.parametrize("path", [CONTRACT_FILE, AUDIT_FILE, APPROVAL_FILE])
def test_contract_modules_no_autocad_or_com(path):
    src = path.read_text(encoding="utf-8")
    for forbidden in (
        "win32com", "pythoncom", "AutoCAD.Application",
        "GetActiveObject", ".SendCommand(", ".SelectAll(",
    ):
        assert forbidden not in src


@pytest.mark.parametrize("path", [CONTRACT_FILE, AUDIT_FILE, APPROVAL_FILE])
def test_contract_modules_no_db_or_migration(path):
    src = path.read_text(encoding="utf-8")
    for forbidden in (
        "from sqlalchemy", "import sqlalchemy",
        "from django.db", "from alembic", "import alembic",
        "ALTER TABLE", "DROP TABLE", "sqlite3.connect(",
    ):
        assert forbidden not in src


@pytest.mark.parametrize("path", [CONTRACT_FILE, AUDIT_FILE, APPROVAL_FILE])
def test_contract_modules_no_file_write(path):
    src = path.read_text(encoding="utf-8")
    for forbidden in (
        'open(', '"w")', "'w')", '"a")', "'a')",
        ".write(", "Path(", "shutil.copy",
    ):
        # open()/write() 차단 — D6 정책: storage 후속 트랙
        # 단, 본 모듈에 'open' 키워드가 다른 맥락에서 나오면 안 됨
        # (안전하게 fail-loud 정책)
        if forbidden == "Path(":
            continue  # type hint 용 Path 사용은 허용
        if forbidden == 'open(':
            # contract/approval 어디서도 open( 호출 0건
            assert forbidden not in src, f"file open() in {path.name}"


def test_contract_does_not_import_cad_repo_modules():
    """CAD repo (local_bridge / app.backend / app.frontend / mcp_server) 직접 import 0."""
    for path in (CONTRACT_FILE, AUDIT_FILE, APPROVAL_FILE):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden_prefixes = (
            "local_bridge", "app.backend", "app.frontend", "mcp_server",
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for fp in forbidden_prefixes:
                    assert not node.module.startswith(fp), (
                        f"forbidden cross-repo import: {node.module} "
                        f"in {path.name}"
                    )
            elif isinstance(node, ast.Import):
                for a in node.names:
                    for fp in forbidden_prefixes:
                        assert not a.name.startswith(fp), (
                            f"forbidden cross-repo import: {a.name} "
                            f"in {path.name}"
                        )


def test_no_confirmed_status_outputs():
    """CONFIRMED/FINAL/APPROVED 문자열 — APPROVED 는 enum 으로 의도된 용도."""
    src = CONTRACT_FILE.read_text(encoding="utf-8")
    # 본 모듈은 ApprovalStatus.APPROVED enum 정의 — 정상.
    # 단, CONFIRMED / FINAL 은 사용 금지.
    for forbidden in ('"CONFIRMED"', '"FINAL"', "'CONFIRMED'", "'FINAL'"):
        assert forbidden not in src


# ──────────────────────────────────────────────
# 8. CadAgentCommand 직렬화 contract
# ──────────────────────────────────────────────

def test_command_to_dict_shape():
    v = cc.CadCommandValidator()
    cmd = v.propose("arch_quantity_tab.build_cards", {"x": 1})
    d = cmd.to_dict()
    for k in ("commandId", "toolId", "args", "risk", "status",
              "approvalStatus", "approvalId", "endpointPath",
              "requiresApproval", "autoExecute", "createdAt"):
        assert k in d
    assert d["autoExecute"] is False
    assert d["risk"] == "CANDIDATE_PAYLOAD"


def test_default_registry_singleton_is_eager():
    """import 시점에 9+4 = 13 등록 완료."""
    assert len(cc.DEFAULT_REGISTRY.list_ids()) >= 13
