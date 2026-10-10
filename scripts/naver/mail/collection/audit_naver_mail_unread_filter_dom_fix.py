"""NAVER-MAIL-UNREAD-FILTER-DOM-FIX-01 audit.

LIST_ONLY 결과와 UNREAD_ONLY 결과를 비교하여 안읽은 필터 실효성 판정.

판정 코드:
  PASS_NAVER_MAIL_UNREAD_FILTER_DOM_FIX
  WARN_UNREAD_FILTER_NO_OP            — 두 결과 동일 (필터 무효)
  WARN_UNREAD_COUNT_SCOPE_DIFFERENT   — 필터 적용됐으나 UI vs 수집 카운트 불일치
  FAIL_SIDE_EFFECT_OCCURRED           — 본문 열람 / 메일 상태 변경 흔적
  WARN_PARTIAL_COMPLETE               — 그 외 경계 케이스
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.naver.mail import inbox_collector as ic

# 불일치 사유 enum
MISMATCH_REASONS = (
    "UI_COUNT_SCOPE_DIFFERENT",  # UI 가 다른 폴더 합산
    "FILTER_DOM_NOT_APPLIED",  # 필터 호출했으나 DOM marker 없음
    "DYNAMIC_PAGE_MISSED",  # next-arrow 페이지가 추가로 있음
    "SESSION_STATE_CHANGED",  # 수집 중 사용자가 메일 읽음 처리
    "UNKNOWN_UNREAD_MISMATCH",
)


@dataclass
class Verdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    mismatch_reason_candidates: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _sn_set(r: ic.CollectionResult) -> set[str]:
    return {it.sn for it in r.items if it.sn}


def _all_unread(r: ic.CollectionResult) -> bool:
    return all(it.read_state == "UNREAD" for it in r.items) if r.items else False


def judge_filter_effectiveness(
    r_list: ic.CollectionResult,
    r_unread: ic.CollectionResult,
) -> Verdict:
    reasons: list[str] = []
    metrics = {
        "list_only_total": len(r_list.items),
        "list_only_unread": r_list.collected_unread,
        "unread_only_total": len(r_unread.items),
        "unread_only_unread": r_unread.collected_unread,
        "ui_unread_count": r_unread.unread_count_ui,
        "filter_applied_flag": r_unread.filter_applied,
        "filter_method": (r_unread.filter_evidence or {}).get("method", ""),
        "li_count_changed": (r_unread.filter_evidence or {}).get("li_count_changed"),
        "url_changed": (r_unread.filter_evidence or {}).get("url_changed"),
    }

    # 1) 두 결과의 sn 집합이 동일 → 필터 무효
    if _sn_set(r_list) == _sn_set(r_unread) and len(r_list.items) > 0:
        return Verdict(
            False,
            "WARN_UNREAD_FILTER_NO_OP",
            reasons=["UNREAD_ONLY_RESULT_EQUALS_LIST_ONLY"],
            mismatch_reason_candidates=["FILTER_DOM_NOT_APPLIED"],
            metrics=metrics,
        )

    # 2) UNREAD 모드에서 read 가 섞여 있으면 필터 부분 적용
    if r_unread.items and not _all_unread(r_unread):
        reasons.append("UNREAD_MODE_CONTAINS_READ_ITEMS")
        return Verdict(
            False,
            "WARN_UNREAD_FILTER_NO_OP",
            reasons=reasons,
            mismatch_reason_candidates=["FILTER_DOM_NOT_APPLIED"],
            metrics=metrics,
        )

    # 3) UI vs 수집 카운트 비교 (UNREAD_ONLY 의 items 수)
    if r_unread.unread_count_ui >= 0 and len(r_unread.items) != r_unread.unread_count_ui:
        candidates: list[str] = []
        # UI count 가 좌측 nav "전체 안읽은" 같이 폴더 합산일 가능성
        if r_unread.unread_count_ui > len(r_unread.items):
            candidates.append("UI_COUNT_SCOPE_DIFFERENT")
            candidates.append("DYNAMIC_PAGE_MISSED")
        else:
            candidates.append("SESSION_STATE_CHANGED")
        candidates.append("UNKNOWN_UNREAD_MISMATCH")
        reasons.append(f"ui({r_unread.unread_count_ui})!=unread_only_collected({len(r_unread.items)})")
        return Verdict(
            False,
            "WARN_UNREAD_COUNT_SCOPE_DIFFERENT",
            reasons=reasons,
            mismatch_reason_candidates=candidates,
            metrics=metrics,
        )

    # 4) PASS
    return Verdict(True, "PASS_NAVER_MAIL_UNREAD_FILTER_DOM_FIX", reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser()
    ap.add_argument("list_only_json", type=Path)
    ap.add_argument("unread_only_json", type=Path)
    args = ap.parse_args(argv)

    def _load(p: Path) -> ic.CollectionResult:
        d = json.loads(p.read_text(encoding="utf-8"))
        r = ic.CollectionResult(
            folder_id=d.get("folder_id", ""),
            folder_name=d.get("folder_name", ""),
            mode=d.get("mode", ""),
        )
        r.unread_count_ui = d.get("unread_count_ui", -1)
        r.collected_unread = d.get("collected_unread", 0)
        r.pages_visited = d.get("pages_visited", [])
        r.filter_applied = d.get("filter_applied", False)
        r.filter_evidence = d.get("filter_evidence", {})
        r.items = [ic.CollectedItem(**it) for it in d.get("items", [])]
        return r

    r1 = _load(args.list_only_json)
    r2 = _load(args.unread_only_json)
    v = judge_filter_effectiveness(r1, r2)
    import json as _json

    print(
        _json.dumps(
            {
                "verdict": v.code,
                "passed": v.passed,
                "reasons": v.reasons,
                "mismatch_reason_candidates": v.mismatch_reason_candidates,
                "metrics": v.metrics,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if v.passed else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
