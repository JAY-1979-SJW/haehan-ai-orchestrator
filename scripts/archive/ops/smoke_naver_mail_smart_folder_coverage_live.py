"""NAVER-MAIL-SMART-FOLDER-COVERAGE-01 — 라이브 smoke.

받은편지함 + 스마트메일함 전수 unread 수집 1회 실행.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.naver.mail import smart_folder_collector as sfc
from scripts.naver.mail.read import cdp
from scripts.naver.mail.collection import audit_naver_mail_smart_folder_coverage as audit


class LiveActions:
    def __init__(self, target_id: str):
        self.target_id = target_id

    def evaluate(self, expr: str):
        return cdp.evaluate(self.target_id, expr, timeout=10.0)

    def navigate(self, url: str):
        cdp.navigate(self.target_id, url)

    def wait_dom(self, expr_truthy: str, timeout_s: float = 8.0):
        return cdp.wait_dom(self.target_id, expr_truthy, timeout=timeout_s)


def main():
    out_dir = Path("data/inspection/naver_mail_smart_folder_coverage")
    out_dir.mkdir(parents=True, exist_ok=True)
    folder_dir = out_dir / "folder_results"
    folder_dir.mkdir(exist_ok=True)

    target_id = cdp.ensure_about_blank_target()
    print(f"[boot] target_id={target_id[:12]}")

    actions = LiveActions(target_id)
    t0 = time.time()
    report = sfc.collect_all(actions, max_pages=200,
                             max_items_per_folder=5000)
    elapsed = round(time.time() - t0, 1)

    rd = sfc.report_to_dict(report)
    rd["elapsed_s"] = elapsed

    # audit
    v = audit.judge_coverage(report)
    rd["verdict"] = v.code
    rd["audit"] = {"verdict": v.code, "passed": v.passed,
                   "reasons": v.reasons, "metrics": v.metrics}

    # save
    (out_dir / "smart_folder_coverage_report.json").write_text(
        json.dumps(rd, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "audit_result.json").write_text(
        json.dumps(rd["audit"], ensure_ascii=False, indent=2), encoding="utf-8")

    for fc_d in rd["folders"]:
        fname = (fc_d["folder_name"] or fc_d["folder_id"] or "unknown").replace("/", "_")
        (folder_dir / f"folder_{fc_d['folder_id']}_{fname}.json").write_text(
            json.dumps(fc_d, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== FOLDERS ===")
    for fc_d in rd["folders"]:
        print(f"  {fc_d['folder_name']:>12} id={fc_d['folder_id']:>3} "
              f"ui={fc_d['ui_unread_count']:>3} collected={fc_d['collected_total']:>3} "
              f"unread={fc_d['collected_unread']:>3} pages={len(fc_d['pages_visited'])} "
              f"strategy={fc_d['pagination_strategy_used']} "
              f"evidence={fc_d['last_page_evidence']}")

    print("\n=== TOTALS ===")
    print(f"  folder_collected_total = {rd['folder_collected_total']}")
    print(f"  unique_sn_total = {rd['unique_sn_total']}")
    print(f"  duplicate_across_folders_n = {len(rd['duplicate_across_folders'])}")
    print(f"  ui_count_snapshot_before.by_folder_sum = "
          f"{rd['ui_count_snapshot_before'].get('by_folder_sum')}")
    print(f"  ui_count_snapshot_after.by_folder_sum = "
          f"{rd['ui_count_snapshot_after'].get('by_folder_sum')}")
    print(f"  warnings = {rd['warnings']}")

    print("\n=== AUDIT ===")
    print(json.dumps(rd["audit"], ensure_ascii=False, indent=2))
    print(f"\nelapsed: {elapsed}s")


if __name__ == "__main__":
    main()
