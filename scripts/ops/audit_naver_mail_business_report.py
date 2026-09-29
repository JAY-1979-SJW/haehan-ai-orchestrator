"""NAVER-MAIL-CONSOLIDATED-BUSINESS-REPORT-CLOSEOUT-01 audit."""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.naver.mail import business_report as br


@dataclass
class ReportVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


_REQUIRED_TOP = (
    "schema_version",
    "run_id",
    "generated_at_iso",
    "total_mails",
    "folder_distribution",
    "sender_domain_top",
    "categories",
    "action_items",
    "pii_detected_total",
    "raw_body_saved",
    "attachment_download_count",
    "external_ai_call_count",
    "unread_restore_summary",
    "leak_self_check",
)


def _check_schema(rep: br.BusinessReport, metrics: dict) -> ReportVerdict | None:
    d = rep.to_dict()
    missing = [k for k in _REQUIRED_TOP if k not in d]
    if missing:
        return ReportVerdict(False, "FAIL_REPORT_SCHEMA_BROKEN", reasons=[f"missing:{missing}"], metrics=metrics)
    return None


def _check_raw_body_leak(rep: br.BusinessReport, metrics: dict) -> ReportVerdict | None:
    if rep.raw_body_saved is True:
        return ReportVerdict(False, "FAIL_RAW_BODY_LEAK", reasons=["raw_body_saved=True"], metrics=metrics)
    return None


def _check_pii_unmasked(metrics: dict) -> ReportVerdict | None:
    # md/json 에 미마스킹 PII 검출
    leak_n = metrics["leak_total"]
    if leak_n > 0:
        return ReportVerdict(False, "FAIL_PII_UNMASKED", reasons=[f"unmasked_pii_n={leak_n}"], metrics=metrics)
    return None


def _check_attachment_downloaded(rep: br.BusinessReport, metrics: dict) -> ReportVerdict | None:
    if rep.attachment_download_count > 0:
        return ReportVerdict(
            False, "FAIL_ATTACHMENT_DOWNLOADED", reasons=[f"n={rep.attachment_download_count}"], metrics=metrics
        )
    return None


def _check_external_ai_call(
    rep: br.BusinessReport, network_log: list[str] | None, metrics: dict
) -> ReportVerdict | None:
    network_log = network_log or []
    forbidden = ("api.anthropic.com", "api.openai.com", "claude.ai", "generativelanguage.googleapis.com")
    ai_hits = [n for n in network_log if any(h in n for h in forbidden)]
    if ai_hits or rep.external_ai_call_count > 0:
        return ReportVerdict(False, "FAIL_EXTERNAL_AI_CALL_USED", reasons=[f"ai_calls:{ai_hits[:3]}"], metrics=metrics)
    return None


def _check_unread_restore_regression(
    rep: br.BusinessReport, prior_unread_restore: dict | None, metrics: dict
) -> ReportVerdict | None:
    # prior summary 와 불일치
    if prior_unread_restore and rep.unread_restore_summary:
        for k in ("restore_attempted", "restore_succeeded", "restore_failed", "state_changed"):
            pv = prior_unread_restore.get(k)
            cv = rep.unread_restore_summary.get(k)
            if pv is not None and cv is not None and pv != cv:
                return ReportVerdict(
                    False, "FAIL_UNREAD_RESTORE_REGRESSION", reasons=[f"{k}_prior={pv}_current={cv}"], metrics=metrics
                )
    return None


def _check_low_confidence_classification(rep: br.BusinessReport, metrics: dict) -> ReportVerdict | None:
    # UNKNOWN_REVIEW_REQUIRED 비율 너무 큼
    unknown_ratio = metrics["unknown_review_required"] / max(rep.total_mails, 1)
    if unknown_ratio > 0.4:  # 40% 초과
        return ReportVerdict(
            False, "WARN_LOW_CONFIDENCE_CLASSIFICATION", reasons=[f"unknown_ratio={unknown_ratio:.2f}"], metrics=metrics
        )
    return None


