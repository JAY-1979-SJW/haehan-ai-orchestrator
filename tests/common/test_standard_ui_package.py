"""표준 UI 패키지 구조/토큰/컴포넌트/보안 테스트.

실제 React 렌더링, 외부 API 호출, DB 접근 없음.
파일 존재 및 내용 검증 중심.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

TARGET = pathlib.Path("admin-web/src/standard-ui")


# ── 헬퍼 ─────────────────────────────────────────────────────────────


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def all_tsx_ts():
    return list(TARGET.rglob("*.ts")) + list(TARGET.rglob("*.tsx"))


# ── 1. 폴더 존재 ──────────────────────────────────────────────────────


def test_standard_ui_dir_exists():
    assert TARGET.is_dir(), f"표준 UI 폴더 없음: {TARGET}"


# ── 2. tokens 파일 ────────────────────────────────────────────────────


def test_tokens_dir_exists():
    assert (TARGET / "tokens").is_dir()


def test_colors_ts_exists():
    assert (TARGET / "tokens/colors.ts").is_file()


def test_spacing_ts_exists():
    assert (TARGET / "tokens/spacing.ts").is_file()


def test_typography_ts_exists():
    assert (TARGET / "tokens/typography.ts").is_file()


def test_radius_ts_exists():
    assert (TARGET / "tokens/radius.ts").is_file()


def test_shadows_ts_exists():
    assert (TARGET / "tokens/shadows.ts").is_file()


# ── 3. 필수 색상 존재 ─────────────────────────────────────────────────


def test_primary_orange_token():
    src = read(TARGET / "tokens/colors.ts")
    assert "#F97316" in src, "primaryOrange #F97316 없음"


def test_navy_base_token():
    src = read(TARGET / "tokens/colors.ts")
    assert "#1E2D4A" in src, "navyBase #1E2D4A 없음"


def test_status_colors_exist():
    src = read(TARGET / "tokens/colors.ts")
    for status in ("PASS", "FAIL", "WARN", "BLOCKED"):
        assert status in src, f"statusColors에 {status} 없음"


# ── 4. TopAccentLine ──────────────────────────────────────────────────


def test_top_accent_line_exists():
    assert (TARGET / "components/layout/TopAccentLine.tsx").is_file()


def test_top_accent_line_is_4px_orange():
    src = read(TARGET / "components/layout/TopAccentLine.tsx")
    assert "4" in src and "#F97316" in src, "TopAccentLine 4px #F97316 명세 없음"


# ── 5. AppShell ───────────────────────────────────────────────────────


def test_app_shell_exists():
    assert (TARGET / "components/layout/AppShell.tsx").is_file()


def test_app_shell_uses_top_accent_line():
    src = read(TARGET / "components/layout/AppShell.tsx")
    assert "TopAccentLine" in src


# ── 6. StatusBadge ────────────────────────────────────────────────────


def test_status_badge_exists():
    assert (TARGET / "components/status/StatusBadge.tsx").is_file()


def test_status_badge_uses_status_colors():
    src = read(TARGET / "components/status/StatusBadge.tsx")
    assert "statusColors" in src


# ── 7. MetricCard ─────────────────────────────────────────────────────


def test_metric_card_exists():
    assert (TARGET / "components/cards/MetricCard.tsx").is_file()


# ── 8. DomainUnitCard ─────────────────────────────────────────────────


def test_domain_unit_card_exists():
    assert (TARGET / "components/cards/DomainUnitCard.tsx").is_file()


# ── 9. GateStatusCard ─────────────────────────────────────────────────


def test_gate_status_card_exists():
    assert (TARGET / "components/cards/GateStatusCard.tsx").is_file()


# ── 10. ConstructionPhaseTable ────────────────────────────────────────


def test_construction_phase_table_exists():
    assert (TARGET / "components/tables/ConstructionPhaseTable.tsx").is_file()


# ── 11. ReportList ────────────────────────────────────────────────────


def test_report_list_exists():
    assert (TARGET / "components/lists/ReportList.tsx").is_file()


# ── 12. WarehouseCard ─────────────────────────────────────────────────


def test_warehouse_card_exists():
    assert (TARGET / "components/cards/WarehouseCard.tsx").is_file()


# ── 13. index.ts export ───────────────────────────────────────────────


def test_index_ts_exists():
    assert (TARGET / "index.ts").is_file()


def test_index_exports_key_components():
    src = read(TARGET / "index.ts")
    for name in (
        "TopAccentLine",
        "AppShell",
        "StatusBadge",
        "MetricCard",
        "DomainUnitCard",
        "GateStatusCard",
        "ConstructionPhaseTable",
        "ReportList",
        "WarehouseCard",
    ):
        assert name in src, f"index.ts에 {name} export 없음"


# ── 14. docs 존재 ─────────────────────────────────────────────────────


def test_docs_design_system():
    assert (TARGET / "docs/design-system.md").is_file()


def test_docs_usage_guide():
    assert (TARGET / "docs/usage-guide.md").is_file()


def test_docs_do_dont():
    assert (TARGET / "docs/do-dont.md").is_file()


def test_docs_migration_guide():
    assert (TARGET / "docs/migration-guide.md").is_file()


# ── 15. patterns 존재 ─────────────────────────────────────────────────


def test_patterns_dashboard():
    assert (TARGET / "patterns/dashboard.md").is_file()


def test_patterns_status_page():
    assert (TARGET / "patterns/status-page.md").is_file()


def test_patterns_report_page():
    assert (TARGET / "patterns/report-page.md").is_file()


def test_patterns_gate_page():
    assert (TARGET / "patterns/gate-page.md").is_file()


def test_patterns_construction_schedule():
    assert (TARGET / "patterns/construction-schedule-page.md").is_file()


def test_patterns_warehouse():
    assert (TARGET / "patterns/warehouse-page.md").is_file()


# ── 16. secret/session/cookie/token 없음 ────────────────────────────

_SECRET_PATTERNS = ["localStorage", "sessionStorage", ".cookie", "getItem('g2b", "token"]


def test_no_secret_session_in_components():
    sensitive = ["localStorage", "sessionStorage", "document.cookie", "access_token", "getItem('g2b"]
    for f in all_tsx_ts():
        src = read(f)
        for pat in sensitive:
            assert pat not in src, f"{f.name}에 '{pat}' 접근 금지"


# ── 17. 외부 API 호출 없음 ────────────────────────────────────────────


def test_no_api_calls():
    api_pats = ["fetch(", "axios.", "G2B_API_BASE", "api_client"]
    for f in all_tsx_ts():
        src = read(f)
        for pat in api_pats:
            assert pat not in src, f"{f.name}에 API 호출 패턴 '{pat}' 금지"


# ── 18. DB 접근 없음 ─────────────────────────────────────────────────


def test_no_db_access():
    db_pats = ["import sqlite3", "sqlalchemy", "from scripts.db", "from scripts.models"]
    for f in all_tsx_ts():
        src = read(f)
        for pat in db_pats:
            assert pat not in src, f"{f.name}에 DB 패턴 '{pat}' 금지"


# ── 19. audit script PASS ────────────────────────────────────────────


def test_audit_script_passes():
    result = subprocess.run(
        [sys.executable, "tools/audits/app/audit_standard_ui_package.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"audit script 실패:\n{result.stdout}\n{result.stderr}"
