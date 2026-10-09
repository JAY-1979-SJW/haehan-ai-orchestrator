"""Read-only local-agent E2E flow contract audit.

This audit exercises the in-memory server/router path:
approved user request -> server queue -> authenticated local-agent WebSocket
-> delivered/running/completed result. It does not start a real server, open a
browser, call external sites, run Docker, build installers, or print secrets.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FORBIDDEN_DISPATCH_FIELDS = {
    "device_token",
    "token_hash",
    "authorization",
    "auth_header",
    "password",
    "otp",
    "cookie",
    "cookies",
    "session",
    "access_token",
    "refresh_token",
    "secret",
}


def _contains_forbidden_key(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_DISPATCH_FIELDS:
                found.append(str(key))
            found.extend(_contains_forbidden_key(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_contains_forbidden_key(child))
    return found


def _make_client() -> TestClient:
    from ai_orchestrator.agent_hub.router.root import local_agent_router
    from tools.gates.auth import get_current_user

    app = FastAPI()
    app.include_router(local_agent_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {
        "actor": "e2e_audit_admin",
        "role": "admin",
    }
    return TestClient(app, raise_server_exceptions=True)


def _reset_runtime_state() -> None:
    import ai_orchestrator.agent_hub.registry.facade as registry
    import ai_orchestrator.agent_hub.router.root as local_agent_router
    import ai_orchestrator.audit.audit_logger as audit_logger
    import tools.gates.approval as approval

    tmp_root = ROOT / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    audit_logger._LOG_PATH = tmp_root / "local_agent_e2e_audit.jsonl"
    approval._STORE_PATH = tmp_root / "local_agent_e2e_approval_tokens.jsonl"
    local_agent_router.log_event = lambda *args, **kwargs: None
    registry.clear()
    approval._store.clear()
    approval.clear_rate_store()


def _e2e_register(client):
    reg = client.post(
        "/api/v1/local-agents/register",
        json={"host": "e2e-audit", "os_name": "Windows", "version": "0.1.0"},
    )
    if reg.status_code != 200:
        return (False, [f"register failed status={reg.status_code}"]), None, None
    reg_body = reg.json()
    agent_id = reg_body.get("agent_id", "")
    device_token = reg_body.get("device_token", "")
    if not agent_id or not device_token:
        return (False, ["register response missing one-time agent credential"]), None, None
    return None, agent_id, device_token


def _e2e_create_task(client, agent_id):
    created = client.post(
        f"/api/v1/local-agents/{agent_id}/browser-readonly-instructions",
        json={
            "instruction": "open page and read title only",
            "url": "https://example.com/",
            "visible_browser": False,
        },
    )
    if created.status_code != 200:
        return (False, [f"readonly task create failed status={created.status_code}"]), None
    created_body = created.json()
    task_id = created_body.get("task_id", "")
    if created_body.get("status") != "queued" or not task_id:
        return (False, ["readonly task was not queued"]), None
    return None, task_id


def _e2e_websocket(client, agent_id, device_token, task_id):
    with client.websocket_connect("/api/v1/local-agents/ws") as ws:
        ws.send_json(
            {
                "type": "auth",
                "agent_id": agent_id,
                "device_token": device_token,
            }
        )
        auth = ws.receive_json()
        if auth.get("type") != "auth_ok":
            return False, ["websocket auth did not return auth_ok"]

        delivered = ws.receive_json()
        task = delivered.get("task", {})
        if delivered.get("type") != "task":
            return False, ["queued task was not delivered over websocket"]
        if task.get("task_id") != task_id:
            return False, ["delivered task_id mismatch"]
        if task.get("action") != "web_open_url_readonly":
            return False, ["delivered action is not readonly browser action"]
        forbidden = sorted(set(_contains_forbidden_key(task)))
        if forbidden:
            return False, ["forbidden dispatch field(s): " + ", ".join(forbidden)]

        ws.send_json({"type": "running", "task_id": task_id})
        running_ack = ws.receive_json()
        if running_ack.get("type") != "running_ack" or running_ack.get("status") != "running":
            return False, ["running ack failed"]

        ws.send_json(
            {
                "type": "result",
                "task_id": task_id,
                "success": True,
                "summary": "readonly page observed",
                "data": {
                    "current_url_host": "example.com",
                    "title_hint": "Example Domain",
                },
            }
        )
        result_ack = ws.receive_json()
        if result_ack.get("type") != "result_ack" or result_ack.get("status") != "completed":
            return False, ["result ack failed"]
    return None


def _e2e_final(client, agent_id, task_id):
    final = client.get(f"/api/v1/local-agents/{agent_id}/tasks/{task_id}")
    if final.status_code != 200:
        return False, [f"final task fetch failed status={final.status_code}"]
    final_body = final.json()
    if final_body.get("status") != "completed":
        return False, ["final task status is not completed"]
    forbidden_final = sorted(set(_contains_forbidden_key(final_body)))
    if forbidden_final:
        return False, ["forbidden final response field(s): " + ", ".join(forbidden_final)]
    return None


def _e2e_high_risk(agent_id):
    import ai_orchestrator.agent_hub.registry.facade as registry

    high = registry.enqueue_task(
        agent_id=agent_id,
        action="capture_screenshot",
        params={"options": {"dry_run": True}},
        requested_by="e2e_audit_admin",
    )
    if high.status != "waiting_approval":
        return False, ["high-risk task did not wait for approval"]
    if any(task.task_id == high.task_id for task in registry.list_pending_for_agent(agent_id)):
        return False, ["unapproved high-risk task appeared in dispatch queue"]
    return None


def audit() -> tuple[bool, list[str]]:
    findings: list[str] = []
    _reset_runtime_state()
    client = _make_client()

    _early, agent_id, device_token = _e2e_register(client)
    if _early is not None:
        return _early

    _early, task_id = _e2e_create_task(client, agent_id)
    if _early is not None:
        return _early

    _early = _e2e_websocket(client, agent_id, device_token, task_id)
    if _early is not None:
        return _early

    _early = _e2e_final(client, agent_id, task_id)
    if _early is not None:
        return _early

    _early = _e2e_high_risk(agent_id)
    if _early is not None:
        return _early

    findings.append("approved user can queue readonly browser task")
    findings.append("authenticated local agent receives task over websocket")
    findings.append("task transitions delivered -> running -> completed")
    findings.append("dispatch and final response contain no forbidden secret fields")
    findings.append("unapproved high-risk task is excluded from dispatch")
    return True, findings


def main() -> int:
    from scripts.common.audit_cli import report_findings

    ok, findings = audit()
    return report_findings(ok, findings, "LOCAL_AGENT_E2E_FLOW_CONTRACT")


if __name__ == "__main__":
    raise SystemExit(main())
