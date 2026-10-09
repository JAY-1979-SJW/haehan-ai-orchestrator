"""표준 UI 패키지 감사 스크립트."""

from __future__ import annotations

import pathlib
import sys

TARGET = pathlib.Path("admin-web/src/standard-ui")

ISSUES: list[str] = []
WARNINGS: list[str] = []


def _check(condition: bool, label: str, *, warn: bool = False) -> None:
    mark = "PASS" if condition else ("WARN" if warn else "FAIL")
    if not condition:
        (WARNINGS if warn else ISSUES).append(f"{mark}  {label}")
    print(f"  [{mark}] {label}")


def _file_contains(path: pathlib.Path, text: str) -> bool:
    try:
        return text in path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 - 표준 UI 패키지 감사 — 파일 내용 검색(_file_contains) 실패 시 False(불일치)를 반환하는 안전한 기본값.
        return False


def run_audit() -> int:
    print("=" * 60)
    print("Standard UI Package Audit")
    print("=" * 60)

    # 1. 폴더 존재
    _check(TARGET.is_dir(), f"TARGET_STANDARD_UI_DIR 존재: {TARGET}")

    # 2. README
    _check((TARGET / "README.md").is_file(), "README.md 존재")

    # 3. tokens 폴더
    _check((TARGET / "tokens").is_dir(), "tokens/ 폴더 존재")

    # 4. colors.ts
    colors_path = TARGET / "tokens" / "colors.ts"
    _check(colors_path.is_file(), "tokens/colors.ts 존재")

    # 5. primaryOrange
    _check(_file_contains(colors_path, "#F97316"), "primaryOrange #F97316 존재")

    # 6. navyBase
    _check(_file_contains(colors_path, "#1E2D4A"), "navyBase #1E2D4A 존재")

    # 7. TopAccentLine
    _check((TARGET / "components/layout/TopAccentLine.tsx").is_file(), "TopAccentLine.tsx 존재")

    # 8. AppShell
    _check((TARGET / "components/layout/AppShell.tsx").is_file(), "AppShell.tsx 존재")

    # 9. StatusBadge
    _check((TARGET / "components/status/StatusBadge.tsx").is_file(), "StatusBadge.tsx 존재")

    # 10. MetricCard
    _check((TARGET / "components/cards/MetricCard.tsx").is_file(), "MetricCard.tsx 존재")

    # 11. DomainUnitCard
    _check((TARGET / "components/cards/DomainUnitCard.tsx").is_file(), "DomainUnitCard.tsx 존재")

    # 12. GateStatusCard
    _check((TARGET / "components/cards/GateStatusCard.tsx").is_file(), "GateStatusCard.tsx 존재")

    # 13. ConstructionPhaseTable
    _check((TARGET / "components/tables/ConstructionPhaseTable.tsx").is_file(), "ConstructionPhaseTable.tsx 존재")

    # 14. ReportList
    _check((TARGET / "components/lists/ReportList.tsx").is_file(), "ReportList.tsx 존재")

    # 15. WarehouseCard
    _check((TARGET / "components/cards/WarehouseCard.tsx").is_file(), "WarehouseCard.tsx 존재")

    # 16. index.ts export
    index_path = TARGET / "index.ts"
    _check(index_path.is_file(), "index.ts 존재")
    _check(_file_contains(index_path, "TopAccentLine"), "index.ts TopAccentLine export 존재")
    _check(_file_contains(index_path, "StatusBadge"), "index.ts StatusBadge export 존재")

    # 17. docs/design-system.md
    _check((TARGET / "docs/design-system.md").is_file(), "docs/design-system.md 존재")

    # 18. patterns/dashboard.md
    _check((TARGET / "patterns/dashboard.md").is_file(), "patterns/dashboard.md 존재")

    # 19~22. 금지 패턴 검사
    # 실제 인증/보안 로직 패턴 (경로명 'tokens' 는 제외)
    _secret_patterns = [
        "password",
        "sessionStorage",
        "localStorage",
        "document.cookie",
        "access_token",
        "refresh_token",
        "getItem('g2b",
    ]
    _api_patterns = ["fetch(", "axios.", "api_client", "G2B_API_BASE"]
    _db_patterns = ["import sqlite3", "import sqlalchemy", "from scripts.db", "from scripts.models"]
    _html_patterns = ["HTMLResponse", "Jinja2Templates", "<html>"]

    all_tsx_ts = list(TARGET.rglob("*.ts")) + list(TARGET.rglob("*.tsx"))

    secret_hit = any(
        any(pat in f.read_text(encoding="utf-8", errors="ignore") for pat in _secret_patterns) for f in all_tsx_ts
    )
    _check(not secret_hit, "secret/session/cookie/token 로직 없음")

    api_hit = any(
        any(pat in f.read_text(encoding="utf-8", errors="ignore") for pat in _api_patterns) for f in all_tsx_ts
    )
    _check(not api_hit, "외부 API 호출 없음")

    db_hit = any(any(pat in f.read_text(encoding="utf-8", errors="ignore") for pat in _db_patterns) for f in all_tsx_ts)
    _check(not db_hit, "DB 접근 없음")

    html_hit = any(
        any(pat in f.read_text(encoding="utf-8", errors="ignore") for pat in _html_patterns) for f in all_tsx_ts
    )
    _check(not html_hit, "임시 FastAPI HTML 문자열 없음")

    print()
    print(f"FAIL: {len(ISSUES)}  WARN: {len(WARNINGS)}")
    for msg in ISSUES:
        print(f"  {msg}")
    for msg in WARNINGS:
        print(f"  {msg}")

    verdict = "PASS" if not ISSUES else "FAIL"
    print(f"\n판정: {verdict}")
    return 0 if not ISSUES else 1


if __name__ == "__main__":
    sys.exit(run_audit())
