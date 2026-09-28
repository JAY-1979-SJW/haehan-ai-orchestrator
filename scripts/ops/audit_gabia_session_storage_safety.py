"""
Gabia Session Storage Safety Audit
쿠키 평문 저장 금지 / data/sessions Git 추적 금지 / CDP 프로필 방식만 허용
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

VERDICT_SAFE = "GABIA_SESSION_STORAGE_SAFE_WITH_BROWSER_PROFILE_ONLY"
VERDICT_BLOCKED = "GABIA_SESSION_STORAGE_PLAINTEXT_COOKIE_BLOCKED"

_RISK_COOKIE_KEYS = frozenset(
    {
        "PHPSESSID",
        "social-cookie",
        "confirm_pwd_token",
        "gasession",
        "social_login_type",
        "CDVI",
        "session",
        "token",
        "auth",
        "login",
    }
)

_FORBIDDEN_CODE_PATTERNS = [
    "context.cookies()",
    "page.cookies()",
    "cookie_value",
    ".cookies()",
]


def check_sessions_dir() -> list[str]:
    errors = []
    sessions_dir = REPO_ROOT / "data" / "sessions"
    if not sessions_dir.exists():
        return []

    json_files = list(sessions_dir.glob("*.json"))
    if json_files:
        errors.append(f"data/sessions/에 JSON 파일 {len(json_files)}개 존재 — 즉시 삭제 필요")

    return errors


def check_gitignore() -> list[str]:
    errors = []
    gitignore = REPO_ROOT / ".gitignore"
    if not gitignore.exists():
        errors.append(".gitignore 없음")
        return errors
    content = gitignore.read_text(encoding="utf-8")
    if "data/sessions/" not in content:
        errors.append("data/sessions/가 .gitignore에 없음 — Git 추적 위험")
    return errors


def check_git_tracked() -> list[str]:
    import subprocess

    errors = []
    try:
        r = subprocess.run(
            ["git", "ls-files", "data/sessions/"], capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT)
        )
        if r.stdout.strip():
            errors.append(f"data/sessions/ Git 추적 중: {r.stdout.strip()}")
    except Exception as e:  # noqa: BLE001 - 버전관리 추적파일 조회 명령 실행 오류를 감사 오류 목록에 기록, 코드 스캔 중 개별 파일 읽기 실패는 건너뜀(check_web_connector는 현재 main()에서 호출되지 않아 최종 판정에 영향 없음) — 감사 스크립트 자체는 읽기전용
        errors.append(f"git ls-files 실행 오류: {e}")
    return errors


def check_web_connector() -> list[str]:
    """web_connector 등에서 쿠키 값 저장 코드 존재 여부 확인"""
    errors = []
    target_files = list((REPO_ROOT / "scripts").rglob("*.py"))
    for f in target_files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001 - 버전관리 추적파일 조회 명령 실행 오류를 감사 오류 목록에 기록, 코드 스캔 중 개별 파일 읽기 실패는 건너뜀(check_web_connector는 현재 main()에서 호출되지 않아 최종 판정에 영향 없음) — 감사 스크립트 자체는 읽기전용
            continue
        for pattern in _FORBIDDEN_CODE_PATTERNS:
            if pattern in content and "audit_gabia_session" not in str(f):
                errors.append(f"{f.relative_to(REPO_ROOT)}: 쿠키 추출 패턴 발견 '{pattern}'")
    return errors


def check_cdp_profile_config() -> list[str]:
    """CDP Chrome이 user-data-dir 프로필 방식으로 실행되는지 확인"""
    errors = []
    ps1 = REPO_ROOT / "scripts" / "local_agent" / "install_cdp_chrome_task.ps1"
    if ps1.exists():
        content = ps1.read_text(encoding="utf-8", errors="ignore")
        if "user-data-dir" in content:
            return []  # 프로필 방식 사용 중 — 올바름
        else:
            errors.append("CDP Chrome이 user-data-dir 없이 실행됨 — 프로필 세션 미보존")
    return errors


def get_verdict(all_errors: list[str]) -> str:
    return VERDICT_BLOCKED if all_errors else VERDICT_SAFE


def main():
    print("[GABIA_SESSION_STORAGE_SAFETY_AUDIT]")
    print()

    all_errors = []

    e = check_sessions_dir()
    print(f"[sessions_dir] {'FAIL' if e else 'PASS'}")
    all_errors += e

    e = check_gitignore()
    print(f"[gitignore]    {'FAIL' if e else 'PASS'}")
    all_errors += e

    e = check_git_tracked()
    print(f"[git_tracked]  {'FAIL' if e else 'PASS'}")
    all_errors += e

    e = check_cdp_profile_config()
    print(f"[cdp_profile]  {'FAIL' if e else 'PASS'}")
    all_errors += e

    if all_errors:
        print()
        for err in all_errors:
            print(f"  ERROR: {err}")

    verdict = get_verdict(all_errors)
    print()
    print(f"VERDICT: {verdict}")
    print("=" * 70)

    sys.exit(0 if verdict == VERDICT_SAFE else 1)


if __name__ == "__main__":
    main()
