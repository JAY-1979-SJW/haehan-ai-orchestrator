"""실제 action_items.json → action_dashboard 산출 + audit.

입력:
  data/inspection/naver_mail_inbox_consolidated_report/action_items.json
출력:
  data/inspection/naver_mail_action_item_dashboard/
    action_dashboard.json / .md / summary.json / audit.json
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.naver.mail import action_item_dashboard as aid
from scripts.naver.mail.analysis import audit_naver_mail_action_item_dashboard as audit


def main():
    src = Path("data/inspection/naver_mail_inbox_consolidated_report/action_items.json")
    out_dir = Path("data/inspection/naver_mail_action_item_dashboard")
    actions = aid.load_action_items(src)
    print(f"[input] {src}: {len(actions)}건 action_items")

    # input hash 용 원본 텍스트
    src_text = src.read_text(encoding="utf-8")

    dash = aid.build_dashboard(actions, input_report_text=src_text)
    summary = aid.build_summary(dash)
    paths = aid.write_outputs(dash, summary, out_dir)
    print(f"[out] {paths['dashboard']}")
    print(f"[out] {paths['summary']}")
    print(f"[out] {paths['md']}")

    md = paths["md"].read_text(encoding="utf-8")
    js = paths["dashboard"].read_text(encoding="utf-8")
    v = audit.judge_dashboard(dash, summary, md_text=md, json_text=js)
    (out_dir / "audit_result.json").write_text(
        json.dumps(
            {"verdict": v.code, "passed": v.passed, "reasons": v.reasons, "metrics": v.metrics},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n=== AUDIT ===\nverdict: {v.code}  passed: {v.passed}")
    if v.reasons:
        print(f"reasons: {v.reasons}")
    print("\n=== SUMMARY ===")
    print(f"total: {summary.total_items}")
    print(f"HIGH/MEDIUM/LOW: {summary.high_count}/{summary.medium_count}/{summary.low_count}")
    print(f"unknown_review: {summary.unknown_review_count}")
    print(f"due_date_candidates: {summary.due_date_candidate_count}")
    print(f"risk_type_counts: {summary.risk_type_counts}")
    print(f"high_required_present: {summary.high_required_present}")


if __name__ == "__main__":
    main()
