"""
inbox 관련 API 라우트 (Flask Blueprint)
POST /api/v1/inbox/email/fetch              — 하이웍스 메일 수집 → inbox 저장
POST /api/v1/inbox/email/classify           — inbox email 분류 → candidate 저장
POST /api/v1/inbox/classify                 — 범용 분류 (?source_type=kakaowork 등)
POST /api/v1/inbox/candidates/<item_id>/task — candidate → task 승격 (명시적 호출만)
GET  /api/v1/inbox                          — inbox 목록 조회 (?source_type=...)
GET  /api/v1/inbox/candidates               — task 후보 목록 조회
GET  /api/v1/tasks/<task_id>               — 생성된 email task 단건 조회
"""
import os
from flask import Blueprint, jsonify, request

import audit_logger
import candidate_store
import candidate_to_task
import email_task_store
import inbox_store
from email_classifier import classify
from hiworks_mail_reader import fetch_recent_mails
from logger import get_logger
from message_classifier import classify_message

log = get_logger("inbox_router")

inbox_bp = Blueprint("inbox", __name__, url_prefix="/api/v1/inbox")

_DEFAULT_FETCH_LIMIT = int(os.environ.get("HIWORKS_FETCH_LIMIT", "20"))


@inbox_bp.route("/email/fetch", methods=["POST"])
def fetch_email():
    """하이웍스 메일을 읽어 inbox에 저장."""
    data = request.get_json(silent=True) or {}
    limit = int(data.get("limit", _DEFAULT_FETCH_LIMIT))
    limit = max(1, min(limit, 100))

    mails = fetch_recent_mails(limit=limit)

    saved = 0
    skipped = 0
    errors = 0

    for mail in mails:
        try:
            result = inbox_store.save_mail(
                external_id=mail["external_id"],
                sender=mail["sender"],
                title=mail["title"],
                body_raw=mail["body_raw"],
                received_at=mail["received_at"],
                source_account=mail["source_account"],
            )
            if result["status"] == "saved":
                saved += 1
            else:
                skipped += 1
        except (KeyError, ValueError) as e:
            log.warning("inbox 저장 실패: %s", e)
            errors += 1

    log.info("fetch_email 완료: fetched=%d saved=%d skipped=%d errors=%d",
             len(mails), saved, skipped, errors)

    return jsonify({
        "status": "ok",
        "fetched": len(mails),
        "saved": saved,
        "skipped": skipped,
        "errors": errors,
    }), 200


@inbox_bp.route("/email/classify", methods=["POST"])
def classify_email():
    """inbox의 email 항목을 분류하고 candidate를 저장."""
    items = inbox_store.list_inbox(source_type="email")

    classified = 0
    skipped = 0
    errors = 0
    results = []

    for item in items:
        try:
            clf = classify(item)
            r = candidate_store.save_candidate(
                external_id=item["external_id"],
                source_account=item["source_account"],
                category=clf["category"],
                priority=clf["priority"],
                needs_review=clf["needs_review"],
                candidate_task_type=clf["candidate_task_type"],
                classification_reason=clf["classification_reason"],
            )
            if r["status"] == "saved":
                classified += 1
                results.append({
                    "item_id": r["item_id"],
                    "external_id": item["external_id"],
                    "category": clf["category"],
                    "priority": clf["priority"],
                    "needs_review": clf["needs_review"],
                    "candidate_task_type": clf["candidate_task_type"],
                })
            else:
                skipped += 1
        except Exception as e:
            log.warning("분류 실패 external_id=%s: %s", item.get("external_id", "?"), e)
            errors += 1

    log.info("classify_email 완료: classified=%d skipped=%d errors=%d",
             classified, skipped, errors)

    return jsonify({
        "status": "ok",
        "classified": classified,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    }), 200


@inbox_bp.route("", methods=["GET"])
def list_inbox():
    """inbox 목록 조회."""
    source_type = request.args.get("source_type")
    limit = int(request.args.get("limit", 50))
    limit = max(1, min(limit, 200))

    items = inbox_store.list_inbox(source_type=source_type, limit=limit)

    return jsonify({
        "status": "ok",
        "count": len(items),
        "items": items,
    }), 200


