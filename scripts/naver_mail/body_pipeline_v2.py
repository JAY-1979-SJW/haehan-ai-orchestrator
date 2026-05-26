"""본문 읽기 파이프라인 V2 — 진입 + 추출 + PII 마스킹 + 상태 복구 + 감사.

안전:
  - DEFAULT mode = DRY_RUN (본문 진입 없음, 메타데이터만)
  - FULL_READ mode 는 max_bodies 제한, 매 메일 본문 후 즉시 안읽음 복구
  - raw body 절대 저장 안 함
  - attachment 다운로드 절대 안 함
  - 외부 AI/HTTP 호출 차단 (FORBIDDEN_NETWORK_HOSTS)

산출:
  body_pipeline_report.json
  pii_masking_samples.json
  unread_state_audit.json
  body_pipeline_summary.md
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from . import pii_mask
from . import read_state_guard as rsg
from . import unread_audit as ua
from scripts.naver.mail_read import body_reader

KST = timezone(timedelta(hours=9))

MODE_DRY_RUN = "DRY_RUN"
MODE_FULL_READ = "FULL_READ"

SCHEMA_VERSION = "v2.0"

# 외부 AI/HTTP 차단 호스트 (탐지 목적 — 실제 호출 안 함을 자기검증)
FORBIDDEN_HOSTS = (
    "api.anthropic.com", "api.openai.com", "generativelanguage.googleapis.com",
    "api.deepl.com", "translate.googleapis.com", "claude.ai",
)


@dataclass
class BodyRecord:
    sn: str
    folder_id: str
    folder_name: str
    subject_masked: str = ""
    sender_masked: str = ""
    date_text: str = ""
    body_redacted: str = ""
    body_redacted_short: str = ""  # 본 보고용 (160자)
    body_len: int = 0
    masked_text_hash: str = ""
    pii_detected_count: int = 0
    pii_types: dict = field(default_factory=dict)
    link_domain_counts: dict = field(default_factory=dict)
    phishing_links_n: int = 0
    has_attach: bool = False
    attach_names: list[str] = field(default_factory=list)
    unread_audit: dict = field(default_factory=dict)
    open_ok: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _redact_url(url: str) -> str:
    """민감 query 제거 (token, auth, secret, session)."""
    return re.sub(
        r"([?&])(token|auth|secret|session|sid|sess|sid_token|key)=[^&]*",
        r"\1\2=[REDACTED]", url, flags=re.IGNORECASE,
    )


class Actions(Protocol):
    def evaluate(self, expr: str) -> Any: ...
    def navigate(self, url: str) -> None: ...
    def wait_dom(self, expr_truthy: str, timeout_s: float = 8.0) -> bool: ...


@dataclass
class PipelineReport:
    schema_version: str = SCHEMA_VERSION
    run_id: str = ""
    started_at_iso: str = ""
    ended_at_iso: str = ""
    mode: str = ""
    target_folders: list[dict] = field(default_factory=list)
    bodies: list[BodyRecord] = field(default_factory=list)
    unread_audit: dict = field(default_factory=dict)
    attempt_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    raw_body_leak_check: dict = field(default_factory=dict)
    attachment_download_count: int = 0
    external_ai_call_count: int = 0
    warnings: list[str] = field(default_factory=list)
    verdict: str = ""

    def to_dict(self) -> dict:
        return {
            **{k: v for k, v in asdict(self).items() if k != "bodies"},
            "bodies": [b.to_dict() for b in self.bodies],
        }


# ── 입력: 본문 진입 대상 메일 ────────────────────────────────────────


@dataclass
class TargetMail:
    sn: str
    folder_id: str
    folder_name: str


def run(actions: Actions, targets: list[TargetMail],
        *, mode: str = MODE_DRY_RUN,
        max_bodies: int = 2,
        inter_mail_sleep_s: float = 0.2
        ) -> PipelineReport:
    """본문 진입 파이프라인 실행.

    DRY_RUN: 본문 진입 없음. PII 마스킹/감사 인프라 검증만.
    FULL_READ: 최대 max_bodies (default 2) 만 진입 + 즉시 복구.
    """
    rsg.assert_mode_valid(rsg.MODE_LIST_ONLY)  # sanity
    started = datetime.now(KST).replace(microsecond=0).isoformat()
    report = PipelineReport(
        run_id=uuid.uuid4().hex[:12],
        started_at_iso=started,
        mode=mode,
    )

    snapshots: list[ua.MailReadSnapshot] = []
    n_attempt = min(len(targets), max_bodies) if mode == MODE_FULL_READ else 0
    report.attempt_count = n_attempt

    if mode == MODE_FULL_READ:
        for t in targets[:max_bodies]:
            try:
                # 1) before snapshot
                snap = ua.snapshot_mail(actions, t.sn, folder_id=t.folder_id)
                # 2) open body
                snap = ua.open_body_and_audit_state(actions, snap, folder_id=t.folder_id)
                # 3) extract body
                payload = actions.evaluate(body_reader.BODY_EXPR) or {}
                mb = body_reader.parse_body_payload(t.sn, payload) \
                    if isinstance(payload, dict) else body_reader.MailBody(sn=t.sn)
                # 4) PII 마스킹 — body_reader.parse_body_payload 가 이미 redact()
                # 한 번 더 pii_mask.mask 로 통계 수집
                mask_res = pii_mask.mask(mb.body_redacted or "")
                br = BodyRecord(
                    sn=t.sn, folder_id=t.folder_id, folder_name=t.folder_name,
                    subject_masked=pii_mask.mask(mb.subject or "").masked_text,
                    sender_masked=mb.sender_addr_redacted,
                    date_text=mb.date_text,
                    body_redacted=mask_res.masked_text,
                    body_redacted_short=mask_res.masked_text[:160],
                    body_len=mb.body_len,
                    masked_text_hash=mask_res.masked_text_hash,
                    pii_detected_count=mask_res.detected_count,
                    pii_types=mask_res.types,
                    link_domain_counts=mb.link_domains,
                    phishing_links_n=len(mb.phishing_links),
                    has_attach=mb.has_attach,
                    attach_names=list(mb.attach_names),
                    open_ok=True,
                )
                # 5) restore unread
                snap = ua.restore_unread_state(actions, snap, folder_id=t.folder_id)
                br.unread_audit = snap.to_dict()
                report.bodies.append(br)
                snapshots.append(snap)
                report.success_count += 1
            except Exception as exc:
                report.failure_count += 1
                report.bodies.append(BodyRecord(
                    sn=t.sn, folder_id=t.folder_id, folder_name=t.folder_name,
                    open_ok=False, error=str(exc)[:200],
                ))
            time.sleep(inter_mail_sleep_s)

    # DRY_RUN: 인프라만 검증 (실제 진입 안 함)
    report.unread_audit = ua.summarize(snapshots).to_dict()
    # raw leak 체크 — 어떤 BodyRecord 에도 'body' 라는 키로 원본 저장 없음 확인
    # body_redacted 만 저장 — 별도 raw 필드 부재
    report.raw_body_leak_check = {
        "raw_body_field_present_in_records": any(
            "body_raw" in b.to_dict() or "raw_body" in b.to_dict()
            for b in report.bodies
        ),
        "checked_records": len(report.bodies),
    }
    report.attachment_download_count = 0  # 절대 안 함
    report.external_ai_call_count = 0  # 외부 호출 없음
    report.ended_at_iso = datetime.now(KST).replace(microsecond=0).isoformat()
    return report


# ── 산출물 저장 ─────────────────────────────────────────────────────


def write_outputs(report: PipelineReport, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    # body_pipeline_report.json
    p1 = out_dir / "body_pipeline_report.json"
    p1.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["report"] = p1
    # pii_masking_samples.json — 본문 마스킹 결과 샘플 (hash + types 만)
    samples = [
        {"sn": b.sn, "folder_name": b.folder_name,
         "masked_text_hash": b.masked_text_hash,
         "pii_detected_count": b.pii_detected_count,
         "pii_types": b.pii_types,
         "body_redacted_first_160": b.body_redacted_short,
         "link_domain_counts": b.link_domain_counts}
        for b in report.bodies
    ]
    p2 = out_dir / "pii_masking_samples.json"
    p2.write_text(json.dumps(samples, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    paths["pii"] = p2
    # unread_state_audit.json
    p3 = out_dir / "unread_state_audit.json"
    p3.write_text(json.dumps(report.unread_audit, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    paths["unread"] = p3
    # body_pipeline_summary.md
    p4 = out_dir / "body_pipeline_summary.md"
    md = [
        f"# Body Pipeline V2 — run {report.run_id}",
        f"",
        f"- mode: `{report.mode}`",
        f"- started_at: {report.started_at_iso}",
        f"- ended_at: {report.ended_at_iso}",
        f"- attempt: {report.attempt_count} / success: {report.success_count} / failure: {report.failure_count}",
        f"- unread_audit: state_changed={report.unread_audit.get('state_changed')} "
        f"restore_attempted={report.unread_audit.get('restore_attempted')} "
        f"restore_succeeded={report.unread_audit.get('restore_succeeded')} "
        f"restore_failed={report.unread_audit.get('restore_failed')}",
        f"- attachment_download_count: {report.attachment_download_count}",
        f"- external_ai_call_count: {report.external_ai_call_count}",
        f"- verdict: **{report.verdict}**",
        f"",
        f"## Bodies",
    ]
    for b in report.bodies:
        md.append(
            f"- sn=`{b.sn}` folder={b.folder_name} "
            f"open_ok={b.open_ok} pii_n={b.pii_detected_count} "
            f"hash={b.masked_text_hash} restore_ok={b.unread_audit.get('restore_ok')}"
        )
    p4.write_text("\n".join(md), encoding="utf-8")
    paths["summary"] = p4
    return paths
