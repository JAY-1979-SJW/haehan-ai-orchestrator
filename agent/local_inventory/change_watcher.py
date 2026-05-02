"""인벤토리 변경 감시.

- 이전 inventory 와 현재 inventory 비교
- 신규 설치/삭제/경로 변경 감지
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class InventoryDiff:
    """인벤토리 변경 요약."""
    added_programs: list[str] = field(default_factory=list)
    removed_programs: list[str] = field(default_factory=list)
    changed_programs: dict[str, dict] = field(default_factory=dict)  # {name: {field: (old, new)}}
    added_dlls: list[str] = field(default_factory=list)
    removed_dlls: list[str] = field(default_factory=list)
    scan_date_old: str | None = None
    scan_date_new: str | None = None
    has_changes: bool = False


def compare_inventory(old: dict, new: dict) -> InventoryDiff:
    """두 인벤토리 비교.

    Args:
        old: 이전 인벤토리
        new: 현재 인벤토리

    Returns:
        InventoryDiff
    """
    diff = InventoryDiff()

    # 스캔 날짜
    if old:
        diff.scan_date_old = old.get("metadata", {}).get("scan_date")
    diff.scan_date_new = new.get("metadata", {}).get("scan_date")

    # 프로그램 변경 비교
    old_programs = old.get("programs", {}) if old else {}
    new_programs = new.get("programs", {})

    # 신규 프로그램
    for prog_name in new_programs:
        if prog_name not in old_programs:
            diff.added_programs.append(prog_name)
            diff.has_changes = True

    # 삭제된 프로그램
    for prog_name in old_programs:
        if prog_name not in new_programs:
            diff.removed_programs.append(prog_name)
            diff.has_changes = True

    # 변경된 프로그램
    for prog_name in old_programs:
        if prog_name in new_programs:
            old_prog = old_programs[prog_name]
            new_prog = new_programs[prog_name]

            changes = {}
            for key in set(list(old_prog.keys()) + list(new_prog.keys())):
                old_val = old_prog.get(key)
                new_val = new_prog.get(key)
                if old_val != new_val:
                    changes[key] = (old_val, new_val)

            if changes:
                diff.changed_programs[prog_name] = changes
                diff.has_changes = True

    # DLL 변경 비교
    old_dlls = old.get("dlls", {}) if old else {}
    new_dlls = new.get("dlls", {})

    for dll_type in new_dlls:
        new_dll_list = new_dlls.get(dll_type, [])
        old_dll_list = old_dlls.get(dll_type, []) if old_dlls else []

        new_paths = [d.get("path") for d in new_dll_list if isinstance(d, dict)]
        old_paths = [d.get("path") for d in old_dll_list if isinstance(d, dict)]

        for path in new_paths:
            if path not in old_paths:
                diff.added_dlls.append(path)
                diff.has_changes = True

        for path in old_paths:
            if path not in new_paths:
                diff.removed_dlls.append(path)
                diff.has_changes = True

    return diff


def format_diff_report(diff: InventoryDiff) -> str:
    """변경 요약 포맷팅.

    Args:
        diff: InventoryDiff

    Returns:
        사람이 읽을 수 있는 보고서
    """
    lines = ["로컬 인벤토리 변경 요약", "=" * 50]

    if not diff.has_changes:
        lines.append("변경 사항 없음")
        return "\n".join(lines)

    if diff.added_programs:
        lines.append(f"\n[신규 설치] {len(diff.added_programs)}개")
        for prog in diff.added_programs:
            lines.append(f"  ✓ {prog}")

    if diff.removed_programs:
        lines.append(f"\n[제거됨] {len(diff.removed_programs)}개")
        for prog in diff.removed_programs:
            lines.append(f"  ✗ {prog}")

    if diff.changed_programs:
        lines.append(f"\n[변경됨] {len(diff.changed_programs)}개")
        for prog, changes in diff.changed_programs.items():
            lines.append(f"  ~ {prog}")
            for field, (old, new) in changes.items():
                lines.append(f"    {field}: {old} → {new}")

    if diff.added_dlls:
        lines.append(f"\n[신규 DLL] {len(diff.added_dlls)}개")
        for dll in diff.added_dlls:
            lines.append(f"  ✓ {dll}")

    if diff.removed_dlls:
        lines.append(f"\n[제거된 DLL] {len(diff.removed_dlls)}개")
        for dll in diff.removed_dlls:
            lines.append(f"  ✗ {dll}")

    lines.append("\n" + "=" * 50)
    return "\n".join(lines)
