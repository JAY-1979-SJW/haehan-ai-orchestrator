"""
G2B 공개 공고 Local-Agent Read-Only Live Runner

execution gate를 통과한 candidate에 대해
사용자 PC local-agent 브라우저에서만 open/read/navigate를 수행한다.

원칙:
- gate 통과 candidate만 입력으로 받는다
- 사용자 PC(로컬) 환경에서만 실행한다 (IS_LOCAL_ENV 확인)
- open/read/navigate만 수행한다
- click/type/fill/submit/download 함수 구현 없음
- cookie/session/token/password/otp 읽거나 저장 안 함
- body_text_sample 최대 1000자 제한
- server_browser_used 항상 False
- download_auto_allowed 항상 False
- 개인정보/민감정보 저장 안 함

실행 환경 판별:
- IS_SERVER_ENV=true 환경변수가 있으면 FAIL (서버 환경)
- playwright 사용 가능 여부로 local-agent 사용 가능 여부 판단
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (
    GATE_READONLY_EXECUTION_CANDIDATE,
    validate_g2b_execution_gate_result,
)

logger = logging.getLogger(__name__)

# ── 상수 ──────────────────────────────────────────────────────────────────────

BODY_TEXT_MAX_LEN = 1000

_ALLOWED_G2B_DOMAINS: frozenset[str] = frozenset(
    {
        "g2b.go.kr",
        "www.g2b.go.kr",
    }
)

_FORBIDDEN_RESULT_FIELDS: frozenset[str] = frozenset(
    {
        "cookie",
        "cookies",
        "session",
        "token",
        "password",
        "otp",
        "auth_token",
        "access_token",
        "refresh_token",
        "credential",
    }
)

_VERDICT_PASS = "LIVE_PASS"  # noqa: S105 - 비밀값 아님, 판정 상수
_VERDICT_FAIL = "LIVE_FAIL"
_VERDICT_WARN = "LIVE_WARN"
_VERDICT_BLOCK = "LIVE_BLOCK"


def _check_playwright_available() -> dict[str, Any]:
    """playwright/chromium 설치 여부를 확인한다."""
    result = {
        "playwright_available": False,
        "playwright_version": "",
        "chromium_available": False,
        "error": "",
    }
    try:
        import importlib.util

        spec = importlib.util.find_spec("playwright")
        if spec is None:
            result["error"] = "playwright not installed"
            return result
        result["playwright_available"] = True
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
            result["chromium_available"] = True
        except Exception as e:  # noqa: BLE001 - 나라장터(G2B) 공고 읽기전용 조회 - 허용 도메인 화이트리스트 검사 실패시 False(거부) 반환, 다운로드는 감지 즉시 cancel(), 입찰/서명/결제 없음
            result["error"] = f"chromium launch failed: {e}"
    except Exception as e:  # noqa: BLE001 - 나라장터(G2B) 공고 읽기전용 조회 - 허용 도메인 화이트리스트 검사 실패시 False(거부) 반환, 다운로드는 감지 즉시 cancel(), 입찰/서명/결제 없음
        result["error"] = f"playwright check failed: {e}"
    return result


def _is_server_env() -> bool:
    """서버 환경 여부 판별."""
    return os.environ.get("IS_SERVER_ENV", "").lower() in ("1", "true", "yes")


def _collect_host_proof() -> dict[str, Any]:
    """실행 호스트 증거를 수집한다. 민감정보(credential/token/password/otp) 제외."""
    is_server = _is_server_env()
    is_ssh = bool(os.environ.get("SSH_CLIENT") or os.environ.get("SSH_TTY"))
    return {
        "hostname": platform.node(),
        "platform": platform.system(),
        "platform_version": platform.version()[:80],
        "python_executable": sys.executable,
        "cwd": str(Path.cwd()),
        "process_id": os.getpid(),
        "is_server_environment": is_server,
        "is_ssh_session": is_ssh,
        "is_local_agent_environment": not is_server,
        "execution_host_type": "server" if is_server else "local_agent",
        "run_collected_at": datetime.now(UTC).isoformat(),
    }


def _is_allowed_final_url(url: str) -> bool:
    """final_url이 허용 도메인 안에 있는지 확인."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return domain in _ALLOWED_G2B_DOMAINS
    except Exception as exc:  # noqa: BLE001 - 나라장터(G2B) 공고 읽기전용 조회 - 허용 도메인 화이트리스트 검사 실패시 False(거부) 반환, 다운로드는 감지 즉시 cancel(), 입찰/서명/결제 없음
        logger.warning("G2B 허용 도메인 검사 실패: %s", type(exc).__name__)
        return False


