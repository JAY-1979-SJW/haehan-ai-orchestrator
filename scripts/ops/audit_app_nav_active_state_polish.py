"""Audit: APP_NAV_ACTIVE_STATE_POLISH_01"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

LAYOUT = ROOT / "admin-web" / "src" / "app" / "assistant" / "layout.tsx"
NAVBAR = ROOT / "admin-web" / "src" / "components" / "assistant" / "AssistantNavBar.tsx"

VERDICT_READY = "APP_NAV_ACTIVE_STATE_POLISH_READY"
VERDICT_WARN = "APP_NAV_ACTIVE_STATE_POLISH_WITH_WARN"
VERDICT_BLOCKED = "APP_NAV_ACTIVE_STATE_POLISH_BLOCKED"

checks: list[tuple[str, bool, str]] = []

def _add(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))

def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""

def run_audit() -> None:
    layout = _src(LAYOUT)
    navbar = _src(NAVBAR)

    _add("layout.tsx 존재", LAYOUT.exists())
    _add("AssistantNavBar.tsx 존재", NAVBAR.exists())
    _add("layout — metadata 유지", "metadata" in layout)
    _add("layout — AssistantNavBar import", "AssistantNavBar" in layout)
    _add("layout — Server Component (use client 없음)", '"use client"' not in layout)
    _add("navbar — use client", '"use client"' in navbar)
    _add("navbar — usePathname 사용", "usePathname" in navbar)
    _add("navbar — 활성 탭 스타일", "isActive" in navbar or "active" in navbar)
    _add("navbar — exact 매칭 지원", "exact" in navbar)
    _add("navbar — 접두사 매칭 지원", "startsWith" in navbar)
    _add("navbar — 7개 탭 모두 존재", navbar.count('href: "/assistant') >= 7)
    _add("navbar — 대시보드 탭", "대시보드" in navbar)
    _add("navbar — 로그·감사 탭", "로그·감사" in navbar or "로그" in navbar)
    _add("navbar — 배포 상태 탭", "배포 상태" in navbar)
    _add("navbar — DRY_RUN 배지 (layout)", "DRY_RUN" in layout)
    _add("navbar — 실행 버튼 없음 배지 (layout)", "실행 버튼 없음" in layout)

def print_report() -> str:
    passed = sum(1 for _, r, _ in checks if r)
    failed = sum(1 for _, r, _ in checks if not r)
    print(f"\n{'=' * 60}")
    print("APP_NAV_ACTIVE_STATE_POLISH AUDIT")
    print(f"{'=' * 60}")
    for name, ok, detail in checks:
        line = f"  [{'PASS' if ok else 'FAIL'}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print(f"{'=' * 60}")
    print(f"  총 {len(checks)}개: PASS={passed}, FAIL={failed}")
    verdict = VERDICT_READY if failed == 0 else (VERDICT_WARN if failed <= 2 else VERDICT_BLOCKED)
    print(f"  최종 판정: {verdict}")
    print(f"{'=' * 60}\n")
    return verdict

if __name__ == "__main__":
    run_audit()
    verdict = print_report()
    sys.exit(0 if verdict != VERDICT_BLOCKED else 1)
