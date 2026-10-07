"""NAVER-MAIL-INBOX-P0-COMPLETE-01 audit.

지정된 CollectionResult 가 P0 완료 기준을 충족하는지 판정한다.

판정:
  PASS — last_page_reached + UI unread 수 == 수집 unread (UNREAD 모드)
                또는 UI unread 와 수집 unread 가 일치
  WARN — limit_reached / unread 불일치 / parse_warning 다수 등
  FAIL — 금지 동작 흔적 / schema 누락
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from scripts.naver.mail import inbox_collector as ic
from scripts.naver.mail import read_state_guard as rsg


@dataclass
class Verdict:
    passed: bool
    code: str  # PASS_NAVER_MAIL_INBOX_P0_COMPLETE / WARN_PARTIAL_COMPLETE / FAIL_*
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _p0_schema(result, reasons, passed):
    d = ic.result_to_dict(result)
    for i, item in enumerate(d["items"]):
        missing = ic.validate_item_schema(item)
        if missing:
            reasons.append(f"schema_missing[{i}]={missing}")
            passed = False
            break
    return passed


def _p0_pagination(result, reasons, passed):
    if result.warn_limit_reached:
        reasons.append("warn_limit_reached")
        passed = False
    if not result.last_page_reached:
        reasons.append("last_page_not_reached")
        passed = False
    return passed


def _p0_unread(result, mode, reasons, passed):
    if result.unread_count_ui >= 0:
        if mode == rsg.MODE_UNREAD_ONLY:
            # UNREAD 필터 모드 — 수집 전체가 unread, 그 수가 UI 와 일치 기대
            if len(result.items) != result.unread_count_ui:
                reasons.append(f"unread_collected({len(result.items)})!=ui({result.unread_count_ui})")
                passed = False
        else:
            if result.collected_unread != result.unread_count_ui:
                # 전체 수집인데 unread 가 UI 와 다르면 누락 후보
                reasons.append(f"unread_collected({result.collected_unread})!=ui({result.unread_count_ui})")
                passed = False
    return passed


def _p0_full_read(mode, plan, unread_snapshot, reasons, passed):
    if mode == rsg.MODE_FULL_READ:
        if plan is None:
            reasons.append("full_read_plan_missing")
            passed = False
        elif not plan.all_restored:
            reasons.append(f"read_state_not_preserved: restored={plan.restore_succeeded}/{plan.restore_attempted}")
            passed = False
        if unread_snapshot and unread_snapshot.before >= 0 and unread_snapshot.after >= 0:
            if unread_snapshot.after < unread_snapshot.before - (plan.restore_failed if plan else 0):
                reasons.append(f"unread_count_dropped: {unread_snapshot.before}->{unread_snapshot.after}")
                passed = False
    return passed


def judge(
    result: ic.CollectionResult,
    *,
    mode: str,
    unread_snapshot: rsg.UnreadCountSnapshot | None = None,
    plan: rsg.FullReadPlan | None = None,
) -> Verdict:
    reasons: list[str] = []
    passed = True

    # 1) schema 검증 — 모든 item 이 필수 필드를 갖는지
    passed = _p0_schema(result, reasons, passed)

    # 2) 페이지네이션 끝까지
    passed = _p0_pagination(result, reasons, passed)

    # 3) UI unread vs 수집 unread
    passed = _p0_unread(result, mode, reasons, passed)

    # 4) FULL_READ 모드 — 안읽음 복구
    passed = _p0_full_read(mode, plan, unread_snapshot, reasons, passed)

    # 5) parse_warning 다수면 WARN (parse 자체 실패는 큰 문제, 가정은 OK)
    bad_parses = [i for i in result.items if i.parsed_at_iso == "" and i.parse_warning.startswith("unknown_format")]
    if bad_parses:
        reasons.append(f"parse_failed_count={len(bad_parses)}")
        # 다수면 fail, 소수면 warn
        if len(bad_parses) > max(3, len(result.items) // 20):
            passed = False

    metrics = {
        "items": len(result.items),
        "unread_collected": result.collected_unread,
        "unread_ui": result.unread_count_ui,
        "dup_count": result.dup_count,
        "pages_visited": len(result.pages_visited),
        "last_page_reached": result.last_page_reached,
        "warn_limit_reached": result.warn_limit_reached,
        "parse_failed": len(bad_parses),
        "mode": mode,
    }
    code = "PASS_NAVER_MAIL_INBOX_P0_COMPLETE" if passed and not reasons else "WARN_PARTIAL_COMPLETE"
    return Verdict(passed=passed, code=code, reasons=reasons, metrics=metrics)


def audit_from_json(path: Path, *, mode: str) -> Verdict:
    data = json.loads(path.read_text(encoding="utf-8"))
    # 최소 필드로 CollectionResult 복원 (이미 dict 라 직접 검증)
    fake = ic.CollectionResult(
        folder_id=data.get("folder_id", ""),
        folder_name=data.get("folder_name", ""),
        mode=data.get("mode", mode),
    )
    fake.unread_count_ui = data.get("unread_count_ui", -1)
    fake.collected_unread = data.get("collected_unread", 0)
    fake.dup_count = data.get("dup_count", 0)
    fake.last_page_reached = data.get("last_page_reached", False)
    fake.warn_limit_reached = data.get("warn_limit_reached", False)
    fake.pages_visited = data.get("pages_visited", [])
    fake.notes = data.get("notes", [])
    fake.items = [ic.CollectedItem(**it) for it in data.get("items", [])]
    return judge(fake, mode=mode)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("json_path", type=Path, help="CollectionResult JSON")
    ap.add_argument("--mode", default=rsg.MODE_LIST_ONLY)
    args = ap.parse_args(argv)
    v = audit_from_json(args.json_path, mode=args.mode)
    print(
        json.dumps(
            {"verdict": v.code, "passed": v.passed, "reasons": v.reasons, "metrics": v.metrics},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if v.passed else 1


if __name__ == "__main__":
    sys.exit(main())
