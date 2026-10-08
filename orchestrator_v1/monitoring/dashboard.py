"""
운영 대시보드 (5단계) — Flask 기반 내부 운영 UI
인증: HTTP Basic Auth (ORCH_DASHBOARD_USER / ORCH_DASHBOARD_PASSWORD 환경변수)
"""

import hmac
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flask import Flask, Response, jsonify, render_template, request

from orchestrator_v1.core import audit_logger
from orchestrator_v1.core.logger import get_logger
from ai_orchestrator.core.logging_utils import mask_sensitive
from orchestrator_v1.inbox.notice_router import notice_bp
from orchestrator_v1.monitoring.log_analyzer import (
    _read_jsonl,
    generate_ai_ops_summary,
    save_cache,
    summarize_failures,
    summarize_pending_approvals,
    summarize_recent_activity,
)
from orchestrator_v1.routers.inbox_router import inbox_bp
from orchestrator_v1.routers.tasks_router import tasks_bp
from orchestrator_v1.tasks import approval_manager
from orchestrator_v1.webhooks.webhooks_router import webhooks_bp

_BASE_DIR = str(Path(__file__).resolve().parents[2])
_DECISIONS_PATH = Path(_BASE_DIR) / "storage" / "approval_decisions.jsonl"

log = get_logger("dashboard")


# ── HTTP Basic Auth ───────────────────────────────────────────────────────────


def _check_auth(username: str, password: str) -> bool:
    exp_user = os.environ.get("ORCH_DASHBOARD_USER", "")
    exp_pass = os.environ.get("ORCH_DASHBOARD_PASSWORD", "")
    if not exp_user or not exp_pass:
        return False
    # 상수시간 비교 — timing attack 방지
    return hmac.compare_digest(username.encode("utf-8"), exp_user.encode("utf-8")) and hmac.compare_digest(
        password.encode("utf-8"), exp_pass.encode("utf-8")
    )


def _require_auth() -> Response | None:
    """before_request 훅 — 인증 실패 시 Response 반환, 통과 시 None."""
    exp_user = os.environ.get("ORCH_DASHBOARD_USER", "")
    exp_pass = os.environ.get("ORCH_DASHBOARD_PASSWORD", "")

    if not exp_user or not exp_pass:
        return Response(
            "대시보드 인증 환경변수 미설정\nORCH_DASHBOARD_USER / ORCH_DASHBOARD_PASSWORD 를 설정하세요.",
            503,
        )

    auth = request.authorization
    # 비-Basic(Bearer 등) 헤더는 username/password 가 None → 빈 문자열로 취급해 401 (fail-closed)
    username = (auth.username or "") if auth else ""
    password = (auth.password or "") if auth else ""

    if not _check_auth(username, password):
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
        log.warning("dashboard.auth_failed ip=%s path=%s", ip, request.path)
        return Response(
            "인증이 필요합니다.",
            401,
            {"WWW-Authenticate": 'Basic realm="haehan-orchestrator"'},
        )
    return None


# 사용자 레지스트리 — 로컬/테스트 전용. 운영 배포 전 실제 인증으로 교체 필요.
_USERS = {
    "viewer-1": {"role": "viewer"},
    "operator-1": {"role": "operator"},
    "admin-1": {"role": "admin"},
}

