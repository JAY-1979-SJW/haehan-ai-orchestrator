"""NAVER-MAIL-SMART-FOLDER-COVERAGE-01 audit.

판정:
  PASS_NAVER_MAIL_SMART_FOLDER_COVERAGE
  WARN_PARTIAL_SMART_FOLDER_COVERAGE
  WARN_FOLDER_COUNT_SCOPE_DIFFERENT
  WARN_SESSION_STATE_CHANGED
  FAIL_SIDE_EFFECT_OCCURRED
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.naver.mail import smart_folder_collector as sfc


@dataclass
class CoverageVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


_FORBIDDEN_HINTS = ("popup/read", "captureScreenshot", "send", "delete", "trash", "spam", "download")


def judge_coverage(report: sfc.CoverageReport, *, side_effect_log: list[str] | None = None) -> CoverageVerdict:
    side_effect_log = side_effect_log or []
    side_hits = [e for e in side_effect_log if any(b in e for b in _FORBIDDEN_HINTS)]
    if side_hits:
        return CoverageVerdict(False, "FAIL_SIDE_EFFECT_OCCURRED", reasons=[f"side_effect:{side_hits[:3]}"])

    reasons: list[str] = []
    metrics = {
        "folder_count": len(report.folders),
        "folder_collected_total": report.folder_collected_total,
        "unique_sn_total": report.unique_sn_total,
        "duplicate_across_folders_n": len(report.duplicate_across_folders),
        "ui_total_before": report.ui_count_snapshot_before.get("by_folder_sum", -1),
        "ui_total_after": report.ui_count_snapshot_after.get("by_folder_sum", -1),
        "warnings_n": len(report.warnings),
    }

    # SESSION_STATE_CHANGED 우선 분류
    before = report.ui_count_snapshot_before.get("by_folder", {})
    after = report.ui_count_snapshot_after.get("by_folder", {})
    if before and after and before != after:
        # 변동 있음
        reasons.append(f"ui_snapshot_changed:before={before}_after={after}")
        return CoverageVerdict(False, "WARN_SESSION_STATE_CHANGED", reasons=reasons, metrics=metrics)

    # 각 폴더별 UI vs 수집 일치 + last_page_evidence 2개
    folder_ok = []
    folder_warn = []
    for f in report.folders:
        ev = set(f.last_page_evidence)
        if f.ui_unread_count >= 0 and f.collected_total != f.ui_unread_count:
            folder_warn.append(f"{f.folder_name}:ui({f.ui_unread_count})!=col({f.collected_total})")
        elif len(ev) < 2:
            folder_warn.append(f"{f.folder_name}:insufficient_evidence={list(ev)}")
        else:
            folder_ok.append(f.folder_name)
    metrics["folder_ok_n"] = len(folder_ok)
    metrics["folder_warn_n"] = len(folder_warn)

    # 전체 합계 검산
    ui_total = report.ui_count_snapshot_before.get("by_folder_sum", -1)  # noqa: F841
    # 받은편지함 + smart 만 계산했으므로 ui_total 도 그 부분합과 비교해야 함.
    # by_folder snapshot 에 폴더가 모두 들어있으므로 folder 목록의 합으로 재계산.
    covered_ui_sum = sum(
        report.ui_count_snapshot_before.get("by_folder", {}).get(f.folder_name, 0) for f in report.folders
    )
    metrics["covered_ui_sum"] = covered_ui_sum

    if folder_warn:
        return CoverageVerdict(False, "WARN_PARTIAL_SMART_FOLDER_COVERAGE", reasons=folder_warn[:10], metrics=metrics)

    if covered_ui_sum != report.folder_collected_total:
        reasons.append(f"covered_ui_sum({covered_ui_sum})!=folder_collected_total({report.folder_collected_total})")
        return CoverageVerdict(False, "WARN_FOLDER_COUNT_SCOPE_DIFFERENT", reasons=reasons, metrics=metrics)

    return CoverageVerdict(True, "PASS_NAVER_MAIL_SMART_FOLDER_COVERAGE", reasons=[], metrics=metrics)


def main(argv=None) -> int:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser()
    ap.add_argument("report_json", type=Path)
    args = ap.parse_args(argv)
    d = json.loads(args.report_json.read_text(encoding="utf-8"))
    # 간단 dict→객체 복원
    folders = [sfc.FolderCoverage(**f) for f in d.get("folders", [])]
    r = sfc.CoverageReport(
        schema_version=d.get("schema_version", "1.0"),
        run_id=d.get("run_id", ""),
        started_at_iso=d.get("started_at_iso", ""),
        ended_at_iso=d.get("ended_at_iso", ""),
        collect_mode=d.get("collect_mode", ""),
        folders=folders,
        ui_count_snapshot_before=d.get("ui_count_snapshot_before", {}),
        ui_count_snapshot_after=d.get("ui_count_snapshot_after", {}),
        folder_collected_total=d.get("folder_collected_total", 0),
        unique_sn_total=d.get("unique_sn_total", 0),
        duplicate_across_folders=d.get("duplicate_across_folders", []),
        warnings=d.get("warnings", []),
    )
    v = judge_coverage(r)
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
