"""로컬 에이전트 WS 핸드셰이크(auth_ok) 자동 스모크 — 오늘 손으로 한 격리 검증
(APP_VERIFY_server.md, W2)을 독립 스크립트로 옮긴 것.

빈 포트 자동 선택 + 임시 config/agent_id + AUTH_ENABLED=false 서버를 기동하고
`--auto-connect`(HAEHAN_AGENT_WS_ONCE=true)로 1회 핸드셰이크한다. auth_ok 로그와
exit 0 을 PASS 기준으로 삼는다(8ba71a67 로 WS_ONCE 를 실제 구현하기 전에는
--once 가 무한 대기했다 — 이 스모크가 그 재발을 자동으로 잡는다).

서버 프로세스 종료·테스트 keyring 엔트리 삭제를 finally 로 보장해, 운영
data/*.json·~/.haehan_agent/config.json·실제 keyring 엔트리는 절대 건드리지 않는다.

이 파일은 app_smoke_all.py(W1 소유)에 배선되지 않은 단독 스크립트다 — run() 함수로
결과를 노출만 하고, 호출/배선은 W1 이 app_smoke_all.py 쪽에서 한다.

사용: python tools/verify/smoke_ws_handshake.py [--json]
종료코드: 0 = PASS, 1 = FAIL.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))
PY = sys.executable

TIMEOUT_SEC = 60


def _free_port() -> int:
    """OS 에 빈 포트를 하나 받아온다(bind(0) 후 바로 닫음 — TOCTOU 창은 짧고
    로컬 스모크 용도라 재시도 없이 그대로 쓴다)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _delete_test_keyring_entry(server_url: str, agent_id: str) -> None:
    try:
        import keyring

        keyring.delete_password("haehan-agent", f"{server_url}::{agent_id}")
    except Exception:  # noqa: BLE001 - 정리 단계, 엔트리 없음/백엔드 없음 등은 무시
        pass


def run() -> dict[str, str]:
    """{"name": "ws_handshake", "status": "PASS"|"FAIL", "detail": "..."}."""
    name = "ws_handshake"
    deadline = time.monotonic() + TIMEOUT_SEC
    port = _free_port()
    server_proc: subprocess.Popen | None = None
    agent_id = ""
    server_url = f"http://127.0.0.1:{port}"
    # mkdtemp(수동) 사용 이유: TemporaryDirectory 컨텍스트매니저를 쓰면 return 시
    # with-블록이 outer finally(서버 종료)보다 먼저 정리돼, 서버가 아직 그 폴더의
    # 파일(storage db·log)을 쥔 상태로 삭제를 시도해 Windows 에서 PermissionError
    # 가 난다 — 서버를 먼저 끝낸 뒤(finally) 수동으로 지운다.
    tmp_dirs = [tempfile.mkdtemp(prefix=p) for p in ("smoke_ws_data_", "smoke_ws_storage_", "smoke_ws_cfg_")]
    data_dir, storage_dir, cfg_dir = tmp_dirs

    try:
        env = {
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "HAEHAN_DATA_DIR": data_dir,
            "HAEHAN_STORAGE_DIR": storage_dir,
            "APP_PORT": str(port),
            "AUTH_ENABLED": "false",
        }
        server_proc = subprocess.Popen(
            [PY, "-m", "uvicorn", "ai_orchestrator.asgi:app", "--port", str(port)],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        healthy = False
        while time.monotonic() < deadline:
            time.sleep(0.5)
            if server_proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(f"{server_url}/api/v1/health", timeout=1) as resp:
                    if resp.status == 200 and json.loads(resp.read()).get("status") == "ok":
                        healthy = True
                        break
            except urllib.error.URLError, ConnectionError, OSError:
                continue
        if not healthy:
            return {"name": name, "status": "FAIL", "detail": "격리 서버 health 200 못 받음(타임아웃)"}

        remaining = max(1, int(deadline - time.monotonic()))
        agent_env = {
            **os.environ,
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "HAEHAN_AGENT_DESKTOP_CONFIG": str(Path(cfg_dir) / "agent_config.json"),
            "HAEHAN_AGENT_WS_ENABLED": "true",
            "HAEHAN_AGENT_WS_ONCE": "true",
        }
        agent_proc = subprocess.run(
            [PY, "-m", "core.agent_runtime.agent", "--auto-connect", "--server", server_url],
            cwd=str(ROOT),
            env=agent_env,
            capture_output=True,
            text=True,
            timeout=remaining,
            check=False,
        )
        out = agent_proc.stdout + agent_proc.stderr
        stdout_stripped = agent_proc.stdout.strip()
        if stdout_stripped.startswith("{"):
            try:
                agent_id = json.loads(stdout_stripped).get("agent_id", "")
            except ValueError:
                pass

        if agent_proc.returncode == 0 and "auth_ok" in out:
            return {
                "name": name,
                "status": "PASS",
                "detail": f"port={port} auth_ok, exit=0, agent_id={agent_id or '?'}",
            }
        return {
            "name": name,
            "status": "FAIL",
            "detail": f"exit={agent_proc.returncode} tail={out[-300:]!r}",
        }
    except subprocess.TimeoutExpired:
        return {"name": name, "status": "FAIL", "detail": f"{TIMEOUT_SEC}s 타임아웃"}
    except Exception as exc:  # noqa: BLE001 - 스모크 자체가 죽지 않고 FAIL 로 보고
        return {"name": name, "status": "FAIL", "detail": f"예외: {exc!r}"}
    finally:
        if server_proc is not None and server_proc.poll() is None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server_proc.kill()
        if agent_id:
            _delete_test_keyring_entry(server_url, agent_id)
        for d in tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    as_json = "--json" in (argv if argv is not None else sys.argv[1:])
    result = run()
    if as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"[{result['status']}] {result['name']}: {result['detail']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
