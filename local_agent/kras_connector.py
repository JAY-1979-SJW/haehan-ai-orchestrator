"""KRAS(위험성평가 서식 작성) API 커넥터.

환경변수:
  KRAS_BASE_URL      — KRAS 서비스 URL (기본 https://kras.haehan-ai.kr)
  KRAS_API_KEY       — X-API-Key 헤더값 (KRAS prod.env의 KRAS_SERVICE_API_KEY)
  KRAS_PROJECT_ID    — 기본 프로젝트 ID (태스크 params에 없을 때 사용)

지원 액션:
  kras.form.create_session  — 서식 세션 생성 (자동 입력 포함)
  kras.form.get_session     — 세션 상태 조회
  kras.form.list_forms      — 사용 가능한 서식 목록 조회
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("KRAS_BASE_URL", "https://kras.haehan-ai.kr").rstrip("/")
_API_KEY = os.getenv("KRAS_API_KEY", "")
_DEFAULT_PROJECT_ID = os.getenv("KRAS_PROJECT_ID", "")

_TIMEOUT = 15


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-API-Key": _API_KEY,
    }


def _validated_url(path: str) -> str:
    """BASE_URL + path 조합 후 https/http 스킴만 허용."""
    url = f"{_BASE_URL}{path}"
    scheme = url.split("://", 1)[0].lower()
    if scheme not in ("https", "http"):
        raise ValueError(f"KRAS URL 스킴 거절: {scheme!r} (https/http 만 허용)")
    return url


def _get(path: str) -> Any:
    req = urllib.request.Request(  # noqa: S310
        _validated_url(path),
        headers=_headers(),
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


def _post(path: str, body: dict) -> Any:
    data = json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(  # noqa: S310
        _validated_url(path),
        data=data,
        headers=_headers(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


# ── 공개 함수 ────────────────────────────────────────────────────────────────


def create_form_session(
    form_type: str,
    project_id: str | int,
    site_id: str | int | None = None,
) -> dict:
    """서식 세션 생성. 자동 입력값(prefill)을 먼저 조회해 initial_inputs에 주입."""
    if not _API_KEY:
        raise RuntimeError("KRAS_API_KEY 환경변수가 설정되지 않았습니다.")

    pid = str(project_id)

    # 1. prefill 조회 (best-effort)
    initial_inputs: dict = {}
    try:
        prefill = _get(f"/api/projects/{pid}/form-prefill?form_type={form_type}")
        if isinstance(prefill, dict):
            initial_inputs = prefill
    except Exception as exc:  # noqa: BLE001 - KRAS 서식 연동 커넥터 -- HTTP 에러 본문 디코딩 실패 시 문자열로 폴백, 폼 프리필 조회 실패는 무시하고 빈 입력값으로 진행(prefill은 편의 기능, 필수 아님)
        logger.warning("kras prefill 조회 실패 (무시): %s", exc)

    # 2. 세션 생성
    body: dict = {"form_type": form_type, "project_id": pid}
    if site_id is not None:
        body["site_id"] = str(site_id)
    if initial_inputs:
        body["initial_inputs"] = initial_inputs

    session = _post("/api/form-writing/sessions", body)
    session["kras_url"] = f"{_BASE_URL}/projects/{pid}/forms/{form_type}"
    return session


def get_form_session(session_id: str) -> dict:
    """세션 상태 조회."""
    if not _API_KEY:
        raise RuntimeError("KRAS_API_KEY 환경변수가 설정되지 않았습니다.")
    return _get(f"/api/form-writing/sessions/{session_id}")


def list_forms() -> list[dict]:
    """사용 가능한 서식 목록 조회."""
    if not _API_KEY:
        raise RuntimeError("KRAS_API_KEY 환경변수가 설정되지 않았습니다.")
    result = _get("/api/forms/types")
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("forms", [])
    return []


__all__ = ["create_form_session", "get_form_session", "list_forms"]
