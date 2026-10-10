"""L6 서비스 — 건설업 공무 업무판: 현장·계약 등록 → 해당 업무 자동 생성 → 상태·서류·기한 알림.

기준서: docs/specs/2026-10-02_construction_gongmu.md (G1)
- 이 모듈은 외부 사이트에 접속하지 않고 아무것도 제출·발송하지 않는다(G3 연동 전까지).
- 업무 판정은 `gates/gongmu_task_policy`(순수), 저장은 `persistence/gongmu_store`.
- 서류 경로·가져오기 파일은 메일 첨부와 같은 허용 폴더 규칙(`naver_mail.draft_policy.validate_attachment_path`)으로
  검사한다(openpyxl 은 XML 공격을 막지 않으므로 임의 경로를 받지 않는다).
- 법률 판단을 제공하지 않는다 — `DISCLAIMER` 를 화면에 보여준다.
"""

from __future__ import annotations

import csv
import hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ai_orchestrator.connectors.naver_mail import draft_policy as draft_policy
from ai_orchestrator.gongmu import gongmu_store as store
from ai_orchestrator.gongmu import gongmu_task_policy as policy

ROOT = Path(__file__).resolve().parents[2]
MAX_NAME = 100
MAX_TEXT = 500
MAX_IMPORT_ROWS = 2000
DISCLAIMER = (
    "이 화면은 업무를 빠짐없이 챙기도록 돕는 관리 도구이며 법률·세무 판단을 제공하지 않습니다. "
    "금액 기준·조문·신고 시점은 이미지 문구를 초기값으로 둔 것이므로 사용 전 국가법령정보센터 원문으로 확인하고, 필요하면 설정에서 수정하세요."
)
_ROLE_WORDS = {
    "원도급": policy.ROLE_PRIME,
    "prime": policy.ROLE_PRIME,
    "하도급": policy.ROLE_SUB,
    "sub": policy.ROLE_SUB,
}
_KIND_WORDS = {
    "도급": policy.KIND_PRIME,
    "원도급": policy.KIND_PRIME,
    "prime": policy.KIND_PRIME,
    "하도급": policy.KIND_SUB,
    "sub": policy.KIND_SUB,
}
_SITE_HEADERS = {
    "name": ("현장명", "공사명", "name"),
    "client": ("발주처", "발주기관", "client"),
    "location": ("위치", "공사 위치", "location"),
    "start_date": ("착공일", "착공"),
    "end_date": ("준공예정일", "준공일", "준공"),
    "role": ("지위", "구분"),
    "contract_amount": ("도급금액", "계약금액", "금액"),
    "manager": ("담당자", "담당"),
    "memo": ("비고", "메모"),
}
_CONTRACT_HEADERS = {
    "site_name": ("현장명", "공사명"),
    "counterparty": ("상대", "협력업체", "업체", "상호"),
    "kind": ("구분", "종류"),
    "amount": ("계약금액", "금액"),
    "contract_date": ("계약일", "체결일"),
    "memo": ("비고", "메모"),
}


def today_kst() -> date:
    try:
        tz: timezone | ZoneInfo = ZoneInfo("Asia/Seoul")
    except ZoneInfoNotFoundError:  # tzdata 없는 환경 — 한국은 일광절약시간이 없어 고정 +9 가 같다
        tz = timezone(timedelta(hours=9))
    return datetime.now(tz).date()


# ── 입력 정리 ─────────────────────────────────────────────────────────────


