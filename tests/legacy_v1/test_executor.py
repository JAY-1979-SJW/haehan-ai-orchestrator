"""
executor.py 단위 테스트 (6단계)
- low task → EXECUTED
- medium task (승인됨) → PREVIEW_ONLY (실행됨)
- high task → BLOCKED (승인돼도 실행 금지)
- critical task → BLOCKED
- task_store 미등록 → FAIL
- 실패 시 logs/execution.jsonl 기록 확인
"""

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Literal

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".."))

import orchestrator_v1.tasks.approval_manager as approval_manager
import orchestrator_v1.tasks.executor as exec_mod
import orchestrator_v1.tasks.task_store as task_store
from orchestrator_v1.core.models import RiskAssessment, TaskRequest
from orchestrator_v1.tasks.policy_engine import load_policy

RiskLevel = Literal["low", "medium", "high", "critical"]

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_stores(tmp_path, monkeypatch):
    task_store.clear()
    approval_manager._store.clear()
    monkeypatch.setattr(exec_mod, "_EXEC_LOG_PATH", str(tmp_path / "execution.jsonl"))
    monkeypatch.setattr(exec_mod, "_exec_logger", None)  # rotating logger 재초기화
    yield
    task_store.clear()
    approval_manager._store.clear()


def _policy_with_tmp() -> dict:
    policy = load_policy()
    tmp = tempfile.gettempdir()
    allowed = policy.get("allowed_paths", [])
    if tmp not in allowed:
        allowed.append(tmp)
    policy["allowed_paths"] = allowed
    return policy


def _register_task(task_id: str, action_type: str, risk_level: RiskLevel, target: str = "") -> tuple:
    if not target:
        # 실제 readable 파일 생성
        f = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False, dir=tempfile.gettempdir()
        )
        f.write("test content")
        f.close()
        target = f.name

    task = TaskRequest(
        task_id=task_id,
        source="pc",
        action_type=action_type,
        target=target,
        description=f"test {action_type}",
    )
    risk = RiskAssessment(
        risk_level=risk_level,
        requires_approval=risk_level != "low",
    )
    policy = _policy_with_tmp()
    task_store.register(task, risk, policy)
    return task, risk, policy


def _issue_and_approve(task_id: str, risk_level: RiskLevel) -> str:
    token_id = f"tok-{task_id}"
    approval_manager._store[token_id] = {
        "task_id": task_id,
        "risk_level": risk_level,
        "issued_at": time.time(),
        "approved": True,
        "rejected": False,
    }
    return token_id


def _read_exec_log(tmp_path) -> list:
    path = str(tmp_path / "execution.jsonl")
    if not Path(path).exists():
        return []
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]  # noqa: E741


# ── Tests ────────────────────────────────────────────────────────────────────


def test_low_task_executed(tmp_path):
    _task, _risk, _policy = _register_task("t-low-001", "read_file", "low")
    result = exec_mod.execute_task("t-low-001")

    assert result["status"] == "EXECUTED", result
    logs = _read_exec_log(tmp_path)
    assert any(l["task_id"] == "t-low-001" and l["status"] == "SUCCESS" for l in logs)  # noqa: E741


def test_medium_task_preview_only(tmp_path):
    _task, _risk, _policy = _register_task("t-med-001", "edit_config", "medium")
    # 토큰 발급 + 승인
    _issue_and_approve("t-med-001", "medium")

    result = exec_mod.execute_task("t-med-001")

    assert result["status"] == "PREVIEW_ONLY", result
    logs = _read_exec_log(tmp_path)
    assert any(l["task_id"] == "t-med-001" and l["status"] == "PREVIEW_ONLY" for l in logs)  # noqa: E741


def test_medium_task_without_approval_blocked(tmp_path):
    _task, _risk, _policy = _register_task("t-med-noapprove", "edit_config", "medium")
    # 토큰 없음 — approval_valid=False → plan.allowed=False → BLOCKED

    result = exec_mod.execute_task("t-med-noapprove")

    assert result["status"] == "BLOCKED", result


def test_high_task_blocked_even_if_approved(tmp_path):
    _task, _risk, _policy = _register_task("t-high-001", "restart_service", "high", target="nginx")
    _issue_and_approve("t-high-001", "high")

    result = exec_mod.execute_task("t-high-001")

    assert result["status"] == "BLOCKED", result
    assert "high" in result.get("error", "").lower()
    logs = _read_exec_log(tmp_path)
    assert any(l["task_id"] == "t-high-001" and l["status"] == "BLOCKED" for l in logs)  # noqa: E741


def test_critical_task_blocked(tmp_path):
    _task, _risk, _policy = _register_task("t-crit-001", "delete_file", "critical", target="/tmp/x.txt")

    result = exec_mod.execute_task("t-crit-001")

    assert result["status"] == "BLOCKED", result
    assert "critical" in result.get("error", "").lower()


def test_task_not_in_store_returns_fail(tmp_path):
    result = exec_mod.execute_task("nonexistent-task-xyz")

    assert result["status"] == "FAIL"
    assert "not found" in result.get("error", "")
    logs = _read_exec_log(tmp_path)
    assert any(l["task_id"] == "nonexistent-task-xyz" and l["status"] == "FAIL" for l in logs)  # noqa: E741


def test_execution_log_contains_duration(tmp_path):
    _register_task("t-dur-001", "read_file", "low")
    exec_mod.execute_task("t-dur-001")

    logs = _read_exec_log(tmp_path)
    entry = next((l for l in logs if l["task_id"] == "t-dur-001"), None)  # noqa: E741
    assert entry is not None
    assert "duration_ms" in entry
    assert entry["duration_ms"] >= 0


