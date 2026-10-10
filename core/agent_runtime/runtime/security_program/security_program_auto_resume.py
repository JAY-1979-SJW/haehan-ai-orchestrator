"""Security Program Auto Resume — 설치 후 원래 task를 자동 재개한다."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from core.agent_runtime.runtime.security_program.local_security_installer_runner import (
    STATUS_INSTALL_COMPLETED,
    STATUS_INSTALL_FAILED,
    STATUS_INSTALL_PERMISSION_REQUIRED,
    STATUS_WAITING_USER_UAC,
    check_install_completed,
    prepare_install,
)
from core.agent_runtime.runtime.security_program.security_installer_candidate_finder import find_installer_candidates
from core.agent_runtime.runtime.security_program.security_installer_policy import evaluate_installer
from core.agent_runtime.runtime.security_program.security_program_detector import detect_security_signals
from core.agent_runtime.runtime.security_program.security_program_install_result_sanitizer import (
    build_safe_report,
)

# 흐름 상태
FLOW_DETECT = "FLOW_DETECT"
FLOW_FIND_CANDIDATE = "FLOW_FIND_CANDIDATE"
FLOW_POLICY_CHECK = "FLOW_POLICY_CHECK"
FLOW_AWAIT_PERMISSION = "FLOW_AWAIT_PERMISSION"
FLOW_AWAIT_UAC = "FLOW_AWAIT_UAC"
FLOW_INSTALL_RUNNING = "FLOW_INSTALL_RUNNING"
FLOW_INSTALL_COMPLETE = "FLOW_INSTALL_COMPLETE"
FLOW_RESUME_ORIGINAL = "FLOW_RESUME_ORIGINAL"
FLOW_BLOCKED = "FLOW_BLOCKED"


def run_security_install_flow(
    page_data: dict[str, Any],
    original_instruction: str,
    original_task_id: str | None = None,
    has_install_permission: bool = False,
    runner_fn: Callable | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    보안프로그램 설치 자동화 전체 흐름을 실행한다.

    1. 보안프로그램 필요 감지
    2. 설치 후보 수집
    3. 정책 검증
    4. 권한 확인 → 없으면 AWAIT_PERMISSION
    5. UAC 필요 → AWAIT_UAC (사용자 직접)
    6. 설치 완료 확인 (dry_run이면 SKIP)
    7. 원래 task 재개 준비

    Returns:
        safe result dict (민감 정보 없음)
    """
    task_id = original_task_id or str(uuid.uuid4())
    url = page_data.get("url", "")
    domain = _extract_domain(url)

    # 1. 감지
    detection = detect_security_signals(page_data)
    if not detection["requires_security_program"]:
        return _safe_result(
            task_id, domain, "NO_SECURITY_PROGRAM_REQUIRED", "보안프로그램 필요 신호가 감지되지 않았습니다."
        )

    # 2. 설치 후보 수집
    candidates_result = find_installer_candidates(page_data, source_host=domain)
    allowed = candidates_result["allowed"]

    if not allowed:
        return _safe_result(
            task_id, domain, "NO_INSTALL_CANDIDATE", "공식 설치 후보를 찾을 수 없습니다. 수동 설치가 필요합니다."
        )

    candidate = allowed[0]
    filename = candidate.get("filename", "")

    # 3. 정책 검증
    policy = evaluate_installer(
        filename=filename,
        source_host=domain,
        is_official_source=True,
        has_user_permission=has_install_permission,
    )

    if policy["policy"] == "POLICY_BLOCKED":
        return _safe_result(task_id, domain, "INSTALL_BLOCKED", f"정책 위반: {policy['violations']}")

    # 4. 권한 확인
    install_state = prepare_install(
        installer_candidate={**candidate, "source_host": domain},
        has_permission=has_install_permission,
        policy_result=policy,
    )

    if install_state["status"] == STATUS_INSTALL_PERMISSION_REQUIRED:
        report = build_safe_report(
            task_id=task_id,
            domain=domain,
            installer_safe_name=filename,
            source_host=domain,
            status=STATUS_INSTALL_PERMISSION_REQUIRED,
        )
        report["flow"] = FLOW_AWAIT_PERMISSION
        report["user_message_ko"] = install_state["user_message_ko"]
        report["signal_count"] = detection["signal_count"]
        report["signals"] = detection["signals"]
        return report

    # 5. UAC 필요 시
    if install_state["status"] == STATUS_WAITING_USER_UAC:
        report = build_safe_report(
            task_id=task_id,
            domain=domain,
            installer_safe_name=filename,
            source_host=domain,
            status=STATUS_WAITING_USER_UAC,
        )
        report["flow"] = FLOW_AWAIT_UAC
        report["user_message_ko"] = install_state["user_message_ko"]
        return report

    # 6. dry_run이면 실행 없이 VERIFIED 상태 반환
    if dry_run:
        report = build_safe_report(
            task_id=task_id,
            domain=domain,
            installer_safe_name=filename,
            source_host=domain,
            status="INSTALLER_VERIFIED",
            retry_ready=True,
        )
        report["flow"] = FLOW_INSTALL_COMPLETE
        report["user_message_ko"] = "설치 준비 완료 (dry_run)"
        return report

    # 7. 설치 완료 확인 (실제 실행은 사용자)
    complete = check_install_completed(page_data)
    if complete["install_completed"]:
        report = build_safe_report(
            task_id=task_id,
            domain=domain,
            installer_safe_name=filename,
            source_host=domain,
            status=STATUS_INSTALL_COMPLETED,
            install_detected=True,
            restart_required=complete["restart_browser_required"],
            retry_ready=complete["retry_original_task_ready"],
        )
        report["flow"] = FLOW_RESUME_ORIGINAL
        return report

    return _safe_result(
        task_id, domain, STATUS_INSTALL_FAILED, "설치 완료를 확인할 수 없습니다. 설치 마법사를 확인해주세요."
    )


def _safe_result(task_id: str, domain: str, status: str, message: str) -> dict[str, Any]:
    report = build_safe_report(
        task_id=task_id,
        domain=domain,
        installer_safe_name="",
        source_host=domain,
        status=status,
    )
    report["user_message_ko"] = message
    return report


def _extract_domain(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001 - URL에서 도메인 추출 실패 시 빈 문자열 반환 — 실제 설치 여부는 별도 정책 함수(evaluate_installer)가 판정하며, 도메인 추출 실패는 매칭 실패로 이어져 fail-closed
        return ""