def _check_unknown_review_required(metrics: dict) -> ReportVerdict | None:
    # 1건이라도 있으면 WARN (단 ratio 작으면)
    if metrics["unknown_review_required"] > 0:
        return ReportVerdict(
            False,
            "WARN_UNKNOWN_REVIEW_REQUIRED",
            reasons=[f"unknown_n={metrics['unknown_review_required']}"],
            metrics=metrics,
        )
    return None


def judge_report(
    rep: br.BusinessReport,
    *,
    md_text: str = "",
    json_text: str = "",
    prior_unread_restore: dict | None = None,
    network_log: list[str] | None = None,
) -> ReportVerdict:
    # 2026-09-29 STD-08(복잡도) 리팩터: 각 FAIL/WARN 게이트를 _check_*(...) -> Verdict|None
    # 함수로 분리 — 첫 실패에서 즉시 반환하는 원본 의미론 그대로(#64/#65 와 동일 패턴).
    metrics = {
        "total_mails": rep.total_mails,
        "action_items": len(rep.action_items),
        "categories_n": len(rep.categories),
        "unknown_review_required": next(
            (cg.count for cg in rep.categories if cg.category == br.CAT_UNKNOWN_REVIEW_REQUIRED), 0
        ),
        "attachment_download_count": rep.attachment_download_count,
        "external_ai_call_count": rep.external_ai_call_count,
        "raw_body_saved": rep.raw_body_saved,
        "leak_total": (rep.leak_self_check or {}).get("total_leak_count", 0),
    }

    result = _check_schema(rep, metrics)
    if result:
        return result
    result = _check_raw_body_leak(rep, metrics)
    if result:
        return result
    result = _check_pii_unmasked(metrics)
    if result:
        return result
    result = _check_attachment_downloaded(rep, metrics)
    if result:
        return result
    result = _check_external_ai_call(rep, network_log, metrics)
    if result:
        return result
    result = _check_unread_restore_regression(rep, prior_unread_restore, metrics)
    if result:
        return result
    result = _check_low_confidence_classification(rep, metrics)
    if result:
        return result
    result = _check_unknown_review_required(metrics)
    if result:
        return result

    return ReportVerdict(True, "PASS_NAVER_MAIL_BUSINESS_REPORT", reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser()
    ap.add_argument("report_json", type=Path)
    ap.add_argument("--md", type=Path, default=None)
    args = ap.parse_args(argv)
    d = json.loads(args.report_json.read_text(encoding="utf-8"))
    rep = br.BusinessReport(
        schema_version=d.get("schema_version", ""),
        run_id=d.get("run_id", ""),
        generated_at_iso=d.get("generated_at_iso", ""),
        total_mails=d.get("total_mails", 0),
        folder_distribution=d.get("folder_distribution", {}),
        sender_domain_top=[tuple(x) for x in d.get("sender_domain_top", [])],
        pii_detected_total=d.get("pii_detected_total", 0),
        pii_types_summary=d.get("pii_types_summary", {}),
        raw_body_saved=d.get("raw_body_saved", False),
        attachment_download_count=d.get("attachment_download_count", 0),
        external_ai_call_count=d.get("external_ai_call_count", 0),
        unread_restore_summary=d.get("unread_restore_summary", {}),
        leak_self_check=d.get("leak_self_check", {}),
    )
    for cg_d in d.get("categories", []):
        rep.categories.append(br.CategoryGroup(**cg_d))
    for a_d in d.get("action_items", []):
        rep.action_items.append(br.ActionItem(**a_d))
    md_text = args.md.read_text(encoding="utf-8") if args.md and args.md.exists() else ""
    json_text = args.report_json.read_text(encoding="utf-8")
    v = judge_report(rep, md_text=md_text, json_text=json_text)
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
