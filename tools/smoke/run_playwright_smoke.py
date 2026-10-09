"""
Playwright 로컬 smoke 테스트 실행 스크립트

안전한 URL(about:blank, data URL, 로컬 HTML)만 사용한다.
외부 인증 사이트에 접속하지 않는다.
사용: python tools/smoke/run_playwright_smoke.py
"""

from __future__ import annotations

import pathlib
import sys

# haehan-root-bootstrap: 정본 paths 를 import 하기 전이라 루트를 직접 찾는다 — 폴더가 옮겨져도 깨지지 않게 pyproject.toml 이 있는 상위 폴더를 찾는다
_REPO_ROOT = next(p for p in pathlib.Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ai_orchestrator.contracts.local_task_protocol import build_task  # noqa: E402
from core.agent_runtime.runtime.playwright.playwright_bootstrap import (  # noqa: E402
    PLAYWRIGHT_READY,
    check_playwright_status,
)

_FIXTURE_PATH = pathlib.Path(_REPO_ROOT) / "tests" / "fixtures" / "local_agent_safe_smoke_page.html"


def _fixture_url() -> str:
    return _FIXTURE_PATH.as_uri()


def _run_smoke() -> list[dict]:
    from core.agent_runtime.runtime.playwright.playwright_runner import run_task

    results = []

    cases = [
        ("about:blank", "open_url"),
        ("data:text/html,<h1>smoke</h1>", "read_page"),
        (_fixture_url(), "open_url"),
        (_fixture_url(), "read_page"),
        (_fixture_url(), "extract_text"),
        (_fixture_url(), "extract_table"),
        (_fixture_url(), "capture_screenshot"),
        (_fixture_url(), "detect_login_status"),
        ("", "wait_for_user_auth"),
    ]

    for url, action in cases:
        task = build_task(action=action, target_url=url, domain="smoke")
        if action == "extract_text":
            task.setdefault("metadata", {})["selector"] = "h1"
        result = run_task(task)
        ok = result.get("ok", False)
        status = result.get("status", "")
        label = f"{action:<22} {url[:40]}"
        mark = "✓" if ok else "✗"
        print(f"  {mark} {label}  → {status}")
        results.append(result)

    return results


def main() -> int:
    print("=== Playwright 로컬 smoke 테스트 ===\n")

    bootstrap = check_playwright_status()
    if bootstrap["status"] != PLAYWRIGHT_READY:
        print(f"✗ Playwright 준비 안 됨: {bootstrap['message_ko']}")
        print("  먼저 check_playwright_bootstrap.py를 실행하세요.")
        return 1

    print(f"Playwright {bootstrap['package_version']} 준비 완료.\n")

    if not _FIXTURE_PATH.exists():
        print(f"✗ fixture 없음: {_FIXTURE_PATH}")
        print("  tests/fixtures/local_agent_safe_smoke_page.html 파일이 필요합니다.")
        return 1

    print("smoke 케이스 실행:\n")
    results = _run_smoke()

    passed = sum(1 for r in results if r.get("ok") or r.get("status") in ("WAITING_USER_AUTH",))
    total = len(results)
    print(f"\n결과: {passed}/{total} 통과")

    if passed == total:
        print("✓ 모든 smoke 케이스 통과.")
        return 0
    else:
        print("✗ 일부 실패. 위 항목을 확인하세요.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
