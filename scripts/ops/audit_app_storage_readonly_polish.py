"""Audit: APP_STORAGE_READONLY_POLISH_01"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PAGE = ROOT / "admin-web" / "src" / "app" / "assistant" / "storage" / "page.tsx"

VERDICT_READY = "APP_STORAGE_READONLY_POLISH_READY"
VERDICT_WARN = "APP_STORAGE_READONLY_POLISH_WITH_WARN"
VERDICT_BLOCKED = "APP_STORAGE_READONLY_POLISH_BLOCKED"

checks: list[tuple[str, bool, str]] = []

def _add(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))

def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""

def run_audit() -> None:
    page = _src(PAGE)

    _add("storage page 존재", PAGE.exists())
    _add("use client", '"use client"' in page)
    _add("ReadOnlyModeBanner", "ReadOnlyModeBanner" in page)
    _add("MUTATION_BLOCKED 배지", "MUTATION_BLOCKED" in page)
    _add("getAppStorageStatus API 연결", "getAppStorageStatus" in page)
    _add("mock_fallback 상태", "mock_fallback" in page)
    _add("ApiConnectionStateBadge", "ApiConnectionStateBadge" in page)
    _add("요약 카드 — 마운트 수", "마운트 수" in page)
    _add("요약 카드 — PERSISTENT", "PERSISTENT" in page)
    _add("요약 카드 — DISPOSABLE", "DISPOSABLE" in page)
    _add("StorageStatusCard 사용", "StorageStatusCard" in page)
    _add("B-3 감사 미완 안내", "B-3" in page or "B3" in page)
    _add("approval_tokens 금고 안내", "approval_tokens" in page)
    _add("delete_btn 없음", "delete_btn" not in page)
    _add("format_btn 없음", "format_btn" not in page)
    _add("POST method 없음", 'method: "POST"' not in page and "method: 'POST'" not in page)
    _add("approval_token_raw 없음", "approval_token_raw" not in page)
    _add("cookie_value 없음", "cookie_value" not in page)
    _add("token 원문 금지 안내", "token 원문" in page or "token 원문 금지" in page)

def print_report() -> str:
    passed = sum(1 for _, r, _ in checks if r)
    failed = sum(1 for _, r, _ in checks if not r)
    print(f"\n{'=' * 60}")
    print("APP_STORAGE_READONLY_POLISH AUDIT")
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
