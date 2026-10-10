"""NAVER-MAIL-ACTION-ITEM-DASHBOARD-01 audit."""
from __future__ import annotations

from dataclasses import dataclass, field

from scripts.naver.mail import action_item_dashboard as aid


_REQUIRED_FIELDS = (
    "actionId", "sourceCategory", "priority", "status", "title_redacted",
    "sender_domain", "received_date", "reason", "recommended_action",
    "evidence_markers", "riskType", "dueDateCandidate",
    "pii_masked", "raw_body_saved",
)


@dataclass
class DashboardVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def judge_dashboard(dash: "aid.Dashboard",
                    summary: "aid.DashboardSummary",
                    *, md_text: str = "", json_text: str = "",
                    network_log: list[str] | None = None
                    ) -> DashboardVerdict:
    network_log = network_log or []
    metrics = summary.to_dict() if summary else {}

    # FAIL_SCHEMA_BROKEN
    for it in dash.items:
        d = it.to_dict()
        missing = [k for k in _REQUIRED_FIELDS if k not in d]
        if missing:
            return DashboardVerdict(False, "FAIL_SCHEMA_BROKEN",
                                    reasons=[f"missing:{missing}_in_sn={it.actionId}"],
                                    metrics=metrics)

    # FAIL_RAW_BODY_LEAK
    if summary and summary.raw_body_saved_any:
        return DashboardVerdict(False, "FAIL_RAW_BODY_LEAK",
                                reasons=["raw_body_saved_any=True"],
                                metrics=metrics)

    # FAIL_PII_UNMASKED — md/json 안에 미마스킹 PII 검출
    md_leaks = aid.find_leaks(md_text)
    json_leaks = aid.find_leaks(json_text)
    total_leak = (sum(len(v) for v in md_leaks.values())
                  + sum(len(v) for v in json_leaks.values()))
    if total_leak > 0:
        return DashboardVerdict(
            False, "FAIL_PII_UNMASKED",
            reasons=[f"md_leaks={md_leaks}", f"json_leaks={json_leaks}"],
            metrics={**metrics, "leak_total": total_leak},
        )

    # FAIL_EXTERNAL_AI_CALL_USED
    forbidden = ("api.anthropic.com", "api.openai.com", "claude.ai",
                 "generativelanguage.googleapis.com")
    ai_hits = [n for n in network_log if any(h in n for h in forbidden)]
    if ai_hits:
        return DashboardVerdict(False, "FAIL_EXTERNAL_AI_CALL_USED",
                                reasons=[f"ai_calls:{ai_hits[:3]}"],
                                metrics=metrics)

    # FAIL_ATTACHMENT_DOWNLOADED — dashboard 자체는 다운로드 안 함 (보고서 가공만)
    # — 별도 트래킹 필드 없음, 단지 외부 호출 검증

    # FAIL_HIGH_ACTION_MISSING — 3건 필수 존재
    hr = summary.high_required_present if summary else {}
    missing_high = [k for k, v in hr.items() if not v]
    if missing_high:
        return DashboardVerdict(False, "FAIL_HIGH_ACTION_MISSING",
                                reasons=[f"missing_high:{missing_high}"],
                                metrics=metrics)

    # WARN_DUE_DATE_INFERENCE_LOW_CONFIDENCE
    low_conf = [it for it in dash.items
                if it.dueDateCandidate and it.dueDateConfidence == "LOW"]
    if low_conf:
        return DashboardVerdict(
            False, "WARN_DUE_DATE_INFERENCE_LOW_CONFIDENCE",
            reasons=[f"low_conf_n={len(low_conf)}"],
            metrics=metrics,
        )

    # WARN_UNKNOWN_REVIEW_ITEMS_PRESENT — UNKNOWN review lane 존재
    if summary and summary.unknown_review_count > 0:
        return DashboardVerdict(
            False, "WARN_UNKNOWN_REVIEW_ITEMS_PRESENT",
            reasons=[f"unknown_review_count={summary.unknown_review_count}"],
            metrics=metrics,
        )

    return DashboardVerdict(True, "PASS_NAVER_MAIL_ACTION_ITEM_DASHBOARD",
                            reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse, json
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("dashboard_json", type=Path)
    ap.add_argument("summary_json", type=Path)
    ap.add_argument("--md", type=Path, default=None)
    args = ap.parse_args(argv)
    dd = json.loads(args.dashboard_json.read_text(encoding="utf-8"))
    sd = json.loads(args.summary_json.read_text(encoding="utf-8"))
    dash = aid.Dashboard(
        schema_version=dd.get("schema_version", ""),
        generated_at=dd.get("generated_at", ""),
        input_report_hash=dd.get("input_report_hash", ""),
    )
    for it in dd.get("items", []):
        dash.items.append(aid.DashboardItem(**it))
    summary = aid.DashboardSummary(**sd)
    md = args.md.read_text(encoding="utf-8") if args.md and args.md.exists() else ""
    jt = args.dashboard_json.read_text(encoding="utf-8")
    v = judge_dashboard(dash, summary, md_text=md, json_text=jt)
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
