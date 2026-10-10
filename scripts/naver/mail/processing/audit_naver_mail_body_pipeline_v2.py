"""NAVER-MAIL-BODY-PIPELINE-V2-01 audit."""
from __future__ import annotations

from dataclasses import dataclass, field

from scripts.naver.mail import body_pipeline_v2 as bp


# 외부 AI 호출 흔적 패턴
_FORBIDDEN_PATTERNS = (
    "api.anthropic.com", "api.openai.com", "claude.ai",
    "generativelanguage.googleapis.com",
)


@dataclass
class BodyVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def judge(report: "bp.PipelineReport",
          *, network_log: list[str] | None = None
          ) -> BodyVerdict:
    network_log = network_log or []
    metrics = {
        "attempt": report.attempt_count,
        "success": report.success_count,
        "failure": report.failure_count,
        "attachment_download_count": report.attachment_download_count,
        "external_ai_call_count": report.external_ai_call_count,
        "unread_state_changed": report.unread_audit.get("state_changed", 0),
        "unread_restore_attempted": report.unread_audit.get("restore_attempted", 0),
        "unread_restore_succeeded": report.unread_audit.get("restore_succeeded", 0),
        "unread_restore_failed": report.unread_audit.get("restore_failed", 0),
        "mode": report.mode,
    }

    # FAIL_RAW_BODY_LEAK — BodyRecord 에 'raw' 본문 필드가 있으면 즉시 FAIL
    leak = report.raw_body_leak_check.get("raw_body_field_present_in_records", False)
    if leak:
        return BodyVerdict(False, "FAIL_RAW_BODY_LEAK",
                           reasons=["raw_body_field_detected_in_records"],
                           metrics=metrics)

    # FAIL_ATTACHMENT_DOWNLOADED
    if report.attachment_download_count > 0:
        return BodyVerdict(False, "FAIL_ATTACHMENT_DOWNLOADED",
                           reasons=[f"attachment_download_count={report.attachment_download_count}"],
                           metrics=metrics)

    # FAIL_EXTERNAL_AI_CALL_USED — network_log 에 forbidden host
    ai_hits = [n for n in network_log
               if any(h in n for h in _FORBIDDEN_PATTERNS)]
    if ai_hits or report.external_ai_call_count > 0:
        return BodyVerdict(False, "FAIL_EXTERNAL_AI_CALL_USED",
                           reasons=[f"external_ai_calls:{ai_hits[:3]}"],
                           metrics=metrics)

    # PII masking 무결성 — 모든 BodyRecord 에 masked_text_hash 존재 + body_redacted 가 raw 아님
    pii_broken = []
    for b in report.bodies:
        if b.open_ok and b.body_len > 0 and not b.masked_text_hash:
            pii_broken.append(b.sn)
    if pii_broken:
        return BodyVerdict(False, "FAIL_PII_MASKING_BROKEN",
                           reasons=[f"masked_hash_missing_for_sn:{pii_broken[:3]}"],
                           metrics=metrics)

    # FAIL_SIDE_EFFECT_OCCURRED — state changed 그리고 restore 실패
    if (report.unread_audit.get("restore_failed", 0) > 0
            or (report.unread_audit.get("state_changed", 0) >
                report.unread_audit.get("restore_succeeded", 0))):
        # 상태 변경 발생하고 복구 미완료 — WARN 또는 FAIL
        return BodyVerdict(False, "WARN_UNREAD_RESTORE_UNVERIFIED",
                           reasons=[f"state_changed={report.unread_audit.get('state_changed')} "
                                    f"restored={report.unread_audit.get('restore_succeeded')}"],
                           metrics=metrics)

    # WARN_PARTIAL_BODY_READ
    if report.attempt_count > 0 and report.failure_count > 0:
        return BodyVerdict(False, "WARN_PARTIAL_BODY_READ",
                           reasons=[f"failures={report.failure_count}"],
                           metrics=metrics)

    return BodyVerdict(True, "PASS_NAVER_MAIL_BODY_PIPELINE_V2",
                       reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse, json
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("report_json", type=Path)
    args = ap.parse_args(argv)
    d = json.loads(args.report_json.read_text(encoding="utf-8"))
    r = bp.PipelineReport(
        schema_version=d.get("schema_version", ""),
        run_id=d.get("run_id", ""),
        started_at_iso=d.get("started_at_iso", ""),
        ended_at_iso=d.get("ended_at_iso", ""),
        mode=d.get("mode", ""),
        target_folders=d.get("target_folders", []),
        unread_audit=d.get("unread_audit", {}),
        attempt_count=d.get("attempt_count", 0),
        success_count=d.get("success_count", 0),
        failure_count=d.get("failure_count", 0),
        raw_body_leak_check=d.get("raw_body_leak_check", {}),
        attachment_download_count=d.get("attachment_download_count", 0),
        external_ai_call_count=d.get("external_ai_call_count", 0),
        warnings=d.get("warnings", []),
        verdict=d.get("verdict", ""),
    )
    for bd in d.get("bodies", []):
        r.bodies.append(bp.BodyRecord(**bd))
    v = judge(r)
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
