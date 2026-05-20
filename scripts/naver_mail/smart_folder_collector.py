"""스마트메일함 + 받은편지함 전수 unread 수집 오케스트레이터.

기존 inbox_collector.collect_inbox() 를 각 folder URL 위에서 재실행.
중복 sn 처리 + UI count snapshot before/after + 전체 합계 검산.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from . import inbox_collector as ic
from . import read_state_guard as rsg
from . import folder_discovery as fd

KST = timezone(timedelta(hours=9))
SCHEMA_VERSION = "1.0"


class _Actions(Protocol):
    def evaluate(self, expr: str) -> Any: ...
    def navigate(self, url: str) -> None: ...
    def wait_dom(self, expr_truthy: str, timeout_s: float = 8.0) -> bool: ...


@dataclass
class FolderCoverage:
    folder_id: str
    folder_name: str
    kind: str
    ui_unread_count: int
    collected_total: int
    collected_unread: int
    pages_visited: list[str]
    pagination_strategy_used: str
    last_page_evidence: list[str]
    last_page_reached: bool
    warn_limit_reached: bool
    page_records: list[dict]
    mismatch_reason: str = ""
    items: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class CoverageReport:
    schema_version: str
    run_id: str
    started_at_iso: str
    ended_at_iso: str
    collect_mode: str
    folders: list[FolderCoverage]
    ui_count_snapshot_before: dict
    ui_count_snapshot_after: dict
    folder_collected_total: int
    unique_sn_total: int
    duplicate_across_folders: list[dict]  # [{sn, folder_names}]
    warnings: list[str]
    verdict: str = ""


def snapshot_ui_counts(actions: _Actions) -> dict:
    """LNB 폴더별 unread count snapshot — folder_discovery 의 raw 추출 활용."""
    raw = actions.evaluate(fd.LNB_FOLDERS_EXPR) or []
    snap: dict[str, int] = {}
    total = 0
    breakdown_lnb = actions.evaluate(ic.LNB_UNREAD_BREAKDOWN_EXPR) or {}
    for r in raw:
        nm = (r.get("name") or "").strip()
        cnt = int(r.get("unread_count", -1))
        if nm and cnt > 0:
            snap[nm] = cnt
            total += cnt
    return {
        "captured_at_iso": datetime.now(KST).replace(microsecond=0).isoformat(),
        "by_folder": snap,
        "by_folder_sum": total,
        "total_aggregate_lnb": (breakdown_lnb or {}).get("total_aggregate", -1),
    }


def collect_all(actions: _Actions, *,
                max_pages: int = 200,
                max_items_per_folder: int = 5000,
                navigate_inter_folder_delay_s: float = 2.5,
                now_for_time: datetime | None = None) -> CoverageReport:
    run_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(KST).replace(microsecond=0).isoformat()
    warnings: list[str] = []

    # 0) 받은편지함으로 시작
    actions.navigate("https://mail.naver.com/v2/folders/0/all")
    time.sleep(2.5)
    actions.wait_dom("document.querySelector('li.mail_item, .lnb')", timeout_s=10.0)

    # 1) UI snapshot BEFORE
    snap_before = snapshot_ui_counts(actions)

    # 2) 폴더 발견 (받은편지함 + smart)
    folders_all = fd.discover_folders(actions, learn_ids=True)
    targets = fd.filter_collectable(folders_all)

    # 3) 각 폴더 수집
    folder_results: list[FolderCoverage] = []
    sn_to_folders: dict[str, list[str]] = {}
    for f in targets:
        unread_url = f"https://mail.naver.com/v2/folders/{f.folder_id}/unread"
        actions.navigate(unread_url)
        time.sleep(navigate_inter_folder_delay_s)
        actions.wait_dom("document.querySelector('li.mail_item, .mail_list_wrap')",
                         timeout_s=15.0)
        # 이 URL 은 이미 UNREAD 필터가 적용된 상태 — apply_unread_filter 호출 불필요
        # 직접 LIST_ONLY 로 페이지네이션 (필터는 URL 로 이미 적용됨)
        result = ic.collect_inbox(
            actions, mode=rsg.MODE_LIST_ONLY,
            max_pages=max_pages, max_items=max_items_per_folder,
            now_for_time=now_for_time,
        )
        # collect_mode 는 UNREAD 의미로 재라벨
        for it in result.items:
            it.collect_mode = rsg.MODE_UNREAD_ONLY
            it.folder_id = f.folder_id
            it.folder_name = f.name
            sn_to_folders.setdefault(it.sn or "", []).append(f.name)

        fc = FolderCoverage(
            folder_id=f.folder_id,
            folder_name=f.name,
            kind=f.kind,
            ui_unread_count=f.unread_count,
            collected_total=len(result.items),
            collected_unread=sum(1 for it in result.items if it.read_state == "UNREAD"),
            pages_visited=list(result.pages_visited),
            pagination_strategy_used=result.pagination_strategy_used,
            last_page_evidence=list(set(result.last_page_evidence)),
            last_page_reached=result.last_page_reached,
            warn_limit_reached=result.warn_limit_reached,
            page_records=list(result.page_records),
            items=[asdict(it) for it in result.items],
            notes=list(result.notes),
        )
        # 폴더별 mismatch 판정
        if fc.ui_unread_count >= 0 and fc.collected_total != fc.ui_unread_count:
            fc.mismatch_reason = f"ui({fc.ui_unread_count})!=collected({fc.collected_total})"
            warnings.append(f"folder_mismatch:{f.name}:{fc.mismatch_reason}")
        if len(fc.last_page_evidence) < 2:
            warnings.append(f"folder_evidence_insufficient:{f.name}:{fc.last_page_evidence}")
        folder_results.append(fc)

    # 4) 중복 across folders
    duplicates = []
    unique_sns: set[str] = set()
    folder_total = 0
    for fc in folder_results:
        folder_total += fc.collected_total
        for it in fc.items:
            sn = it.get("sn") or ""
            if sn:
                unique_sns.add(sn)
    for sn, fnames in sn_to_folders.items():
        if sn and len(set(fnames)) > 1:
            duplicates.append({"sn": sn, "folder_names": sorted(set(fnames))})

    # 5) UI snapshot AFTER
    snap_after = snapshot_ui_counts(actions)
    if snap_before.get("by_folder") != snap_after.get("by_folder"):
        warnings.append("SESSION_STATE_CHANGED: UI count snapshot 변경됨")

    ended_at = datetime.now(KST).replace(microsecond=0).isoformat()

    report = CoverageReport(
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        started_at_iso=started_at,
        ended_at_iso=ended_at,
        collect_mode=rsg.MODE_UNREAD_ONLY,
        folders=folder_results,
        ui_count_snapshot_before=snap_before,
        ui_count_snapshot_after=snap_after,
        folder_collected_total=folder_total,
        unique_sn_total=len(unique_sns),
        duplicate_across_folders=duplicates,
        warnings=warnings,
    )
    return report


def report_to_dict(r: CoverageReport) -> dict:
    return {
        "schema_version": r.schema_version,
        "run_id": r.run_id,
        "started_at_iso": r.started_at_iso,
        "ended_at_iso": r.ended_at_iso,
        "collect_mode": r.collect_mode,
        "folders": [asdict(f) for f in r.folders],
        "ui_count_snapshot_before": r.ui_count_snapshot_before,
        "ui_count_snapshot_after": r.ui_count_snapshot_after,
        "folder_collected_total": r.folder_collected_total,
        "unique_sn_total": r.unique_sn_total,
        "duplicate_across_folders": r.duplicate_across_folders,
        "warnings": r.warnings,
        "verdict": r.verdict,
    }
