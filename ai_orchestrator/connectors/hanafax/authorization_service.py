"""L6 서비스 — 하나팩스 발송 승인서 만들기·승인·취소·정지 (API 라우터가 호출한다).

기준서: docs/specs/2026-10-02_hanafax_auto_send.md
검증·해시 계산은 여기서 하고, 저장은 `authorization_store`, 판정은 `fax_send_policy` 가 맡는다.
승인서는 한 번 승인하면 수정할 수 없다(범위를 바꾸려면 새로 만든다).
"""

from __future__ import annotations

import contextlib
import csv
import json
import os
import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ai_orchestrator.connectors.hanafax import attachments as attachments
from ai_orchestrator.connectors.hanafax import authorization_store as store
from ai_orchestrator.connectors.hanafax import auto_sender as adapter
from ai_orchestrator.connectors.hanafax import send_job
from ai_orchestrator.connectors.hanafax import send_policy as policy
from ai_orchestrator.paths.runtime import data_dir, storage_dir

MAX_RECIPIENTS = 1000
MAX_PER_RUN_CAP = 1000
MAX_PER_DAY_CAP = 1000
MAX_TOTAL_CAP = 5000
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# ── 첨부 문서·주소록 경로 제한 ────────────────────────────────────────────────────
# AI 가 만든 초안의 경로를 그대로 믿으면 민감한 파일을 외부 번호로 보내거나(유출) 네트워크 경로로 접속하게 만들 수 있다.
# 허용: 홈 폴더·이 저장소·`HAEHAN_FAX_ALLOWED_DIRS`(os.pathsep 로 구분). 거부: UNC·상대 경로·점(.)으로 시작하는 폴더·키/설정 폴더.
_BLOCKED_PARTS = {"appdata", ".ssh", ".aws", ".gnupg", ".claude", ".git", "node_modules", "secrets"}


def _allowed_roots() -> list[Path]:
    roots = [Path.home(), Path(__file__).resolve().parents[3]]
    roots += [Path(p) for p in os.environ.get("HAEHAN_FAX_ALLOWED_DIRS", "").split(os.pathsep) if p.strip()]
    return [r.resolve() for r in roots if r.exists()]


def _safe_path(path_text: str, label: str) -> str:
    """허용된 위치의 실제 파일 경로만 돌려준다(심볼릭 링크는 실제 위치로 풀어서 검사). 아니면 ValueError."""
    text = str(path_text or "").strip().strip('"')
    if text.startswith(("\\\\", "//")):
        raise ValueError(f"{label}: 네트워크(UNC) 경로는 사용할 수 없습니다")
    path = Path(text)
    if not text or not path.is_absolute():
        raise ValueError(f"{label}: 전체(절대) 경로가 필요합니다")
    try:
        real = path.resolve(strict=True)
    except OSError:
        raise ValueError(f"{label}: 파일을 찾을 수 없습니다") from None
    if any(part.lower() in _BLOCKED_PARTS or part.startswith(".") for part in real.parts[1:]):
        raise ValueError(f"{label}: 설정·키·시스템 폴더의 파일은 사용할 수 없습니다")
    if not any(real == root or root in real.parents for root in _allowed_roots()):
        raise ValueError(f"{label}: 허용된 폴더(내 문서·다운로드 등 홈 폴더, 앱 폴더) 밖의 파일입니다 — 필요하면 HAEHAN_FAX_ALLOWED_DIRS 에 폴더를 추가하세요")
    return str(real)


