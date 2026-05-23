"""Clean local generated UI residue after audit.

Only generated, reproducible, or empty local residue paths are eligible. Active
UI entrypoints and fallback approval UI modules are intentionally out of scope.
"""
from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALLOW_DELETE = (
    "admin-web/.next",
    "admin-web/node_modules",
    "admin-web/vendor/@haehan/design-system/node_modules",
    "desktop/__pycache__",
    "desktop/ui_new/__pycache__",
    "desktop/local_ui",
)

FORBIDDEN_DELETE = (
    "admin-web/src",
    "admin-web/public",
    "admin-web/vendor/@haehan/design-system/src",
    "desktop/ui_dist",
    "desktop/ui_new",
    "desktop/local_server.py",
    "desktop/admin_webview.py",
    "ai_orchestrator/admin_ui_router.py",
    "local_agent/user_present_ui_server.py",
    "ai_orchestrator/local_agent/browser/approval_server.py",
)


@dataclass(frozen=True)
class CleanupItem:
    path: str
    status: str
    detail: str


def normalize(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _inside_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def _is_forbidden(path: Path) -> bool:
    if not _inside_root(path):
        return True
    resolved = path.resolve()
    allowed = {(ROOT / rel).resolve() for rel in ALLOW_DELETE}
    if resolved in allowed:
        return False
    for rel in FORBIDDEN_DELETE:
        forbidden = (ROOT / rel).resolve()
        if resolved == forbidden or forbidden in resolved.parents:
            return True
    return False


def _measure(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    if path.is_file():
        return 1, path.stat().st_size
    count = 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            count += 1
            total += child.stat().st_size
    return count, total


def cleanup(*, apply: bool = False) -> list[CleanupItem]:
    items: list[CleanupItem] = []
    for rel in ALLOW_DELETE:
        path = ROOT / rel
        if _is_forbidden(path):
            items.append(CleanupItem(rel, "FAIL", "refused by safety boundary"))
            continue
        if not path.exists():
            items.append(CleanupItem(rel, "PASS", "already absent"))
            continue
        count, total = _measure(path)
        if not apply:
            items.append(CleanupItem(rel, "DRY_RUN", f"would remove files={count} bytes={total}"))
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path, onexc=_clear_readonly)
            else:
                path.unlink()
        except OSError as exc:
            items.append(CleanupItem(rel, "FAIL", f"remove failed: {type(exc).__name__}"))
            continue
        items.append(CleanupItem(rel, "PASS", f"removed files={count} bytes={total}"))
    return items


def _clear_readonly(func, path, exc_info) -> None:
    os.chmod(path, 0o700)
    func(path)


def print_report(items: list[CleanupItem]) -> None:
    failed = 0
    changed = 0
    for item in items:
        print(f"[{item.status}] {item.path} - {item.detail}")
        if item.status == "FAIL":
            failed += 1
        if item.status == "PASS" and item.detail.startswith("removed "):
            changed += 1
    result = "FAIL_UI_RESIDUE_CLEANUP" if failed else "PASS_UI_RESIDUE_CLEANUP"
    print(f"RESULT={result} changed={changed} failed={failed}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean generated UI residue only")
    parser.add_argument("--apply", action="store_true", help="delete allowed generated residue paths")
    args = parser.parse_args(argv)

    items = cleanup(apply=args.apply)
    print_report(items)
    return 1 if any(item.status == "FAIL" for item in items) else 0


if __name__ == "__main__":
    raise SystemExit(main())
