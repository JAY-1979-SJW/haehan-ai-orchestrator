"""
admin-web/vendor/@haehan/design-system 동기화 감사 스크립트.

원본(00.디자인시스템)과 vendor 복사본의 drift를 감지한다.
VENDOR_MAINTENANCE_WARN 관리 규칙 이행용.

실행:
    python tools/audits/app/audit_vendor_design_system_sync.py

판정:
    PASS  - 원본과 vendor 일치 (소스 파일 기준)
    WARN  - 파일 수/내용 차이 발생
    SKIP  - 원본 경로 없음 (로컬 전용)
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
VENDOR_PATH = ROOT / "admin-web" / "vendor" / "@haehan" / "design-system"
ORIGIN_CANDIDATES = [
    ROOT.parents[0] / "00.디자인시스템",
    ROOT.parents[0] / "00.디자인시스템",
]

EXCLUDE_PATTERNS = {
    "node_modules",
    ".next",
    "storybook-static",
    ".git",
    ".tsbuildinfo",
    "__pycache__",
}

SOURCE_EXTENSIONS = {".ts", ".tsx", ".css", ".mjs", ".json"}
EXCLUDE_FILES = {"package-lock.json"}


def _collect(base: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for f in base.rglob("*"):
        if f.is_dir():
            continue
        parts = set(f.relative_to(base).parts)
        if parts & EXCLUDE_PATTERNS:
            continue
        if f.suffix not in SOURCE_EXTENSIONS:
            continue
        if f.name in EXCLUDE_FILES:
            continue
        rel = str(f.relative_to(base)).replace("\\", "/")
        # 파일 변경 감지용 체크섬일 뿐 보안 용도 아님(bandit B324, 2026-09-29 확인).
        result[rel] = hashlib.md5(f.read_bytes(), usedforsecurity=False).hexdigest()
    return result


def main() -> None:
    origin: Path | None = None
    for c in ORIGIN_CANDIDATES:
        if c.exists():
            origin = c
            break

    if origin is None:
        print("판정: SKIP — 원본 경로 없음 (서버/CI 환경, 로컬 전용 감사)")
        sys.exit(0)

    if not VENDOR_PATH.exists():
        print("판정: FAIL — vendor 경로 없음:", VENDOR_PATH)
        sys.exit(1)

    origin_files = _collect(origin)
    vendor_files = _collect(VENDOR_PATH)

    only_origin = sorted(set(origin_files) - set(vendor_files))
    only_vendor = sorted(set(vendor_files) - set(origin_files))
    modified = sorted(f for f in origin_files if f in vendor_files and origin_files[f] != vendor_files[f])

    report = {
        "origin": str(origin),
        "vendor": str(VENDOR_PATH),
        "origin_file_count": len(origin_files),
        "vendor_file_count": len(vendor_files),
        "only_in_origin": only_origin,
        "only_in_vendor": only_vendor,
        "modified": modified,
    }

    has_diff = bool(only_origin or only_vendor or modified)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print()

    if has_diff:
        print("판정: WARN — 원본과 vendor 불일치")
        print(f"  원본에만 있음: {len(only_origin)}개")
        print(f"  vendor에만 있음: {len(only_vendor)}개")
        print(f"  내용 변경: {len(modified)}개")
        print()
        print("  조치: admin-web/vendor 동기화 후 typecheck + Docker build 필수")
        sys.exit(1)
    else:
        print("판정: PASS — 원본과 vendor 일치")
        sys.exit(0)


if __name__ == "__main__":
    main()
