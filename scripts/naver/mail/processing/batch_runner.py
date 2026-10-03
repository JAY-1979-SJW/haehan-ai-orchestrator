"""244건 batch 본문 진입 + 복구 + 감사 — 안전 우선.

특징:
  - target dedupe (sn 기준)
  - checkpoint/resume — 성공 항목 재처리 안 함
  - throttle: 기본 4초 + ±1초 jitter
  - 복구 실패 즉시 중단 (--continue-on-warn 옵션으로만 허용)
  - PII masking 유지 + raw body 0
  - 첨부 다운로드 0, 외부 AI 호출 0

산출:
  data/inspection/naver_mail_body_pipeline_batch/
    batch_report.json, batch_summary.md, checkpoint.json,
    unread_restore_audit.json, pii_masking_summary.json,
    failure_records.json
"""

from __future__ import annotations

import json
import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from scripts.naver.mail.utilities import pii_mask
from scripts.naver.mail_read import body_reader

from . import unread_audit as ua

KST = timezone(timedelta(hours=9))

SCHEMA_VERSION = "batch-1.0"
DEFAULT_DELAY_S = 4.0
DEFAULT_JITTER_S = 1.0

# 메일별 status enum
PENDING = "PENDING"
BODY_READ_OK = "BODY_READ_OK"
BODY_READ_FAILED = "BODY_READ_FAILED"
UNREAD_UNCHANGED = "UNREAD_UNCHANGED"
UNREAD_CHANGED_RESTORED = "UNREAD_CHANGED_RESTORED"
UNREAD_CHANGED_RESTORE_FAILED = "UNREAD_CHANGED_RESTORE_FAILED"
MASKED_OK = "MASKED_OK"
SKIPPED_ALREADY_DONE = "SKIPPED_ALREADY_DONE"

# 성공으로 간주되는 terminal status
SUCCESS_STATUSES = frozenset(
    {
        BODY_READ_OK,
        UNREAD_UNCHANGED,
        UNREAD_CHANGED_RESTORED,
        MASKED_OK,
        SKIPPED_ALREADY_DONE,
    }
)

# 실패로 간주되는 terminal status
FAILURE_STATUSES = frozenset(
    {
        BODY_READ_FAILED,
        UNREAD_CHANGED_RESTORE_FAILED,
    }
)


class Actions(Protocol):
    def evaluate(self, expr: str) -> Any: ...
    def navigate(self, url: str) -> None: ...
    def wait_dom(self, expr_truthy: str, timeout_s: float = 8.0) -> bool: ...


# ── target ─────────────────────────────────────────────────────────


@dataclass
class BatchTarget:
    sn: str
    folder_id: str
    folder_name: str

    @property
    def key(self) -> str:
        return self.sn  # sn 기준 dedupe


def dedupe_targets(targets: list[BatchTarget]) -> tuple[list[BatchTarget], int]:
    seen: set[str] = set()
    out: list[BatchTarget] = []
    dup = 0
    for t in targets:
        if not t.sn:
            continue
        if t.sn in seen:
            dup += 1
            continue
        seen.add(t.sn)
        out.append(t)
    return out, dup


# ── 결과 ──────────────────────────────────────────────────────────


@dataclass
class MailResult:
    sn: str
    folder_id: str
    folder_name: str
    status: str = PENDING
    body_open_ok: bool = False
    masked_text_hash: str = ""
    pii_detected_count: int = 0
    pii_types: dict = field(default_factory=dict)
    has_attach: bool = False
    attach_names: list[str] = field(default_factory=list)
    # 보고서용 — PII 마스킹 후의 제목/발신자/본문 발췌. raw 금지.
    subject_masked: str = ""
    sender_masked: str = ""
    date_text: str = ""
    body_redacted_short: str = ""  # 첫 400자 (마스킹 적용 후)
    link_domain_top: list[str] = field(default_factory=list)
    state_before: str = ""
    state_after_open: str = ""
    state_after_restore: str = ""
    state_changed_on_open: bool = False
    restore_attempted: bool = False
    restore_ok: bool = False
    restore_reason: str = ""
    elapsed_ms: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BatchReport:
    schema_version: str = SCHEMA_VERSION
    run_id: str = ""
    started_at_iso: str = ""
    ended_at_iso: str = ""
    target_total: int = 0
    duplicate_sn_count: int = 0
    limit: int = 0
    continue_on_warn: bool = False
    attempted: int = 0
    success: int = 0
    failed: int = 0
    skipped_already_done: int = 0
    unread_state_changed: int = 0
    unread_restore_attempted: int = 0
    unread_restore_succeeded: int = 0
    unread_restore_failed: int = 0
    raw_body_leak_count: int = 0
    attachment_download_count: int = 0
    external_ai_call_count: int = 0
    pii_detected_total: int = 0
    pii_types_summary: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    avg_seconds_per_message: float = 0.0
    results: list[MailResult] = field(default_factory=list)
    halted_early: bool = False
    halt_reason: str = ""
    verdict: str = ""

    def to_dict(self) -> dict:
        return {
            **{k: v for k, v in asdict(self).items() if k != "results"},
            "results": [r.to_dict() for r in self.results],
        }


