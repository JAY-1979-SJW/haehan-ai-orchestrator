"""Audit Google login entry policy.

Google automation must start from Google Home. Direct navigation to
accounts.google.com is allowed only as a user/browser redirect after the user
chooses sign-in, not as an automation entrypoint.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.agent_runtime.policy import site_entry_policy  # noqa: E402
from scripts.common.config import LOGIN_PROBE_URLS  # noqa: E402
from scripts.common.gates.work_mode_gate import build_google_work_mode_policy  # noqa: E402
from scripts.google import auth, managed_console  # noqa: E402

GOOGLE_HOME = "https://www.google.com/"
FORBIDDEN_ACCOUNTS = "https://accounts.google.com/signin"
BASELINE = ROOT / "docs" / "baseline" / "GOOGLE_AUTOMATION_BASELINE.md"
REQUIRED_BASELINE_PHRASES = (
    "Open Google Home: `https://www.google.com/`.",
    "google_work_mode",
    "`main`",
    "`background`",
    "The user handles only Google login/MFA and the final visible approval button.",
    "The agent must stop before the final Google Console Create/Save",
    "secret_action_mode",
    "raw secret, token, API key, OAuth client",
)


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def _audit_login_urls(failures):
    if auth.GOOGLE_LOGIN_URL != GOOGLE_HOME:
        failures.append(f"scripts.google.auth.GOOGLE_LOGIN_URL must be {GOOGLE_HOME!r}")

    if LOGIN_PROBE_URLS.get("google") != GOOGLE_HOME:
        failures.append(f"LOGIN_PROBE_URLS['google'] must be {GOOGLE_HOME!r}")

    try:
        site_entry_policy.assert_main_page_first(GOOGLE_HOME, site_key="google")
    except Exception as exc:  # noqa: BLE001 - 구글 홈 로그인 게이트 감사 — site_entry_policy.assert_main_page_first 가 예외를 던지면 failures 리스트에 추가해 감사를 실패시키는 fail-closed 경로.
        failures.append(f"Google Home must pass main-page-first gate: {exc}")

    try:
        site_entry_policy.assert_main_page_first(FORBIDDEN_ACCOUNTS, site_key="google")
    except ValueError:
        pass
    else:
        failures.append("accounts.google.com direct login URL must be blocked")


def _audit_enforcement_sources(failures):
    auth_src = _source("scripts/google/auth.py")
    if 'site_entry_policy.assert_main_page_first(GOOGLE_LOGIN_URL, site_key="google")' not in auth_src:
        failures.append("scripts/google/auth.py must enforce main-page-first before page.goto")

    login_session_src = _source("scripts/site_engine/login_session.py")
    if 'site_entry_policy.assert_main_page_first(LOGIN_PROBE_URLS[site], site_key="google")' not in login_session_src:
        failures.append("scripts/site_engine/login_session.py must enforce main-page-first for google probe")

    plan = managed_console.build_youtube_oauth_console_open_plan()
    sequence = plan.get("sequence") or []
    if not sequence or sequence[0].get("url") != GOOGLE_HOME:
        failures.append("managed Google console sequence must start from Google Home")


def _audit_work_mode(failures):
    missing_mode = build_google_work_mode_policy(None)
    if missing_mode.get("status") != "blocked" or missing_mode.get("blocked_reason") != "google_work_mode_required":
        failures.append("missing Google work mode must be blocked")

    main_mode = build_google_work_mode_policy("main")
    if main_mode.get("status") != "ok" or not main_mode.get("visible_browser_required"):
        failures.append("main Google work mode must require a visible browser")

    background_mode = build_google_work_mode_policy("background")
    if (
        background_mode.get("status") != "blocked"
        or background_mode.get("blocked_reason") != "background_mode_requires_explicit_user_approval"
    ):
        failures.append("background Google work mode must require explicit user approval")

    approved_background_mode = build_google_work_mode_policy("background", background_approved=True)
    if approved_background_mode.get("status") != "ok" or not approved_background_mode.get(
        "headless_or_background_allowed"
    ):
        failures.append("approved background Google work mode must be allowed")


def audit() -> list[str]:
    failures: list[str] = []

    _audit_login_urls(failures)

    _audit_enforcement_sources(failures)

    _audit_work_mode(failures)

    if not BASELINE.exists():
        failures.append("Google automation baseline document is missing")
    else:
        baseline_text = BASELINE.read_text(encoding="utf-8", errors="replace")
        missing = [phrase for phrase in REQUIRED_BASELINE_PHRASES if phrase not in baseline_text]
        if missing:
            failures.append("Google home login baseline lock missing phrase(s): " + ", ".join(missing))

    return failures


def main() -> int:
    failures = audit()
    print("Google home login gate audit")
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        print("RESULT=FAIL_GOOGLE_HOME_LOGIN_GATE")
        return 1
    print("RESULT=PASS_GOOGLE_HOME_LOGIN_GATE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
