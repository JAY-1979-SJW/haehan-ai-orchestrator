"""
G2B Host Proof Schema 테스트

G2B_ACTUAL_LIVE_EXECUTION_HOST_PROOF_AUDIT_1 요구사항:
- hostname/platform/cwd/process_id/python_executable 등 host 증거 필드가 결과에 포함되는지 확인
- local_agent_used=True가 고정값이 아니라 실제 playwright 가용 여부에 따라 결정됨을 검증
- server environment 탐지 및 차단 로직 확인
- browser.close() 후 browser_close_reason 기록 확인
- 서버 환경 탐지(IS_SERVER_ENV) 로직 확인
"""

from __future__ import annotations

import os
import platform
from pathlib import Path
from unittest.mock import patch

_repo_root = Path(__file__).resolve().parent.parent.parent


# ── 1. _collect_host_proof 필드 확인 ─────────────────────────────────────────


def test_01_collect_host_proof_returns_required_fields():
    """_collect_host_proof가 필수 host 증거 필드를 반환한다."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        _collect_host_proof,
    )

    proof = _collect_host_proof()
    required = [
        "hostname",
        "platform",
        "platform_version",
        "python_executable",
        "cwd",
        "process_id",
        "is_server_environment",
        "is_ssh_session",
        "is_local_agent_environment",
        "execution_host_type",
        "run_collected_at",
    ]
    for field in required:
        assert field in proof, f"host proof 필드 누락: {field}"


def test_02_collect_host_proof_hostname_is_string():
    """hostname이 비어있지 않은 문자열이다."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        _collect_host_proof,
    )

    proof = _collect_host_proof()
    assert isinstance(proof["hostname"], str)
    assert len(proof["hostname"]) > 0


def test_03_collect_host_proof_local_agent_env_true():
    """IS_SERVER_ENV 없으면 is_local_agent_environment=True."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        _collect_host_proof,
    )

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("IS_SERVER_ENV", None)
        proof = _collect_host_proof()
    assert proof["is_local_agent_environment"] is True
    assert proof["is_server_environment"] is False
    assert proof["execution_host_type"] == "local_agent"


def test_04_collect_host_proof_server_env_detected():
    """IS_SERVER_ENV=true 이면 is_server_environment=True, is_local_agent_environment=False."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        _collect_host_proof,
    )

    with patch.dict(os.environ, {"IS_SERVER_ENV": "true"}):
        proof = _collect_host_proof()
    assert proof["is_server_environment"] is True
    assert proof["is_local_agent_environment"] is False
    assert proof["execution_host_type"] == "server"


def test_05_collect_host_proof_no_sensitive_fields():
    """host proof에 credential/token/password/otp 등 금지 필드가 없다."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        _collect_host_proof,
    )

    proof = _collect_host_proof()
    forbidden = ["cookie", "session", "token", "password", "otp", "credential", "auth_token", "access_token"]
    for f in forbidden:
        assert f not in proof, f"금지 필드 포함됨: {f}"


def test_06_collect_host_proof_process_id_is_int():
    """process_id가 정수형이다."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        _collect_host_proof,
    )

    proof = _collect_host_proof()
    assert isinstance(proof["process_id"], int)
    assert proof["process_id"] > 0


def test_07_collect_host_proof_python_executable_is_python():
    """python_executable이 python을 가리킨다."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        _collect_host_proof,
    )

    proof = _collect_host_proof()
    exe = proof["python_executable"].lower()
    assert "python" in exe or "py" in exe


# ── 2. local_agent_used 고정값 방지 ──────────────────────────────────────────


def test_08_local_agent_used_not_hardcoded_in_source():
    """runner.py에서 local_agent_used=True는 조건부로 설정된다(고정값 아님)."""
    runner_path = _repo_root / "ai_orchestrator" / "connectors" / "g2b" / "g2b_public_notice_local_live_runner.py"
    source = runner_path.read_text(encoding="utf-8")
    # local_agent_used=True가 단독 할당이 아니라 조건문 뒤에 있어야 함
    # "local_agent_used": True 고정 초기값은 존재하되
    # 이후 pw_available 체크 후 덮어씀
    assert '"local_agent_used": False' in source, (
        "result 초기값에 local_agent_used=False 가 없음 (초기값은 False여야 함)"
    )
    assert 'result["local_agent_used"] = True' in source, (
        "playwright 가용 확인 후 local_agent_used=True 설정 코드가 없음"
    )


def test_09_local_agent_used_false_when_playwright_unavailable():
    """playwright import 실패 시 local_agent_used=False, LIVE_WARN/FAIL 반환."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (
        build_g2b_readonly_execution_candidate,
    )
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        run_g2b_public_notice_readonly_live,
    )

    candidate = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")
    assert candidate["execution_allowed"] is True

    # playwright를 사용 불가로 모킹
    with patch(
        "ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read",
        return_value={
            "local_agent_available": False,
            "error": "mocked_unavailable",
            "title": "",
            "body_text_sample": "",
            "body_text_length": 0,
            "final_url": "",
        },
    ):
        result = run_g2b_public_notice_readonly_live(candidate)

    assert result["local_agent_used"] is False
    assert result["verdict"] in ("LIVE_WARN", "LIVE_FAIL")