# ── checkpoint ────────────────────────────────────────────────────


def load_checkpoint(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "sn_to_status": {}, "run_id": ""}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 체크포인트 파일 손상시 run_id를 broken으로 표시한 안전 기본 상태 반환, 메일본문 읽기 실패시 BODY_READ_FAILED 상태로 명시적 실패 처리(fail-closed)
        return {"schema_version": SCHEMA_VERSION, "sn_to_status": {}, "run_id": "broken"}


def save_checkpoint(path: Path, run_id: str, sn_to_status: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "saved_at_iso": datetime.now(KST).replace(microsecond=0).isoformat(),
        "sn_to_status": sn_to_status,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 실행 ──────────────────────────────────────────────────────────


def _process_one(  # noqa: PLR0913 - 공개 시그니처 유지(동작 변경 금지 리팩터링)
    actions: Actions,
    t: BatchTarget,
    *,
    body_read_fn=None,
    snapshot_fn=None,
    open_body_fn=None,
    restore_fn=None,
    sleep_fn=None,
) -> MailResult:
    """본문 1건 처리 — DI 가능한 함수 주입으로 테스트 가능."""
    snapshot_fn = snapshot_fn or ua.snapshot_mail
    open_body_fn = open_body_fn or ua.open_body_and_audit_state
    restore_fn = restore_fn or ua.restore_unread_state
    body_read_fn = body_read_fn or (lambda a: a.evaluate(body_reader.BODY_EXPR))
    sleep_fn = sleep_fn or time.sleep

    res = MailResult(sn=t.sn, folder_id=t.folder_id, folder_name=t.folder_name)
    t0 = time.time()
    try:
        # 1) before snapshot
        snap = snapshot_fn(actions, t.sn, folder_id=t.folder_id)
        res.state_before = snap.before_state
        # 2) open body
        snap = open_body_fn(actions, snap, folder_id=t.folder_id)
        # 3) extract body
        payload = body_read_fn(actions)
        mb = (
            body_reader.parse_body_payload(t.sn, payload)
            if isinstance(payload, dict)
            else body_reader.MailBody(sn=t.sn)
        )
        mask_res = pii_mask.mask(mb.body_redacted or "")
        # 제목/발신자도 추가 PII 마스킹 통과 (이미 redact 됐지만 한 번 더)
        subj_mask = pii_mask.mask(mb.subject or "")
        sender_mask = pii_mask.mask(mb.sender_addr_redacted or mb.sender_name or "")
        res.body_open_ok = True
        res.masked_text_hash = mask_res.masked_text_hash
        res.pii_detected_count = mask_res.detected_count
        res.pii_types = mask_res.types
        res.has_attach = mb.has_attach
        res.attach_names = list(mb.attach_names)
        res.subject_masked = subj_mask.masked_text[:300]
        res.sender_masked = sender_mask.masked_text[:200]
        res.date_text = mb.date_text or ""
        res.body_redacted_short = (mask_res.masked_text or "").replace("\n", " ")[:400]
        # 링크 상위 5개 도메인만
        top = sorted(mb.link_domains.items(), key=lambda x: -x[1])[:5]
        res.link_domain_top = [f"{d}({n})" for d, n in top]
        # 4) restore
        snap = restore_fn(actions, snap, folder_id=t.folder_id)
        res.state_after_open = snap.after_open_state
        res.state_after_restore = snap.after_restore_state
        res.state_changed_on_open = snap.state_changed_on_open
        res.restore_attempted = snap.restore_attempted
        res.restore_ok = snap.restore_ok
        res.restore_reason = snap.restore_reason
        # 5) terminal status 판정
        if snap.before_state == ua.STATE_UNREAD:
            if snap.state_changed_on_open and not snap.restore_ok:
                res.status = UNREAD_CHANGED_RESTORE_FAILED
            elif snap.state_changed_on_open and snap.restore_ok:
                res.status = UNREAD_CHANGED_RESTORED
            else:
                res.status = UNREAD_UNCHANGED
        else:
            res.status = BODY_READ_OK
    except Exception as exc:  # noqa: BLE001 - 체크포인트 파일 손상시 run_id를 broken으로 표시한 안전 기본 상태 반환, 메일본문 읽기 실패시 BODY_READ_FAILED 상태로 명시적 실패 처리(fail-closed)
        res.status = BODY_READ_FAILED
        res.error = str(exc)[:200]
    res.elapsed_ms = int((time.time() - t0) * 1000)
    return res


def _tally_result(rep: BatchReport, res: MailResult) -> None:
    """처리 결과 1건을 report 카운터에 반영."""
    if res.status in SUCCESS_STATUSES:
        rep.success += 1
    elif res.status in FAILURE_STATUSES:
        rep.failed += 1
    if res.state_changed_on_open:
        rep.unread_state_changed += 1
    if res.restore_attempted:
        rep.unread_restore_attempted += 1
        if res.restore_ok:
            rep.unread_restore_succeeded += 1
        else:
            rep.unread_restore_failed += 1
    rep.pii_detected_total += res.pii_detected_count
    for k, v in (res.pii_types or {}).items():
        rep.pii_types_summary[k] = rep.pii_types_summary.get(k, 0) + int(v)


def run_batch(  # noqa: PLR0913 - 공개 시그니처 유지(동작 변경 금지 리팩터링)
    actions: Actions,
    targets: list[BatchTarget],
    *,
    limit: int = 0,
    checkpoint_path: Path | None = None,
    delay_s: float = DEFAULT_DELAY_S,
    jitter_s: float = DEFAULT_JITTER_S,
    continue_on_warn: bool = False,
    sleep_fn=None,
    process_fn=None,
) -> BatchReport:
    """대량 batch 실행. resume + halt-on-restore-failure + throttle."""
    sleep_fn = sleep_fn or time.sleep
    process_fn = process_fn or _process_one
    targets, dup = dedupe_targets(targets)
    if limit and limit > 0:
        targets = targets[:limit]
    rep = BatchReport(
        run_id=uuid.uuid4().hex[:12],
        started_at_iso=datetime.now(KST).replace(microsecond=0).isoformat(),
        target_total=len(targets),
        duplicate_sn_count=dup,
        limit=limit,
        continue_on_warn=continue_on_warn,
    )

    # checkpoint 로드
    ck = load_checkpoint(checkpoint_path) if checkpoint_path else {"sn_to_status": {}, "run_id": ""}
    prior = ck.get("sn_to_status", {})

    t_start = time.time()
    for idx, t in enumerate(targets):
        # resume: 이미 성공한 항목은 skip
        prev = prior.get(t.sn)
        if prev and prev.get("status") in SUCCESS_STATUSES and prev.get("status") != SKIPPED_ALREADY_DONE:
            res = MailResult(
                sn=t.sn,
                folder_id=t.folder_id,
                folder_name=t.folder_name,
                status=SKIPPED_ALREADY_DONE,
                masked_text_hash=prev.get("masked_text_hash", ""),
                pii_detected_count=prev.get("pii_detected_count", 0),
            )
            rep.results.append(res)
            rep.skipped_already_done += 1
            continue

        # 처리
        res = process_fn(actions, t)
        rep.attempted += 1
        rep.results.append(res)
        # 카운터
        _tally_result(rep, res)

        # checkpoint 업데이트
        prior[t.sn] = {
            "status": res.status,
            "masked_text_hash": res.masked_text_hash,
            "pii_detected_count": res.pii_detected_count,
            "elapsed_ms": res.elapsed_ms,
        }
        if checkpoint_path:
            save_checkpoint(checkpoint_path, rep.run_id, prior)

        # 복구 실패 — 즉시 중단 (--continue-on-warn 아니면)
        if res.status == UNREAD_CHANGED_RESTORE_FAILED and not continue_on_warn:
            rep.halted_early = True
            rep.halt_reason = f"restore_failed_at_sn={res.sn}"
            break

        # throttle (마지막 메일 후엔 skip)
        if idx < len(targets) - 1:
            d = delay_s + random.uniform(0, jitter_s) if jitter_s > 0 else delay_s
            sleep_fn(d)

    rep.elapsed_seconds = round(time.time() - t_start, 2)
    rep.avg_seconds_per_message = round(rep.elapsed_seconds / max(rep.attempted, 1), 2)
    rep.ended_at_iso = datetime.now(KST).replace(microsecond=0).isoformat()
    return rep


# ── 산출물 저장 ──────────────────────────────────────────────────


def write_outputs(rep: BatchReport, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    p1 = out_dir / "batch_report.json"
    p1.write_text(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    paths["report"] = p1
    p2 = out_dir / "unread_restore_audit.json"
    p2.write_text(
        json.dumps(
            {
                "state_changed": rep.unread_state_changed,
                "restore_attempted": rep.unread_restore_attempted,
                "restore_succeeded": rep.unread_restore_succeeded,
                "restore_failed": rep.unread_restore_failed,
                "per_mail": [
                    {
                        "sn": r.sn,
                        "state_before": r.state_before,
                        "state_after_open": r.state_after_open,
                        "state_after_restore": r.state_after_restore,
                        "restore_ok": r.restore_ok,
                        "restore_reason": r.restore_reason,
                    }
                    for r in rep.results
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    paths["unread"] = p2
    p3 = out_dir / "pii_masking_summary.json"
    p3.write_text(
        json.dumps(
            {
                "pii_detected_total": rep.pii_detected_total,
                "pii_types_summary": rep.pii_types_summary,
                "per_mail_hashes": [
                    {"sn": r.sn, "masked_text_hash": r.masked_text_hash, "pii_detected_count": r.pii_detected_count}
                    for r in rep.results
                    if r.body_open_ok
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    paths["pii"] = p3
    p4 = out_dir / "failure_records.json"
    failures = [r.to_dict() for r in rep.results if r.status in FAILURE_STATUSES]
    p4.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["failures"] = p4
    md = [
        f"# Body Pipeline BATCH — run {rep.run_id}",
        "",
        f"- target_total: {rep.target_total}",
        f"- limit: {rep.limit}",
        f"- duplicate_sn_count: {rep.duplicate_sn_count}",
        f"- attempted: {rep.attempted} / success: {rep.success} / failed: {rep.failed} / "
        f"skipped: {rep.skipped_already_done}",
        f"- unread state_changed={rep.unread_state_changed} "
        f"restore_attempted={rep.unread_restore_attempted} "
        f"restore_succeeded={rep.unread_restore_succeeded} "
        f"restore_failed={rep.unread_restore_failed}",
        f"- raw_body_leak_count: {rep.raw_body_leak_count}",
        f"- attachment_download_count: {rep.attachment_download_count}",
        f"- external_ai_call_count: {rep.external_ai_call_count}",
        f"- pii_detected_total: {rep.pii_detected_total}",
        f"- pii_types_summary: `{rep.pii_types_summary}`",
        f"- elapsed: {rep.elapsed_seconds}s (avg {rep.avg_seconds_per_message}s/mail)",
        f"- halted_early: {rep.halted_early} ({rep.halt_reason})",
        f"- **verdict: {rep.verdict}**",
    ]
    p5 = out_dir / "batch_summary.md"
    p5.write_text("\n".join(md), encoding="utf-8")
    paths["summary"] = p5
    # 비즈니스 보고서 (마스킹된 제목/발신자/본문 발췌)
    p6 = out_dir / "mail_inbox_business_report.md"
    p6.write_text(_render_business_report(rep), encoding="utf-8")
    paths["business_report"] = p6
    return paths


# ── 비즈니스 보고서 렌더러 (PII 마스킹된 데이터만 사용) ──────────


def _classify_priority(subj: str, sender: str) -> str:
    """제목/발신자로 액션 우선순위 분류 (단순 키워드 — 외부 AI 호출 X)."""
    s = (subj + " " + sender).lower()
    if any(k in s for k in ("노출 정지", "휴면", "정지 안내", "확약서", "미답변", "복원")):
        return "ACTION_REQUIRED"
    if any(k in s for k in ("색인", "indexing", "수동 조치", "오류", "service down", "장애")):
        return "REVIEW"
    if any(k in s for k in ("undelivered", "returned to sender", "반송", "전달 실패")):
        return "ATTENTION"
    if any(
        k in s
        for k in ("보안 알림", "새로운 환경", "새로운 기기", "security alert", "비밀번호", "로그인", "간편 로그인")
    ):
        return "SECURITY_NOTICE"
    if any(k in s for k in ("약관", "개정", "수수료", "처리방침", "이용약관", "정책")):
        return "POLICY_NOTICE"
    if any(k in s for k in ("결제", "영수증", "매출실적", "포인트", "마일리지", "리볼빙")):
        return "BILLING"
    if any(k in s for k in ("뉴스레터", "newsletter", "광고", "이벤트", "할인", "프로모션", "안내")):
        return "PROMO"
    return "OTHER"



PRIORITY_ORDER = (
    "ACTION_REQUIRED",
    "ATTENTION",
    "REVIEW",
    "SECURITY_NOTICE",
    "BILLING",
    "POLICY_NOTICE",
    "PROMO",
    "OTHER",
)


def _append_priority_sections(md: list[str], by_priority: dict[str, list[MailResult]]) -> None:
    """우선순위 분류 섹션을 md 에 추가."""
    for pri in PRIORITY_ORDER:
        lst = by_priority.get(pri, [])
        if not lst:
            continue
        md.append(f"\n### [{pri}] {len(lst)}건")
        for r in lst[:30]:  # 카테고리당 상위 30건만
            subj = r.subject_masked or "(제목없음)"
            sender = r.sender_masked or "(발신자미상)"
            date = r.date_text or ""
            attach = " 📎" if r.has_attach else ""
            pii = f" pii={r.pii_detected_count}" if r.pii_detected_count > 0 else ""
            md.append(
                f"- **{subj[:70]}**{attach}{pii}  \n"
                f"  발신: {sender[:60]}  |  날짜: {date[:30]}  "
                f"|  links: {','.join(r.link_domain_top) or '-'}"
            )
            if r.body_redacted_short:
                md.append(f"  > {r.body_redacted_short[:200]}")
        if len(lst) > 30:
            md.append(f"- … ({len(lst) - 30}건 더)")


def _render_business_report(rep: BatchReport) -> str:
    """마스킹된 제목/발신자/본문 발췌로 비즈니스 보고서 작성. raw 사용 X."""
    by_priority: dict[str, list[MailResult]] = {}
    by_folder: dict[str, int] = {}
    by_sender_domain: dict[str, int] = {}
    import re

    domain_re = re.compile(r"@([A-Za-z0-9.\-]+)")
    for r in rep.results:
        if not r.body_open_ok and r.status != SKIPPED_ALREADY_DONE:
            continue
        by_folder[r.folder_name] = by_folder.get(r.folder_name, 0) + 1
        # 발신자 도메인 추출
        m = domain_re.search(r.sender_masked or "")
        if m:
            dom = m.group(1).lower()
            by_sender_domain[dom] = by_sender_domain.get(dom, 0) + 1
        pri = _classify_priority(r.subject_masked, r.sender_masked)
        by_priority.setdefault(pri, []).append(r)


    md = [
        f"# 메일함 비즈니스 보고서 — run {rep.run_id}",
        "",
        f"- 처리 메일: {len(rep.results)}건 "
        f"(success {rep.success} / failed {rep.failed} / skipped {rep.skipped_already_done})",
        f"- 시작: {rep.started_at_iso}",
        f"- 종료: {rep.ended_at_iso}",
        f"- unread 토글/복구: {rep.unread_state_changed} → {rep.unread_restore_succeeded} "
        f"(실패 {rep.unread_restore_failed})",
        "- raw body leak: 0  attachment download: 0  external AI: 0",
        f"- PII 검출 총 {rep.pii_detected_total}건 — types {rep.pii_types_summary}",
        "",
        "> 본 보고서는 **PII 마스킹된 제목/발신자/본문 첫 400자**만 사용합니다. 원문 0건 노출.",
        "",
        "## 폴더별 분포",
    ]
    for folder, n in sorted(by_folder.items(), key=lambda x: -x[1]):
        md.append(f"- {folder}: {n}건")

    md += ["", "## 발신자 도메인 분포 (상위 15)"]
    for dom, n in sorted(by_sender_domain.items(), key=lambda x: -x[1])[:15]:
        md.append(f"- `{dom}` — {n}건")

    md += ["", "## 우선순위 분류"]
    _append_priority_sections(md, by_priority)

    return "\n".join(md)
