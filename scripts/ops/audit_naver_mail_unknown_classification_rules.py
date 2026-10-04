"""NAVER-MAIL-UNKNOWN-CLASSIFICATION-RULES-01 audit."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scripts.naver.mail import unknown_classification_rules as ur

_FORBIDDEN = ("api.anthropic.com", "api.openai.com", "claude.ai", "generativelanguage.googleapis.com")

_RAW_EMAIL_RE = re.compile(r"\b[A-Za-z0-9_.+\-]{3,}@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_RAW_PHONE_RE = re.compile(r"\b01[016789]-\d{3,4}-\d{4}\b")


@dataclass
class RulesVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _find_leaks(text: str) -> int:
    return len(_RAW_EMAIL_RE.findall(text or "")) + len(_RAW_PHONE_RE.findall(text or ""))


def _rules_leak_gates(raw_body_saved, md_text, json_text, network_log, attachment_download_count, metrics):
    # FAIL_RAW_BODY_LEAK
    if raw_body_saved:
        return RulesVerdict(False, "FAIL_RAW_BODY_LEAK", reasons=["raw_body_saved=True"], metrics=metrics)

    # FAIL_PII_UNMASKED
    leak_n = _find_leaks(md_text) + _find_leaks(json_text)
    if leak_n > 0:
        return RulesVerdict(False, "FAIL_PII_UNMASKED", reasons=[f"unmasked_pii_n={leak_n}"], metrics=metrics)

    # FAIL_EXTERNAL_AI_CALL_USED
    ai_hits = [n for n in network_log if any(h in n for h in _FORBIDDEN)]
    if ai_hits:
        return RulesVerdict(False, "FAIL_EXTERNAL_AI_CALL_USED", reasons=[f"ai_calls:{ai_hits[:3]}"], metrics=metrics)

    if attachment_download_count > 0:
        return RulesVerdict(
            False, "FAIL_ATTACHMENT_DOWNLOADED", reasons=[f"n={attachment_download_count}"], metrics=metrics
        )
    return None


def _rules_decision_gates(report, metrics):
    # FAIL_OVERCLASSIFIED_LOW_CONFIDENCE
    # LOW confidence 인데 promoted 된 결정이 있으면 정책 위반
    bad = [d for d in report.decisions if d.confidence == ur.CONF_LOW and d.promoted]
    if bad:
        return RulesVerdict(
            False,
            "FAIL_OVERCLASSIFIED_LOW_CONFIDENCE",
            reasons=[f"low_conf_promoted={len(bad)}"],
            metrics=metrics,
        )

    # FAIL_SCHEMA_BROKEN
    for d in report.decisions:
        dd = d.to_dict()
        for k in (
            "actionId",
            "original_category",
            "promoted_category",
            "confidence",
            "evidence_markers",
            "promoted",
            "kept_unknown",
        ):
            if k not in dd:
                return RulesVerdict(False, "FAIL_SCHEMA_BROKEN", reasons=[f"missing:{k}"], metrics=metrics)
    return None


def judge_rules(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수/CLI 인자 보존)
    report: ur.ReclassifyReport,
    *,
    actions_before: list[dict] | None = None,
    actions_after: list[dict] | None = None,
    md_text: str = "",
    json_text: str = "",
    network_log: list[str] | None = None,
    raw_body_saved: bool = False,
    attachment_download_count: int = 0,
) -> RulesVerdict:
    network_log = network_log or []
    metrics = {
        "previous_unknown": report.previous_unknown_count,
        "resolved": report.resolved_unknown_count,
        "new_unknown": report.new_unknown_count,
        "low_kept": report.low_confidence_kept_unknown,
        "promoted_by_category": report.promoted_by_category,
    }

    _early = _rules_leak_gates(raw_body_saved, md_text, json_text, network_log, attachment_download_count, metrics)
    if _early is not None:
        return _early

    # FAIL_HIGH_ACTION_CHANGED
    if actions_before is not None and actions_after is not None:
        preserved = ur.assert_high_preserved(actions_before, actions_after)
        missing = [k for k, v in preserved.items() if not v]
        metrics["high_preserved"] = preserved
        if missing:
            return RulesVerdict(
                False, "FAIL_HIGH_ACTION_CHANGED", reasons=[f"missing_or_changed:{missing}"], metrics=metrics
            )

    _early = _rules_decision_gates(report, metrics)
    if _early is not None:
        return _early

    # WARN_UNKNOWN_ITEMS_REMAIN
    if report.new_unknown_count > 0:
        # WARN_LOW_CONFIDENCE_ITEMS_KEPT 가 더 구체적이면 우선
        if report.low_confidence_kept_unknown > 0:
            return RulesVerdict(
                False,
                "WARN_LOW_CONFIDENCE_ITEMS_KEPT",
                reasons=[f"low_kept={report.low_confidence_kept_unknown} new_unknown={report.new_unknown_count}"],
                metrics=metrics,
            )
        return RulesVerdict(
            False, "WARN_UNKNOWN_ITEMS_REMAIN", reasons=[f"new_unknown={report.new_unknown_count}"], metrics=metrics
        )

    return RulesVerdict(True, "PASS_NAVER_MAIL_UNKNOWN_CLASSIFICATION_RULES", reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser()
    ap.add_argument("report_json", type=Path)
    args = ap.parse_args(argv)
    d = json.loads(args.report_json.read_text(encoding="utf-8"))
    rep = ur.ReclassifyReport(
        previous_unknown_count=d.get("previous_unknown_count", 0),
        new_unknown_count=d.get("new_unknown_count", 0),
        resolved_unknown_count=d.get("resolved_unknown_count", 0),
        unresolved_unknown_count=d.get("unresolved_unknown_count", 0),
        promoted_by_category=d.get("promoted_by_category", {}),
        low_confidence_kept_unknown=d.get("low_confidence_kept_unknown", 0),
    )
    for dec_d in d.get("decisions", []):
        rep.decisions.append(ur.ReclassifyDecision(**dec_d))
    v = judge_rules(rep)
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
