"""L6 서비스 — 메일 순차 대량 발송 승인서 만들기·시험 발송·승인·취소·멈춤·실행 (API 라우터가 호출한다).

기준서: docs/specs/2026-10-02_mail_bulk_sequential.md (하나팩스 `hanafax_authorization_service` 와 같은 구조)
검증·해시 계산은 여기서 하고, 저장은 `bulk_store`, 판정은 `bulk_policy`, 차례 발송은 `naver_mail_bulk` 가 맡는다.
승인서는 한 번 승인하면 수정할 수 없다. 실행은 **백그라운드 스레드**(긴 간격 대기가 예약 작업 루프를 막지 않게).
AI(에이전트)에게는 이 서비스를 열지 않는다 — `mcp_server.API_REGISTRY` 에 없고 테스트가 고정한다.
주소록 파일은 허용 폴더(첨부와 같은 경로 안전 규칙) 안의 사용자 본인 파일만 읽는다(openpyxl 은 XML 공격을 막지 않으므로 임의 경로를 받지 않는다).
"""

from __future__ import annotations

import csv
import hashlib
import json
import threading
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ai_orchestrator.gongmu.gongmu_service import _read_rows
from ai_orchestrator.connectors.naver_mail import bulk_policy as policy
from ai_orchestrator.connectors.naver_mail import draft_policy as draft_policy
from ai_orchestrator.paths import repo_root
from ai_orchestrator.connectors.naver_mail import bulk_store as store
from ai_orchestrator.connectors.naver_mail import bulk_workflow as flow
from ai_orchestrator.connectors.naver_mail import drafts_workflow as drafts
from ai_orchestrator.connectors.naver_mail import mailbox_flow as mailbox_flow
from scripts.naver.mail.imap import bulk_sender
from scripts.naver.mail.imap import sender as smtp_draft

ROOT = repo_root()
MAX_RECIPIENTS = 5000
MAX_SUBJECT = 200
MAX_BODY = 20000
MAX_ATTACH = 5
_EMAIL_HEADERS = ("이메일", "메일", "email", "e-mail", "mail")
_NAME_HEADERS = ("이름", "성명", "담당자", "name")
_COMPANY_HEADERS = ("업체명", "상호", "회사", "company")