def _clean_recipients(raw: Any) -> list[dict[str, str]]:
    """번호 형식을 검증하고 숫자만 남겨 중복을 제거한다. 하나라도 잘못되면 거부(조용히 빼지 않는다)."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("수신자 목록이 비어 있습니다")
    if len(raw) > MAX_RECIPIENTS:
        raise ValueError(f"수신자는 최대 {MAX_RECIPIENTS}명입니다")
    seen: set[str] = set()
    cleaned: list[dict[str, str]] = []
    for item in raw:
        raw = item.get("fax", "") if isinstance(item, dict) else ""
        number = policy.parse_number(raw)
        if number is None:
            raise ValueError(f"팩스번호 형식이 올바르지 않습니다(숫자·하이픈만, 국제·휴대폰·내선 표기 불가): {policy.mask_number(str(raw))}")
        if number in seen:
            continue
        seen.add(number)
        cleaned.append({"fax": number, "name": str(item.get("name", "")).strip()[:50]})
    return cleaned


# ── 주소록 파일(엑셀·CSV) 가져오기 ────────────────────────────────────────────────
_FAX_HEADERS = ("팩스", "fax")  # 우선순위 순 — 없으면 전화·연락처 열을 쓴다
_PHONE_HEADERS = ("수신번호", "연락처", "전화")
_NAME_HEADERS = ("업체명", "상호", "회사", "수신자", "이름", "name")
_OLD_LOG = data_dir() / "hanafax_sent_log.json"
_OLD_OK = {"sent", "전송 성공"}  # 예전 이력에서 이미 성공한 상태


def _read_rows(path: Path) -> list[list[str]]:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            return [["" if c is None else str(c).strip() for c in row] for row in wb.active.iter_rows(values_only=True)]
        finally:
            wb.close()
    if suffix in (".csv", ".txt"):
        for enc in ("utf-8-sig", "cp949"):
            try:
                with path.open(encoding=enc, newline="") as fh:
                    return [[c.strip() for c in row] for row in csv.reader(fh)]
            except UnicodeDecodeError:
                continue
    raise ValueError("주소록은 .xlsx 또는 .csv 파일이어야 합니다")


def _find_col(header: list[str], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        for i, h in enumerate(header):
            if key in h.lower():
                return i
    return None


def already_sent_numbers() -> set[str]:
    """예전(앱 이전) 발송 이력에서 이미 성공한 번호 — 같은 영업 공문을 다시 보내지 않기 위해 가져오기 때 제외한다."""
    try:
        records = json.loads(_OLD_LOG.read_text(encoding="utf-8"))["records"]
    except (OSError, ValueError, KeyError):
        return set()
    return {policy.normalize_number(r.get("fax_number_digits", "")) for r in records if r.get("status") in _OLD_OK}


def import_recipients(path_text: str, *, exclude_already_sent: bool = True) -> tuple[list[dict[str, str]], dict[str, int]]:
    """주소록 파일에서 수신자를 읽는다. 잘못된 번호·중복·수신거부·이미 발송한 번호는 **빼고 건수를 알려 준다**."""
    path = Path(path_text.strip().strip('"'))
    if not path.is_file():
        raise ValueError(f"주소록 파일을 찾을 수 없습니다: {path_text}")
    rows = _read_rows(path)
    if len(rows) < 2:
        raise ValueError("주소록에 데이터가 없습니다")
    header = [h.lower() for h in rows[0]]
    fax_col = _find_col(header, _FAX_HEADERS)
    if fax_col is None:
        fax_col = _find_col(header, _PHONE_HEADERS)
    if fax_col is None:
        raise ValueError("주소록에서 팩스번호 열('팩스'·'연락처' 등)을 찾지 못했습니다")
    name_col = _find_col(header, _NAME_HEADERS)
    pairs = [
        (row[fax_col] if fax_col < len(row) else "", row[name_col] if name_col is not None and name_col < len(row) else "")
        for row in rows[1:]
    ]
    return _screen(pairs, exclude_already_sent=exclude_already_sent)


def _screen(pairs: list[tuple[str, str]], *, exclude_already_sent: bool) -> tuple[list[dict[str, str]], dict[str, int]]:
    """(팩스번호, 이름) 목록을 검수한다 — 잘못된 번호·중복·수신거부·예전 이력에서 이미 보낸 번호는 빼고 건수를 알려 준다."""
    skip_numbers = store.opt_out_numbers() | (already_sent_numbers() if exclude_already_sent else set())
    summary = {"rows": len(pairs), "invalid": 0, "duplicate": 0, "opted_out_or_already_sent": 0}
    seen: set[str] = set()
    recipients: list[dict[str, str]] = []
    for raw, name in pairs:
        number = policy.parse_number(raw)
        if number is None:
            summary["invalid"] += 1
        elif number in seen:
            summary["duplicate"] += 1
        elif number in skip_numbers:
            summary["opted_out_or_already_sent"] += 1
        else:
            seen.add(number)
            recipients.append({"fax": number, "name": str(name)[:50]})
    summary["to_send"] = len(recipients)
    return recipients, summary


def _limit(value: Any, label: str, cap: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}은(는) 숫자여야 합니다") from None
    if not 1 <= number <= cap:
        raise ValueError(f"{label}은(는) 1~{cap} 사이여야 합니다")
    return number


def _hhmm(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not _HHMM.match(text):
        raise ValueError(f"{label}은(는) HH:MM 형식이어야 합니다")
    return text


def _iso(value: Any, label: str) -> str | None:
    """유효기간 값 검증 — 비어 있으면 None, 형식이 틀리면 거부한다(조용히 무시하면 만료 없는 승인서가 된다)."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{label}은(는) 2026-12-31T18:00:00 같은 ISO 형식이어야 합니다") from None
    return text


