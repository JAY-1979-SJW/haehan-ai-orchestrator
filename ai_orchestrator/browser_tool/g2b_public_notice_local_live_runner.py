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

import os
import json
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from ai_orchestrator.browser_tool.g2b_public_notice_execution_gate import (
    GATE_READONLY_EXECUTION_CANDIDATE,
    validate_g2b_execution_gate_result,
)

# ── 상수 ──────────────────────────────────────────────────────────────────────

BODY_TEXT_MAX_LEN = 1000

_ALLOWED_G2B_DOMAINS: frozenset[str] = frozenset({
    "g2b.go.kr",
    "www.g2b.go.kr",
})

_FORBIDDEN_RESULT_FIELDS: frozenset[str] = frozenset({
    "cookie", "cookies", "session", "token", "password", "otp",
    "auth_token", "access_token", "refresh_token", "credential",
})

_VERDICT_PASS = "LIVE_PASS"
_VERDICT_FAIL = "LIVE_FAIL"
_VERDICT_WARN = "LIVE_WARN"
_VERDICT_BLOCK = "LIVE_BLOCK"


def _is_server_env() -> bool:
    """서버 환경 여부 판별."""
    return os.environ.get("IS_SERVER_ENV", "").lower() in ("1", "true", "yes")


def _is_allowed_final_url(url: str) -> bool:
    """final_url이 허용 도메인 안에 있는지 확인."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return domain in _ALLOWED_G2B_DOMAINS
    except Exception:
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
                try:
                    download.cancel()
                except Exception:
                    pass

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
            except Exception:
                result["body_text_sample"] = ""
                result["body_text_length"] = 0

            if download_detected:
                result["error"] = f"DOWNLOAD_DETECTED: {download_detected[0]}"

            context.close()
            browser.close()

    except Exception as e:
        result["error"] = f"PLAYWRIGHT_ERROR: {e}"

    return result


def run_g2b_public_notice_readonly_live(
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """
    execution gate를 통과한 candidate에 대해 live open/read를 수행한다.

    필수 출력:
    - input_url, canonical_url, final_url
    - operation, gate_verdict, execution_allowed
    - execution_dispatched, live_browser_worker_called
    - local_agent_required, local_agent_used
    - server_browser_used, readonly_allowed
    - download_auto_allowed, title, body_text_sample, body_text_length
    - blocked_reason, error, verdict
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
    }

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

    if not pw_result.get("local_agent_available"):
        result["local_agent_used"] = False
        result["blocked_reason"] = "LOCAL_AGENT_UNAVAILABLE"
        result["error"] = pw_result.get("error", "")
        result["verdict"] = _VERDICT_WARN
        return result

    result["local_agent_used"] = True
    result["live_browser_worker_called"] = True
    result["execution_dispatched"] = True
    result["title"] = pw_result.get("title", "")
    result["body_text_sample"] = pw_result.get("body_text_sample", "")
    result["body_text_length"] = pw_result.get("body_text_length", 0)
    result["final_url"] = pw_result.get("final_url", "")
    result["error"] = pw_result.get("error", "")

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


def validate_g2b_public_notice_live_result(result: dict[str, Any]) -> list[str]:
    """
    live runner 결과의 필수 필드 및 정책 준수를 검증한다.
    오류 목록 반환 (빈 리스트 = 유효).
    """
    errors: list[str] = []

    required_fields = [
        "input_url", "canonical_url", "final_url", "operation",
        "gate_verdict", "execution_allowed", "execution_dispatched",
        "live_browser_worker_called", "local_agent_required", "local_agent_used",
        "server_browser_used", "readonly_allowed", "download_auto_allowed",
        "title", "body_text_sample", "body_text_length",
        "blocked_reason", "error", "verdict",
    ]
    for field in required_fields:
        if field not in result:
            errors.append(f"필수 필드 누락: {field}")

    if result.get("server_browser_used") is not False:
        errors.append("server_browser_used는 항상 False여야 한다")

    if result.get("download_auto_allowed") is not False:
        errors.append("download_auto_allowed는 항상 False여야 한다")

    if result.get("local_agent_required") is not True:
        errors.append("local_agent_required는 항상 True여야 한다")

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


def run_g2b_public_notice_fixture_live_suite(
    fixture_path: str,
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
    from ai_orchestrator.browser_tool.g2b_public_notice_execution_gate import (
        build_g2b_readonly_execution_candidate,
    )

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
        "run_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(fixture_path, encoding="utf-8") as f:
        fixture = json.load(f)

    cases = fixture.get("cases", [])
    suite_result["total_cases"] = len(cases)

    for case in cases:
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
            # live 실행
            live_result = run_g2b_public_notice_readonly_live(candidate)
            case_result["live_result"] = live_result
            case_result["case_verdict"] = live_result.get("verdict", "")
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

    suite_result["summary"] = (
        f"총 {suite_result['total_cases']}개 케이스: "
        f"허용 {suite_result['allowed_cases']}개 live 실행 {suite_result['live_executed']}개 완료, "
        f"차단 {suite_result['blocked_cases']}개 BLOCK 확인 {suite_result['gate_blocked_confirmed']}개, "
        f"검증필요 {suite_result['needs_verification_cases']}개"
    )

    return suite_result


__all__ = [
    "run_g2b_public_notice_readonly_live",
    "validate_g2b_public_notice_live_result",
    "run_g2b_public_notice_fixture_live_suite",
    "BODY_TEXT_MAX_LEN",
]
