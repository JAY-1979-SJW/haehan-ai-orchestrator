"""
email task 레벨 API 라우트 (Flask Blueprint)
POST /api/v1/tasks/<task_id>/approval-request  — approval 요청 생성 (승인 전 실행 없음)
POST /api/v1/tasks/<task_id>/approve           — approval 승인 → task status=ready
POST /api/v1/tasks/<task_id>/reject            — approval 거절
POST /api/v1/tasks/<task_id>/execute           — ready task 실행 (risk 정책 적용)
GET  /api/v1/tasks/<task_id>                   — task 단건 조회
GET  /api/v1/tasks/<task_id>/approval          — task approval 상태 조회
"""

from typing import cast

from flask import Blueprint, jsonify, request

from orchestrator_v1.tasks import (
    email_task_approval,
    email_task_executor,
    email_task_store,
)

tasks_bp = Blueprint("tasks", __name__, url_prefix="/api/v1/tasks")


@tasks_bp.route("/<task_id>/approval-request", methods=["POST"])
def create_approval_request(task_id: str):
    """email task approval 요청 생성. 승인 요청만 하고 실행하지 않음."""
    result = email_task_approval.request_approval(task_id)
    status_map = {
        "created": 201,
        "duplicate": 200,
        "not_found": 404,
    }
    code = status_map.get(result["status"], 500)
    return jsonify(result), code


@tasks_bp.route("/<task_id>/approve", methods=["POST"])
def approve_task(task_id: str):
    """email task approval 승인. task status → ready (자동 실행 없음)."""
    data = request.get_json(silent=True) or {}
    approved_by = data.get("approved_by", "")
    if not approved_by:
        return jsonify({"status": "error", "message": "approved_by required"}), 400

    result = email_task_executor.approve_task(task_id, approved_by)
    status_map = {
        "approved": 200,
        "not_found": 404,
        "no_approval_request": 404,
        "approval_failed": 409,
    }
    code = status_map.get(result["status"], 500)
    return jsonify(result), code


@tasks_bp.route("/<task_id>/reject", methods=["POST"])
def reject_task(task_id: str):
    """email task approval 거절. task status 유지(pending)."""
    data = request.get_json(silent=True) or {}
    rejected_by = data.get("rejected_by", "")
    if not rejected_by:
        return jsonify({"status": "error", "message": "rejected_by required"}), 400

    result = email_task_executor.reject_task(task_id, rejected_by)
    status_map = {
        "rejected": 200,
        "not_found": 404,
        "no_approval_request": 404,
        "rejection_failed": 409,
    }
    code = status_map.get(result["status"], 500)
    return jsonify(result), code


@tasks_bp.route("/<task_id>/execute", methods=["POST"])
def execute_task(task_id: str):
    """ready 상태 email task 실행. risk_level 정책 적용 (medium/high/critical 차단)."""
    result = email_task_executor.execute_email_task(task_id)
    status_map = {
        "not_found": 404,
        "not_ready": 409,
        "not_approved": 409,
        "blocked_policy": 403,
        "skipped": 200,
        "error": 500,
        "EXECUTED": 200,
        "BLOCKED": 403,
        "PREVIEW_ONLY": 200,
    }
    code = status_map.get(cast(str, result.get("status")), 200)
    return jsonify(result), code


@tasks_bp.route("/<task_id>", methods=["GET"])
def get_task(task_id: str):
    """email task 단건 조회."""
    task = email_task_store.get_email_task(task_id)
    if task is None:
        return jsonify({"status": "not_found", "task_id": task_id}), 404
    return jsonify({"status": "ok", "task": task}), 200


@tasks_bp.route("/<task_id>/approval", methods=["GET"])
def get_task_approval(task_id: str):
    """email task의 approval 상태 조회."""
    token = email_task_approval.get_approval_for_task(task_id)
    if token is None:
        return jsonify({"status": "not_found", "task_id": task_id}), 404
    return jsonify({"status": "ok", "task_id": task_id, "approval": token}), 200
