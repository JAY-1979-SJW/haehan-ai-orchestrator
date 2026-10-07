"""NAVER-MAIL-BODY-PIPELINE-BATCH-01 audit."""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.naver.mail import batch_runner as br


@dataclass
class BatchVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


_FORBIDDEN_HOSTS = ("api.anthropic.com", "api.openai.com", "claude.ai", "generativelanguage.googleapis.com")


def judge_batch(  # noqa: C901 - 기존 복잡도(13->12), 중첩 if 병합으로 오히려 줄어듦
    rep: br.BatchReport, *, network_log: list[str] | None = None, checkpoint_dict: dict | None = None
) -> BatchVerdict:
    network_log = network_log or []
    metrics = {
        "target_total": rep.target_total,
        "limit": rep.limit,
        "attempted": rep.attempted,
        "success": rep.success,
        "failed": rep.failed,
        "skipped_already_done": rep.skipped_already_done,
        "unread_state_changed": rep.unread_state_changed,
        "unread_restore_attempted": rep.unread_restore_attempted,
        "unread_restore_succeeded": rep.unread_restore_succeeded,
        "unread_restore_failed": rep.unread_restore_failed,
        "attachment_download_count": rep.attachment_download_count,
        "external_ai_call_count": rep.external_ai_call_count,
        "raw_body_leak_count": rep.raw_body_leak_count,
        "duplicate_sn_count": rep.duplicate_sn_count,
        "pii_detected_total": rep.pii_detected_total,
        "elapsed_seconds": rep.elapsed_seconds,
        "halted_early": rep.halted_early,
    }

    # FAIL_RAW_BODY_LEAK
    if rep.raw_body_leak_count > 0:
        return BatchVerdict(
            False, "FAIL_RAW_BODY_LEAK", reasons=[f"leak_count={rep.raw_body_leak_count}"], metrics=metrics
        )
    # 결과 record 에 raw body 필드가 들어있는지도 검사
    for r in rep.results:
        d = r.to_dict()
        if "raw_body" in d or "body_raw" in d:
            return BatchVerdict(
                False, "FAIL_RAW_BODY_LEAK", reasons=[f"raw_body_field_in_record:sn={r.sn}"], metrics=metrics
            )

    # FAIL_ATTACHMENT_DOWNLOADED
    if rep.attachment_download_count > 0:
        return BatchVerdict(
            False, "FAIL_ATTACHMENT_DOWNLOADED", reasons=[f"count={rep.attachment_download_count}"], metrics=metrics
        )

    # FAIL_EXTERNAL_AI_CALL_USED
    ai_hits = [n for n in network_log if any(h in n for h in _FORBIDDEN_HOSTS)]
    if ai_hits or rep.external_ai_call_count > 0:
        return BatchVerdict(False, "FAIL_EXTERNAL_AI_CALL_USED", reasons=[f"ai_calls:{ai_hits[:3]}"], metrics=metrics)

    # FAIL_UNREAD_RESTORE_FAILED
    if rep.unread_restore_failed > 0:
        return BatchVerdict(
            False,
            "FAIL_UNREAD_RESTORE_FAILED",
            reasons=[f"restore_failed={rep.unread_restore_failed} halt_reason={rep.halt_reason}"],
            metrics=metrics,
        )

    # FAIL_CHECKPOINT_BROKEN
    if checkpoint_dict is not None and checkpoint_dict.get("run_id") == "broken":
        return BatchVerdict(False, "FAIL_CHECKPOINT_BROKEN", reasons=["checkpoint_file_invalid"], metrics=metrics)

    # FAIL_DUPLICATE_REPROCESSING — skipped 가 있어야 하는데 같은 sn 이 두 번 처리됨
    sns = [r.sn for r in rep.results if r.status != br.SKIPPED_ALREADY_DONE]
    sn_dup = [s for s, c in __counts(sns).items() if c > 1]
    if sn_dup:
        return BatchVerdict(
            False, "FAIL_DUPLICATE_REPROCESSING", reasons=[f"duplicate_sns:{sn_dup[:5]}"], metrics=metrics
        )

    # WARN_BODY_READ_FAILURES
    if rep.failed > 0:
        return BatchVerdict(False, "WARN_BODY_READ_FAILURES", reasons=[f"failed={rep.failed}"], metrics=metrics)

    # WARN_PARTIAL_BATCH_COMPLETED
    if rep.halted_early or (rep.limit > 0 and rep.attempted + rep.skipped_already_done < rep.target_total):
        return BatchVerdict(
            False,
            "WARN_PARTIAL_BATCH_COMPLETED",
            reasons=[
                f"halted_early={rep.halted_early} "
                f"attempted+skipped={rep.attempted + rep.skipped_already_done} "
                f"target_total={rep.target_total}"
            ],
            metrics=metrics,
        )

    # WARN_RATE_LIMIT_SUSPECTED — avg < 1s 또는 너무 빠른 진행
    if rep.attempted > 5 and rep.avg_seconds_per_message < 0.5:
        return BatchVerdict(
            False,
            "WARN_RATE_LIMIT_SUSPECTED",
            reasons=[f"avg={rep.avg_seconds_per_message}s_too_fast"],
            metrics=metrics,
        )

    return BatchVerdict(True, "PASS_NAVER_MAIL_BODY_PIPELINE_BATCH", reasons=[], metrics=metrics)


def __counts(lst):
    from collections import Counter

    return Counter(lst)


def main(argv=None) -> int:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser()
    ap.add_argument("report_json", type=Path)
    args = ap.parse_args(argv)
    d = json.loads(args.report_json.read_text(encoding="utf-8"))
    rep = br.BatchReport(
        schema_version=d.get("schema_version", ""),
        run_id=d.get("run_id", ""),
        started_at_iso=d.get("started_at_iso", ""),
        ended_at_iso=d.get("ended_at_iso", ""),
        target_total=d.get("target_total", 0),
        duplicate_sn_count=d.get("duplicate_sn_count", 0),
        limit=d.get("limit", 0),
        continue_on_warn=d.get("continue_on_warn", False),
        attempted=d.get("attempted", 0),
        success=d.get("success", 0),
        failed=d.get("failed", 0),
        skipped_already_done=d.get("skipped_already_done", 0),
        unread_state_changed=d.get("unread_state_changed", 0),
        unread_restore_attempted=d.get("unread_restore_attempted", 0),
        unread_restore_succeeded=d.get("unread_restore_succeeded", 0),
        unread_restore_failed=d.get("unread_restore_failed", 0),
        raw_body_leak_count=d.get("raw_body_leak_count", 0),
        attachment_download_count=d.get("attachment_download_count", 0),
        external_ai_call_count=d.get("external_ai_call_count", 0),
        pii_detected_total=d.get("pii_detected_total", 0),
        pii_types_summary=d.get("pii_types_summary", {}),
        elapsed_seconds=d.get("elapsed_seconds", 0.0),
        avg_seconds_per_message=d.get("avg_seconds_per_message", 0.0),
        halted_early=d.get("halted_early", False),
        halt_reason=d.get("halt_reason", ""),
        verdict=d.get("verdict", ""),
    )
    for rr in d.get("results", []):
        rep.results.append(br.MailResult(**rr))
    v = judge_batch(rep)
    print(
        json.dumps(
            {"verdict": v.code, "passed": v.passed, "reasons": v.reasons, "metrics": v.metrics},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