def test_10_local_agent_used_true_when_playwright_available():
    """playwright 실행 성공 시 local_agent_used=True, mock_used=False."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (
        build_g2b_readonly_execution_candidate,
    )
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        run_g2b_public_notice_readonly_live,
    )

    candidate = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")

    with patch(
        "ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read",
        return_value={
            "local_agent_available": True,
            "error": "",
            "title": "테스트 타이틀",
            "body_text_sample": "테스트 본문",
            "body_text_length": 8,
            "final_url": "https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do",
            "browser_headless": False,
            "browser_close_reason": "read_complete_normal_close",
        },
    ):
        result = run_g2b_public_notice_readonly_live(candidate)

    assert result["local_agent_used"] is True
    assert result["mock_used"] is False
    assert result["verdict"] == "LIVE_PASS"


# ── 3. server environment 차단 ────────────────────────────────────────────────


def test_11_server_env_blocks_execution():
    """IS_SERVER_ENV=true 이면 LIVE_FAIL 반환, execution_dispatched=False."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (
        build_g2b_readonly_execution_candidate,
    )
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        run_g2b_public_notice_readonly_live,
    )

    candidate = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")

    with patch.dict(os.environ, {"IS_SERVER_ENV": "true"}):
        result = run_g2b_public_notice_readonly_live(candidate)

    assert result["verdict"] == "LIVE_FAIL"
    assert result["blocked_reason"] == "SERVER_ENV_DETECTED"
    assert result["execution_dispatched"] is False


def test_12_server_env_false_by_default():
    """IS_SERVER_ENV 없으면 서버 차단이 발동하지 않는다."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        _is_server_env,
    )

    env_backup = os.environ.pop("IS_SERVER_ENV", None)
    try:
        assert _is_server_env() is False
    finally:
        if env_backup is not None:
            os.environ["IS_SERVER_ENV"] = env_backup


def test_13_server_env_case_insensitive():
    """IS_SERVER_ENV는 '1', 'true', 'yes' 대소문자 무관하게 서버 감지."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        _is_server_env,
    )

    for val in ("1", "true", "True", "TRUE", "yes", "YES"):
        with patch.dict(os.environ, {"IS_SERVER_ENV": val}):
            assert _is_server_env() is True, f"IS_SERVER_ENV={val!r}에서 서버 감지 실패"


# ── 4. browser_close_reason 기록 ──────────────────────────────────────────────


def test_14_browser_close_reason_normal_close():
    """정상 read 완료 후 browser_close_reason='read_complete_normal_close'."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (
        build_g2b_readonly_execution_candidate,
    )
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        run_g2b_public_notice_readonly_live,
    )

    candidate = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")

    with patch(
        "ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read",
        return_value={
            "local_agent_available": True,
            "error": "",
            "title": "정상 타이틀",
            "body_text_sample": "본문",
            "body_text_length": 2,
            "final_url": "https://www.g2b.go.kr/",
            "browser_headless": False,
            "browser_close_reason": "read_complete_normal_close",
        },
    ):
        result = run_g2b_public_notice_readonly_live(candidate)

    assert result["browser_close_reason"] == "read_complete_normal_close"
    assert result["browser_headless"] is False


def test_15_browser_headless_false():
    """browser_headless는 False (headful 모드)."""
    runner_path = _repo_root / "ai_orchestrator" / "connectors" / "g2b" / "g2b_public_notice_local_live_runner.py"
    source = runner_path.read_text(encoding="utf-8")
    # _try_playwright_open_read에서 headless=False 사용
    assert "headless=False" in source, "headless=False 설정이 소스에 없음"
    # _try_playwright_open_read 함수 내부에 headless=True가 없어야 함 (check 함수 제외)
    # _check_playwright_available은 headless=True 사용 허용 (preflight only)
    lines = source.split("\n")
    in_try_open_read = False
    for line in lines:
        if "def _try_playwright_open_read" in line:
            in_try_open_read = True
        elif line.startswith("def ") and in_try_open_read:
            break
        if in_try_open_read and "headless=True" in line:
            assert False, f"_try_playwright_open_read에 headless=True 발견: {line}"


# ── 5. result schema에 host proof 포함 여부 ───────────────────────────────────


def test_16_live_result_contains_host_proof_fields():
    """run_g2b_public_notice_readonly_live 결과에 host proof 필드가 포함된다."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (
        build_g2b_readonly_execution_candidate,
    )
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        run_g2b_public_notice_readonly_live,
    )

    candidate = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")

    with patch(
        "ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read",
        return_value={
            "local_agent_available": True,
            "error": "",
            "title": "t",
            "body_text_sample": "b",
            "body_text_length": 1,
            "final_url": "https://www.g2b.go.kr/",
            "browser_headless": False,
            "browser_close_reason": "read_complete_normal_close",
        },
    ):
        result = run_g2b_public_notice_readonly_live(candidate)

    host_fields = [
        "hostname",
        "platform",
        "cwd",
        "process_id",
        "python_executable",
        "is_server_environment",
        "is_local_agent_environment",
        "execution_host_type",
    ]
    for f in host_fields:
        assert f in result, f"live result에 host proof 필드 누락: {f}"


