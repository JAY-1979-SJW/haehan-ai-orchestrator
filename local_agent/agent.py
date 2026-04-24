"""로컬 에이전트 메인 엔트리 (Stage 1 — 폴링 데모).

사용자가 직접 실행:
  > python -m local_agent.agent

서버에 register → device_token 발급 → POLL_INTERVAL_SEC 마다
자기에게 할당된 작업이 있는지 확인 (1단계는 단일 작업 ID 폴링 데모).

본 모듈은 백그라운드 서비스로 등록되지 않으며, 사용자가 Ctrl+C 로
즉시 종료할 수 있다. 자동 시작 / 은폐 실행 / 백도어 기능 없음.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import sys
import time
from pathlib import Path
from typing import Optional
from urllib import request as _urlreq
from urllib import error as _urlerr

from . import __version__, config
from .actions import execute_action
from .audit import log_local_event

logger = logging.getLogger(__name__)


def _http_post(url: str, body: dict, basic_auth: Optional[tuple[str, str]] = None) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = _urlreq.Request(url, data=data, method="POST",
                          headers={"Content-Type": "application/json"})
    if basic_auth:
        import base64
        u, p = basic_auth
        creds = base64.b64encode(f"{u}:{p}".encode()).decode()
        req.add_header("Authorization", f"Basic {creds}")
    with _urlreq.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get(url: str, basic_auth: Optional[tuple[str, str]] = None) -> dict:
    req = _urlreq.Request(url, method="GET")
    if basic_auth:
        import base64
        u, p = basic_auth
        creds = base64.b64encode(f"{u}:{p}".encode()).decode()
        req.add_header("Authorization", f"Basic {creds}")
    with _urlreq.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def register(basic_auth: Optional[tuple[str, str]]) -> dict:
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
        path.write_text(json.dumps({"agent_id": agent_id, "device_token": device_token}),
                        encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # Windows 등에서는 별도 ACL 필요
    except OSError as e:
        logger.error("device_token 저장 실패: %s", e)


def poll_task(agent_id: str, task_id: str,
              basic_auth: Optional[tuple[str, str]]) -> dict:
    url = (f"{config.SERVER_BASE_URL.rstrip('/')}"
           f"/api/v1/local-agents/{agent_id}/tasks/{task_id}")
    return _http_get(url, basic_auth=basic_auth)


def execute_local(action: str, params: dict) -> dict:
    """로컬에서 액션 실행 + 결과 dict 반환."""
    result = execute_action(action, params)
    log_local_event(
        "action_executed", action=action, success=result.success,
        error_code=result.error_code,
    )
    return {
        "success": result.success,
        "summary": result.summary,
        "data": result.data,
        "error": result.error,
        "error_code": result.error_code,
    }


def _load_persisted_token() -> Optional[tuple[str, str]]:
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


def run_websocket() -> int:
    """Stage 2 — WebSocket 세션 실행 (사용자 명시적 기동)."""
    from . import websocket_client

    if not config.WEBSOCKET_ENABLED:
        print("WebSocket 비활성 상태. 환경변수 HAEHAN_AGENT_WS_ENABLED=true 후 실행",
              file=sys.stderr)
        return 2
    token_pair = _load_persisted_token()
    if token_pair is None:
        print("device_token 파일이 없다. 먼저 --register 를 실행하라.",
              file=sys.stderr)
        return 2
    agent_id, device_token = token_pair
    try:
        websocket_client.connect(agent_id, device_token)
    except websocket_client.WebSocketDisabled as e:
        print(str(e), file=sys.stderr)
        return 2
    except websocket_client.WebSocketDependencyMissing as e:
        print(str(e), file=sys.stderr)
        return 3
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="local_agent",
                                description="haehan-ai 로컬 에이전트 (Stage 1/2)")
    p.add_argument("--register", action="store_true",
                   help="서버에 신규 에이전트 등록")
    p.add_argument("--ping", action="store_true",
                   help="local ping 액션 실행 후 종료 (서버 호출 없음)")
    p.add_argument("--run", action="store_true",
                   help="Stage 2 — WebSocket 세션 기동 (HAEHAN_AGENT_WS_ENABLED=true 필요)")
    p.add_argument("--user", default=os.getenv("HAEHAN_AGENT_USER", ""),
                   help="서버 Basic auth 사용자")
    p.add_argument("--password", default=os.getenv("HAEHAN_AGENT_PASSWORD", ""),
                   help="서버 Basic auth 비밀번호")
    return p.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    args = _parse_args()
    auth = (args.user, args.password) if args.user else None

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
        print(json.dumps({k: v for k, v in resp.items()
                          if k != "device_token"}, ensure_ascii=False, indent=2))
        print(f"\n[device_token 1회 노출] {resp.get('device_token')}")
        print(f"[저장 위치] {config.TOKEN_STORE_PATH}")
        return 0

    if args.run:
        return run_websocket()

    print("사용법: python -m local_agent.agent --register | --ping | --run",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