def _clean_recipients(raw: Any) -> list[dict[str, str]]:
    """형식을 검증하고 소문자로 맞춰 중복을 제거한다. 하나라도 잘못되면 거부(조용히 빼지 않는다)."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("수신자 목록이 비어 있습니다")
    if len(raw) > MAX_RECIPIENTS:
        raise ValueError(f"수신자는 최대 {MAX_RECIPIENTS}명입니다")
    seen: set[str] = set()
    cleaned: list[dict[str, str]] = []
    for item in raw:
        data = item if isinstance(item, dict) else {}
        email = policy.normalize_email(data.get("email", ""))
        if not policy.is_valid_email(email):
            raise ValueError(f"메일 주소 형식이 올바르지 않습니다: {policy.mask_email(email)}")
        if email in seen:
            continue
        seen.add(email)
        cleaned.append(
            {
                "email": email,
                "name": str(data.get("name", "")).strip()[:50],
                "company": str(data.get("company", "")).strip()[:80],
            }
        )
    return cleaned


# ── 주소록 파일(엑셀·CSV) 가져오기 ────────────────────────────────────────────────



def _find_col(header: list[str], keys: tuple[str, ...]) -> int | None:
    lowered = [h.strip().lower() for h in header]
    for key in keys:
        for i, h in enumerate(lowered):
            if key in h:
                return i
    return None


def import_recipients(path_text: str) -> tuple[list[dict[str, str]], dict[str, int]]:
    """주소록 파일에서 수신자를 읽는다. 허용 폴더 안의 파일만. 잘못된 주소·중복·수신거부는 세어서 알린다."""
    try:
        real = draft_policy.validate_attachment_path(
            path_text, allowed_dirs=draft_policy.allowed_attachment_dirs(), deny_roots=[ROOT]
        )
    except draft_policy.PathRejected as e:
        raise ValueError(str(e)) from e
    rows = _read_rows(real)
    if len(rows) < 2:
        raise ValueError("데이터 행이 없습니다(첫 줄은 제목 줄이어야 합니다)")
    header = rows[0]
    col_email = _find_col(header, _EMAIL_HEADERS)
    if col_email is None:
        raise ValueError("'이메일' 열을 찾지 못했습니다")
    col_name, col_company = _find_col(header, _NAME_HEADERS), _find_col(header, _COMPANY_HEADERS)

    def cell(r: list[str], i: int | None) -> str:
        return r[i].strip() if i is not None and i < len(r) else ""

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    stats = {"rows": len(rows) - 1, "invalid": 0, "duplicate": 0, "opted_out": 0}
    opted = store.opt_out_emails()
    for r in rows[1:]:
        email = policy.normalize_email(cell(r, col_email))
        if not policy.is_valid_email(email):
            stats["invalid"] += 1
        elif email in seen:
            stats["duplicate"] += 1
        elif email in opted:
            stats["opted_out"] += 1
        else:
            seen.add(email)
            out.append({"email": email, "name": cell(r, col_name), "company": cell(r, col_company)})
    stats["usable"] = len(out)
    return out, stats


# ── 승인서 ────────────────────────────────────────────────────────────────────


def _limit(value: Any, label: str, low: int, high: int, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{label}은(는) 숫자여야 합니다") from e
    if not low <= number <= high:
        raise ValueError(f"{label}은(는) {low}~{high} 사이여야 합니다")
    return number


def _hhmm(value: Any, label: str, default: str) -> str:
    text = str(value or default).strip()
    try:
        hh, mm = text.split(":")
        if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
            raise ValueError
    except ValueError as e:
        raise ValueError(f"{label}은(는) HH:MM 형식이어야 합니다") from e
    return f"{int(hh):02d}:{int(mm):02d}"


def _attachments(paths: Any) -> tuple[list[dict[str, Any]], str]:
    items = [str(p) for p in (paths or []) if str(p).strip()]
    if len(items) > MAX_ATTACH:
        raise ValueError(f"첨부는 최대 {MAX_ATTACH}개입니다")
    metas = [drafts.path_attachment(p)[0] for p in items]
    digest = hashlib.sha256(json.dumps(sorted(m["sha256"] for m in metas)).encode()).hexdigest() if metas else ""
    return metas, digest


def create(payload: dict[str, Any], *, user: str) -> dict[str, Any]:
    account = mailbox_flow.require_account(str(payload.get("account", "")))
    kind = str(payload.get("kind", "")).strip()
    subject, body = str(payload.get("subject", "")).strip(), str(payload.get("body", "")).strip()
    if not subject or not body:
        raise ValueError("제목과 본문을 입력하세요")
    if len(subject) > MAX_SUBJECT or len(body) > MAX_BODY:
        raise ValueError(f"제목은 {MAX_SUBJECT}자, 본문은 {MAX_BODY}자 이하여야 합니다")
    errors = policy.compliance_errors(kind, subject, body)
    if errors:
        raise ValueError(" / ".join(errors))
    recipients = _clean_recipients(payload.get("recipients"))
    metas, att_hash = _attachments(payload.get("attachment_paths"))
    per_day = _limit(payload.get("max_per_day"), "하루 상한", 1, policy.HARD_DAILY_CAP, policy.DEFAULT_DAILY_CAP)
    interval = _limit(
        payload.get("interval_sec"),
        "발송 간격(초)",
        policy.MIN_INTERVAL_SEC,
        policy.MAX_INTERVAL_SEC,
        policy.DEFAULT_INTERVAL_SEC,
    )
    new = store.NewAuthorization(
        name=str(payload.get("name", "")).strip()[:80] or subject[:40],
        account=account,
        kind=kind,
        recipients=recipients,
        subject=subject,
        body=body,
        attachments=metas,
        attachments_hash=att_hash,
        document_hash=policy.document_hash(subject, body, att_hash),
        scope_hash=policy.scope_hash(recipients, subject, body, att_hash, kind),
        interval_sec=interval,
        max_per_run=_limit(payload.get("max_per_run"), "회차 상한", 1, policy.HARD_DAILY_CAP, per_day),
        max_per_day=per_day,
        max_total=_limit(payload.get("max_total"), "전체 상한", 1, MAX_RECIPIENTS, len(recipients)),
        allowed_start=_hhmm(payload.get("allowed_start"), "허용 시작 시각", "09:00"),
        allowed_end=_hhmm(payload.get("allowed_end"), "허용 종료 시각", "18:00"),
        valid_from=str(payload["valid_from"]) if payload.get("valid_from") else None,
        valid_until=str(payload["valid_until"]) if payload.get("valid_until") else None,
        created_by=user,
    )
    return public_view(store.create_authorization(new))


def public_view(row: dict[str, Any]) -> dict[str, Any]:
    """화면·API 용: 주소는 마스킹하고 본문 미리보기만 보인다(전체 주소는 DB 에만)."""
    out = {k: v for k, v in row.items() if k not in ("recipients", "body", "attachments")}
    out["recipient_count"] = len(row["recipients"])
    out["recipients_preview"] = [
        {"email": policy.mask_email(r["email"]), "name": r.get("name", ""), "company": r.get("company", "")}
        for r in row["recipients"][:20]
    ]
    out["body_preview"] = row["body"][:300]
    out["attachments"] = [{"name": a["name"], "size": a["size"]} for a in row["attachments"]]
    return out


def list_all() -> list[dict[str, Any]]:
    return [public_view(r) for r in store.list_authorizations()]


def get(auth_id: str) -> dict[str, Any]:
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    return public_view(row)


def _smtp(account: str) -> bulk_sender.BulkSmtp:
    """운영 SMTP 연결(테스트가 이 함수를 바꿔 가짜 발송기를 쓴다)."""
    return bulk_sender.BulkSmtp(account)


def _test_subject(subject: str) -> str:
    """시험 메일임을 제목에 표시한다(이미 `[시험]` 으로 시작하면 중복하지 않는다)."""
    return subject if subject.lstrip().startswith("[시험]") else "[시험] " + subject


def send_self_test(auth_id: str, to_self: str) -> dict[str, Any]:
    """승인서의 첫 수신자 값으로 내용을 채워 **지정한 본인 주소 1통**만 보낸다. 성공하면 시험 발송 완료로 기록한다."""
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    if row["revoked"]:
        raise ValueError("취소된 승인서입니다")
    if not policy.is_valid_email(to_self):
        raise ValueError("시험 발송 받을 본인 주소가 올바르지 않습니다")
    first = row["recipients"][0]
    fields = {"이름": first.get("name", ""), "업체명": first.get("company", "")}
    uploads = drafts.rebuild_uploads(row["account"], row["attachments"])
    draft = smtp_draft.make_draft(
        row["account"],
        policy.normalize_email(to_self),
        _test_subject(policy.render(row["subject"], fields)),
        policy.render(row["body"], fields),
        uploads=uploads,
    )
    with _smtp(row["account"]) as conn:
        result = conn.send(draft)
    if not result.get("ok") or result.get("refused"):
        raise ValueError(
            "시험 발송에 실패했습니다: " + str(result.get("message") or result.get("error") or "수신자 거부")
        )
    store.mark_test_sent(auth_id)
    return {"ok": True, "to": policy.mask_email(to_self)}


def approve(auth_id: str, *, user: str, live: bool) -> dict[str, Any]:
    return public_view(store.approve(auth_id, user=user, live=live))


def revoke(auth_id: str, *, user: str) -> dict[str, Any]:
    return public_view(store.revoke(auth_id, user=user))


def resume(auth_id: str) -> dict[str, Any]:
    return public_view(store.resume(auth_id))


def pause(auth_id: str) -> dict[str, Any]:
    store.pause(auth_id, "manual")
    return get(auth_id)


def set_kill_switch(on: bool, *, user: str) -> dict[str, Any]:
    store.set_kill_switch(on, user=user)
    return {"kill_switch": store.kill_switch_on()}


def add_opt_out(email: str, *, reason: str, user: str) -> str:
    value = policy.normalize_email(email)
    if not policy.is_valid_email(value):
        raise ValueError("메일 주소 형식이 올바르지 않습니다")
    store.add_opt_out(value, reason=reason, user=user)
    return policy.mask_email(value)


def send_log(auth_id: str) -> list[dict[str, Any]]:
    """발송 이력(주소는 마스킹)."""
    return [{**r, "email": policy.mask_email(r["email"])} for r in store.list_send_log(auth_id)]


# ── 백그라운드 실행 ─────────────────────────────────────────────────────────────

_run_lock = threading.Lock()
_running: set[str] = set()
_last_run: dict[str, dict[str, Any]] = {}


def _korea_tz() -> timezone | ZoneInfo:
    """한국 표준시. 시간대 데이터가 없는 PC 에서는 UTC+9 고정 오프셋(한국은 서머타임이 없다)."""
    try:
        return ZoneInfo("Asia/Seoul")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=9), "KST")


KST = _korea_tz()


def _now_local() -> datetime:
    """허용 시간대·'오늘' 판정에 쓰는 현재 시각 — PC 시간대와 무관하게 항상 한국 시간."""
    return datetime.now(KST)


def _execute(auth_id: str) -> dict[str, Any]:
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    if not row["live"]:
        return flow.run(auth_id, lambda _d: {"ok": False, "error": "dry_run"}, _now_local).summary()
    uploads = drafts.rebuild_uploads(row["account"], row["attachments"])  # 승인 때 본 파일과 다르면 여기서 멈춘다
    with _smtp(row["account"]) as conn:
        return flow.run(auth_id, conn.send, _now_local, uploads=uploads).summary()


def _run_job(auth_id: str) -> None:
    try:
        outcome = {"status": "done", "summary": _execute(auth_id)}
    except Exception as exc:  # noqa: BLE001 - 실패 사유를 화면에 보여 주기 위해 기록한다(발송 재시도는 하지 않는다)
        outcome = {"status": "failed", "message": str(exc)[:300] or type(exc).__name__}
    with _run_lock:
        _last_run[auth_id] = {**outcome, "finished_at": datetime.now(UTC).isoformat(timespec="seconds")}
        _running.discard(auth_id)


def start(auth_id: str) -> dict[str, Any]:
    """승인된 승인서를 백그라운드에서 한 번 실행한다(이미 실행 중이면 거부). 승인·취소·멈춤 상태를 먼저 확인한다."""
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    if not row["approved"]:
        raise ValueError("승인되지 않은 승인서는 발송할 수 없습니다")
    if row["revoked"]:
        raise ValueError("취소된 승인서입니다")
    if row["paused"]:
        raise ValueError("멈춘 승인서입니다 — 원인을 확인하고 재개한 뒤 다시 실행하세요")
    with _run_lock:
        if auth_id in _running:
            raise ValueError("이미 발송 중입니다")
        _running.add(auth_id)
        _last_run.pop(auth_id, None)
    threading.Thread(target=_run_job, args=(auth_id,), daemon=True, name=f"mailbulk-{auth_id[:8]}").start()
    return status(auth_id)


def status(auth_id: str) -> dict[str, Any]:
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    with _run_lock:
        running = auth_id in _running
        last = dict(_last_run.get(auth_id, {}))
    counts = store.count_by_status(auth_id)
    sent_or_unknown = counts.get("sent", 0) + counts.get("unknown", 0)
    return {
        "running": running,
        "last": last or None,
        "counts": counts,
        "remaining": max(0, len(row["recipients"]) - sent_or_unknown),
        "paused": row["paused"],
        "paused_reason": row["paused_reason"],
        "kill_switch": store.kill_switch_on(),
    }