@inbox_bp.route("/classify", methods=["POST"])
def classify_messages():
    """
    범용 메시지 분류 — source_type으로 대상 지정.
    ?source_type=kakaowork  또는 body JSON {"source_type": "kakaowork"}
    분류 결과를 candidate로 저장. 자동 task 생성 없음.
    """
    data = request.get_json(silent=True) or {}
    source_type = request.args.get("source_type") or data.get("source_type", "")

    if not source_type:
        return jsonify({"status": "error", "message": "source_type required"}), 400

    _ALLOWED_SOURCE_TYPES = {"email", "kakaowork", "kakaotalk_channel"}
    if source_type not in _ALLOWED_SOURCE_TYPES:
        return jsonify({
            "status": "error",
            "message": f"source_type must be one of {sorted(_ALLOWED_SOURCE_TYPES)}",
        }), 400

    items = inbox_store.list_inbox(source_type=source_type)
    classified = 0
    skipped = 0
    errors = 0
    results = []

    _AUDIT_EVENT = {
        "kakaowork": "KAKAOWORK_MESSAGE_CLASSIFIED",
        "kakaotalk_channel": "KAKAOTALK_CHANNEL_MESSAGE_CLASSIFIED",
        "email": "KAKAOWORK_MESSAGE_CLASSIFIED",  # fallback (email은 /email/classify 사용 권장)
    }

    for item in items:
        try:
            clf = classify_message(item)
            r = candidate_store.save_candidate(
                external_id=item["external_id"],
                source_account=item["source_account"],
                category=clf["category"],
                priority=clf["priority"],
                needs_review=clf["needs_review"],
                candidate_task_type=clf["candidate_task_type"],
                classification_reason=clf["classification_reason"],
            )

            if r["status"] == "saved":
                classified += 1
                audit_logger.record(
                    _AUDIT_EVENT.get(source_type, "KAKAOWORK_MESSAGE_CLASSIFIED"),
                    actor="classifier",
                    note=f"item_id={r['item_id']} category={clf['category']}",
                )
                audit_logger.record(
                    "MESSAGE_CANDIDATE_CREATED",
                    actor="classifier",
                    note=f"item_id={r['item_id']} source={source_type}",
                )
                results.append({
                    "item_id": r["item_id"],
                    "external_id": item["external_id"],
                    "category": clf["category"],
                    "priority": clf["priority"],
                    "needs_review": clf["needs_review"],
                    "candidate_task_type": clf["candidate_task_type"],
                })
            else:
                skipped += 1
                audit_logger.record(
                    "MESSAGE_CANDIDATE_SKIPPED",
                    actor="classifier",
                    note=f"duplicate item external_id={item['external_id'][:20]}",
                )
        except Exception as e:
            log.warning("분류 실패 source=%s external_id=%s: %s",
                        source_type, item.get("external_id", "?"), e)
            errors += 1

    log.info("classify_messages 완료: source=%s classified=%d skipped=%d errors=%d",
             source_type, classified, skipped, errors)

    return jsonify({
        "status": "ok",
        "source_type": source_type,
        "classified": classified,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    }), 200


@inbox_bp.route("/candidates", methods=["GET"])
def list_candidates():
    """task 후보 목록 조회."""
    category = request.args.get("category")
    needs_review_param = request.args.get("needs_review")
    limit = int(request.args.get("limit", 50))
    limit = max(1, min(limit, 200))

    needs_review: bool | None = None
    if needs_review_param is not None:
        needs_review = needs_review_param.lower() in ("true", "1", "yes")

    items = candidate_store.list_candidates(
        category=category,
        needs_review=needs_review,
        limit=limit,
    )

    return jsonify({
        "status": "ok",
        "count": len(items),
        "candidates": items,
    }), 200


@inbox_bp.route("/candidates/<item_id>/task", methods=["POST"])
def promote_candidate(item_id: str):
    """candidate를 task로 승격. 명시적 호출만 — 자동 실행 없음."""
    result = candidate_to_task.promote(item_id)

    status_map = {
        "created":      201,
        "duplicate":    200,
        "not_found":    404,
        "no_task_type": 422,
    }
    http_code = status_map.get(result["status"], 500)
    return jsonify(result), http_code


@inbox_bp.route("/tasks/<task_id>", methods=["GET"])
def get_email_task(task_id: str):
    """email candidate에서 생성된 task 단건 조회."""
    task = email_task_store.get_email_task(task_id)
    if task is None:
        return jsonify({"status": "not_found", "task_id": task_id}), 404
    return jsonify({"status": "ok", "task": task}), 200