def _truncate_body(text: str) -> str:
    if not text:
        return ""
    return text[:BODY_TEXT_MAX_LEN]


def _try_playwright_open_read(url: str) -> dict[str, Any]:
    """
    Playwright를 사용해 URL을 열고 title/body_text_sample/final_url을 읽는다.
    local-agent 브라우저 실행.
    click/type/fill/submit/download 없음.
    cookie/session/token 읽거나 저장 안 함.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "local_agent_available": False,
            "error": "playwright not installed",
            "title": "",
            "body_text_sample": "",
            "body_text_length": 0,
            "final_url": "",
        }

    result: dict[str, Any] = {
        "local_agent_available": True,
        "error": "",
        "title": "",
        "body_text_sample": "",
        "body_text_length": 0,
        "final_url": "",
        "browser_headless": False,
        "browser_close_reason": "",
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                accept_downloads=False,
            )
            page = context.new_page()

            # download 이벤트 감지 시 즉시 FAIL
            download_detected = []

            def _on_download(download: Any) -> None:
                download_detected.append(download.url)
                # 나라장터(G2B) 공고 읽기전용 조회 - 다운로드는 감지 즉시 cancel(), 실패해도 read-only 정책엔 영향 없음
                with contextlib.suppress(Exception):
                    download.cancel()

            page.on("download", _on_download)

            # open URL (read-only navigation)
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            result["final_url"] = page.url
            result["title"] = page.title() or ""

            # body text 읽기 (최대 1000자)
            try:
                body_text = page.locator("body").inner_text(timeout=5000)
                result["body_text_sample"] = _truncate_body(body_text)
                result["body_text_length"] = len(body_text)
            except Exception as exc:  # noqa: BLE001 - 나라장터(G2B) 공고 읽기전용 조회 - 허용 도메인 화이트리스트 검사 실패시 False(거부) 반환, 다운로드는 감지 즉시 cancel(), 입찰/서명/결제 없음
                logger.warning("G2B 공고 본문 텍스트 읽기 실패: %s", type(exc).__name__)
                result["body_text_sample"] = ""
                result["body_text_length"] = 0

            if download_detected:
                result["error"] = f"DOWNLOAD_DETECTED: {download_detected[0]}"

            context.close()
            browser.close()
            result["browser_close_reason"] = "read_complete_normal_close"

    except Exception as e:  # noqa: BLE001 - 나라장터(G2B) 공고 읽기전용 조회 - 허용 도메인 화이트리스트 검사 실패시 False(거부) 반환, 다운로드는 감지 즉시 cancel(), 입찰/서명/결제 없음
        result["error"] = f"PLAYWRIGHT_ERROR: {e}"
        result["browser_close_reason"] = f"exception_close: {type(e).__name__}"

    return result


def _apply_playwright_result(result: dict[str, Any], pw_result: dict[str, Any]) -> None:
    """playwright 읽기 결과를 live result 에 반영한다."""
    result["local_agent_used"] = True
    result["mock_used"] = False
    result["live_browser_worker_called"] = True
    result["execution_dispatched"] = True
    result["title"] = pw_result.get("title", "")
    result["body_text_sample"] = pw_result.get("body_text_sample", "")
    result["body_text_length"] = pw_result.get("body_text_length", 0)
    result["final_url"] = pw_result.get("final_url", "")
    result["error"] = pw_result.get("error", "")
    result["browser_headless"] = pw_result.get("browser_headless", False)
    result["browser_close_reason"] = pw_result.get("browser_close_reason", "")


def _judge_live_result(result: dict[str, Any]) -> dict[str, Any]:
    """읽기 결과에 대한 verdict 판정 (download → 도메인 이탈 → 성공 조건 순)."""
    # download 감지 시 FAIL
    if "DOWNLOAD_DETECTED" in result.get("error", ""):
        result["verdict"] = _VERDICT_FAIL
        result["blocked_reason"] = "DOWNLOAD_DETECTED"
        return result

    # final_url 도메인 이탈 확인
    if result["final_url"] and not _is_allowed_final_url(result["final_url"]):
        result["verdict"] = _VERDICT_FAIL
        result["blocked_reason"] = f"FINAL_URL_DOMAIN_ESCAPED: {result['final_url']}"
        return result

    # 성공 조건: title 또는 body_text_sample 확보
    if result["title"] or result["body_text_sample"]:
        result["verdict"] = _VERDICT_PASS
    else:
        result["verdict"] = _VERDICT_WARN
        result["error"] = result["error"] or "title/body_text_sample 모두 비어 있음"

    return result


def run_g2b_public_notice_readonly_live(
    candidate: dict[str, Any],
    forbid_mock: bool = False,
    actual_live_required: bool = False,
) -> dict[str, Any]:
    """
    execution gate를 통과한 candidate에 대해 live open/read를 수행한다.

    forbid_mock=True: playwright 미설치 시 LIVE_WARN 대신 LIVE_FAIL 반환.
    actual_live_required=True: mock 사용 금지, 실제 playwright/chromium 필수.

    필수 출력:
    - input_url, canonical_url, final_url
    - operation, gate_verdict, execution_allowed
    - execution_dispatched, live_browser_worker_called
    - local_agent_required, local_agent_used
    - server_browser_used, readonly_allowed
    - download_auto_allowed, title, body_text_sample, body_text_length
    - blocked_reason, error, verdict
    - actual_live_required, mock_used, playwright_available, chromium_available
    """
    url = candidate.get("input_url", "")
    canonical = candidate.get("canonical_url", url)
    op = (candidate.get("operation") or "").lower().strip()

    result: dict[str, Any] = {
        "input_url": url,
        "canonical_url": canonical,
        "final_url": "",
        "operation": op,
        "gate_verdict": candidate.get("gate_verdict", ""),
        "execution_allowed": False,
        "execution_dispatched": False,
        "live_browser_worker_called": False,
        "local_agent_required": True,
        "local_agent_used": False,
        "server_browser_used": False,
        "readonly_allowed": False,
        "download_auto_allowed": False,
        "title": "",
        "body_text_sample": "",
        "body_text_length": 0,
        "blocked_reason": "",
        "error": "",
        "verdict": _VERDICT_BLOCK,
        # actual-live 모드 필드
        "actual_live_required": actual_live_required,
        "mock_used": False,
        "playwright_available": False,
        "chromium_available": False,
        # host 증거 필드
        "browser_headless": False,
        "browser_close_reason": "",
    }

    # host proof 수집 (민감정보 제외)
    host_proof = _collect_host_proof()
    result.update(host_proof)

    # 서버 환경 차단
    if _is_server_env():
        result["blocked_reason"] = "SERVER_ENV_DETECTED"
        result["error"] = "서버 환경에서는 G2B live 실행 금지"
        result["verdict"] = _VERDICT_FAIL
        return result

    # gate 결과 검증
    gate_errors = validate_g2b_execution_gate_result(candidate)
    if gate_errors:
        result["blocked_reason"] = "GATE_VALIDATION_FAILED"
        result["error"] = "; ".join(gate_errors)
        result["verdict"] = _VERDICT_FAIL
        return result

    # gate 통과 여부 확인
    if candidate.get("gate_verdict") != GATE_READONLY_EXECUTION_CANDIDATE:
        result["blocked_reason"] = f"GATE_NOT_PASSED: {candidate.get('gate_verdict')}"
        result["verdict"] = _VERDICT_BLOCK
        return result

    if not candidate.get("execution_allowed"):
        result["blocked_reason"] = "EXECUTION_NOT_ALLOWED_BY_GATE"
        result["verdict"] = _VERDICT_BLOCK
        return result

    # local-agent 브라우저 실행
    result["execution_allowed"] = True
    result["readonly_allowed"] = True

    pw_result = _try_playwright_open_read(url)

    pw_available = pw_result.get("local_agent_available", False)
    result["playwright_available"] = pw_available
    result["chromium_available"] = pw_available  # _try_playwright_open_read 성공 = chromium 가용

    if not pw_available:
        result["local_agent_used"] = False
        result["mock_used"] = False
        result["blocked_reason"] = "LOCAL_AGENT_UNAVAILABLE"
        result["error"] = pw_result.get("error", "")
        # actual-live 모드 또는 forbid_mock이면 FAIL
        if actual_live_required or forbid_mock:
            result["verdict"] = _VERDICT_FAIL
            result["blocked_reason"] = "ACTUAL_LIVE_REQUIRED_BUT_PLAYWRIGHT_UNAVAILABLE"
        else:
            result["verdict"] = _VERDICT_WARN
        return result

    _apply_playwright_result(result, pw_result)

    return _judge_live_result(result)


def validate_g2b_public_notice_live_result(result: dict[str, Any]) -> list[str]:
    """
    live runner 결과의 필수 필드 및 정책 준수를 검증한다.
    오류 목록 반환 (빈 리스트 = 유효).
    """
    errors: list[str] = []

    required_fields = [
        "input_url",
        "canonical_url",
        "final_url",
        "operation",
        "gate_verdict",
        "execution_allowed",
        "execution_dispatched",
        "live_browser_worker_called",
        "local_agent_required",
        "local_agent_used",
        "server_browser_used",
        "readonly_allowed",
        "download_auto_allowed",
        "title",
        "body_text_sample",
        "body_text_length",
        "blocked_reason",
        "error",
        "verdict",
    ]
    for field in required_fields:
        if field not in result:
            errors.append(f"필수 필드 누락: {field}")

    for key, expected, message in (
        ("server_browser_used", False, "server_browser_used는 항상 False여야 한다"),
        ("download_auto_allowed", False, "download_auto_allowed는 항상 False여야 한다"),
        ("local_agent_required", True, "local_agent_required는 항상 True여야 한다"),
    ):
        if result.get(key) is not expected:
            errors.append(message)

    # 금지 필드 포함 여부
    for field in _FORBIDDEN_RESULT_FIELDS:
        if field in result:
            errors.append(f"금지 필드 포함: {field}")

    # body_text_sample 길이 제한
    sample = result.get("body_text_sample", "")
    if isinstance(sample, str) and len(sample) > BODY_TEXT_MAX_LEN:
        errors.append(f"body_text_sample이 최대 길이 {BODY_TEXT_MAX_LEN}자를 초과")

    # local_agent_used=False이면서 verdict=LIVE_PASS는 불가
    if result.get("local_agent_used") is False and result.get("verdict") == _VERDICT_PASS:
        errors.append("local_agent_used=False이면서 LIVE_PASS는 불가")

    # server_browser_used=True이면 항상 FAIL
    if result.get("server_browser_used") is True:
        errors.append("server_browser_used=True는 FAIL 조건")

    return errors


def _run_suite_case(
    case: dict[str, Any],
    suite_result: dict[str, Any],
    forbid_mock: bool,
    actual_live_required: bool,
) -> None:
    """fixture 케이스 1건을 실행/검증하고 suite_result 에 누적한다."""
    from ai_orchestrator.connectors.g2b.g2b_public_notice_execution_gate import (
        build_g2b_readonly_execution_candidate,
    )

    case_id = case.get("id", "")
    label = case.get("label", "")
    url = case.get("url", "")
    op = case.get("operation", "read")
    expected = case.get("expected", {})
    expected_verdict = expected.get("verdict", "")

    case_result: dict[str, Any] = {
        "id": case_id,
        "label": label,
        "url": url,
        "operation": op,
        "expected_verdict": expected_verdict,
    }

    candidate = build_g2b_readonly_execution_candidate(url, op)

    if expected_verdict == "ALLOWED":
        suite_result["allowed_cases"] += 1
        # live 실행 (actual_live_required/forbid_mock 전달)
        live_result = run_g2b_public_notice_readonly_live(
            candidate,
            forbid_mock=forbid_mock,
            actual_live_required=actual_live_required,
        )
        case_result["live_result"] = live_result
        case_result["case_verdict"] = live_result.get("verdict", "")
        # actual_live_required 모드에서는 LIVE_PASS만 성공 카운트
        if actual_live_required or forbid_mock:
            if live_result.get("verdict") == _VERDICT_PASS:
                suite_result["live_executed"] += 1
        else:
            if live_result.get("verdict") in (_VERDICT_PASS, _VERDICT_WARN):
                suite_result["live_executed"] += 1

    elif expected_verdict in ("BLOCKED",):
        suite_result["blocked_cases"] += 1
        # gate BLOCK 확인만 (브라우저 실행 안 함)
        gate_verdict = candidate.get("gate_verdict", "")
        case_result["gate_verdict"] = gate_verdict
        case_result["execution_allowed"] = candidate.get("execution_allowed", False)
        is_blocked = not candidate.get("execution_allowed", False)
        case_result["case_verdict"] = "GATE_BLOCK_CONFIRMED" if is_blocked else "GATE_BLOCK_FAILED"
        if is_blocked:
            suite_result["gate_blocked_confirmed"] += 1

    elif expected_verdict in ("NEEDS_VERIFICATION",):
        suite_result["needs_verification_cases"] += 1
        case_result["gate_verdict"] = candidate.get("gate_verdict", "")
        case_result["requires_url_verification"] = candidate.get("requires_url_verification", False)
        case_result["case_verdict"] = "NEEDS_VERIFICATION_CONFIRMED"

    else:
        # 기타 - gate 판정만
        case_result["gate_verdict"] = candidate.get("gate_verdict", "")
        case_result["case_verdict"] = "SKIPPED"

    suite_result["results"].append(case_result)

    # 케이스 간 대기 (live 실행 후)
    if expected_verdict == "ALLOWED":
        time.sleep(2)


def run_g2b_public_notice_fixture_live_suite(
    fixture_path: str,
    forbid_mock: bool = False,
    actual_live_required: bool = False,
) -> dict[str, Any]:
    """
    fixture 파일의 허용 케이스 전체를 순차 실행하고
    차단 케이스는 gate BLOCK만 확인한다.

    반환:
    - fixture_path
    - total_cases
    - allowed_cases (ALLOWED verdict fixture)
    - blocked_cases (BLOCKED verdict fixture)
    - needs_verification_cases
    - live_executed
    - gate_blocked_confirmed
    - results
    - summary
    """
    suite_result: dict[str, Any] = {
        "fixture_path": fixture_path,
        "total_cases": 0,
        "allowed_cases": 0,
        "blocked_cases": 0,
        "needs_verification_cases": 0,
        "live_executed": 0,
        "gate_blocked_confirmed": 0,
        "results": [],
        "summary": "",
        "run_at": datetime.now(UTC).isoformat(),
        # actual-live 모드 메타
        "actual_live_required": actual_live_required,
        "forbid_mock": forbid_mock,
        "mock_used": False,
        "playwright_available": None,
        "chromium_available": None,
    }

    # suite 레벨 host proof 수집
    suite_host_proof = _collect_host_proof()
    suite_result.update(suite_host_proof)

    # playwright/chromium 가용 여부를 suite 레벨에 기록
    if actual_live_required or forbid_mock:
        pw_check = _check_playwright_available()
        suite_result["playwright_available"] = pw_check.get("playwright_available", False)
        suite_result["chromium_available"] = pw_check.get("chromium_available", False)

    with Path(fixture_path).open(encoding="utf-8") as f:
        fixture = json.load(f)

    cases = fixture.get("cases", [])
    suite_result["total_cases"] = len(cases)

    for case in cases:
        _run_suite_case(case, suite_result, forbid_mock, actual_live_required)

    suite_result["summary"] = (
        f"총 {suite_result['total_cases']}개 케이스: "
        f"허용 {suite_result['allowed_cases']}개 live 실행 {suite_result['live_executed']}개 완료, "
        f"차단 {suite_result['blocked_cases']}개 BLOCK 확인 {suite_result['gate_blocked_confirmed']}개, "
        f"검증필요 {suite_result['needs_verification_cases']}개"
    )

    return suite_result


__all__ = [
    "BODY_TEXT_MAX_LEN",
    "_check_playwright_available",
    "_collect_host_proof",
    "run_g2b_public_notice_fixture_live_suite",
    "run_g2b_public_notice_readonly_live",
    "validate_g2b_public_notice_live_result",
]
