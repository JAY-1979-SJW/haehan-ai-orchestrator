"""로컬 에이전트 메인 엔트리 (Stage 1 — 폴링 데모).

사용자가 직접 실행:
  > python -m core.agent_runtime.agent

서버에 register → device_token 발급 → POLL_INTERVAL_SEC 마다
자기에게 할당된 작업이 있는지 확인 (1단계는 단일 작업 ID 폴링 데모).

본 모듈은 백그라운드 서비스로 등록되지 않으며, 사용자가 Ctrl+C 로
즉시 종료할 수 있다. 자동 시작 / 은폐 실행 / 백도어 기능 없음.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import platform
import sys
from pathlib import Path
from urllib import error as _urlerr
from urllib import request as _urlreq

from core.agent_runtime.common import config
from core.agent_runtime.common import desktop_config as _desk_cfg
from core.agent_runtime.common.audit import log_local_event
from core.agent_runtime.common.redaction import safe_summary as _safe_summary
from core.agent_runtime.connection import network_bypass as _network_bypass
from core.agent_runtime.connection import token_store as _token_store
from core.agent_runtime.connection.actions import execute_action
from core.agent_runtime.connection.registration_client import RegistrationError
from core.agent_runtime.connection.registration_client import register_with_code as _register_with_code
from local_agent import __version__

logger = logging.getLogger(__name__)


def _http_post(url: str, body: dict, basic_auth: tuple[str, str] | None = None) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = _urlreq.Request(  # noqa: S310
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    if basic_auth:
        import base64

        u, p = basic_auth
        creds = base64.b64encode(f"{u}:{p}".encode()).decode()
        req.add_header("Authorization", f"Basic {creds}")
    with _network_bypass.urlopen_for_server(url, req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get(url: str, basic_auth: tuple[str, str] | None = None) -> dict:
    req = _urlreq.Request(url, method="GET")  # noqa: S310
    if basic_auth:
        import base64

        u, p = basic_auth
        creds = base64.b64encode(f"{u}:{p}".encode()).decode()
        req.add_header("Authorization", f"Basic {creds}")
    with _network_bypass.urlopen_for_server(url, req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def register(basic_auth: tuple[str, str] | None) -> dict:
    url = f"{config.SERVER_BASE_URL.rstrip('/')}/api/v1/local-agents/register"
    body = {
        "host": platform.node(),
        "os_name": f"{platform.system()} {platform.release()}",
        "version": __version__,
    }
    resp = _http_post(url, body, basic_auth=basic_auth)
    # device_token 원문은 메모리에만 보관하고 audit 에는 기록하지 않는다.
    log_local_event(
        "agent_registered",
        agent_id=resp.get("agent_id"),
        host=resp.get("host"),
        os_name=resp.get("os_name"),
    )
    _persist_token(resp.get("agent_id", ""), resp.get("device_token", ""))
    return resp


def _persist_token(agent_id: str, device_token: str) -> None:
    """device_token 을 사용자 홈에 저장 (Windows ACL 권장).

    파일 자체는 0600 권한으로 만들 수 없는 OS 가 있으므로,
    적어도 사용자 디렉터리 하위에 저장하고 셸에서 보호하도록 README 안내.
    """
    if not agent_id or not device_token:
        return
    path: Path = config.TOKEN_STORE_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"agent_id": agent_id, "device_token": device_token}), encoding="utf-8")
        with contextlib.suppress(OSError):
            path.chmod(0o600)  # Windows 등에서는 별도 ACL 필요
    except OSError as e:
        logger.error("device_token 저장 실패: %s", e)


def execute_local(action: str, params: dict) -> dict:
    """로컬에서 액션 실행 + 결과 dict 반환."""
    result = execute_action(action, params)
    log_local_event(
        "action_executed",
        action=action,
        success=result.success,
        error_code=result.error_code,
    )
    return {
        "success": result.success,
        "summary": result.summary,
        "data": result.data,
        "error": result.error,
        "error_code": result.error_code,
    }


def cmd_register_with_code(*, server_url: str, registration_code: str, allow_plaintext: bool = False) -> int:
    """--register-with-code 흐름. 성공 시 0.

    출력 정책:
      - registration_code 원문 미출력
      - device_token 원문 미출력
      - agent_id / code_id / backend 이름만 출력
    """
    if not server_url:
        print("--server <URL> 이 필요합니다.", file=sys.stderr)
        return 2
    host = platform.node()
    os_name = f"{platform.system()} {platform.release()}"
    try:
        meta, device_token = _register_with_code(
            server_url,
            registration_code,
            host=host,
            os_name=os_name,
            version=__version__,
        )
    except RegistrationError as e:
        # generic_message 외 원문 노출 금지.
        print(f"등록 실패: {e.generic_message}", file=sys.stderr)
        return 1

    try:
        backend = _token_store.save_device_token(
            server_url,
            meta.agent_id,
            device_token,
            allow_plaintext_fallback=allow_plaintext,
        )
    except _token_store.TokenStoreError as e:
        # device_token이 keyring에 저장되지 않았다면 즉시 실패. 평문 미저장.
        print(f"token 저장 실패: {e}", file=sys.stderr)
        return 1
    finally:
        # 호출자 메모리에서 device_token 참조 해제.
        del device_token

    cfg = _desk_cfg.DesktopConfig(
        server_url=server_url.rstrip("/"),
        agent_id=meta.agent_id,
        label=meta.label,
        created_at=meta.registered_at,
        version=__version__,
    )
    _desk_cfg.save_config(cfg)

    log_local_event(
        "agent_registered_with_code",
        agent_id=meta.agent_id,
        code_id=meta.code_id,
        host=meta.host,
        backend=backend,
    )
    summary = _safe_summary(
        {
            "agent_id": meta.agent_id,
            "code_id": meta.code_id,
            "label": meta.label,
            "host": meta.host,
            "os_name": meta.os_name,
            "registered_at": meta.registered_at,
            "allowed_actions": meta.allowed_actions,
        }
    )
    summary["token_saved"] = True
    summary["token_backend"] = backend
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_auto_connect(*, server_url: str, allow_plaintext: bool = False) -> int:
    """상태 확인 -> 미등록이면 등록코드 자동 발급+소비 -> WebSocket 세션 시작.

    2026-09-29 추가: Electron(lib/agent.js) 등 자동 기동 경로 전용 — 사용자가 매번
    수동으로 --register-with-code를 실행하지 않아도 되게 한다. 등록코드 발급은
    AUTH_ENABLED=False(로컬 개발) 서버에서만 인증 없이 성공한다(ai_orchestrator/gates/
    auth.py get_current_user 확인) — 운영(AUTH_ENABLED=True) 서버에서는 401로 실패하며,
    그 경우 관리자가 수동으로 등록코드를 발급해 --register-with-code로 등록해야 한다.
    이미 등록돼 있으면(keyring에 device_token 존재) 발급 자체를 시도하지 않고 바로
    --run과 동일하게 동작한다.
    """
    if not server_url:
        print("--server <URL> 이 필요합니다.", file=sys.stderr)
        return 2

    cfg = _desk_cfg.load_config()
    already_registered = bool(
        cfg.agent_id
        and _token_store.has_device_token(server_url, cfg.agent_id, allow_plaintext_fallback=allow_plaintext)
    )

    if not already_registered:
        host = platform.node()
        try:
            code_resp = _http_post(
                f"{server_url.rstrip('/')}/api/v1/local-agents/registration-codes",
                {
                    "label": f"auto-{host}",
                    "expires_in_minutes": 10,
                    "allowed_actions": ["run_claude_agent"],
                    "note": "local_agent --auto-connect 자동 발급",
                },
            )
        except _urlerr.URLError as e:
            print(
                f"등록코드 자동 발급 실패({e}) — 운영 서버라면 관리자가 등록코드를 발급해 "
                "--register-with-code로 등록해야 합니다.",
                file=sys.stderr,
            )
            return 1
        code = code_resp.get("registration_code", "")
        if not code:
            print("등록코드 발급 응답이 비었습니다.", file=sys.stderr)
            return 1
        rc = cmd_register_with_code(server_url=server_url, registration_code=code, allow_plaintext=allow_plaintext)
        del code
        if rc != 0:
            return rc

    return run_websocket(server_url=server_url, allow_plaintext=allow_plaintext)


def cmd_status(*, server_url: str | None = None, allow_plaintext: bool = False) -> int:
    """--status — token 원문은 절대 출력하지 않는다."""
    cfg = _desk_cfg.load_config()
    effective_server = server_url or cfg.server_url
    usable, backend = _token_store.describe_backend()
    token_saved = False
    if effective_server and cfg.agent_id:
        token_saved = _token_store.has_device_token(
            effective_server,
            cfg.agent_id,
            allow_plaintext_fallback=allow_plaintext,
        )
    out = {
        "server_url": effective_server,
        "agent_id": cfg.agent_id,
        "label": cfg.label,
        "version": cfg.version,
        "token_saved": token_saved,
        "keyring_usable": usable,
        "keyring_backend": backend,
        "config_path": str(_desk_cfg.DEFAULT_CONFIG_PATH),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _load_token_for_run(server_url: str, agent_id: str, *, allow_plaintext: bool = False) -> str | None:
    """websocket 실행 직전에만 호출. 호출 후 즉시 변수 참조 해제 권장."""
    return _token_store.load_device_token(server_url, agent_id, allow_plaintext_fallback=allow_plaintext)


def _load_persisted_token() -> tuple[str, str] | None:
    """TOKEN_STORE_PATH 에서 agent_id + device_token 을 읽어 반환."""
    path = config.TOKEN_STORE_PATH
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("device_token 파일 읽기 실패: %s", e)
        return None
    agent_id = str(data.get("agent_id", "")).strip()
    device_token = str(data.get("device_token", "")).strip()
    if not agent_id or not device_token:
        return None
    return agent_id, device_token


def run_websocket(*, server_url: str | None = None, allow_plaintext: bool = False) -> int:
    """Stage 2 — WebSocket 세션 실행 (사용자 명시적 기동).

    토큰 로드 우선순위:
      1) keyring (config.json의 agent_id + server_url 기준)
      2) 평문 fallback (allow_plaintext=True 인 경우만)
      3) 레거시 ``TOKEN_STORE_PATH`` 평문 파일 (backward compat)
    """
    from core.agent_runtime.connection import websocket_client

    if not config.WEBSOCKET_ENABLED:
        print("WebSocket 비활성 상태. 환경변수 HAEHAN_AGENT_WS_ENABLED=true 후 실행", file=sys.stderr)
        return 2

    cfg = _desk_cfg.load_config()
    effective_server = server_url or cfg.server_url or config.SERVER_BASE_URL
    if effective_server:
        config.SERVER_BASE_URL = effective_server

    agent_id = ""
    device_token = ""
    if cfg.agent_id and effective_server:
        loaded = _load_token_for_run(effective_server, cfg.agent_id, allow_plaintext=allow_plaintext)
        if loaded:
            agent_id = cfg.agent_id
            device_token = loaded

    if not (agent_id and device_token):
        legacy = _load_persisted_token()
        if legacy is not None:
            agent_id, device_token = legacy

    if not (agent_id and device_token):
        print("device_token이 없다. --register-with-code 또는 --register 후 다시 실행하라.", file=sys.stderr)
        return 2
    try:
        os.environ["NO_PROXY"] = _network_bypass.extend_no_proxy()
        os.environ["no_proxy"] = _network_bypass.extend_no_proxy()
        websocket_client.connect(agent_id, device_token)
    except websocket_client.WebSocketDisabled as e:
        print(str(e), file=sys.stderr)
        return 2
    except websocket_client.WebSocketDependencyMissing as e:
        print(str(e), file=sys.stderr)
        return 3
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="local_agent", description="haehan-ai 로컬 에이전트 (Stage 1/2)")
    p.add_argument("--register", action="store_true", help="서버에 신규 에이전트 등록 (legacy Basic Auth)")
    p.add_argument(
        "--register-with-code",
        dest="register_with_code",
        default="",
        help="registration_code로 서버 등록 (Basic Auth 미사용)",
    )
    p.add_argument(
        "--server",
        default=os.getenv("HAEHAN_AGENT_SERVER", ""),
        help="서버 base URL. 미지정 시 config.json 또는 환경변수 사용",
    )
    p.add_argument("--status", action="store_true", help="현재 config/keyring 상태 표시 (token 원문 미표시)")
    p.add_argument("--ping", action="store_true", help="local ping 액션 실행 후 종료 (서버 호출 없음)")
    p.add_argument("--run", action="store_true", help="WebSocket 세션 기동 (HAEHAN_AGENT_WS_ENABLED=true 필요)")
    p.add_argument("--once", action="store_true", help="WebSocket 1회 처리 후 종료 (--run의 단발 변형)")
    p.add_argument(
        "--auto-connect",
        action="store_true",
        help="미등록이면 등록코드 자동 발급+등록 후 WebSocket 기동 (HAEHAN_AGENT_WS_ENABLED=true 필요, Electron 자동 기동 전용)",
    )
    p.add_argument(
        "--allow-plaintext-token-store",
        dest="allow_plaintext",
        action="store_true",
        help="keyring 사용 불가 시 평문 fallback 허용 (운영 비권장)",
    )
    p.add_argument(
        "--user", default=os.getenv("HAEHAN_AGENT_USER", ""), help="서버 Basic auth 사용자 (--register 전용)"
    )
    p.add_argument(
        "--password", default=os.getenv("HAEHAN_AGENT_PASSWORD", ""), help="서버 Basic auth 비밀번호 (--register 전용)"
    )
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    args = _parse_args()
    auth = (args.user, args.password) if args.user else None

    server_arg = (args.server or "").strip()

    if args.status:
        return cmd_status(server_url=server_arg or None, allow_plaintext=args.allow_plaintext)

    if args.register_with_code:
        return cmd_register_with_code(
            server_url=server_arg,
            registration_code=args.register_with_code,
            allow_plaintext=args.allow_plaintext,
        )

    if args.ping:
        result = execute_local("ping", {})
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.register:
        try:
            resp = register(auth)
        except _urlerr.URLError as e:
            print(f"register 실패: {e}", file=sys.stderr)
            return 1
        # device_token 은 한 번만 표시. 이후 호출자는 TOKEN_STORE_PATH 에서 읽는다.
        print(json.dumps({k: v for k, v in resp.items() if k != "device_token"}, ensure_ascii=False, indent=2))
        print(f"\n[device_token 1회 노출] {resp.get('device_token')}")
        print(f"[저장 위치] {config.TOKEN_STORE_PATH}")
        return 0

    if args.run or args.once:
        # --once는 첫 세션 종료 시 자연 종료. run_forever 자체는 루프이지만,
        # ws_client는 정상 종료 시 함수가 반환되므로 --once는 해당 동작에 의존.
        if args.once:
            os.environ.setdefault("HAEHAN_AGENT_WS_ONCE", "true")
        return run_websocket(server_url=server_arg or None, allow_plaintext=args.allow_plaintext)

    if args.auto_connect:
        return cmd_auto_connect(server_url=server_arg, allow_plaintext=args.allow_plaintext)

    print(
        "사용법: python -m core.agent_runtime.agent --register-with-code <CODE> --server <URL> | "
        "--status | --run | --once | --auto-connect",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
