"""
로컬 Agent 사용자 직접 인증 UI 서버

127.0.0.1 전용 바인딩. 외부 네트워크 노출 금지.
mock/fake 데이터 금지. store에 있는 실제 task만 표시.
HTML에 비밀번호/OTP/인증서 비밀번호 input 필드 없음.
click/type/submit 코드 없음.
safe_to_execute는 항상 False.
"""

from __future__ import annotations

import logging
import os
from typing import Any

try:
    from fastapi import FastAPI, HTTPException, Path
    from fastapi.responses import HTMLResponse, JSONResponse

    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

from core.agent_runtime.user_present.user_present_state_store import (
    _CONFIRMABLE_STATES,
    STATE_BLOCKED,
    STATE_CANCELLED,
    STATE_FAILED,
    STATE_USER_CONFIRMED,
    STATE_WAITING_FOR_USER,
    UserPresentStateStore,
    default_store,
)

logger = logging.getLogger(__name__)

# ── 서버 기본값 ──────────────────────────────────────────────────────────────

DEFAULT_HOST = "127.0.0.1"  # 외부 네트워크 노출 금지
DEFAULT_PORT = 18080


def _html_ui_fallback_enabled() -> bool:
    return os.getenv("HAEHAN_USER_PRESENT_UI_FALLBACK", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# ── HTML 생성 헬퍼 ───────────────────────────────────────────────────────────


def _auth_method_label(detected: list[str]) -> str:
    labels = {
        "certificate": "공동인증서/공인인증서",
        "financial_certificate": "금융인증서",
        "otp": "OTP (일회용 비밀번호)",
        "security_card": "보안카드",
        "simple_auth": "간편인증 (PASS/카카오/네이버)",
        "password": "비밀번호",
    }
    return ", ".join(labels.get(m, m) for m in detected) if detected else "일반 인증"


def _state_badge(state: str) -> str:
    colors = {
        STATE_WAITING_FOR_USER: "#F97316",
        STATE_USER_CONFIRMED: "#059669",
        STATE_CANCELLED: "#6B7280",
        STATE_BLOCKED: "#B91C1C",
        STATE_FAILED: "#B91C1C",
    }
    color = colors.get(state, "#374151")
    return f'<span style="color:{color};font-weight:600;">{state}</span>'


def _render_task_html(task: dict[str, Any]) -> str:
    """단일 task를 HTML 카드로 렌더링한다. 민감정보 필드 없음."""
    state = task.get("state", "UNKNOWN")
    can_confirm = state in _CONFIRMABLE_STATES
    can_cancel = state in {STATE_WAITING_FOR_USER, STATE_BLOCKED, STATE_FAILED}
    wfid = task.get("workflow_run_id", "")

    auth_label = _auth_method_label(task.get("detected_auth_methods") or [])
    site_name = task.get("site_name") or task.get("target_domain") or task.get("site_category") or "—"
    task_title = task.get("task_title") or task.get("operation_type") or "작업"

    confirm_btn = (
        f'<form method="post" action="/tasks/{wfid}/confirm" style="display:inline;">'
        f'<button type="submit" style="background:#F97316;color:#fff;border:none;'
        f'padding:8px 20px;border-radius:6px;cursor:pointer;font-size:14px;">인증 완료</button></form>'
        if can_confirm
        else '<button disabled style="background:#E5E7EB;color:#9CA3AF;border:none;'
        'padding:8px 20px;border-radius:6px;font-size:14px;">인증 완료</button>'
    )
    cancel_btn = (
        f'<form method="post" action="/tasks/{wfid}/cancel" style="display:inline;">'
        f'<button type="submit" style="background:#6B7280;color:#fff;border:none;'
        f'padding:8px 20px;border-radius:6px;cursor:pointer;font-size:14px;margin-left:8px;">중단</button></form>'
        if can_cancel
        else '<button disabled style="background:#E5E7EB;color:#9CA3AF;border:none;'
        'padding:8px 20px;border-radius:6px;font-size:14px;margin-left:8px;">중단</button>'
    )

    return f"""
<div style="border:1px solid #E5E7EB;border-radius:10px;padding:20px;margin-bottom:16px;background:#fff;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
    <span style="font-size:15px;font-weight:700;color:#0F172A;">{task_title}</span>
    {_state_badge(state)}
  </div>
  <div style="font-size:13px;color:#374151;line-height:1.8;">
    <div><strong>사이트:</strong> {site_name}</div>
    <div><strong>인증 방식:</strong> {auth_label}</div>
    <div><strong>작업 ID:</strong> <code style="font-size:11px;color:#6B7280;">{wfid}</code></div>
    <div><strong>생성 시각:</strong> {task.get("created_at", "—")}</div>
  </div>
  <div style="margin-top:14px;padding:12px;background:#FFF7ED;border-radius:6px;font-size:13px;color:#92400E;">
    ⚠️ 이 단계는 사용자가 직접 인증을 완료해야 합니다.<br>
    AI는 비밀번호·OTP·인증서 비밀번호를 입력하거나 볼 수 없습니다.<br>
    제출·결제·이체는 자동 실행되지 않습니다.<br>
    현재 화면에는 사용자 본인 작업 정보만 표시됩니다.
  </div>
  <div style="margin-top:14px;">
    {confirm_btn}
    {cancel_btn}
  </div>
</div>
"""


def _render_page_html(tasks: list[dict[str, Any]], title: str = "사용자 직접 인증 대기") -> str:
    """전체 페이지 HTML을 반환한다. 민감정보 필드 없음."""
    if not tasks:
        body = '<p style="color:#6B7280;text-align:center;padding:40px;">대기 중인 작업이 없습니다.</p>'
    else:
        body = "".join(_render_task_html(t) for t in tasks)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #F9FAFB; padding: 24px; color: #111827; }}
h1 {{ font-size: 20px; font-weight: 700; margin-bottom: 6px; color: #0F172A; }}
.subtitle {{ font-size: 13px; color: #6B7280; margin-bottom: 20px; }}
.info-bar {{ background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 8px;
             padding: 10px 14px; font-size: 12px; color: #1E40AF; margin-bottom: 20px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="subtitle">로컬 Agent 사용자 직접 인증 대기 화면 · 127.0.0.1 전용</p>
<div class="info-bar">
  🔒 이 화면은 사용자 본인 작업만 표시합니다.
  내부 정책·감사 로그·토큰·쿠키는 표시되지 않습니다.
  safe_to_execute = false (모든 작업).
</div>
{body}
</body>
</html>"""


# ── FastAPI 앱 팩토리 ─────────────────────────────────────────────────────────


def _apply_task_transition(
    _store: UserPresentStateStore,
    workflow_run_id: str,
    transition: Any,
    html_ui_enabled: bool,
) -> Any:
    """confirm / cancel 공통: 존재 확인 → 상태 전이 → 응답 (브라우저 action 미실행)."""
    task = _store.get_user_present_task(workflow_run_id)
    if task is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    try:
        updated = transition(workflow_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    sanitized = _store.sanitize_user_present_task_for_user(updated)
    if html_ui_enabled:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/", status_code=303)
    return JSONResponse({**sanitized, "safe_to_execute": False})


def create_app(
    store: UserPresentStateStore | None = None,
    *,
    enable_html_ui: bool | None = None,
) -> Any:
    """
    FastAPI 앱 인스턴스를 생성한다.
    store를 주입하지 않으면 default_store를 사용한다.
    테스트 시 store를 주입해 격리할 수 있다.
    """
    if not _FASTAPI_AVAILABLE:
        raise RuntimeError("fastapi가 설치되어 있지 않습니다. pip install fastapi 후 재시도하세요.")

    _store = store if store is not None else default_store
    html_ui_enabled = _html_ui_fallback_enabled() if enable_html_ui is None else bool(enable_html_ui)

    app = FastAPI(
        title="로컬 Agent 사용자 직접 인증 UI",
        description="127.0.0.1 전용 로컬 웹 UI. 민감정보 미표시.",
        version="1.0.0",
        docs_url=None,  # 외부 docs 노출 금지
        redoc_url=None,
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "safe_to_execute": False,
            "host": DEFAULT_HOST,
            "note": "127.0.0.1 전용 로컬 UI 서버",
        }

    @app.get("/")
    async def index() -> Any:
        tasks = _store.list_user_present_tasks()
        sanitized = [_store.sanitize_user_present_task_for_user(t) for t in tasks]
        if html_ui_enabled:
            return HTMLResponse(_render_page_html(sanitized))
        return JSONResponse(
            {
                "tasks": sanitized,
                "count": len(sanitized),
                "safe_to_execute": False,
                "html_ui_enabled": False,
            }
        )

    @app.get("/tasks")
    async def list_tasks() -> dict[str, Any]:
        tasks = _store.list_user_present_tasks()
        sanitized = [_store.sanitize_user_present_task_for_user(t) for t in tasks]
        return {"tasks": sanitized, "count": len(sanitized), "safe_to_execute": False}

    @app.get("/tasks/{workflow_run_id}")
    async def get_task(workflow_run_id: str = Path(...)) -> dict[str, Any]:
        task = _store.get_user_present_task(workflow_run_id)
        if task is None:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        sanitized = _store.sanitize_user_present_task_for_user(task)
        return {**sanitized, "safe_to_execute": False}

    @app.post("/tasks/{workflow_run_id}/confirm")
    async def confirm_task(workflow_run_id: str = Path(...)) -> Any:
        """
        사용자가 인증 완료 버튼을 클릭한 신호를 수신한다.
        이 endpoint는 상태 전이만 수행한다. 브라우저 action을 실행하지 않는다.
        click/type/submit을 실행하지 않는다.
        safe_to_execute는 전이 후에도 항상 False다.
        """
        return _apply_task_transition(
            _store,
            workflow_run_id,
            lambda wid: _store.mark_user_confirmed(wid),
            html_ui_enabled,
        )

    @app.post("/tasks/{workflow_run_id}/cancel")
    async def cancel_task(workflow_run_id: str = Path(...)) -> Any:
        """
        사용자가 중단 버튼을 클릭한 신호를 수신한다.
        상태 전이만 수행한다. 브라우저 action을 실행하지 않는다.
        """
        return _apply_task_transition(
            _store,
            workflow_run_id,
            lambda wid: _store.mark_user_cancelled(wid),
            html_ui_enabled,
        )

    return app


# ── 서버 실행 진입점 ──────────────────────────────────────────────────────────


def run_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    store: UserPresentStateStore | None = None,
) -> None:
    """
    로컬 UI 서버를 실행한다.
    host는 기본값 127.0.0.1. 0.0.0.0은 명시적으로 전달하지 않는 한 사용 불가.
    """
    if host == "0.0.0.0":  # noqa: S104
        raise ValueError("0.0.0.0 bind는 보안 정책상 금지됩니다. 127.0.0.1을 사용하세요.")

    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn이 설치되어 있지 않습니다. pip install uvicorn 후 재시도하세요.") from exc

    app = create_app(store)
    logger.info("[user-present-ui] 서버 시작: http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="warning")
