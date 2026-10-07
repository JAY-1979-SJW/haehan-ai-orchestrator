"""browser.attach_file — 폼에 파일 첨부 (1차 구현).

- USER_DELEGATED — 사용자 승인 필요
- 사전 요약 + 사후 evidence
- 첨부만 수행 (제출은 별도 액션)
- 쿠키/session/storage_state 추출 안 함
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_orchestrator.agent_hub.action_evidence_collector import collect_evidence
from ai_orchestrator.agent_hub.action_registry import register_handler
from ai_orchestrator.agent_hub.policy.user_approval_gate import verify_and_consume_token

ACTION_NAME = "browser.attach_file"


def _find_file_input(page: Any, form_field_label: str) -> Any:
    """label 매칭 우선, 없으면 첫 번째 input[type=file]."""
    target = None
    # label 텍스트 매칭
    label = page.get_by_label(form_field_label) if form_field_label else None
    if label:
        try:
            target = label
        except Exception:  # noqa: BLE001 - 라벨탐색 실패 시 fallback 셀렉터로 전환(승인 토큰은 execute 진입부에서 이미 검증됨)
            target = None
    if target is None:
        # fallback: 첫 file input
        target = page.query_selector("input[type=file]")
    return target


def _attach_on_page(
    page: Any, page_url: str, file_path: str, form_field_label: str, timeout_seconds: int, raw: dict[str, Any]
) -> None:
    try:
        page.goto(page_url, timeout=timeout_seconds * 1000, wait_until="domcontentloaded")

        # input[type=file] 매핑 — label 기준
        target = _find_file_input(page, form_field_label)
        if target is None:
            raw["ok"] = False
            raw["verdict"] = "FILE_INPUT_NOT_FOUND"
        else:
            try:
                target.set_input_files(file_path)
                raw["ok"] = True
                raw["verdict"] = "FILE_ATTACHED"
                raw["attached_file_name"] = Path(file_path).name
                raw["attached_at"] = datetime.now(UTC).isoformat()
                raw["form_state_after"] = {
                    "field_label": form_field_label,
                    "filled": True,
                }
            except Exception as e:  # noqa: BLE001 - 첨부 실패는 ATTACH_FAILED verdict로 명확히 반환(승인 토큰은 execute 진입부에서 이미 검증됨, 제출 버튼은 클릭하지 않음)
                raw["ok"] = False
                raw["verdict"] = "ATTACH_FAILED"
                raw["error"] = f"{type(e).__name__}: {str(e)[:100]}"

    except Exception as e:  # noqa: BLE001 - 페이지 로드 실패는 PAGE_LOAD_FAILED verdict로 명확히 반환(승인 토큰은 execute 진입부에서 이미 검증됨, 제출 버튼은 클릭하지 않음)
        raw["ok"] = False
        raw["verdict"] = "PAGE_LOAD_FAILED"
        raw["error"] = f"{type(e).__name__}: {str(e)[:100]}"


def execute(
    page_url: str,
    file_path: str,
    form_field_label: str,
    approval_token: str,
    headless: bool = False,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """
    1. 승인 토큰 검증 (1회용 + 만료 + scope-bound)
    2. 토큰 PASS 시 페이지 열고 파일 input에 첨부
    3. evidence 수집

    제출 클릭은 하지 않는다.
    """
    if not file_path or not Path(file_path).exists():
        return {"ok": False, "verdict": "ERROR", "error": "file_path가 존재하지 않음"}

    # 승인 검증 (sanitize된 params hash로 검증)
    # file_name 은 승인요청 생성측(create_approval_request 호출부)과 동일하게
    # os.path.basename 방식(trailing slash 시 빈 문자열)을 유지해야 토큰 해시가 일치한다.
    # Path(...).name 은 trailing slash가 있으면 다르게 동작하므로 전환하지 않는다 (STD-02 예외).
    params_for_verify = {
        "page_url": page_url,
        "file_name": os.path.basename(file_path),
        "form_field_label": form_field_label,
    }
    verify = verify_and_consume_token(approval_token, ACTION_NAME, params_for_verify)
    if not verify["ok"]:
        return {
            "ok": False,
            "verdict": "APPROVAL_REJECTED",
            "reason": verify["reason"],
        }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "verdict": "PLAYWRIGHT_NOT_AVAILABLE"}

    raw: dict[str, Any] = {"approval_request_id": verify["request_id"]}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            context = browser.new_context()
            page = context.new_page()
            _attach_on_page(page, page_url, file_path, form_field_label, timeout_seconds, raw)
        finally:
            browser.close()

    evidence = collect_evidence(ACTION_NAME, raw)
    raw["evidence"] = evidence
    return raw


# registry 등록
register_handler(ACTION_NAME, execute)
