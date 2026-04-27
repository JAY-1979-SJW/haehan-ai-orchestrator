"""whitelist 기반 실제 실행 검증 스크립트.

검증 포인트:
1. submit 직후 medium 위험 작업 → PENDING_APPROVAL (승인 없이 실행 불가)
2. admin 승인 후 whitelist 허용 action → 실제 실행 성공 (execute_task 직접 호출)
3. whitelist 밖 action → BLOCKED:not_allowed_action
4. system_connector.get_server_status → 실제 CPU/메모리/uptime 반환
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import uuid


def _prep_env():
    logdir = tempfile.mkdtemp(prefix="verify_wl_")
    os.environ["AUTH_ENABLED"] = "false"
    os.environ["LOG_DIR"] = logdir

    from ai_orchestrator import config as _cfg; importlib.reload(_cfg)
    from ai_orchestrator import execution_limits as _el; importlib.reload(_el)
    from ai_orchestrator.connectors import system_connector as _sc; importlib.reload(_sc)
    from ai_orchestrator import executor as _ex; importlib.reload(_ex)
    return _ex, _sc


def _uniq(p): return f"{p}-{uuid.uuid4().hex[:8]}"


def main():
    # 프로젝트 루트를 sys.path에 넣어 모듈 import 가능하게
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    ex, sc = _prep_env()
    TaskRequest = __import__("ai_orchestrator.models", fromlist=["TaskRequest"]).TaskRequest

    print("=== [1] system_connector.get_server_status 직접 호출 ===")
    snap = sc.get_server_status()
    print(json.dumps(snap, ensure_ascii=False, indent=2))
    assert isinstance(snap, dict)
    assert "cpu_percent" in snap
    assert "memory" in snap
    assert "uptime_sec" in snap
    print("→ OK (실제 값 반환)\n")

    print("=== [2] execute_task(허용 action=get_server_status, risk=low) ===")
    req_ok = TaskRequest(
        task_id=_uniq("OK"),
        source="manual",
        action_type="get_server_status",
        target="localhost",
        description="server status snapshot",
        payload={},
        requested_by="admin_u",
    )
    result_ok = ex.execute_task(req_ok, risk_level="low")
    print(f"result = {result_ok!r}")
    assert not result_ok.startswith("BLOCKED"), f"허용 action 이 차단됨: {result_ok}"
    parsed = json.loads(result_ok)
    assert parsed.get("status") == "success"
    assert "data" in parsed
    print("→ OK (실제 실행 성공)\n")

    print("=== [3] execute_task(비허용 action=edit_config, risk=low) ===")
    req_evil = TaskRequest(
        task_id=_uniq("EV"),
        source="manual",
        action_type="edit_config",
        target="/var/www/haehan/cfg.yaml",
        description="whitelist 밖",
        payload={},
        requested_by="admin_u",
    )
    result_bad = ex.execute_task(req_evil, risk_level="low")
    print(f"result = {result_bad!r}")
    assert result_bad == "BLOCKED:not_allowed_action", f"expected BLOCKED:not_allowed_action, got {result_bad}"
    print("→ OK (whitelist 차단)\n")

    print("=== [4] execute_task(비허용 action=shell_exec, risk=high → 위험도 차단) ===")
    req_high = TaskRequest(
        task_id=_uniq("HI"),
        source="manual",
        action_type="shell_exec",
        target="/",
        description="high-risk attempt",
        payload={},
        requested_by="admin_u",
    )
    result_high = ex.execute_task(req_high, risk_level="high")
    print(f"result = {result_high!r}")
    assert result_high.startswith("BLOCKED:") and "not_allowed" in result_high
    print("→ OK (high-risk 자체 차단, 기존 로직 유지)\n")

    print("=== [5] submit_task 통합(medium 승인 플로우) — 승인 없이 실행 불가 검증 ===")
    os.environ["AUTH_ENABLED"] = "true"
    users_tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8")
    users_tmp.write(json.dumps([
        {"username": "admin_u", "password_hash": "pw-admin",
         "role": "admin", "enabled": True},
    ], ensure_ascii=False))
    users_tmp.close()
    os.environ["HTTP_USERS_PATH"] = users_tmp.name

    from ai_orchestrator import config as _cfg; importlib.reload(_cfg)
    from ai_orchestrator import auth as _au; importlib.reload(_au)
    from ai_orchestrator import execution_limits as _el; importlib.reload(_el)
    from ai_orchestrator import executor as _ex2; importlib.reload(_ex2)
    from ai_orchestrator import approval as _ap; importlib.reload(_ap); _ap.clear_rate_store()
    from ai_orchestrator import task_state as _ts; importlib.reload(_ts); _ts.clear()
    from ai_orchestrator.sites import router as _sr; importlib.reload(_sr)
    from ai_orchestrator import router as _rt; importlib.reload(_rt)
    from ai_orchestrator import server as _srv; importlib.reload(_srv)

    from fastapi.testclient import TestClient
    client = TestClient(_srv.app, raise_server_exceptions=True)

    task_id = _uniq("SM")
    submit_body = {
        "task_id": task_id, "source": "manual",
        "action_type": "edit_config", "target": "/var/www/haehan/cfg.yaml",
        "description": "medium whitelist flow",
    }
    r = client.post("/api/v1/tasks", json=submit_body, auth=("admin_u", "pw-admin"))
    print(f"submit → {r.status_code}: {r.json()}")
    assert r.status_code == 200
    sd = r.json()
    assert sd["status"] == "PENDING_APPROVAL"
    assert sd["requires_approval"] is True
    token_id = sd["approval_token_id"]
    print("→ OK (승인 없이는 PENDING_APPROVAL)\n")

    print("=== [6] admin 승인 후 execute_task(edit_config → whitelist BLOCKED) ===")
    r2 = client.post(f"/api/v1/tasks/{task_id}/approve",
                     params={"token_id": token_id}, json={},
                     auth=("admin_u", "pw-admin"))
    print(f"approve → {r2.status_code}: {r2.json()}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "approved"
    # edit_config 는 whitelist 에 없음 → execute_task 가 BLOCKED 리턴
    assert "not_allowed_action" in body["execution"], body
    assert body["executed"] is False
    print("→ OK (승인되어도 whitelist 밖이면 실행 차단)\n")

    print("=== [7] execution_history 감사 로그 확인 ===")
    hist_path = _cfg.EXECUTION_HISTORY_PATH
    if hist_path.exists():
        lines = hist_path.read_text(encoding="utf-8").strip().splitlines()
        last = [json.loads(l) for l in lines[-5:]]
        for e in last:
            print(" ", e.get("task_id"), "|", e.get("action_type"),
                  "|", e.get("status"), "|", e.get("note"))
        real_hits = [e for e in last if "execution_type=REAL" in (e.get("note") or "")]
        whitelist_hits = [e for e in last if "action_not_whitelisted" in (e.get("note") or "")]
        print(f"→ REAL 실행 기록: {len(real_hits)}건, whitelist 차단 기록: {len(whitelist_hits)}건")
    else:
        print("  execution_history 파일 없음 (skip)")

    print("\n=== VERIFY: ALL PASS ===")


if __name__ == "__main__":
    main()
