"""LIVE_PUBLIC_WS_FROM_USER_IP_01 — public endpoint 외부 흐름 라이브 검증.

운영 서버 (haehan-ai.kr) 의 nginx 공개 endpoint 가
사용자 데스크앱 흐름을 정상 수용하는지 검증.

검증 단계:
  1) register-with-code POST (HTTPS) → agent_id + device_token
  2) WSS ws → 첫 frame auth → auth_ok
  3) heartbeat → heartbeat_ack
  4) disconnect → reconnect 동일 token 재사용
  5) bad token → 4401 close
  6) admin endpoint 접근 시도 → 차단 또는 4xx
  7) 산출물: PII 마스킹된 JSON/MD

주의:
  - registration_code 원문은 보고서/로그에 저장하지 않는다.
  - device_token 원문은 보고서에 저장하지 않는다. (hash 만)
  - agent_id 는 mask.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import ssl
import time
import urllib.request
from pathlib import Path
from typing import Any

OUT_DIR = Path("data/inspection/local_agent_public_ws_user_ip")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SERVER_BASE = os.environ.get("SMOKE_SERVER_BASE", "https://haehan-ai.kr/orchestrator")
REGISTER_URL = SERVER_BASE + "/api/v1/local-agents/register-with-code"
WS_URL = SERVER_BASE.replace("https://", "wss://").replace("http://", "ws://") + "/api/v1/local-agents/ws"
ADMIN_LIST_URL = SERVER_BASE + "/api/v1/local-agents"
ADMIN_CODES_URL = SERVER_BASE + "/api/v1/local-agents/registration-codes"


def _mask(s: str, head: int = 4, tail: int = 4) -> str:
    if not s:
        return ""
    if len(s) <= head + tail:
        return "***"
    return f"{s[:head]}***{s[-tail:]}"


def _hash(s: str) -> str:
    return hashlib.sha256((s or "").encode()).hexdigest()[:16]


def http_post_json(url: str, body: dict, timeout: float = 10.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return {"status": r.status, "body": json.loads(r.read().decode("utf-8") or "{}")}
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode("utf-8")[:300]
        except Exception:  # noqa: BLE001 - 로컬 에이전트 외부 접근 smoke 테스트 - HTTP/WS 실패를 에러 dict로 반환
            body_text = ""
        return {"status": e.code, "error": str(e.reason), "body_excerpt": body_text}
    except Exception as e:  # noqa: BLE001 - 로컬 에이전트 외부 접근 smoke 테스트 - HTTP/WS 실패를 에러 dict로 반환
        return {"status": -1, "error": str(e)[:200]}


def http_get(url: str, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(url, method="GET")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            body = r.read(500).decode("utf-8", errors="replace")
            return {"status": r.status, "body_excerpt": body[:300]}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "error": str(e.reason)}
    except Exception as e:  # noqa: BLE001 - 로컬 에이전트 외부 접근 smoke 테스트 - HTTP/WS 실패를 에러 dict로 반환
        return {"status": -1, "error": str(e)[:200]}


# ── WS smoke ────────────────────────────────────────────────────


async def ws_auth_flow(agent_id: str, device_token: str, *, send_bad: bool = False, heartbeats: int = 1) -> dict:
    """auth → heartbeat → disconnect 라이프사이클 1회."""
    import websockets

    res: dict[str, Any] = {"steps": [], "ok": False}
    try:
        async with websockets.connect(WS_URL, open_timeout=10) as ws:
            res["steps"].append("ws_open")
            tok = "wrong_token_xxx" if send_bad else device_token
            await ws.send(json.dumps({"type": "auth", "agent_id": agent_id, "device_token": tok}))
            res["steps"].append("auth_sent")
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=8)
            except TimeoutError:
                res["steps"].append("auth_recv_timeout")
                return res
            msg = json.loads(raw)
            res["auth_response_type"] = msg.get("type", "")
            if send_bad:
                # close 발생 대기 (4401 close 또는 auth_failed)
                res["bad_token_response"] = msg.get("type", "")
                # 자연 close 확인
                try:
                    await asyncio.wait_for(ws.recv(), timeout=3)
                except websockets.exceptions.ConnectionClosed as cc:
                    res["bad_close_code"] = cc.code
                except TimeoutError:
                    pass
                return res
            if msg.get("type") != "auth_ok":
                res["error"] = "no auth_ok"
                return res
            res["steps"].append("auth_ok")
            # heartbeat
            for i in range(heartbeats):
                await ws.send(json.dumps({"type": "heartbeat"}))
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=8)
                except TimeoutError:
                    res["steps"].append(f"hb_{i}_timeout")
                    return res
                m = json.loads(raw)
                if m.get("type") in ("heartbeat_ack", "idle"):
                    res["steps"].append(f"hb_{i}_{m.get('type')}")
                else:
                    res["steps"].append(f"hb_{i}_unexpected:{m.get('type', '')}")
            res["ok"] = True
    except Exception as e:  # noqa: BLE001 - 로컬 에이전트 외부 접근 smoke 테스트 - HTTP/WS 실패를 에러 dict로 반환
        res["error"] = str(e)[:200]
    return res


def main():
    print(f"[boot] server={SERVER_BASE}")
    report = {
        "server_base": SERVER_BASE,
        "register_url": REGISTER_URL,
        "ws_url_mask": WS_URL.replace("haehan-ai.kr", "***.kr"),
        "steps": {},
    }

    # 0) registration_code (from local /tmp/regcode.txt, file-only)
    code_path = "/tmp/regcode.txt"
    try:
        # 로컬 머신이므로 /tmp 는 WSL 외부 — skip Windows fallback
        if Path(code_path).exists():
            raw_code = Path(code_path).read_text(encoding="utf-8").strip()
        else:
            raw_code = os.environ.get("SMOKE_REGISTRATION_CODE", "").strip()
    except Exception:  # noqa: BLE001 - 로컬 에이전트 외부 접근 smoke 테스트 - HTTP/WS 실패를 에러 dict로 반환
        raw_code = ""
    if not raw_code:
        # /tmp 가 ssh server-side 경로일 수 있음 — fetch via ssh
        import subprocess

        r = subprocess.run(
            ["ssh", "haehan-app", "cat /tmp/regcode.txt"], capture_output=True, text=True, encoding="utf-8", timeout=10
        )
        if r.returncode == 0:
            raw_code = r.stdout.strip()
    report["steps"]["00_regcode_loaded"] = {
        "ok": bool(raw_code),
        "len": len(raw_code),
        "redacted": True,
    }

    # 1) external POST register-with-code
    print("[1] POST /register-with-code ...")
    r1 = http_post_json(REGISTER_URL, {"registration_code": raw_code})
    body = r1.get("body") or {}
    agent_id = body.get("agent_id") or ""
    device_token = body.get("device_token") or ""
    report["steps"]["01_register_with_code"] = {
        "status": r1.get("status"),
        "ok": r1.get("status") == 200 and bool(agent_id and device_token),
        "agent_id_masked": _mask(agent_id),
        "device_token_hash": _hash(device_token),
        # device_token / agent_id 원문 미저장
        "error": r1.get("error", ""),
    }
    if not (agent_id and device_token):
        report["steps"]["01_register_with_code"]["body_excerpt"] = (r1.get("body_excerpt", "") or str(body))[:200]
        _save(report)
        return

    # 2) WSS auth + heartbeat
    print("[2] wss auth + heartbeat ...")
    res_ok = asyncio.run(ws_auth_flow(agent_id, device_token, send_bad=False, heartbeats=2))
    report["steps"]["02_ws_auth_ok"] = res_ok

    # 3) reconnect with same token
    print("[3] wss reconnect (same token) ...")
    res_reconnect = asyncio.run(ws_auth_flow(agent_id, device_token, send_bad=False, heartbeats=1))
    report["steps"]["03_reconnect_same_token"] = res_reconnect

    # 4) bad token → 4401
    print("[4] wss bad token ...")
    res_bad = asyncio.run(ws_auth_flow(agent_id, "wrong_token_xxx", send_bad=True, heartbeats=0))
    report["steps"]["04_bad_token"] = res_bad

    # 5) admin endpoint 차단 확인 (from this allowed IP it would succeed,
    #    so we measure status to know expected behavior elsewhere)
    print("[5] admin endpoint GET (from allowed IP — verifies routing only) ...")
    a1 = http_get(ADMIN_LIST_URL)
    a2 = http_post_json(ADMIN_CODES_URL, {"label": "smoke", "expires_in_minutes": 1, "issued_by": "smoke"})
    report["steps"]["05_admin_endpoints_from_allowed_ip"] = {
        "list_status": a1.get("status"),
        "issue_status": a2.get("status"),
        "note": (
            "이 IP 는 allowlist 멤버라 admin 접근 성공 가능. 외부 IP 차단은 nginx config 검증으로 보장 (deploy audit)."
        ),
    }

    # 6) 사용자 진단 메시지 — connection_diagnostics 출력 예시
    from core.agent_runtime.connection import connection_diagnostics as cd

    diag_ok = cd.build_diagnostics(
        server_base_url=SERVER_BASE,
        agent_id=agent_id,
        state=cd.STATE_CONNECTED,
        last_heartbeat_iso=time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        reconnect_count=1,
    )
    diag_fail = cd.build_diagnostics(
        server_base_url=SERVER_BASE,
        agent_id=agent_id,
        state=cd.STATE_AUTH_FAILED,
        last_error_code="AUTH_FAILED_4401",
    )
    report["steps"]["06_user_diagnostics"] = {
        "connected_block": cd.render_user_block(diag_ok),
        "auth_failed_block": cd.render_user_block(diag_fail),
    }

    _save(report)


def _save(report: dict) -> None:
    p1 = OUT_DIR / "live_public_ws_report.json"
    p1.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_lines = [
        "# Live Public WS — from user IP",
        "",
        f"server: `{report.get('server_base', '')}`",
        f"ws: `{report.get('ws_url_mask', '')}`",
        "",
    ]
    for k, v in report.get("steps", {}).items():
        md_lines.append(f"## {k}")
        md_lines.append("```")
        md_lines.append(json.dumps(v, ensure_ascii=False, indent=2)[:1500])
        md_lines.append("```")
    (OUT_DIR / "live_public_ws_summary.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\n[saved] {p1}")


if __name__ == "__main__":
    main()