def create(payload: dict[str, Any], *, user: str) -> dict[str, Any]:
    """승인 대기 승인서를 만든다. 문서는 허용 형식의 실제 파일이어야 하고, 내용 해시가 범위에 고정된다."""
    name = str(payload.get("name", "")).strip()
    subject = str(payload.get("subject", "")).strip()
    if not name or not subject:
        raise ValueError("이름과 제목은 필수입니다")
    document_ref = _safe_path(str(payload.get("document_ref", "")), "첨부 문서")
    error = adapter.validate_document(document_ref)
    if error:
        raise ValueError(error)
    attachments.inspect_file(document_ref)  # 크기(10MB)·내용 머리(이름만 바꾼 파일 거부)
    start, end = (
        _hhmm(payload.get("allowed_start", "09:00"), "허용 시작 시각"),
        _hhmm(payload.get("allowed_end", "18:00"), "허용 종료 시각"),
    )
    if start >= end:
        raise ValueError("허용 시작 시각이 종료 시각보다 빨라야 합니다")
    valid_from, valid_until = _iso(payload.get("valid_from"), "유효 시작"), _iso(payload.get("valid_until"), "유효 종료")
    if valid_from and valid_until and datetime.fromisoformat(valid_from) >= datetime.fromisoformat(valid_until):
        raise ValueError("유효 시작이 종료보다 빨라야 합니다")
    import_summary: dict[str, int] | None = None
    if payload.get("recipients_file"):
        recipients, import_summary = import_recipients(
            _safe_path(str(payload["recipients_file"]), "주소록 파일"), exclude_already_sent=bool(payload.get("exclude_already_sent", True))
        )
        if not recipients:
            raise ValueError(f"보낼 수신자가 없습니다 ({import_summary})")
        if len(recipients) > MAX_RECIPIENTS:
            raise ValueError(f"수신자는 최대 {MAX_RECIPIENTS}명입니다 — 주소록을 나눠 주세요 (현재 {len(recipients)}명)")
    elif payload.get("site_group"):
        recipients, import_summary = recipients_from_site_group(
            str(payload["site_group"]),
            offset=int(payload.get("group_offset") or 0),
            limit=int(payload.get("group_limit") or MAX_RECIPIENTS),
            exclude_already_sent=bool(payload.get("exclude_already_sent", True)),
        )
        if not recipients:
            raise ValueError(f"보낼 수신자가 없습니다 ({import_summary})")
    else:
        recipients = _clean_recipients(payload.get("recipients"))
    document_hash = adapter.file_sha256(document_ref)
    row = store.create_authorization(
        store.NewAuthorization(
            name=name[:80],
            recipients=recipients,
            subject=subject[:80],
            document_hash=document_hash,
            document_ref=document_ref,
            scope_hash=policy.scope_hash(recipients, subject, document_hash),
            max_per_run=_limit(payload.get("max_per_run") or len(recipients), "1회 최대 건수", MAX_PER_RUN_CAP),
            max_per_day=_limit(payload.get("max_per_day") or len(recipients), "1일 최대 건수", MAX_PER_DAY_CAP),
            max_total=_limit(payload.get("max_total") or len(recipients), "총 최대 건수", MAX_TOTAL_CAP),
            allowed_start=start,
            allowed_end=end,
            valid_from=valid_from,
            valid_until=valid_until,
            created_by=user,
        )
    )
    return {**row, "import_summary": import_summary}  # import_summary 는 저장하지 않고 호출자(AI·화면)에게 알리기만 한다


