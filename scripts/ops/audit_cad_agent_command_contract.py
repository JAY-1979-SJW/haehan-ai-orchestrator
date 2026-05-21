# -*- coding: utf-8 -*-
"""CAD-AGENT-CAD-CONTROL-COMMAND-CONTRACT-01 정책 감사."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "local_agent" / "cad" / "command_contract.py"
AUDIT = ROOT / "local_agent" / "cad" / "command_audit.py"
APPROVAL = ROOT / "local_agent" / "cad" / "command_approval.py"
INIT = ROOT / "local_agent" / "cad" / "__init__.py"
TEST = ROOT / "tests" / "test_cad_agent_command_contract.py"

REQUIRED_FILES = (CONTRACT, AUDIT, APPROVAL, INIT, TEST)

FORBIDDEN_NETWORK_OR_PROCESS = (
    "subprocess.Popen", "subprocess.run", "subprocess.call",
    "from subprocess", "import subprocess",
    "urlopen(", "from urllib.request", "import urllib.request",
    "import httpx", "from httpx",
    "import requests", "from requests",
)

FORBIDDEN_AUTOCAD = (
    "win32com", "pythoncom", "AutoCAD.Application",
    "GetActiveObject", ".SendCommand(", ".SelectAll(",
)

FORBIDDEN_DB = (
    "from sqlalchemy", "import sqlalchemy",
    "from django.db", "from alembic", "import alembic",
    "ALTER TABLE", "DROP TABLE", "sqlite3.connect(",
)

CROSS_REPO_FORBIDDEN = (
    "local_bridge", "app.backend", "app.frontend", "mcp_server",
)

REQUIRED_RISK_LEVELS = (
    "READ_ONLY", "CANDIDATE_PAYLOAD",
    "MUTATING_DXF", "MUTATING_AUTOCAD_COM",
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _scan(text, tokens) -> list:
    return [t for t in tokens if t in text]


def _imports(src: str) -> list:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    mods = []
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.append(n.module)
        elif isinstance(n, ast.Import):
            for a in n.names:
                mods.append(a.name)
    return mods


def audit():
    findings: dict = {}

    for p in REQUIRED_FILES:
        if not p.exists():
            findings.setdefault("_missing_files", []).append(
                str(p.relative_to(ROOT)))
    if findings:
        return {
            "verdict": "FAIL_CAD_AGENT_COMMAND_CONTRACT",
            "findings": findings,
        }

    contract_src = _read(CONTRACT)
    audit_src = _read(AUDIT)
    approval_src = _read(APPROVAL)
    init_src = _read(INIT)

    # 1) RiskLevel 4 enum 정의
    risks_ok = all(
        f'{v} = "{v}"' in contract_src for v in REQUIRED_RISK_LEVELS
    )
    if not risks_ok:
        findings.setdefault("_risks", []).append(
            "4 risk level enum 누락")

    # 2) READ_ONLY 9 + CANDIDATE_PAYLOAD 4 시드
    cp_tools_ok = (
        "arch_quantity_tab.build_cards" in contract_src
        and "drawing_inventory.analyze_drawing_inventory" in contract_src
        and "schedule_tables.detect" in contract_src
        and "construction_sequence.plan" in contract_src
    )
    if not cp_tools_ok:
        findings.setdefault("_candidate_seed", []).append(
            "CANDIDATE_PAYLOAD 4 시드 누락")

    # 3) READ_ONLY_TOOLS import (tool_catalog 재사용)
    read_only_import_ok = (
        "from . import tool_catalog" in contract_src
        or "from .tool_catalog import" in contract_src
    )
    if not read_only_import_ok:
        findings.setdefault("_read_only_import", []).append(
            "tool_catalog 의 READ_ONLY_TOOLS 재사용 누락")

    # 4) MUTATING risk 가 approval required 로 분류되는지 (정적 검증)
    mutating_approval_ok = (
        "MUTATING_DXF" in contract_src
        and "MUTATING_AUTOCAD_COM" in contract_src
        and "requires_approval" in contract_src
    )
    if not mutating_approval_ok:
        findings.setdefault("_mutating_approval", []).append(
            "MUTATING 의 requires_approval 정책 표기 누락")

    # 5) autoExecute=False 강제
    auto_off_ok = (
        "def autoExecute" in contract_src
        and "return False" in contract_src
    )
    if not auto_off_ok:
        findings.setdefault("_auto_execute", []).append(
            "autoExecute property 의 return False 누락")

    # 6) raw_text 필드 명시 금지
    raw_text_forbidden_ok = (
        "raw_text" not in contract_src
        # audit 에는 redact 정책 docstring 에 단어 등장 가능 — 데이터클래스
        # 필드로는 0건이어야 함
        and "rawText:" not in audit_src
        and "raw_text:" not in audit_src
    )
    if not raw_text_forbidden_ok:
        findings.setdefault("_raw_text_field", []).append(
            "raw_text / rawText 데이터 필드 0건 정책 위반")

    # 7) token 원문 저장 금지 — ApprovalRecord 에 raw token 필드 0.
    # method 매개변수의 `token: str` 은 허용 (verify/consume 가 token 인자 받음).
    # dataclass 저장 필드로서의 raw token 만 금지.
    import re as _re
    # ApprovalRecord 클래스 본문에서 raw token 필드 추출
    record_block = ""
    m = _re.search(
        r"class ApprovalRecord:.*?(?=\nclass |\n@|\Z)",
        approval_src, _re.S,
    )
    if m:
        record_block = m.group(0)
    # dataclass field 형태 (`    token: str` 등) 만 차단
    raw_token_field_patterns = (
        _re.compile(r"^\s{4,}token:\s+str", _re.M),
        _re.compile(r"^\s{4,}rawToken", _re.M),
        _re.compile(r"^\s{4,}raw_token:", _re.M),
        _re.compile(r"^\s{4,}token_raw", _re.M),
    )
    has_raw_field = any(p.search(record_block) for p in raw_token_field_patterns)
    token_hash_only_ok = (
        "tokenHash" in approval_src
        and not has_raw_field
        # 추가: module-level 변수로 raw token 저장 금지
        and "self.token =" not in approval_src
        and "self._token =" not in approval_src
        and "self.raw_token" not in approval_src
    )
    if not token_hash_only_ok:
        findings.setdefault("_token_hash_only", []).append(
            "approval record 에 raw token 저장 필드가 있음 "
            "(tokenHash 만 허용)")

    # 8) DuplicateApprovalError
    dup_err_ok = "class DuplicateApprovalError" in approval_src
    if not dup_err_ok:
        findings.setdefault("_dup_err", []).append(
            "DuplicateApprovalError 누락")

    # 9) one-time use — USED 상태 전이
    one_time_use_ok = (
        "ApprovalRecordStatus.USED" in approval_src
        and "def consume" in approval_src
    )
    if not one_time_use_ok:
        findings.setdefault("_one_time_use", []).append(
            "one-time use (consume → USED) 전이 누락")

    # 10) network / process 0건
    for p, src in (
        (CONTRACT, contract_src), (AUDIT, audit_src), (APPROVAL, approval_src),
    ):
        hits = _scan(src, FORBIDDEN_NETWORK_OR_PROCESS)
        if hits:
            findings.setdefault(f"_network_or_process[{p.name}]", []).extend(hits)

    # 11) AutoCAD / COM 0건
    for p, src in (
        (CONTRACT, contract_src), (AUDIT, audit_src), (APPROVAL, approval_src),
    ):
        hits = _scan(src, FORBIDDEN_AUTOCAD)
        if hits:
            findings.setdefault(f"_autocad[{p.name}]", []).extend(hits)

    # 12) DB / migration 0건
    for p, src in (
        (CONTRACT, contract_src), (AUDIT, audit_src), (APPROVAL, approval_src),
    ):
        hits = _scan(src, FORBIDDEN_DB)
        if hits:
            findings.setdefault(f"_db[{p.name}]", []).extend(hits)

    # 13) cross-repo import 0건
    for p, src in (
        (CONTRACT, contract_src), (AUDIT, audit_src), (APPROVAL, approval_src),
    ):
        for mod in _imports(src):
            for fp in CROSS_REPO_FORBIDDEN:
                if mod.startswith(fp):
                    findings.setdefault(
                        f"_cross_repo[{p.name}]", []).append(mod)

    # 14) 파일 write 0건 (D6 — audit log persistence 없음)
    for p, src in (
        (CONTRACT, contract_src), (AUDIT, audit_src), (APPROVAL, approval_src),
    ):
        # 'open(' literal 등장 0건
        if "open(" in src:
            findings.setdefault(
                f"_file_write[{p.name}]", []).append("open() 호출 존재")

    # 15) __init__ 재export
    init_export_ok = (
        "CadAgentCommand" in init_src
        and "CAD_COMMAND_REGISTRY" in init_src
        and "CAD_APPROVAL_STORE" in init_src
    )
    if not init_export_ok:
        findings.setdefault("_init_export", []).append(
            "local_agent/cad/__init__.py 의 신규 re-export 누락")

    # 16) import 가능
    sys.path.insert(0, str(ROOT))
    try:
        from local_agent.cad import command_contract as _c  # noqa
        from local_agent.cad import command_audit as _a  # noqa
        from local_agent.cad import command_approval as _p  # noqa
        from local_agent.cad import (  # noqa
            CadAgentCommand, CadCommandValidator,
            CAD_COMMAND_REGISTRY, CAD_APPROVAL_STORE, RiskLevel,
        )
        import_ok = True
    except Exception as e:
        import_ok = False
        findings.setdefault("_import", []).append(str(e))

    verdict = (
        "PASS_CAD_AGENT_COMMAND_CONTRACT"
        if (not findings and risks_ok and cp_tools_ok
            and read_only_import_ok and mutating_approval_ok
            and auto_off_ok and raw_text_forbidden_ok
            and token_hash_only_ok and dup_err_ok and one_time_use_ok
            and init_export_ok and import_ok)
        else "FAIL_CAD_AGENT_COMMAND_CONTRACT"
    )
    return {
        "verdict": verdict,
        "risks_ok": risks_ok,
        "cp_tools_ok": cp_tools_ok,
        "read_only_import_ok": read_only_import_ok,
        "mutating_approval_ok": mutating_approval_ok,
        "auto_off_ok": auto_off_ok,
        "raw_text_forbidden_ok": raw_text_forbidden_ok,
        "token_hash_only_ok": token_hash_only_ok,
        "dup_err_ok": dup_err_ok,
        "one_time_use_ok": one_time_use_ok,
        "init_export_ok": init_export_ok,
        "import_ok": import_ok,
        "findings": findings,
    }


def main():
    r = audit()
    print(f"[CAD AGENT COMMAND CONTRACT AUDIT] verdict={r['verdict']}")
    if r["verdict"].startswith("PASS"):
        print(
            f"  risks: {r['risks_ok']} cp: {r['cp_tools_ok']} "
            f"roImport: {r['read_only_import_ok']} "
            f"mutApproval: {r['mutating_approval_ok']} "
            f"autoOff: {r['auto_off_ok']} "
            f"noRawText: {r['raw_text_forbidden_ok']} "
            f"tokenHashOnly: {r['token_hash_only_ok']} "
            f"dupErr: {r['dup_err_ok']} oneTime: {r['one_time_use_ok']} "
            f"initExport: {r['init_export_ok']} import: {r['import_ok']}"
        )
    for f, lines in r.get("findings", {}).items():
        print(f"  {f}:")
        for entry in lines:
            print(f"    {entry}")
    return 0 if r["verdict"].startswith("PASS") else 2


if __name__ == "__main__":
    sys.exit(main())