def test_17_suite_result_contains_host_proof_fields():
    """run_g2b_public_notice_fixture_live_suite 결과에 host proof 필드가 포함된다."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        run_g2b_public_notice_fixture_live_suite,
    )

    fixture_path = str(_repo_root / "tests" / "fixtures" / "g2b_public_notice_workflow_fixture_20260507.json")

    with patch(
        "ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read",
        return_value={
            "local_agent_available": True,
            "error": "",
            "title": "t",
            "body_text_sample": "b",
            "body_text_length": 1,
            "final_url": "https://www.g2b.go.kr/",
            "browser_headless": False,
            "browser_close_reason": "read_complete_normal_close",
        },
    ):
        suite = run_g2b_public_notice_fixture_live_suite(fixture_path)

    host_fields = [
        "hostname",
        "platform",
        "cwd",
        "process_id",
        "python_executable",
        "is_server_environment",
        "is_local_agent_environment",
        "execution_host_type",
    ]
    for f in host_fields:
        assert f in suite, f"suite result에 host proof 필드 누락: {f}"


def test_18_suite_hostname_is_not_server():
    """suite 결과의 hostname이 현재 PC hostname과 일치하고 서버가 아니다."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        run_g2b_public_notice_fixture_live_suite,
    )

    fixture_path = str(_repo_root / "tests" / "fixtures" / "g2b_public_notice_workflow_fixture_20260507.json")

    with patch(
        "ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read",
        return_value={
            "local_agent_available": True,
            "error": "",
            "title": "t",
            "body_text_sample": "b",
            "body_text_length": 1,
            "final_url": "https://www.g2b.go.kr/",
            "browser_headless": False,
            "browser_close_reason": "read_complete_normal_close",
        },
    ):
        suite_result = run_g2b_public_notice_fixture_live_suite(fixture_path)

    assert suite_result["hostname"] == platform.node()
    assert suite_result["is_local_agent_environment"] is True
    assert suite_result["is_server_environment"] is False


def test_19_live_result_execution_host_type_local_agent():
    """서버 환경 아닐 때 execution_host_type='local_agent'."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (
        build_g2b_readonly_execution_candidate,
    )
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        run_g2b_public_notice_readonly_live,
    )

    candidate = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")
    os.environ.pop("IS_SERVER_ENV", None)

    with patch(
        "ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read",
        return_value={
            "local_agent_available": True,
            "error": "",
            "title": "t",
            "body_text_sample": "b",
            "body_text_length": 1,
            "final_url": "https://www.g2b.go.kr/",
            "browser_headless": False,
            "browser_close_reason": "read_complete_normal_close",
        },
    ):
        result = run_g2b_public_notice_readonly_live(candidate)

    assert result["execution_host_type"] == "local_agent"


def test_20_server_browser_used_always_false_in_host_proof_mode():
    """host proof 포함 후에도 server_browser_used는 항상 False."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (
        build_g2b_readonly_execution_candidate,
    )
    from ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner import (
        run_g2b_public_notice_readonly_live,
    )

    candidate = build_g2b_readonly_execution_candidate("https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do", "read")

    with patch(
        "ai_orchestrator.connectors.g2b.g2b_public_notice_local_live_runner._try_playwright_open_read",
        return_value={
            "local_agent_available": True,
            "error": "",
            "title": "t",
            "body_text_sample": "b",
            "body_text_length": 1,
            "final_url": "https://www.g2b.go.kr/",
            "browser_headless": False,
            "browser_close_reason": "read_complete_normal_close",
        },
    ):
        result = run_g2b_public_notice_readonly_live(candidate)

    assert result["server_browser_used"] is False
    assert result["download_auto_allowed"] is False