def test_execution_log_error_on_fail(tmp_path):
    exec_mod.execute_task("missing-task")
    logs = _read_exec_log(tmp_path)
    entry = next((l for l in logs if l["task_id"] == "missing-task"), None)  # noqa: E741
    assert entry is not None
    assert entry["error"] is not None


# ── Integration: dashboard approve → execute_task ─────────────────────────────


def test_dashboard_approve_triggers_execution(tmp_path, monkeypatch):
    """dashboard POST /approve → execute_task 호출 → execution 결과 응답에 포함"""
    import orchestrator_v1.core.audit_logger as al
    import orchestrator_v1.monitoring.dashboard as dash_mod
    import orchestrator_v1.monitoring.log_analyzer as log_analyzer

    monkeypatch.setattr(log_analyzer, "_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(log_analyzer, "_HISTORY_PATH", str(tmp_path / "history.jsonl"))
    monkeypatch.setattr(log_analyzer, "_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setattr(dash_mod, "_DECISIONS_PATH", str(tmp_path / "decisions.jsonl"))
    monkeypatch.setattr(exec_mod, "_EXEC_LOG_PATH", str(tmp_path / "execution.jsonl"))

    tmp_logs = str(tmp_path / "logs")
    Path(tmp_logs).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(al, "_LOGS_DIR", tmp_logs)
    monkeypatch.setattr(al, "_AUDIT_PATH", str(Path(tmp_logs) / "audit.jsonl"))
    al._logger = None

    # low task 등록
    _register_task("t-integ-low", "read_file", "low")
    # medium token 발급 (미승인 상태)
    token_id = "tok-t-integ-low"
    approval_manager._store[token_id] = {
        "task_id": "t-integ-low",
        "risk_level": "low",
        "issued_at": time.time(),
        "approved": False,
        "rejected": False,
    }

    monkeypatch.setenv("ORCH_DASHBOARD_USER", "test")
    monkeypatch.setenv("ORCH_DASHBOARD_PASSWORD", "test")

    import base64

    _auth_hdr = {"Authorization": "Basic " + base64.b64encode(b"test:test").decode()}

    from orchestrator_v1.monitoring.dashboard import create_app

    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as c:
        resp = c.post(
            "/dashboard/approve",
            headers=_auth_hdr,
            json={
                "token_id": token_id,
                "task_id": "t-integ-low",
                "user_id": "operator-1",
            },
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["decision"] == "APPROVED"
    assert "execution" in data, "execution result should be included in response"
    assert data["execution"]["status"] in {"EXECUTED", "PREVIEW_ONLY", "BLOCKED"}

    al._logger = None


# ── Rotation 검증 ─────────────────────────────────────────────────────────────


def test_exec_logger_uses_rotating_handler(tmp_path, monkeypatch):
    """_get_exec_logger() 가 RotatingFileHandler 를 사용하는지 확인."""
    from logging.handlers import RotatingFileHandler

    monkeypatch.setattr(exec_mod, "_EXEC_LOG_PATH", str(tmp_path / "execution.jsonl"))
    monkeypatch.setattr(exec_mod, "_exec_logger", None)

    lg = exec_mod._get_exec_logger()
    assert any(isinstance(h, RotatingFileHandler) for h in lg.handlers)


def test_rotation_creates_backup(tmp_path, monkeypatch):
    """maxBytes 초과 시 .1 백업 파일이 생성되는지 확인."""
    import logging
    from logging.handlers import RotatingFileHandler

    log_path = str(tmp_path / "execution.jsonl")
    monkeypatch.setattr(exec_mod, "_EXEC_LOG_PATH", log_path)

    lg = logging.getLogger("orchestrator.execution_jsonl_rot_test")
    fh = RotatingFileHandler(log_path, maxBytes=200, backupCount=2, encoding="utf-8")
    fh.setFormatter(exec_mod._ExecJsonFormatter())
    lg.addHandler(fh)
    lg.setLevel(logging.INFO)
    lg.propagate = False
    monkeypatch.setattr(exec_mod, "_exec_logger", lg)

    for i in range(10):
        exec_mod._log_execution(f"rot-{i:03d}", "SUCCESS", float(i))

    assert Path(log_path).exists()
    assert Path(log_path + ".1").exists(), "rotation backup not created"


def test_jsonl_format_preserved_after_rotation(tmp_path, monkeypatch):
    """rotation 후에도 각 줄이 유효한 JSON 이고 필수 필드를 보유하는지 확인."""
    import logging
    from logging.handlers import RotatingFileHandler

    log_path = str(tmp_path / "execution.jsonl")
    monkeypatch.setattr(exec_mod, "_EXEC_LOG_PATH", log_path)

    lg = logging.getLogger("orchestrator.execution_jsonl_fmt_test")
    fh = RotatingFileHandler(log_path, maxBytes=300, backupCount=10, encoding="utf-8")
    fh.setFormatter(exec_mod._ExecJsonFormatter())
    lg.addHandler(fh)
    lg.setLevel(logging.INFO)
    lg.propagate = False
    monkeypatch.setattr(exec_mod, "_exec_logger", lg)

    for i in range(15):
        exec_mod._log_execution(f"fmt-{i:03d}", "SUCCESS", float(i), None)

    records = []
    _log_path_obj = Path(log_path)
    for fp in sorted(_log_path_obj.parent.glob(_log_path_obj.name + "*")):
        with fp.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    obj = json.loads(line)  # JSONDecodeError 시 테스트 실패
                    records.append(obj)

    assert len(records) == 15
    for r in records:
        assert {"timestamp", "task_id", "status", "duration_ms"} <= r.keys()
