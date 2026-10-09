"""LOCAL-DESKTOP-AGENT-LIVE-INSTALL-CONNECTION-SMOKE-01 라이브 smoke.

검증 단계:
  A) 서버 HEAD 확인 (remote git)
  B) docker 컨테이너 상태 (SSH 가능 시)
  C) nginx config 의 WebSocket 경로 검증
  D) 인 프로세스(in-process) E2E:
     register_agent → authenticate_agent → set_connected → set_last_seen
     → set_disconnected → reconnect
  E) ws URL normalize round-trip
  F) connection_diagnostics 출력에 토큰/secret 누출 없음
  G) 결과 → audit 입력 JSON 생성

본 smoke 는 운영 서버에 destructive 호출을 하지 않는다.
SSH 가능 시 read-only 점검만 (docker ps, nginx config dump).
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from ai_orchestrator.agent_hub.registry import facade as reg
from ai_orchestrator.auth import registration_codes as rc
from core.agent_runtime.connection import connection_diagnostics as cd

OUT_DIR = Path("data/inspection/local_desktop_agent_live_connection")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _ssh(cmd: str, timeout: float = 10.0) -> tuple[bool, str]:
    """haehan-app SSH alias 로 명령 실행. 실패 시 (False, error)."""
    try:
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={int(timeout)}", "haehan-app", cmd],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
            encoding="utf-8",
        )
        if r.returncode == 0:
            return (True, r.stdout)
        return (False, (r.stderr or r.stdout)[:300])
    except Exception as exc:  # noqa: BLE001 - 로컬 데스크톱 에이전트 실시간 연결 스모크테스트 — ssh/git head 조회 실패는 빈 문자열 폴백, 각 검증 단계(step) 실패는 report에 에러 기록 후 다음 단계 계속, 모두 read-only 진단
        return (False, str(exc)[:300])


def step_a_server_head() -> dict:
    out: dict[str, object] = {"step": "A_server_head"}
    # 1) 로컬 git 의 remote head
    try:
        r = subprocess.run(
            ["git", "ls-remote", "haehan-server", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
        )
        remote_head = r.stdout.split()[0] if r.returncode == 0 and r.stdout else ""
    except Exception:  # noqa: BLE001 - 로컬 데스크톱 에이전트 실시간 연결 스모크테스트 — ssh/git head 조회 실패는 빈 문자열 폴백, 각 검증 단계(step) 실패는 report에 에러 기록 후 다음 단계 계속, 모두 read-only 진단
        remote_head = ""
    # 2) ssh 로 deployed head (이중 확인)
    ok, ssh_head = _ssh(
        "cd /home/ubuntu/apps/haehan-ai-orchestrator && git rev-parse HEAD",
        timeout=8,
    )
    out["remote_head"] = remote_head[:16]
    ssh_head_short = ssh_head.strip()[:16] if ok else ""
    out["ssh_head"] = ssh_head_short
    # 3) 로컬 HEAD
    local_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()[:16]
    out["local_head"] = local_head
    out["server_matches_local"] = remote_head[:7] == local_head[:7] or ssh_head_short[:7] == local_head[:7]
    return out


def step_b_containers() -> dict:
    out: dict[str, object] = {"step": "B_containers"}
    ok, txt = _ssh("docker ps --format '{{.Names}}\\t{{.Status}}' | grep -E 'orchestrator|nginx|edge'", timeout=8)
    out["ssh_ok"] = ok
    if ok:
        out["containers"] = [ln.strip() for ln in txt.splitlines() if ln.strip()]
    else:
        out["error"] = txt
    return out


def step_c_nginx_ws() -> dict:
    out: dict[str, object] = {"step": "C_nginx_ws"}
    ok, txt = _ssh(
        "docker exec nginx cat /etc/nginx/conf.d/default.conf 2>/dev/null | grep -A 10 'local-agents/ws'",
        timeout=8,
    )
    out["ssh_ok"] = ok
    if not ok:
        out["error"] = txt
        return out
    body = txt
    out["has_proxy_http_version_11"] = "proxy_http_version 1.1" in body
    out["has_upgrade_header"] = "Upgrade" in body and "$http_upgrade" in body
    out["has_connection_upgrade"] = "upgrade" in body.lower() and "Connection" in body
    out["has_proxy_read_timeout"] = "proxy_read_timeout" in body
    out["has_ip_allowlist"] = "allow " in body and "deny" in body
    # 경로 prefix 확인 — /orchestrator/api/v1/local-agents/ws
    out["uses_orchestrator_prefix"] = "/orchestrator/api/v1/local-agents/ws" in body
    out["upstream_target"] = "haehan-ai-orchestrator-api:8400" in body
    out["snippet"] = body[:800]
    return out


def step_d_inprocess_e2e() -> dict:
    out: dict[str, object] = {"step": "D_inprocess_e2e"}
    reg.clear()
    rc.clear()
    try:
        res_issue = rc.issue_code(
            label="smoke",
            expires_in_minutes=10,
            issued_by="smoke",
            issuer_role="admin",
        )
        rec = rc.consume_code(res_issue.registration_code)
        out["issue_consume_ok"] = rec.code_id == res_issue.code.code_id
        reg_res = reg.register_agent(
            host="smoke-host",
            os_name="smoke-os",
            version="0.0.1",
            requested_by=f"registration_code:{rec.code_id}",
        )
        out["register_ok"] = bool(reg_res.agent.agent_id and reg_res.device_token)
        # token 원문 저장 안 됨
        stored = reg.get_agent(reg_res.agent.agent_id)
        out["token_not_stored_raw"] = "device_token" not in getattr(stored, "__dataclass_fields__", {})
        # auth ok
        ok = reg.authenticate_agent(reg_res.agent.agent_id, reg_res.device_token)
        out["auth_ok"] = ok is not None
        bad = reg.authenticate_agent(reg_res.agent.agent_id, "wrong")
        out["bad_token_4401_ok"] = bad is None
        # heartbeat 시뮬레이션
        reg.set_agent_connected(reg_res.agent.agent_id)
        out["set_connected_ok"] = True
        reg.set_agent_last_seen(reg_res.agent.agent_id)
        out["heartbeat_ok"] = True
        reg.set_agent_disconnected(reg_res.agent.agent_id)
        # reconnect
        ok2 = reg.authenticate_agent(reg_res.agent.agent_id, reg_res.device_token)
        out["reconnect_ok"] = ok2 is not None
    finally:
        reg.clear()
        rc.clear()
    return out


def step_e_url_normalize() -> dict:
    out: dict[str, object] = {"step": "E_url_normalize"}
    cases = [
        ("https://api.haehan.ai", "wss://api.haehan.ai/api/v1/local-agents/ws"),
        ("https://api.haehan.ai/orchestrator", "wss://api.haehan.ai/orchestrator/api/v1/local-agents/ws"),
        ("http://localhost:8400", "ws://localhost:8400/api/v1/local-agents/ws"),
    ]
    results = []
    for base, expected in cases:
        actual = cd.normalize_ws_url(base)
        results.append({"input": base, "expected": expected, "actual": actual, "ok": actual == expected})
    out["cases"] = results
    out["all_ok"] = all(c["ok"] for c in results)
    return out


def step_f_token_leak_self_check() -> dict:
    """diagnostics 출력에 token/secret 미노출 확인."""
    out: dict[str, object] = {"step": "F_token_leak"}
    d = cd.build_diagnostics(
        server_base_url="https://api.haehan.ai/orchestrator?token=SECRETXYZ&device_token=ABCDEF",
        agent_id="la-abc123def456",
        state=cd.STATE_AUTH_FAILED,
        last_heartbeat_iso="2026-05-21T01:00:00+09:00",
        last_error_code="AUTH_FAILED_4401",
    )
    block = cd.render_user_block(d)
    one = cd.render_one_line(d)
    leaks_block = cd.find_token_leaks(block)
    leaks_one = cd.find_token_leaks(one)
    out["secret_in_output"] = "SECRETXYZ" in block or "ABCDEF" in block or "SECRETXYZ" in one or "ABCDEF" in one
    out["raw_agent_id_in_output"] = "abc123def456" in (block + one)
    out["leak_keywords_block"] = leaks_block
    out["leak_keywords_one"] = leaks_one
    out["pass"] = not out["secret_in_output"] and not out["raw_agent_id_in_output"]
    return out


def main() -> None:
    report: dict[str, Any] = {
        "schema_version": "live-smoke-1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "steps": {},
    }
    for name, fn in (
        ("A_server_head", step_a_server_head),
        ("B_containers", step_b_containers),
        ("C_nginx_ws", step_c_nginx_ws),
        ("D_inprocess_e2e", step_d_inprocess_e2e),
        ("E_url_normalize", step_e_url_normalize),
        ("F_token_leak", step_f_token_leak_self_check),
    ):
        try:
            report["steps"][name] = fn()
        except Exception as exc:  # noqa: BLE001 - 로컬 데스크톱 에이전트 실시간 연결 스모크테스트 — ssh/git head 조회 실패는 빈 문자열 폴백, 각 검증 단계(step) 실패는 report에 에러 기록 후 다음 단계 계속, 모두 read-only 진단
            report["steps"][name] = {"error": str(exc)[:300]}
    # audit 입력용 e2e_results 추출
    d = report["steps"].get("D_inprocess_e2e", {})
    f = report["steps"].get("F_token_leak", {})
    c = report["steps"].get("C_nginx_ws", {})
    e = report["steps"].get("E_url_normalize", {})
    a = report["steps"].get("A_server_head", {})
    audit_input = {
        "e2e_results": {
            "register_ok": d.get("register_ok"),
            "auth_ok": d.get("auth_ok"),
            "heartbeat_ok": d.get("heartbeat_ok"),
            "bad_token_4401_ok": d.get("bad_token_4401_ok"),
            "reconnect_ok": d.get("reconnect_ok"),
        },
        "token_leak_detected": not f.get("pass", True),
        "nginx_ok": (
            c.get("ssh_ok")
            and c.get("has_proxy_http_version_11")
            and c.get("has_upgrade_header")
            and c.get("has_connection_upgrade")
        ),
        "uses_orchestrator_prefix": c.get("uses_orchestrator_prefix", False),
        "has_ip_allowlist": c.get("has_ip_allowlist", False),
        "server_matches_local": a.get("server_matches_local", False),
        "url_normalize_all_ok": e.get("all_ok", False),
    }
    report["audit_input"] = audit_input
    out = OUT_DIR / "live_smoke_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # 사람용 텍스트
    md = ["# Local Desktop Agent — Live Connection Smoke", f"- generated_at: {report['generated_at']}", ""]
    for k, v in report["steps"].items():
        md.append(f"## {k}")
        md.append("```")
        md.append(json.dumps(v, ensure_ascii=False, indent=2)[:1500])
        md.append("```")
    (OUT_DIR / "live_smoke_report.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2)[:3000])
    print(f"\n[saved] {out}")


if __name__ == "__main__":
    main()