_RISK_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_ROLE_MAX_RISK = {
    "viewer": None,
    "operator": "medium",
    "admin": "high",
}


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(_BASE_DIR) / "ui" / "templates"),
        static_folder=str(Path(_BASE_DIR) / "ui" / "static"),
        static_url_path="/static",
    )

    app.before_request(_require_auth)
    app.register_blueprint(inbox_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(notice_bp)

    @app.route("/dashboard")
    def dashboard():
        activity = summarize_recent_activity(limit=100)
        failures = summarize_failures(limit=100)
        pending_log = summarize_pending_approvals()
        live_pending = _get_live_pending_tokens()

        combined = {
            **activity,
            **failures,
            "pending_approvals": len(live_pending),
        }
        ai_summary = generate_ai_ops_summary(combined)
        save_cache(combined)

        return render_template(
            "dashboard.html",
            activity=activity,
            failures=failures,
            pending_log=pending_log,
            live_pending=live_pending,
            ai_summary=ai_summary,
        )

    @app.route("/dashboard/tasks/<task_id>")
    def task_detail(task_id: str):
        audit_path = Path(_BASE_DIR) / "logs" / "audit.jsonl"
        history_path = Path(_BASE_DIR) / "storage" / "execution_history.jsonl"

        audit_events = [e for e in _read_jsonl(audit_path) if e.get("task_id") == task_id]
        history_events = [e for e in _read_jsonl(history_path) if e.get("task_id") == task_id]

        token_info = None
        for tid, entry in approval_manager._store.items():
            if entry.get("task_id") == task_id:
                elapsed = time.time() - entry.get("issued_at", 0)
                token_info = {
                    "token_id_display": tid[:6] + "***",
                    "token_full": tid,
                    "risk_level": entry.get("risk_level"),
                    "approved": entry.get("approved"),
                    "rejected": entry.get("rejected"),
                    "issued_at": entry.get("issued_at"),
                    "expired": elapsed > approval_manager.TOKEN_TTL_SECONDS,
                    "ttl_remaining": max(0, int(approval_manager.TOKEN_TTL_SECONDS - elapsed)),
                }
                break

        task_info = {}
        if history_events:
            latest = history_events[-1]
            task_info = {
                "task_id": task_id,
                "action_type": latest.get("action_type", ""),
                "target": latest.get("target", ""),
                "risk_level": latest.get("risk_level", ""),
                "status": latest.get("execution_status", ""),
            }
        elif audit_events:
            first = audit_events[0]
            task_info = {
                "task_id": task_id,
                "action_type": first.get("action_type", ""),
                "target": "",
                "risk_level": first.get("risk_level", ""),
                "status": "UNKNOWN",
            }
        else:
            task_info = {"task_id": task_id, "action_type": "", "target": "", "risk_level": "", "status": "NOT_FOUND"}

        return render_template(
            "task_detail.html",
            task_id=task_id,
            task_info=task_info,
            audit_events=audit_events,
            token_info=token_info,
        )

    @app.route("/dashboard/approve", methods=["POST"])
    def approve():
        data = request.get_json(silent=True) or request.form.to_dict()
        result, code = _process_decision(
            data.get("token_id", ""),
            data.get("task_id", ""),
            data.get("user_id", ""),
            data.get("reason", ""),
            "approve",
        )
        return jsonify(result), code

    @app.route("/dashboard/reject", methods=["POST"])
    def reject():
        data = request.get_json(silent=True) or request.form.to_dict()
        result, code = _process_decision(
            data.get("token_id", ""),
            data.get("task_id", ""),
            data.get("user_id", ""),
            data.get("reason", ""),
            "reject",
        )
        return jsonify(result), code

    return app


def _get_live_pending_tokens() -> list:
    now = time.time()
    pending = []
    for token_id, entry in approval_manager._store.items():
        if entry.get("approved") or entry.get("rejected"):
            continue
        elapsed = now - entry.get("issued_at", now)
        if elapsed > approval_manager.TOKEN_TTL_SECONDS:
            continue
        pending.append(
            {
                "token_id_display": token_id[:6] + "***",
                "token_full": token_id,
                "task_id": entry.get("task_id"),
                "risk_level": entry.get("risk_level"),
                "issued_at": entry.get("issued_at"),
                "ttl_remaining": int(approval_manager.TOKEN_TTL_SECONDS - elapsed),
            }
        )
    return pending


def _check_decision_allowed(token_id: str, task_id: str, user_id: str) -> tuple:
    """승인/거부 사전 검증. (오류응답 또는 None, role, entry, risk_level) 반환."""
    if not token_id or not task_id or not user_id:
        return ({"error": "token_id, task_id, user_id are required"}, 400), None, None, None

    user = _USERS.get(user_id)
    if not user:
        return ({"error": f"unknown user_id: {user_id}"}, 403), None, None, None

    role = user["role"]
    if role == "viewer":
        return ({"error": "viewer role cannot approve or reject tasks"}, 403), None, None, None

    entry = approval_manager._store.get(token_id)
    if not entry:
        return ({"error": "token not found"}, 404), None, None, None

    risk_level = entry.get("risk_level", "critical")

    if risk_level == "critical":
        return ({"error": "critical tasks cannot be approved by anyone"}, 403), None, None, None

    max_risk = _ROLE_MAX_RISK.get(role)
    if max_risk is None or _RISK_RANK.get(risk_level, 99) > _RISK_RANK.get(max_risk, 0):
        return ({"error": f"role '{role}' cannot approve '{risk_level}' risk tasks"}, 403), None, None, None

    # 만료된 승인 토큰은 승인·거부 모두 거절한다(TTL 10분). 이 검사가 80b93dac 에서 실수로 빠져
    # 만료 토큰으로도 승인·실행이 되고 있었다(2026-10-04 시험 실패로 발견).
    elapsed = time.time() - entry.get("issued_at", 0)
    if elapsed > approval_manager.TOKEN_TTL_SECONDS:
        return ({"error": "token has expired"}, 410), None, None, None

    if entry.get("approved"):
        return ({"error": "token already approved"}, 409), None, None, None
    if entry.get("rejected"):
        return ({"error": "token already rejected"}, 409), None, None, None
    return None, role, entry, risk_level


def _process_decision(token_id: str, task_id: str, user_id: str, reason: str, action: str) -> tuple:
    err, role, _entry, risk_level = _check_decision_allowed(token_id, task_id, user_id)
    if err is not None:
        return err

    if action == "approve":
        approval_manager.approve_token(token_id)
        decision = "APPROVED"
        event_type = "APPROVAL_GRANTED"
    else:
        approval_manager.reject_token(token_id)
        decision = "REJECTED"
        event_type = "APPROVAL_REJECTED"

    audit_logger.record(
        event_type=event_type,
        task_id=task_id,
        action_type=None,
        actor=user_id,
        risk_level=risk_level,
        note=f"{decision} via dashboard by {user_id} (role={role}). reason: {reason}",
    )
    _record_decision(token_id, task_id, user_id, role, decision, risk_level, reason)

    # ── 승인 후 실행 연결 (low/medium만) ───────────────────────
    execution_result = None
    if action == "approve" and risk_level in {"low", "medium"}:
        from orchestrator_v1.tasks.executor import execute_task

        execution_result = execute_task(task_id)

    resp: dict = {
        "status": "ok",
        "decision": decision,
        "task_id": task_id,
        "risk_level": risk_level,
        "user_id": user_id,
        "role": role,
        "note": (
            "high risk approved but execution remains blocked"
            if risk_level == "high" and decision == "APPROVED"
            else ""
        ),
    }
    if execution_result is not None:
        resp["execution"] = {
            "status": execution_result.get("status"),
            "duration_ms": execution_result.get("duration_ms"),
            "error": execution_result.get("error"),
        }
    return resp, 200


def _record_decision(  # noqa: PLR0913 - 공개 시그니처 유지(동작 불변 리팩터링 범위)
    token_id: str, task_id: str, user_id: str, role: str, decision: str, risk_level: str, reason: str = ""
) -> None:
    entry = mask_sensitive(
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "token_prefix": token_id[:6] + "***" if token_id else None,
            "task_id": task_id,
            "user_id": user_id,
            "role": role,
            "decision": decision,
            "risk_level": risk_level,
            "reason": reason,
        }
    )
    decisions_path = Path(_DECISIONS_PATH)  # 테스트가 str로 monkeypatch하는 경우 호환
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    with decisions_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_dashboard(host: str = "127.0.0.1", port: int = 5050, debug: bool = False) -> None:
    app = create_app()
    print(f"\n{'=' * 60}")
    print("  haehan-ai-orchestrator 운영 대시보드")
    print(f"  http://{host}:{port}/dashboard")
    print("  [주의] 인증 없음 — 로컬/내부 테스트 전용")
    print(f"{'=' * 60}\n")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dashboard()
