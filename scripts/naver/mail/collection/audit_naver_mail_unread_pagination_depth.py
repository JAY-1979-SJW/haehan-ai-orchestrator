"""NAVER-MAIL-UNREAD-FILTER-PAGINATION-DEPTH-01 audit.

판정:
  PASS_NAVER_MAIL_UNREAD_FILTER_PAGINATION_DEPTH
    — UNREAD_ONLY 수집 == UI 받은편지함 unread
    — 모든 item.read_state == UNREAD
    — last_page_evidence ≥ 2 근거
  WARN_UNREAD_COUNT_SCOPE_DIFFERENT
    — UI count 가 합산값이고 받은편지함 단독은 일치
  WARN_DYNAMIC_PAGE_MISSED
    — pagination 종료 근거 부족 또는 페이지 누락 가능
  FAIL_SIDE_EFFECT_OCCURRED
    — 본문 열람 / 상태 변경 흔적
"""
from __future__ import annotations

from dataclasses import dataclass, field

from scripts.naver.mail import inbox_collector as ic


@dataclass
class DepthVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _all_unread(r: ic.CollectionResult) -> bool:
    return bool(r.items) and all(it.read_state == "UNREAD" for it in r.items)


def judge_pagination_depth(r: ic.CollectionResult,
                           *, side_effect_log: list[str] | None = None
                           ) -> DepthVerdict:
    reasons: list[str] = []
    side_effect_log = side_effect_log or []

    # FAIL — 본문/상태 변경 흔적
    bad = ("popup/read", "captureScreenshot", "Page.captureScreenshot",
           "send", "delete", "trash", "spam", "download")
    side_hits = [e for e in side_effect_log if any(b in e for b in bad)]
    if side_hits:
        return DepthVerdict(False, "FAIL_SIDE_EFFECT_OCCURRED",
                            reasons=[f"side_effect:{side_hits[:3]}"],
                            metrics={})

    scope = r.ui_count_scope_evidence or {}
    inbox_unread = scope.get("inbox_unread", -1)
    total_aggregate = scope.get("total_aggregate", -1)
    smart = scope.get("smart_folder_breakdown", {})
    source = scope.get("source", "")

    metrics = {
        "collected": len(r.items),
        "collected_unread": r.collected_unread,
        "ui_unread_count": r.unread_count_ui,
        "inbox_unread_lnb": inbox_unread,
        "total_aggregate_lnb": total_aggregate,
        "smart_folder_breakdown": smart,
        "ui_scope_source": source,
        "pagination_strategy_used": r.pagination_strategy_used,
        "pages_visited_n": len(r.pages_visited),
        "last_page_evidence": list(set(r.last_page_evidence)),
        "last_page_reached": r.last_page_reached,
    }

    # 1) FILTER 적용 + 모두 unread?
    if not r.filter_applied:
        reasons.append("filter_not_applied")
    if not _all_unread(r):
        reasons.append("collected_contains_read_items")
        return DepthVerdict(False, "WARN_UNREAD_FILTER_NO_OP",
                            reasons=reasons, metrics=metrics)

    # 2) last_page_evidence — 최소 2개 근거 필요
    unique_ev = set(r.last_page_evidence)
    if len(unique_ev) < 2:
        reasons.append(f"insufficient_last_page_evidence={list(unique_ev)}")
        return DepthVerdict(False, "WARN_DYNAMIC_PAGE_MISSED",
                            reasons=reasons, metrics=metrics)

    # 3) UI count vs 수집 비교
    # 받은편지함 unread (lnb 출처) 와 수집 일치하면 PASS
    target = inbox_unread if inbox_unread >= 0 else r.unread_count_ui
    if target >= 0 and len(r.items) == target:
        return DepthVerdict(True,
                            "PASS_NAVER_MAIL_UNREAD_FILTER_PAGINATION_DEPTH",
                            reasons=[], metrics=metrics)

    # 4) UI count > 수집: 합산 출처면 WARN_UNREAD_COUNT_SCOPE_DIFFERENT
    if source == "aggregate_with_smart_folders" \
       and total_aggregate > 0 and inbox_unread > 0 \
       and r.unread_count_ui >= total_aggregate:
        reasons.append(
            f"ui_count_is_aggregate({total_aggregate})_not_inbox({inbox_unread})"
        )
        # 단, 받은편지함 단독 카운트와는 일치해야 함
        if len(r.items) == inbox_unread:
            return DepthVerdict(False, "WARN_UNREAD_COUNT_SCOPE_DIFFERENT",
                                reasons=reasons, metrics=metrics)

    # 5) 그 외 — 페이지 누락 가능
    reasons.append(
        f"collected({len(r.items)})!=target_inbox_unread({target})"
    )
    return DepthVerdict(False, "WARN_DYNAMIC_PAGE_MISSED",
                        reasons=reasons, metrics=metrics)


def main(argv=None) -> int:
    import argparse, json
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("unread_only_json", type=Path)
    args = ap.parse_args(argv)
    d = json.loads(args.unread_only_json.read_text(encoding="utf-8"))
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
    r.last_page_evidence = d.get("last_page_evidence", [])
    r.pages_visited = d.get("pages_visited", [])
    r.page_records = d.get("page_records", [])
    r.ui_count_scope_evidence = d.get("ui_count_scope_evidence", {})
    r.last_page_reached = d.get("last_page_reached", False)
    r.items = [ic.CollectedItem(**it) for it in d.get("items", [])]
    v = judge_pagination_depth(r)
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
