"""사용자 데스크앱 진입점 (production 용).

흐름:
  1) 저장된 agent_id/device_token 로드 시도 (token_store)
  2) 없으면 stdin/UI 에서 registration_code 입력
  3) registration_client.register_with_code 호출
  4) device_token 저장 (keyring 우선, fallback 평문 — 옵트인)
  5) websocket_client.run_forever 로 wss 연결 + heartbeat

지원 모드:
  --diagnostics : 연결 상태만 출력 후 종료
  --self-test   : 의존성/경로/URL normalize 검증 후 종료
  --reset       : 저장된 token 삭제
  (default)     : connect + heartbeat 무한 루프

PII 정책:
  device_token / registration_code 원문은 stdout 에 절대 출력 금지.
  agent_id 는 마스킹 표시.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from local_agent import connection_diagnostics as cd
from local_agent import registration_client as rcli
from local_agent import token_store as ts

# 기본 서버 URL (사용자가 환경변수/플래그로 override 가능)
DEFAULT_SERVER_URL = "https://haehan-ai.kr/orchestrator"


# ── self-test ────────────────────────────────────────────────────


def self_test() -> dict:
    """의존성/경로/URL normalize 종합 검사. 외부 호출 없음."""
    result = {"checks": {}}

    # 1) 핵심 의존성
    for mod in (
        "local_agent.token_store",
        "local_agent.registration_client",
        "local_agent.websocket_client",
        "local_agent.connection_diagnostics",
    ):
        try:
            __import__(mod)
            result["checks"][mod] = "ok"
        except Exception as exc:
            result["checks"][mod] = f"fail:{exc}"

    # 2) URL normalize
    try:
        for base in ("https://haehan-ai.kr/orchestrator", "http://localhost:8400", "wss://example.com"):
            url = cd.normalize_ws_url(base)
            result["checks"][f"ws_url:{base}"] = url
    except Exception as exc:
        result["checks"]["ws_url"] = f"fail:{exc}"

    # 3) token_store backend
    try:
        available, name = ts.describe_backend()
        result["checks"]["token_store_backend"] = f"available={available} name={name}"
    except Exception as exc:
        result["checks"]["token_store_backend"] = f"fail:{exc}"

    # 4) sample diagnostic render
    diag = cd.build_diagnostics(
        server_base_url=DEFAULT_SERVER_URL,
        agent_id="la-self-test-0000",
        state=cd.STATE_NOT_REGISTERED,
    )
    block = cd.render_user_block(diag)
    leaks = cd.find_token_leaks(block)
    result["checks"]["diagnostics_render_leaks"] = leaks
    result["checks"]["diagnostics_render_ok"] = not leaks and "agent_id" in block

    ok = all(
        (v == "ok" or "fail" not in str(v)) if not isinstance(v, list) else (v == []) for v in result["checks"].values()
    )
    result["ok"] = ok
    return result


# ── 진단 출력 ────────────────────────────────────────────────────


def show_diagnostics(server_url: str) -> dict:
    """Print connection diagnostics without exposing token values."""
    available, backend = ts.describe_backend()
    cur_agent = ""
    effective_server = server_url
    try:
        from local_agent import desktop_config as dc

        cfg = dc.load_config()
        if not effective_server and cfg.server_url:
            effective_server = cfg.server_url
        cur_agent = cfg.agent_id or ""
    except Exception:  # noqa: S110
        pass

    token_present = False
    if cur_agent and effective_server:
        try:
            token_present = ts.has_device_token(
                server_url=effective_server,
                agent_id=cur_agent,
            )
        except Exception:
            token_present = False

    if not cur_agent:
        diag_state = cd.STATE_NOT_REGISTERED
        last_error_code = ""
    elif token_present:
        diag_state = cd.STATE_DISCONNECTED
        last_error_code = ""
    else:
        diag_state = cd.STATE_NOT_REGISTERED
        last_error_code = "TOKEN_NOT_STORED"

    diag = cd.build_diagnostics(
        server_base_url=effective_server,
        agent_id=cur_agent,
        state=diag_state,
        last_error_code=last_error_code,
    )
    recovery = cd.build_recovery_plan(
        state=diag_state,
        last_error_code=last_error_code,
        token_present=token_present,
    )
    return {
        "server_url": diag.server_url_redacted,
        "ws_url": diag.ws_url_redacted,
        "token_store_backend": backend,
        "token_store_available": available,
        "agent_id_masked": cd.mask_agent_id(cur_agent),
        "token_present": token_present,
        "recovery_plan": recovery.to_dict(),
        "diagnostics_block": cd.render_user_block(diag),
        "recovery_block": cd.render_recovery_block(recovery),
    }


# ── register flow ────────────────────────────────────────────────


def _redacted_log(msg: str) -> None:
    """token/code 원문 노출 없는 안전 로그."""
    logging.getLogger("desktop_launcher").info(msg)


def register_flow(server_url: str, registration_code: str) -> dict:
    """register-with-code → device_token 저장 까지."""
    import platform
    import socket

    _redacted_log("register-with-code 호출 시작")
    try:
        meta, device_token = rcli.register_with_code(
            server_url=server_url,
            registration_code=registration_code,
            host=socket.gethostname() or "unknown-host",
            os_name=(platform.system() + " " + platform.release()) or "unknown-os",
            version="0.1.0",
        )
    except rcli.RegistrationError as exc:
        return {
            "ok": False,
            "error_code": "REGISTRATION_ERROR",
            "user_message": cd.explain_error("REG_CODE_INVALID")
            if "401" in str(exc) or "404" in str(exc)
            else cd.explain_error("SERVER_NOT_REACHABLE"),
        }
    agent_id = meta.agent_id
    # 안전 저장
    try:
        ts.save_device_token(server_url=server_url, agent_id=agent_id, token=device_token)
    except ts.TokenStoreError:
        return {"ok": False, "error_code": "TOKEN_NOT_STORED", "user_message": cd.explain_error("TOKEN_NOT_STORED")}
    # 원문 폐기
    device_token = ""
    return {
        "ok": True,
        "agent_id_masked": cd.mask_agent_id(agent_id),
        "registered_at_iso": getattr(meta, "registered_at", getattr(meta, "registered_at_iso", "")),
    }


# ── connect flow ─────────────────────────────────────────────────


def connect_flow(server_url: str, agent_id: str) -> int:
    """저장된 device_token 으로 wss 연결. 반환 = exit code."""
    token = ts.load_device_token(server_url=server_url, agent_id=agent_id)
    if not token:
        diag = cd.build_diagnostics(
            server_base_url=server_url,
            agent_id=agent_id,
            state=cd.STATE_NOT_REGISTERED,
            last_error_code="TOKEN_NOT_STORED",
        )
        print(cd.render_user_block(diag))
        return 2
    from local_agent import websocket_client as ws

    try:
        ws.connect(agent_id=agent_id, device_token=token)
    finally:
        token = ""
    return 0


# ── CLI ────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="haehan-agent")
    ap.add_argument("--server", default=os.environ.get("HAEHAN_AGENT_SERVER", DEFAULT_SERVER_URL))
    ap.add_argument("--diagnostics", action="store_true", help="진단 정보만 출력 후 종료")
    ap.add_argument("--self-test", action="store_true", help="의존성/경로/URL normalize 검증")
    ap.add_argument("--register", action="store_true", help="registration_code 입력하여 등록")
    ap.add_argument("--agent-id", default="", help="기존 agent_id (재연결용)")
    ap.add_argument("--registration-code-env", default="HAEHAN_AGENT_CODE", help="registration_code 환경변수명")
    ap.add_argument("--reset", action="store_true", help="저장된 token 삭제 (server+agent_id 필요)")
    ap.add_argument("--gui", action="store_true", help="GUI 모드 (tkinter + pystray tray) 실행")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.gui:
        try:
            from . import gui_tray

            return gui_tray.run_tray_with_app(server_url=args.server)
        except Exception as exc:
            print(f"GUI 실행 실패: {type(exc).__name__}")
            return 1

    if args.self_test:
        r = self_test()
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["ok"] else 1

    if args.diagnostics:
        r = show_diagnostics(args.server)
        print(
            json.dumps(
                {k: v for k, v in r.items() if k not in ("diagnostics_block", "recovery_block")},
                ensure_ascii=False,
                indent=2,
            )
        )
        print()
        print(r["diagnostics_block"])
        print()
        print(r["recovery_block"])
        return 0

    if args.reset:
        if not args.agent_id:
            print("--reset 은 --agent-id 필요")
            return 2
        ts.delete_device_token(server_url=args.server, agent_id=args.agent_id)
        print(f"token 삭제 완료 ({cd.mask_agent_id(args.agent_id)})")
        return 0

    if args.register:
        raw_code = os.environ.get(args.registration_code_env, "").strip()
        if not raw_code:
            print(f"환경변수 {args.registration_code_env} 에 registration_code 를 설정하세요")
            return 2
        r = register_flow(args.server, raw_code)
        if r.get("ok"):
            print(f"등록 성공: agent_id={r['agent_id_masked']}")
            return 0
        print(f"등록 실패: {r.get('user_message', '')}")
        return 1

    if not args.agent_id:
        # 기본 동작 = GUI 실행 (인자 없이 더블클릭 / .exe 실행)
        try:
            from . import gui_tray

            return gui_tray.run_tray_with_app(server_url=args.server)
        except Exception as exc:
            print(f"GUI 실행 실패: {type(exc).__name__}: {exc}")
            print("CLI 사용: --self-test / --diagnostics / --register / --agent-id")
            return 1
    return connect_flow(args.server, args.agent_id)


if __name__ == "__main__":
    sys.exit(main())
