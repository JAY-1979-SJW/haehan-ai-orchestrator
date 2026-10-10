"""NAVER-MAIL-INBOX-P0-COMPLETE-01 — 실제 네이버 메일 smoke.

destructive action 없이 LIST_ONLY 와 UNREAD_ONLY 두 번 실행.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.naver.mail import inbox_collector as ic
from scripts.naver.mail import read_state_guard as rsg
from scripts.naver.mail.read import cdp
from scripts.naver.mail.collection import audit_naver_mail_inbox_p0_complete as audit


class LiveActions:
    def __init__(self, target_id: str):
        self.target_id = target_id

    def evaluate(self, expr: str):
        return cdp.evaluate(self.target_id, expr, timeout=8.0)

    def click(self, sel: str):
        return cdp.evaluate(self.target_id, sel, timeout=4.0)

    def navigate(self, url: str):
        cdp.navigate(self.target_id, url)

    def wait_dom(self, expr_truthy: str, timeout_s: float = 8.0):
        return cdp.wait_dom(self.target_id, expr_truthy, timeout=timeout_s)


def run_mode(target_id: str, mode: str, out_dir: Path,
             max_pages: int = 200, max_items: int = 5000) -> dict:
    actions = LiveActions(target_id)
    # 안전: 매번 받은편지함 처음 페이지로 진입
    actions.navigate("https://mail.naver.com/v2/folders/0/all")
    time.sleep(3.5)
    actions.wait_dom("document.querySelector('li.mail_item')", timeout_s=20.0)
    t0 = time.time()
    result = ic.collect_inbox(actions, mode=mode,
                              max_pages=max_pages, max_items=max_items)
    elapsed = round(time.time() - t0, 1)
    out = ic.result_to_dict(result)
    out["elapsed_s"] = elapsed
    v = audit.judge(result, mode=mode)
    out["audit"] = {"code": v.code, "passed": v.passed, "reasons": v.reasons,
                    "metrics": v.metrics}
    path = out_dir / f"smoke_{mode.lower()}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== {mode} ===")
    print(f"folder={out['folder_name']} ui_unread={out['unread_count_ui']} "
          f"collected={len(out['items'])} unread_in_collection={out['collected_unread']} "
          f"dup={out['dup_count']} pages={len(out['pages_visited'])} "
          f"last_page_reached={out['last_page_reached']} elapsed={elapsed}s")
    print(f"audit: {v.code}  passed={v.passed}  reasons={v.reasons}")
    return out


def main():
    out_dir = Path("data/inspection/naver_mail_unread_pagination_depth")
    out_dir.mkdir(parents=True, exist_ok=True)
    target_id = cdp.ensure_about_blank_target()
    print(f"[boot] target_id={target_id[:12]}")

    list_only = run_mode(target_id, rsg.MODE_LIST_ONLY, out_dir)
    unread_only = run_mode(target_id, rsg.MODE_UNREAD_ONLY, out_dir)

    # 필터 실효성 audit
    from scripts.naver.mail.collection import audit_naver_mail_unread_filter_dom_fix as audit_filter
    # CollectionResult 재구성 (smoke 가 dict 로 저장하므로 ic.CollectionResult 로 변환)
    def _to_result(d):
        r = ic.CollectionResult(
            folder_id=d.get("folder_id", ""),
            folder_name=d.get("folder_name", ""),
            mode=d.get("mode", ""),
        )
        r.unread_count_ui = d.get("unread_count_ui", -1)
        r.collected_unread = d.get("collected_unread", 0)
        r.filter_applied = d.get("filter_applied", False)
        r.filter_evidence = d.get("filter_evidence", {})
        r.pagination_strategy_used = d.get("pagination_strategy_used", "")
        r.page_records = d.get("page_records", [])
        r.last_page_evidence = d.get("last_page_evidence", [])
        r.ui_count_scope_evidence = d.get("ui_count_scope_evidence", {})
        r.last_page_reached = d.get("last_page_reached", False)
        r.pages_visited = d.get("pages_visited", [])
        r.items = [ic.CollectedItem(**it) for it in d.get("items", [])]
        return r
    r1 = _to_result(list_only)
    r2 = _to_result(unread_only)
    v = audit_filter.judge_filter_effectiveness(r1, r2)
    filter_audit = {
        "verdict": v.code, "passed": v.passed, "reasons": v.reasons,
        "mismatch_reason_candidates": v.mismatch_reason_candidates,
        "metrics": v.metrics,
    }
    (out_dir / "filter_audit.json").write_text(
        json.dumps(filter_audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== FILTER AUDIT ===")
    print(json.dumps(filter_audit, ensure_ascii=False, indent=2))

    # 새: pagination depth audit
    from scripts.naver.mail.collection import audit_naver_mail_unread_pagination_depth as audit_depth
    dv = audit_depth.judge_pagination_depth(r2)
    depth_audit = {
        "verdict": dv.code, "passed": dv.passed, "reasons": dv.reasons,
        "metrics": dv.metrics,
    }
    (out_dir / "pagination_depth_audit.json").write_text(
        json.dumps(depth_audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== PAGINATION DEPTH AUDIT ===")
    print(json.dumps(depth_audit, ensure_ascii=False, indent=2))

    summary = {
        "list_only": {k: list_only.get(k) for k in
                      ("folder_name", "unread_count_ui", "collected_unread",
                       "dup_count", "last_page_reached", "warn_limit_reached",
                       "elapsed_s")},
        "list_only_total_collected": len(list_only["items"]),
        "unread_only": {k: unread_only.get(k) for k in
                        ("folder_name", "unread_count_ui", "collected_unread",
                         "dup_count", "last_page_reached", "warn_limit_reached",
                         "elapsed_s")},
        "unread_only_total_collected": len(unread_only["items"]),
        "verdicts": {
            "list_only": list_only["audit"]["code"],
            "unread_only": unread_only["audit"]["code"],
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