def preview(auth_id: str) -> dict[str, Any]:
    """승인 전 미리보기 — 사람이 보고 승인한다. 수신번호는 승인 대상이므로 전체를 보여 준다."""
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    pending = store.unknown_numbers(row["document_hash"])
    return {
        **row,
        "recipient_count": len(row["recipients"]),
        "document_name": re.split(r"[\\/]", row["document_ref"])[-1],
        "document_matches": _document_matches(row),
        "draft_expired": _draft_expired(row),
        "pending_numbers": [r["fax"] for r in row["recipients"] if r["fax"] in pending],  # 결과 확인이 필요한 번호
    }


DRAFT_TTL_HOURS = 24  # 승인 대기 초안은 만든 지 이 시간이 지나면 승인할 수 없다(오래된 초안으로 카드를 다시 띄워 승인을 유도하는 것 방지)


def _draft_expired(row: dict[str, Any]) -> bool:
    if row["approved"]:
        return False
    created = datetime.fromisoformat(row["created_at"])
    return datetime.now(UTC) - created > timedelta(hours=DRAFT_TTL_HOURS)


def resolve_pending(auth_id: str, fax: str, outcome: str, *, user: str) -> dict[str, Any]:
    """'확인 필요'(결과 불명) 번호를 사람이 하나팩스 발송 내역에서 확인한 뒤 해소한다.

    outcome: "sent"(실제로 발송됨 → 성공으로 기록, 다시 보내지 않음) | "not_sent"(발송되지 않음 → 실패로 기록, 다시 보낼 수 있음).
    """
    if outcome not in ("sent", "not_sent"):
        raise ValueError("outcome 은 sent 또는 not_sent 여야 합니다")
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    number = policy.parse_number(fax)
    if number is None or number not in store.unknown_numbers(row["document_hash"]):
        raise ValueError("확인 필요 상태인 번호가 아닙니다")
    sent = outcome == "sent"
    store.record_send(
        store.SendRecord(
            auth_id,
            number,
            row["document_hash"],
            store.SENT if sent else store.FAILED,
            None,
            f"사람이 확인({user}): {'발송됨' if sent else '발송되지 않음'}",
        )
    )
    return preview(auth_id)


def _document_matches(row: dict[str, Any]) -> bool:
    try:
        return (
            not adapter.validate_document(row["document_ref"])
            and adapter.file_sha256(row["document_ref"]) == row["document_hash"]
        )
    except OSError:
        return False


def approve(auth_id: str, *, user: str, live: bool) -> dict[str, Any]:
    """승인한다. 승인 순간에도 문서가 생성 때와 같은지 확인한다."""
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    if _draft_expired(row):
        raise ValueError(f"초안을 만든 지 {DRAFT_TTL_HOURS}시간이 지나 만료되었습니다 — 새로 요청하세요")
    if not _document_matches(row):
        raise ValueError("문서가 승인서를 만든 뒤 바뀌었거나 없습니다 — 새 승인서를 만드세요")
    return store.approve(auth_id, user=user, live=live)


def revoke(auth_id: str, *, user: str) -> dict[str, Any]:
    return store.revoke(auth_id, user=user)


def set_kill_switch(on: bool, *, user: str) -> dict[str, Any]:
    """전역 정지를 켜거나 끈다."""
    store.set_kill_switch(on, user=user)
    return {"kill_switch": store.kill_switch_on()}


def send_log(auth_id: str) -> list[dict[str, Any]]:
    """발송 이력 — 수신번호는 마스킹해서 돌려준다."""
    return [{**r, "fax_digits": policy.mask_number(r["fax_digits"])} for r in store.list_send_log(auth_id)]


def add_opt_out(number: str, *, reason: str, user: str) -> str:
    digits = policy.parse_number(number)
    if digits is None:
        raise ValueError("팩스번호 형식이 올바르지 않습니다")
    store.add_opt_out(digits, reason=reason, user=user)
    return policy.mask_number(digits)


# ── 지금 발송 (승인된 승인서만) ────────────────────────────────────────────────
# 팩스 1건이 수십 초 걸리므로 백그라운드 스레드로 돌리고, 화면은 상태·이력을 조회한다. 같은 승인서의 동시 실행은 막는다.
_run_lock = threading.Lock()
_running: set[str] = set()
_last_run: dict[str, dict[str, str]] = {}