def _text(value: Any, label: str, limit: int, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{label}을(를) 입력하세요")
    if len(text) > limit:
        raise ValueError(f"{label}은(는) {limit}자 이내여야 합니다")
    return text


def _date_text(value: Any) -> str | None:
    parsed = policy.parse_date(value)
    return parsed.isoformat() if parsed else None


def _word(value: Any, words: dict[str, str]) -> str | None:
    text = str(value or "").strip()
    return words.get(text) or words.get(text.lower())


def _site_fields(raw: dict[str, Any]) -> dict[str, Any]:
    role = _word(raw.get("role"), _ROLE_WORDS)
    if role is None:
        raise ValueError("우리 회사 지위는 원도급 또는 하도급이어야 합니다")
    fields: dict[str, Any] = {
        "name": _text(raw.get("name"), "현장명", MAX_NAME, required=True),
        "client": _text(raw.get("client"), "발주처", MAX_TEXT),
        "location": _text(raw.get("location"), "공사 위치", MAX_TEXT),
        "start_date": _date_text(raw.get("start_date")),
        "end_date": _date_text(raw.get("end_date")),
        "role": role,
        "contract_amount": policy.parse_amount(raw.get("contract_amount")),
        "manager": _text(raw.get("manager"), "담당자", 50),
        "memo": _text(raw.get("memo"), "비고", MAX_TEXT),
    }
    if fields["start_date"] and fields["end_date"] and fields["end_date"] < fields["start_date"]:
        raise ValueError("준공예정일이 착공일보다 빠릅니다")
    return fields


def _contract_fields(raw: dict[str, Any]) -> dict[str, Any]:
    kind = _word(raw.get("kind"), _KIND_WORDS)
    if kind is None:
        raise ValueError("계약 구분은 도급 또는 하도급이어야 합니다")
    return {
        "kind": kind,
        "counterparty": _text(raw.get("counterparty"), "상대 업체", MAX_NAME),
        "amount": policy.parse_amount(raw.get("amount")),
        "contract_date": _date_text(raw.get("contract_date")),
        "memo": _text(raw.get("memo"), "비고", MAX_TEXT),
        "file_path": "",
    }


# ── 업무 생성 ─────────────────────────────────────────────────────────────


def generate_for_site(site_id: str, *, actor: str = "system", today: date | None = None) -> dict[str, Any]:
    """현장의 현재 상태에서 필요한 업무를 계산해 없는 것만 추가한다(멱등)."""
    site = store.get_site(site_id)
    if site is None:
        raise ValueError("현장을 찾을 수 없습니다")
    planned = policy.plan_tasks(
        site, store.list_contracts(site_id), store.list_catalog(), store.get_settings(), today or today_kst()
    )
    created = store.insert_planned(planned, actor=actor)
    return {"site_id": site_id, "planned": len(planned), "created": len(created)}


def generate_all(*, actor: str = "system", today: date | None = None) -> dict[str, int]:
    """모든 현장에 대해 새 기간(월·연) 업무를 포함해 다시 계산한다."""
    totals = {"sites": 0, "created": 0}
    for site in store.list_sites():
        result = generate_for_site(site["id"], actor=actor, today=today)
        totals["sites"] += 1
        totals["created"] += result["created"]
    return totals


# ── 현장·계약 ─────────────────────────────────────────────────────────────


def create_site(raw: dict[str, Any], *, actor: str) -> dict[str, Any]:
    site = store.create_site(_site_fields(raw), actor=actor)
    return {"site": site, "generation": generate_for_site(site["id"], actor=actor)}


def update_site(site_id: str, raw: dict[str, Any], *, actor: str) -> dict[str, Any]:
    current = store.get_site(site_id)
    if current is None:
        raise ValueError("현장을 찾을 수 없습니다")
    site = store.update_site(site_id, _site_fields({**current, **raw}), actor=actor)
    return {"site": site, "generation": generate_for_site(site_id, actor=actor)}


def create_contract(site_id: str, raw: dict[str, Any], *, actor: str) -> dict[str, Any]:
    contract = store.create_contract(site_id, _contract_fields(raw), actor=actor)
    if contract is None:
        raise ValueError("현장을 찾을 수 없습니다")
    return {"contract": contract, "generation": generate_for_site(site_id, actor=actor)}


def add_contract_change(contract_id: str, raw: dict[str, Any], *, actor: str) -> dict[str, Any]:
    when = _date_text(raw.get("date"))
    if when is None:
        raise ValueError("변경일을 입력하세요")
    change = {
        "date": when,
        "amount": policy.parse_amount(raw.get("amount")),
        "period_end": _date_text(raw.get("period_end")),
        "memo": _text(raw.get("memo"), "변경 사유", MAX_TEXT),
    }
    contract = store.add_contract_change(contract_id, change, actor=actor)
    if contract is None:
        raise ValueError("계약을 찾을 수 없습니다")
    return {"contract": contract, "generation": generate_for_site(contract["site_id"], actor=actor)}


# ── 업무 조회·변경 ────────────────────────────────────────────────────────


def _graded(task: dict[str, Any], today: date, soon_days: int) -> dict[str, Any]:
    due = policy.parse_date(task["due_date"])
    grade = policy.classify_due(due, task["status"], today, soon_days)
    days_left = (due - today).days if due else None
    return {
        **task,
        "grade": grade,
        "days_left": days_left,
        "status_label": policy.STATUS_LABEL.get(task["status"], task["status"]),
    }


def list_tasks(
    site_id: str | None = None, status: str | None = None, *, today: date | None = None
) -> list[dict[str, Any]]:
    today, soon = today or today_kst(), store.get_settings()["soon_days"]
    return [_graded(t, today, soon) for t in store.list_tasks(site_id, status)]


def get_task(task_id: str, *, today: date | None = None) -> dict[str, Any]:
    task = store.get_task(task_id)
    if task is None:
        raise ValueError("업무를 찾을 수 없습니다")
    graded = _graded(task, today or today_kst(), store.get_settings()["soon_days"])
    known = {d["doc_name"] for d in task["docs"]}
    ready = {d["doc_name"] for d in task["docs"] if d["ready"]}
    graded["missing_docs"] = [n for n in task["catalog_docs"] if n not in ready]
    graded["docs_checklist"] = task["docs"] + [
        {"doc_name": n, "ready": False, "file_path": "", "sha256": ""} for n in task["catalog_docs"] if n not in known
    ]
    return graded


def summary(*, today: date | None = None) -> dict[str, Any]:
    """화면 배지·예약 알림용 — 지연·임박·기한 확인 필요 건수와 목록(종료된 업무 제외)."""
    tasks = [t for t in list_tasks(today=today) if t["grade"] != policy.CLOSED]
    buckets = {g: [t for t in tasks if t["grade"] == g] for g in (policy.OVERDUE, policy.SOON, policy.UNKNOWN)}
    return {
        "counts": {g: len(v) for g, v in buckets.items()} | {"open": len(tasks)},
        "overdue": buckets[policy.OVERDUE],
        "soon": buckets[policy.SOON],
        "unknown": buckets[policy.UNKNOWN],
        "disclaimer": DISCLAIMER,
    }


def notice_text(*, today: date | None = None, limit: int = 10) -> str:
    """예약 작업(gongmu_due_notice)의 결과 문장 — 읽기·요약만, 어디로도 보내지 않는다."""
    data = summary(today=today)
    c = data["counts"]
    lines = [
        f"공무 업무 알림: 지연 {c['overdue']}건 · 임박 {c['soon']}건 · 기한 확인 필요 {c['unknown']}건 (진행 중 {c['open']}건)"
    ]
    for label, key in (("지연", "overdue"), ("임박", "soon")):
        for t in data[key][:limit]:
            lines.append(
                f"- [{label}] {t['site_name']} · {t['catalog_code']} {t['catalog_name']} · 기한 {t['due_date']}"
            )
    return "\n".join(lines)


def set_status(task_id: str, status: str, *, actor: str) -> dict[str, Any]:
    if not store.set_task_status(task_id, status, actor=actor):
        raise ValueError("업무를 찾을 수 없습니다")
    return get_task(task_id)


def update_task(task_id: str, raw: dict[str, Any], *, actor: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if "due_date" in raw:
        fields["due_date"] = _date_text(raw["due_date"])
    if "assignee" in raw:
        fields["assignee"] = _text(raw["assignee"], "담당자", 50)
    if "memo" in raw:
        fields["memo"] = _text(raw["memo"], "메모", 2000)
    if not store.update_task(task_id, fields, actor=actor):
        raise ValueError("업무를 찾을 수 없거나 바꿀 내용이 없습니다")
    return get_task(task_id)


def _validated_path(path_text: str) -> Path:
    try:
        return draft_policy.validate_attachment_path(
            path_text, allowed_dirs=draft_policy.allowed_attachment_dirs(), deny_roots=[ROOT]
        )
    except draft_policy.PathRejected as e:
        raise ValueError(str(e)) from e


def set_doc(task_id: str, doc_name: str, *, ready: bool, path: str, actor: str) -> dict[str, Any]:
    """서류 준비 여부와(선택) 파일 경로. 경로는 허용 폴더 안만, 앱 내부·비밀 파일은 거부한다."""
    name = _text(doc_name, "서류명", 100, required=True)
    file_path, digest = "", ""
    if path.strip():
        real = _validated_path(path)
        file_path, digest = str(real), hashlib.sha256(real.read_bytes()).hexdigest()
    if not store.set_doc(
        task_id, name, ready=ready or bool(file_path), file_path=file_path, sha256=digest, actor=actor
    ):
        raise ValueError("업무를 찾을 수 없습니다")
    return get_task(task_id)


# ── 엑셀·CSV 가져오기(전부 검증 후 한 번에 — 하나라도 잘못되면 아무것도 넣지 않는다) ─────────────


def _read_rows(path: Path) -> list[list[str]]:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:  # 읽기 전용 통합 문서는 지연 로딩이라 반드시 닫는다(공식 문서)
            return [["" if c is None else str(c) for c in row] for row in wb.active.iter_rows(values_only=True)]
        finally:
            wb.close()
    if suffix in (".csv", ".txt"):
        for enc in ("utf-8-sig", "cp949"):
            try:
                with path.open(encoding=enc, newline="") as f:
                    return [list(r) for r in csv.reader(f)]
            except UnicodeDecodeError:
                continue
    raise ValueError("엑셀(.xlsx) 또는 CSV 파일만 가져올 수 있습니다")


def _column_map(header: list[str], spec: dict[str, tuple[str, ...]]) -> dict[str, int]:
    lowered = [h.strip().lower() for h in header]
    found: dict[str, int] = {}
    for field, words in spec.items():
        for word in words:
            idx = next((i for i, h in enumerate(lowered) if h == word.lower()), None)
            if idx is None:
                idx = next((i for i, h in enumerate(lowered) if word.lower() in h and i not in found.values()), None)
            if idx is not None and idx not in found.values():
                found[field] = idx
                break
    return found


def _load_import(path_text: str, spec: dict[str, tuple[str, ...]], required: tuple[str, ...]) -> list[dict[str, Any]]:
    rows = _read_rows(_validated_path(path_text))
    if len(rows) < 2:
        raise ValueError("데이터 행이 없습니다(첫 줄은 제목 줄이어야 합니다)")
    if len(rows) - 1 > MAX_IMPORT_ROWS:
        raise ValueError(f"한 번에 최대 {MAX_IMPORT_ROWS}행까지 가져올 수 있습니다")
    cols = _column_map(rows[0], spec)
    missing = [f for f in required if f not in cols]
    if missing:
        raise ValueError(f"필요한 열을 찾지 못했습니다: {', '.join(missing)}")
    out = []
    for line, row in enumerate(rows[1:], start=2):
        if any(c.strip() for c in row):
            out.append({"_line": line, **{f: (row[i].strip() if i < len(row) else "") for f, i in cols.items()}})
    return out


def import_sites(path_text: str, *, actor: str) -> dict[str, Any]:
    """현장 목록 가져오기. 같은 현장명이 이미 있으면 건너뛴다(중복 방지)."""
    rows = _load_import(path_text, _SITE_HEADERS, ("name", "role"))
    valid, errors = [], []
    for row in rows:
        try:
            valid.append(_site_fields(row))
        except ValueError as e:
            errors.append({"line": row["_line"], "error": str(e)})
    if errors:
        return {"imported": 0, "skipped_existing": 0, "errors": errors}
    existing = {s["name"] for s in store.list_sites()}
    created = skipped = 0
    for fields in valid:
        if fields["name"] in existing:
            skipped += 1
            continue
        existing.add(fields["name"])
        site = store.create_site(fields, actor=actor)
        generate_for_site(site["id"], actor=actor)
        created += 1
    return {"imported": created, "skipped_existing": skipped, "errors": []}


def import_contracts(path_text: str, *, actor: str) -> dict[str, Any]:
    """계약 목록 가져오기. '현장명'으로 이미 등록된 현장에 연결한다(없는 현장이면 오류)."""
    rows = _load_import(path_text, _CONTRACT_HEADERS, ("site_name", "kind"))
    by_name = {s["name"]: s["id"] for s in store.list_sites()}
    valid, errors = [], []
    for row in rows:
        try:
            site_id = by_name.get(row.get("site_name", ""))
            if site_id is None:
                raise ValueError(f"등록되지 않은 현장입니다: {row.get('site_name', '')!r}")
            valid.append((site_id, _contract_fields(row)))
        except ValueError as e:
            errors.append({"line": row["_line"], "error": str(e)})
    if errors:
        return {"imported": 0, "errors": errors}
    for site_id, fields in valid:
        store.create_contract(site_id, fields, actor=actor)
    for site_id in {s for s, _ in valid}:
        generate_for_site(site_id, actor=actor)
    return {"imported": len(valid), "errors": []}


# ── 설정·기준표·이력 ──────────────────────────────────────────────────────


def get_settings() -> dict[str, int]:
    return store.get_settings()


def update_settings(raw: dict[str, Any], *, actor: str) -> dict[str, Any]:
    values = policy.validate_settings(raw)
    settings = store.update_settings(values, actor=actor) if values else store.get_settings()
    return {
        "settings": settings,
        "generation": generate_all(actor=actor),
    }  # 기준이 바뀌면 새로 해당되는 업무가 생길 수 있다


def list_sites() -> list[dict[str, Any]]:
    return store.list_sites()


def get_site(site_id: str) -> dict[str, Any]:
    site = store.get_site(site_id)
    if site is None:
        raise ValueError("현장을 찾을 수 없습니다")
    return {"site": site, "contracts": store.list_contracts(site_id)}


def list_catalog() -> list[dict[str, Any]]:
    return store.list_catalog()


def list_events(limit: int = 100) -> list[dict[str, Any]]:
    return store.list_events(min(max(limit, 1), 500))


# ── G2 AI 초안 (AI 는 만들기만, 확정·취소는 사람) ─────────────────────────────

DRAFT_KINDS = {
    "progress_billing": "기성 청구 내역서",
    "hq_report": "본사 정기 보고서",
    "subcontract_review": "하도급 계약 검토 체크리스트",
    "safety_checklist": "안전서류 작성 점검표",
    "missing_docs": "서류 누락 요약",
}


def create_draft(raw: dict[str, Any], *, actor: str) -> dict[str, Any]:
    kind = str(raw.get("kind") or "").strip()
    if kind not in DRAFT_KINDS:
        raise ValueError(f"초안 종류는 {', '.join(DRAFT_KINDS)} 중 하나여야 합니다")
    site_id = str(raw.get("site_id") or "").strip() or None
    task_id = str(raw.get("task_id") or "").strip() or None
    if site_id and store.get_site(site_id) is None:
        raise ValueError("현장을 찾을 수 없습니다")
    if task_id and store.get_task(task_id) is None:
        raise ValueError("업무를 찾을 수 없습니다")
    fields = {
        "kind": kind,
        "title": _text(raw.get("title") or DRAFT_KINDS[kind], "제목", 100),
        "body": _text(raw.get("body"), "내용", 6000, required=True),
        "site_id": site_id,
        "task_id": task_id,
    }
    return store.create_draft(fields, actor=actor)


def list_drafts(status: str | None = None) -> list[dict[str, Any]]:
    if status and status not in ("pending", "confirmed", "cancelled"):
        raise ValueError("상태는 pending·confirmed·cancelled 중 하나여야 합니다")
    return store.list_drafts(status)


def get_draft(draft_id: str) -> dict[str, Any]:
    draft = store.get_draft(draft_id)
    if draft is None:
        raise ValueError("초안을 찾을 수 없습니다")
    return draft


def confirm_draft(draft_id: str, *, actor: str) -> dict[str, Any]:
    return _decide(draft_id, True, actor)


def cancel_draft(draft_id: str, *, actor: str) -> dict[str, Any]:
    return _decide(draft_id, False, actor)


def _decide(draft_id: str, confirm: bool, actor: str) -> dict[str, Any]:
    done = store.decide_draft(draft_id, confirm=confirm, actor=actor)
    if done is None:
        get_draft(draft_id)  # 없으면 '찾을 수 없습니다'
        raise ValueError("이미 처리된 초안입니다")
    return done
