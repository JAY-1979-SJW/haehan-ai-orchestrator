"""
CAD MCP 컨테이너 분리 검증 테스트

실행 전 필요 조건:
  - docker compose ps 로 cad-backend, cad-mcp 기동 확인
  - orchestrator API 인증 정보 환경변수 설정

환경변수:
  CAD_BACKEND_HOST  : cad-backend 직접 접근 주소 (기본 http://127.0.0.1:8092)
  ORCHESTRATOR_HOST : orchestrator 주소 (기본 http://127.0.0.1:8400)
  ORCHESTRATOR_USER : HTTP Basic 사용자 (기본 admin)
  ORCHESTRATOR_PASS : HTTP Basic 비밀번호 (기본 "")

주의: 실제 서버 연결이 필요한 테스트는 pytest -m "not integration" 으로 스킵 가능
"""

import os
import socket
import subprocess
import pytest

CAD_BACKEND = os.environ.get("CAD_BACKEND_HOST", "http://127.0.0.1:8092")
ORCHESTRATOR = os.environ.get("ORCHESTRATOR_HOST", "http://127.0.0.1:8400")
ORCH_USER = os.environ.get("ORCHESTRATOR_USER", "admin")
ORCH_PASS = os.environ.get("ORCHESTRATOR_PASS", "")

MCP_INTERNAL_PORT = int(os.environ.get("MCP_INTERNAL_PORT", "8001"))


# ─── 단위 검증 ────────────────────────────────────────────────────────────────

def test_cad_mcp_no_external_port():
    """cad-mcp가 호스트에 직접 포트를 노출하지 않음을 확인한다."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        result = s.connect_ex(("127.0.0.1", MCP_INTERNAL_PORT))
    assert result != 0, (
        f"포트 {MCP_INTERNAL_PORT}가 호스트에 열려 있습니다. "
        "cad-mcp는 expose만 사용해야 하며 host port 바인딩은 금지입니다."
    )


def test_nginx_no_cad_mcp_block():
    """nginx 설정에 cad-mcp 직접 노출 블록이 없음을 확인한다."""
    sites_dir = "/etc/nginx/sites-enabled"
    if not os.path.isdir(sites_dir):
        pytest.skip("nginx sites-enabled 디렉터리 없음 (로컬 환경)")

    found = []
    for fname in os.listdir(sites_dir):
        fpath = os.path.join(sites_dir, fname)
        try:
            content = open(fpath).read()
        except (PermissionError, OSError):
            continue
        if "cad-mcp" in content or ":8001" in content:
            found.append(fname)

    assert not found, f"nginx에 cad-mcp 직접 노출 블록 발견: {found}"


# ─── 통합 검증 (서버 연결 필요) ───────────────────────────────────────────────

@pytest.mark.integration
def test_cad_backend_health():
    """cad-backend /health 가 200 응답을 반환한다."""
    import urllib.request
    try:
        resp = urllib.request.urlopen(f"{CAD_BACKEND}/health", timeout=5)
        assert resp.status == 200, f"cad-backend health 실패: {resp.status}"
    except Exception as e:
        pytest.fail(f"cad-backend 연결 실패: {e}")


@pytest.mark.integration
def test_orchestrator_cad_proxy_read():
    """orchestrator → /api/v1/cad/projects 읽기 요청이 성공한다."""
    import urllib.request
    import base64
    creds = base64.b64encode(f"{ORCH_USER}:{ORCH_PASS}".encode()).decode()
    req = urllib.request.Request(
        f"{ORCHESTRATOR}/api/v1/cad/projects",
        headers={"Authorization": f"Basic {creds}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        assert resp.status == 200, f"CAD proxy read 실패: {resp.status}"
    except urllib.error.HTTPError as e:
        assert e.code in (200, 404), f"예상치 못한 HTTP 오류: {e.code}"
    except Exception as e:
        pytest.fail(f"orchestrator CAD proxy 연결 실패: {e}")


@pytest.mark.integration
def test_orchestrator_cad_write_denied_without_approval():
    """orchestrator → CAD 쓰기 요청이 approval 없으면 403으로 거부된다."""
    import json
    import urllib.request
    import urllib.error
    import base64
    creds = base64.b64encode(f"{ORCH_USER}:{ORCH_PASS}".encode()).decode()
    data = json.dumps({"name": "test-write", "description": "approval 없는 쓰기 테스트"}).encode()
    req = urllib.request.Request(
        f"{ORCHESTRATOR}/api/v1/cad/projects",
        data=data,
        headers={
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        pytest.fail("approval 없이 쓰기가 성공했습니다 — 정책 위반")
    except urllib.error.HTTPError as e:
        assert e.code == 403, f"403 이외의 응답: {e.code}"


@pytest.mark.integration
def test_cad_mcp_container_internal_port():
    """cad-mcp 컨테이너 내부에서 8001 포트가 열려있는지 docker exec으로 확인한다."""
    result = subprocess.run(
        [
            "docker", "exec", "cad-mcp",
            "python3", "-c",
            "import socket; s=socket.socket(); s.settimeout(3); "
            "s.connect(('127.0.0.1', 8001)); s.close(); print('OK')",
        ],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, (
        f"cad-mcp 내부 포트 확인 실패:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK" in result.stdout


@pytest.mark.integration
def test_cad_mcp_backend_reachable_from_mcp():
    """cad-mcp 컨테이너에서 cad-backend:8000 에 도달 가능하다."""
    result = subprocess.run(
        [
            "docker", "exec", "cad-mcp",
            "python3", "-c",
            "import socket; s=socket.socket(); s.settimeout(5); "
            "s.connect(('cad-backend', 8000)); s.close(); print('OK')",
        ],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, (
        f"cad-mcp → cad-backend 연결 실패:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