def _run_job(auth_id: str) -> None:
    try:
        message = send_job.run_send({"authorization_id": auth_id})
        outcome = {"status": "done", "message": message}
    except Exception as exc:  # noqa: BLE001 - 실패 사유를 화면에 보여 주기 위해 기록한다(발송 재시도는 하지 않는다)
        outcome = {"status": "failed", "message": str(exc)[:300] or type(exc).__name__}
    with _run_lock:
        _last_run[auth_id] = {**outcome, "finished_at": datetime.now(UTC).isoformat(timespec="seconds")}
        _running.discard(auth_id)
    # 사이트가 최종 결과를 확정할 시간을 준 뒤 전송결과와 자동 대조한다(읽기 전용, 실패해도 발송과 무관).
    # 응답 없음은 사이트가 몇 분간 재시도한 뒤 확정하므로(실측: 접수 9분 뒤 완료) 3분·15분 두 번 확인한다.
    for delay in AUTO_RECONCILE_DELAYS_SECONDS:
        timer = threading.Timer(delay, _auto_reconcile, args=(auth_id,))
        timer.daemon = True
        timer.start()


def run_now(auth_id: str) -> dict[str, Any]:
    """승인된 승인서를 지금 한 번 실행한다. 승인되지 않았거나 취소됐으면 거부한다(발송 전 승인 필수)."""
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    if not row["approved"]:
        raise ValueError("승인되지 않은 승인서는 발송할 수 없습니다 — 미리보기를 확인하고 먼저 승인하세요")
    if row["revoked"]:
        raise ValueError("취소된 승인서입니다")
    with _run_lock:
        if auth_id in _running:
            raise ValueError("이미 발송 중입니다")
        _running.add(auth_id)
        _last_run.pop(auth_id, None)
    threading.Thread(target=_run_job, args=(auth_id,), daemon=True, name=f"fax-run-{auth_id[:8]}").start()
    return run_status(auth_id)


def run_status(auth_id: str) -> dict[str, Any]:
    with _run_lock:
        running = auth_id in _running
        last = dict(_last_run.get(auth_id, {}))
    return {"running": running, "last": last or None}


# ── 하나팩스 실제 화면 미리보기 (전송 없음) ─────────────────────────────────────
# 승인서의 수신번호·제목·첨부를 하나팩스 접수 화면에 채워 스크린샷만 만든다(`scripts/hanafax/preview.py`).
# 보내기 버튼은 누르지 않는다. 사용자가 볼지 말지 정하며, 승인에는 필요하지 않다.
# 스크린샷에 수신번호가 보이므로 로컬 `data/` 에만 두고 커밋하지 않는다.
_PREVIEW_DIR = data_dir() / "hanafax_preview"
_previewing: set[str] = set()
_preview_state: dict[str, dict[str, Any]] = {}


def preview_image_path(auth_id: str) -> Path:
    return _PREVIEW_DIR / f"{re.sub(r'[^0-9a-f]', '', auth_id)}.png"


def _preview_job(auth_id: str, fax_nos: list[str], subject: str, document_ref: str) -> None:
    from scripts.hanafax.preview import capture_preview

    try:
        outcome = capture_preview(fax_nos, subject, document_ref, preview_image_path(auth_id))
    except Exception as exc:  # noqa: BLE001 - 미리보기 실패는 사유만 알린다(전송과 무관)
        outcome = {"ok": False, "message": f"미리보기 실패: {type(exc).__name__}"}
    with _run_lock:
        _preview_state[auth_id] = {**outcome, "finished_at": datetime.now(UTC).isoformat(timespec="seconds")}
        _previewing.discard(auth_id)


def start_preview(auth_id: str) -> dict[str, Any]:
    row = store.get_authorization(auth_id)
    if row is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    if row["revoked"]:
        raise ValueError("취소된 승인서입니다")
    if not _document_matches(row):
        raise ValueError("문서가 요청 때와 달라졌거나 없습니다")
    with _run_lock:
        if auth_id in _previewing:
            raise ValueError("미리보기를 만드는 중입니다")
        _previewing.add(auth_id)
        _preview_state.pop(auth_id, None)
    numbers = [r["fax"] for r in row["recipients"]]
    threading.Thread(
        target=_preview_job,
        args=(auth_id, numbers, row["subject"], row["document_ref"]),
        daemon=True,
        name=f"fax-preview-{auth_id[:8]}",
    ).start()
    return preview_status(auth_id)


