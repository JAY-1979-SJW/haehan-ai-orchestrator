"""기존 action_items.json 에 unknown_classification_rules 적용 후
dashboard 재생성 + audit + 회귀 비교.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.naver.mail import (
    action_item_dashboard as aid,
)
from scripts.naver.mail import (
    unknown_classification_rules as ur,
)
from scripts.naver.mail.analysis import (
    audit_naver_mail_action_item_dashboard as audit_dash,
)
from scripts.naver.mail.analysis import (
    audit_naver_mail_unknown_classification_rules as audit_rules,
)


def main():
    src = Path("data/inspection/naver_mail_inbox_consolidated_report/action_items.json")
    out_dir = Path("data/inspection/naver_mail_unknown_classification_rules")
    out_dir.mkdir(parents=True, exist_ok=True)

    actions = json.loads(src.read_text(encoding="utf-8"))
    print(f"[input] action_items: {len(actions)}건")

    # 1) UNKNOWN 재분류
    rep = ur.reclassify(actions)
    print(
        f"[1] previous_unknown={rep.previous_unknown_count} "
        f"resolved={rep.resolved_unknown_count} "
        f"new_unknown={rep.new_unknown_count}"
    )
    print(f"    promoted_by_category={rep.promoted_by_category}")

    # 2) actions 에 승격 적용
    actions_after = ur.apply_promotions(actions, rep)

    # 3) HIGH 보존 검증
    preserved = ur.assert_high_preserved(actions, actions_after)
    print(f"[2] high_preserved={preserved}")

    # 4) dashboard 재생성
    dash = aid.build_dashboard(actions_after, input_report_text=src.read_text(encoding="utf-8"))
    summary = aid.build_summary(dash)
    dash_paths = aid.write_outputs(dash, summary, out_dir)
    print(f"[3] dashboard saved: {dash_paths['dashboard']}")

    # 5) unknown classification 보고서 저장
    ur_json = out_dir / "unknown_classification_report.json"
    ur_json.write_text(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    ur_md = out_dir / "unknown_classification_report.md"
    ur_md.write_text(ur.render_unknown_classification_markdown(rep), encoding="utf-8")

    # 6) audit (rules) — md/json leak 검증
    rules_md = ur_md.read_text(encoding="utf-8")
    rules_js = ur_json.read_text(encoding="utf-8")
    v_rules = audit_rules.judge_rules(
        rep,
        actions_before=actions,
        actions_after=actions_after,
        md_text=rules_md,
        json_text=rules_js,
    )
    (out_dir / "audit_unknown_rules.json").write_text(
        json.dumps(
            {"verdict": v_rules.code, "passed": v_rules.passed, "reasons": v_rules.reasons, "metrics": v_rules.metrics},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # 7) audit (dashboard) — 재생성된 dashboard 도 audit
    dash_md = dash_paths["md"].read_text(encoding="utf-8")
    dash_js = dash_paths["dashboard"].read_text(encoding="utf-8")
    v_dash = audit_dash.judge_dashboard(dash, summary, md_text=dash_md, json_text=dash_js)
    (out_dir / "audit_dashboard_after.json").write_text(
        json.dumps(
            {"verdict": v_dash.code, "passed": v_dash.passed, "reasons": v_dash.reasons, "metrics": v_dash.metrics},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== AUDIT (rules) ===")
    print(
        json.dumps(
            {"verdict": v_rules.code, "passed": v_rules.passed, "reasons": v_rules.reasons, "metrics": v_rules.metrics},
            ensure_ascii=False,
            indent=2,
        )
    )
    print("\n=== AUDIT (dashboard after) ===")
    print(
        json.dumps(
            {
                "verdict": v_dash.code,
                "passed": v_dash.passed,
                "reasons": v_dash.reasons,
                "metrics": {
                    k: v_dash.metrics.get(k)
                    for k in (
                        "total_items",
                        "high_count",
                        "medium_count",
                        "low_count",
                        "unknown_review_count",
                        "category_counts",
                        "risk_type_counts",
                        "pii_masked_all",
                        "raw_body_saved_any",
                        "high_required_present",
                    )
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