def preview_status(auth_id: str) -> dict[str, Any]:
    with _run_lock:
        running = auth_id in _previewing
        state = dict(_preview_state.get(auth_id, {}))
    return {
        "running": running,
        "state": state or None,
        "image_ready": preview_image_path(auth_id).is_file() and bool(state.get("ok")),
    }


# ── 전송결과 대조 (최종 성공/실패 확정, 읽기 전용) ─────────────────────────────────
# 앱의 sent 는 '접수'일 뿐이다 — 하나팩스 전송결과 화면과 대조해 delivered/delivery_failed 로 확정한다(hanafax_reconcile).
AUTO_RECONCILE_DELAYS_SECONDS = (180, 900)
_reconciling: set[str] = set()
_reconcile_state: dict[str, dict[str, Any]] = {}


def _reconcile_job(auth_id: str) -> None:
    from ai_orchestrator.connectors.hanafax import reconcile as hanafax_reconcile

    try:
        state: dict[str, Any] = {"ok": True, **hanafax_reconcile.reconcile(auth_id)}
    except Exception as exc:  # noqa: BLE001 - 대조 실패는 사유만 알린다(발송·이력은 그대로)
        state = {"ok": False, "message": f"전송결과 확인 실패: {type(exc).__name__}"}
    with _run_lock:
        _reconcile_state[auth_id] = {**state, "finished_at": datetime.now(UTC).isoformat(timespec="seconds")}
        _reconciling.discard(auth_id)


def start_reconcile(auth_id: str) -> dict[str, Any]:
    if store.get_authorization(auth_id) is None:
        raise ValueError("승인서를 찾을 수 없습니다")
    with _run_lock:
        if auth_id in _reconciling:
            raise ValueError("전송결과를 확인하는 중입니다")
        _reconciling.add(auth_id)
        _reconcile_state.pop(auth_id, None)
    threading.Thread(target=_reconcile_job, args=(auth_id,), daemon=True, name=f"fax-reconcile-{auth_id[:8]}").start()
    return reconcile_status(auth_id)


def _auto_reconcile(auth_id: str) -> None:
    with contextlib.suppress(ValueError):  # 이미 확인 중이면 건너뛴다
        start_reconcile(auth_id)


def reconcile_status(auth_id: str) -> dict[str, Any]:
    with _run_lock:
        return {"running": auth_id in _reconciling, "state": dict(_reconcile_state.get(auth_id, {})) or None}


# ── 하나팩스 사이트 주소록 그룹 가져오기 (읽기 전용) ─────────────────────────────────
# 그룹 연락처는 사이트에서 10명씩 넘겨 가며 읽으므로(1천 명대는 몇 분) 백그라운드로 읽어 **로컬 캐시**에 두고,
# 승인서를 만들 때 그 캐시를 쓴다(`site_group`=그룹 번호). 캐시에는 개인정보(번호·이름)가 있어 `storage/`(커밋 제외)에만 둔다.
GROUP_CACHE_TTL_HOURS = 24
_CACHE_DIR = storage_dir() / "fax_address_cache"
_group_syncing: set[str] = set()
_group_state: dict[str, dict[str, Any]] = {}


def _valid_intid(intid: str) -> str:
    text = str(intid).strip()
    if not re.fullmatch(r"\d{1,12}", text):
        raise ValueError("그룹 번호가 올바르지 않습니다")
    return text


def _cache_path(intid: str) -> Path:
    return _CACHE_DIR / f"{_valid_intid(intid)}.json"


def list_site_groups() -> list[dict[str, Any]]:
    """하나팩스 주소록 그룹 목록(이름·인원) — 사이트에 로그인해 읽는다(수십 초 걸릴 수 있다)."""
    from scripts.hanafax.address_book import list_groups

    return list_groups()


def _group_sync_job(intid: str) -> None:
    from scripts.hanafax import address_book

    def progress(page: int, pages: int) -> None:
        with _run_lock:
            _group_state[intid] = {"ok": None, "page": page, "pages": pages}

    try:
        members = address_book.fetch_group(intid, progress=progress)
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(intid).write_text(
            json.dumps({"intid": intid, "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"), "members": members}, ensure_ascii=False),
            encoding="utf-8",
        )
        state: dict[str, Any] = {"ok": True, "members": len(members)}
    except Exception as exc:  # noqa: BLE001 - 읽기 실패는 사유만 알린다
        state = {"ok": False, "message": f"그룹을 읽지 못했습니다: {type(exc).__name__}"}
    with _run_lock:
        _group_state[intid] = {**state, "finished_at": datetime.now(UTC).isoformat(timespec="seconds")}
        _group_syncing.discard(intid)


def start_group_sync(intid: str) -> dict[str, Any]:
    intid = _valid_intid(intid)
    with _run_lock:
        if intid in _group_syncing:
            raise ValueError("이 그룹을 읽는 중입니다")
        _group_syncing.add(intid)
        _group_state[intid] = {"ok": None, "page": 0, "pages": 0}
    threading.Thread(target=_group_sync_job, args=(intid,), daemon=True, name=f"fax-group-{intid[-4:]}").start()
    return group_sync_status(intid)


def group_sync_status(intid: str) -> dict[str, Any]:
    intid = _valid_intid(intid)
    with _run_lock:
        running = intid in _group_syncing
        state = dict(_group_state.get(intid, {}))
    cached = _cache_path(intid).is_file()
    return {"running": running, "state": state or None, "cached": cached}


def _read_group_cache(intid: str) -> list[dict[str, str]]:
    path = _cache_path(intid)
    if not path.is_file():
        raise ValueError("이 그룹을 아직 가져오지 않았습니다 — 먼저 그룹을 가져오세요(그룹 가져오기)")
    data = json.loads(path.read_text(encoding="utf-8"))
    if datetime.now(UTC) - datetime.fromisoformat(data["fetched_at"]) > timedelta(hours=GROUP_CACHE_TTL_HOURS):
        raise ValueError(f"가져온 지 {GROUP_CACHE_TTL_HOURS}시간이 지났습니다 — 그룹을 다시 가져오세요")
    return list(data["members"])


def recipients_from_site_group(
    intid: str, *, offset: int = 0, limit: int = MAX_RECIPIENTS, exclude_already_sent: bool = True
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """가져온 그룹 캐시에서 `offset` 번째부터 `limit` 명을 수신자로 읽는다(큰 그룹은 구간을 나눠 승인). 검수 결과를 함께 돌려준다."""
    members = _read_group_cache(intid)
    if offset < 0 or limit < 1 or limit > MAX_RECIPIENTS:
        raise ValueError(f"구간은 시작 0 이상, 인원 1~{MAX_RECIPIENTS} 이어야 합니다")
    part = members[offset : offset + limit]
    if not part:
        raise ValueError(f"그룹 인원({len(members)}명)을 벗어난 구간입니다")
    recipients, summary = _screen([(m["fax"], m.get("name", "")) for m in part], exclude_already_sent=exclude_already_sent)
    summary.update({"group_total": len(members), "range_start": offset + 1, "range_end": offset + len(part)})
    return recipients, summary


# ── 첨부 파일: 경로 확인·올리기 (화면의 파일 선택·경로 확인 버튼) ─────────────────────────
def check_attachment(path_text: str) -> dict[str, Any]:
    """경로를 승인서 만들 때와 같은 규칙으로 미리 검사한다(허용 폴더·형식·크기·내용). 문제 있으면 ValueError."""
    real = _safe_path(str(path_text or ""), "첨부 문서")
    error = adapter.validate_document(real)
    if error:
        raise ValueError(error)
    return {"path": real, **attachments.inspect_file(real)}


def upload_attachment(filename: str, data: bytes) -> dict[str, Any]:
    """화면에서 고른 파일을 앱 폴더에 저장한다. 승인서가 참조하지 않는 오래된 업로드는 함께 정리한다."""
    saved = attachments.save_upload(filename, data)
    attachments.purge_old({a["document_ref"] for a in store.list_authorizations()})
    return saved
