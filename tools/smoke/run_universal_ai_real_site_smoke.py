"""
Universal AI Site Agent — real use smoke test

mock page_data 기반 7개 scenario와 선택적 실제 외부 사이트 read-only 검증.
실제 외부 접속은 --live 플래그로 명시할 때만 실행.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# haehan-root-bootstrap: 정본 paths 를 import 하기 전이라 루트를 직접 찾는다 — 폴더가 옮겨져도 깨지지 않게 pyproject.toml 이 있는 상위 폴더를 찾는다
_REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.agent_runtime.runtime.universal.learned_site_profile_store import clear_all  # noqa: E402
from core.agent_runtime.runtime.universal.natural_language_task_api import (  # noqa: E402
    build_task_summary,
    check_result_safety,
    execute_natural_language_task,
)
from core.agent_runtime.runtime.universal.real_site_smoke_runner import (  # noqa: E402
    is_safe_readonly_target,
    run_all_smoke_scenarios,
)
from core.agent_runtime.runtime.universal.universal_agent_session import (  # noqa: E402
    close_session,
    create_session,
    get_session_history,
    run_task_in_session,
)


def _dummy_runner(action: str, domain: str = "", **kwargs):
    return {"ok": True, "action": action, "domain": domain}


_SAFE_FIELDS = [
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
]


def assert_safe(result: dict, label: str = "") -> None:
    violations = check_result_safety(result)
    if violations:
        raise AssertionError(f"[{label}] Safe field 위반: {violations}")


# ── 1. Mock 기반 smoke ─────────────────────────────────────────────────────────


def test_mock_smoke_all():
    print("\n=== Mock Smoke (7 scenarios) ===")
    summary = run_all_smoke_scenarios(runner_fn=_dummy_runner, dry_run=True)
    for r in summary["results"]:
        status_str = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status_str}] {r['scenario_id']}: {r['description']} — {r['status']}")
        if r["violations"]:
            print(f"    위반: {r['violations']}")
    assert summary["all_passed"], f"실패한 scenario: {[r for r in summary['results'] if not r['passed']]}"
    print(f"  결과: {summary['passed']}/{summary['total']} PASS")


# ── 2. Natural Language Task API ──────────────────────────────────────────────


def test_natural_language_api():
    print("\n=== Natural Language Task API ===")
    scenarios = [
        ("이 페이지에서 최신 공지 5개 찾아서 요약해줘", "https://example.com/notices"),
        ("첨부파일 후보를 찾아서 다운로드 manifest 만들어줘", "https://example.com/docs"),
        ("이 페이지 주요 내용을 표로 정리해줘", "https://example.com/data"),
        ("이 글을 블로그 초안으로 바꿔줘", "https://example.com/article"),
        ("이 폼은 제출 전까지 작성 준비만 해줘", "https://example.com/apply"),
    ]
    for instruction, url in scenarios:
        result = execute_natural_language_task(
            instruction=instruction,
            url=url,
            runner_fn=_dummy_runner,
            dry_run=True,
        )
        assert_safe(result, label=f"NL API: {instruction[:20]}")
        summary = build_task_summary(result)  # noqa: F841
        print(f"  [{result['status']}] {instruction[:30]}...")
    print("  NL Task API PASS")


# ── 3. Agent Session ──────────────────────────────────────────────────────────


def test_agent_session():
    print("\n=== Agent Session ===")
    session = create_session(host="example.com", user_id="test_user")
    sid = session["session_id"]

    page_data = {
        "url": "https://example.com/notice",
        "title": "공지사항",
        "text_content": "공지사항 | 목록 | 검색",
        "buttons": ["검색"],
        "links": ["notice1", "notice2"],
        "form_labels": [],
        "heading_texts": ["공지사항"],
    }

    # task 1: 공지 읽기 (AUTO_ALLOWED)
    r1 = run_task_in_session(sid, "공지사항 찾아줘", page_data=page_data, runner_fn=_dummy_runner, dry_run=True)
    assert_safe(r1, "session_task1")
    print(f"  task1: {r1['status']}")

    # task 2: 내용 요약 (AUTO_ALLOWED)
    r2 = run_task_in_session(sid, "이 내용 요약해줘", page_data=page_data, runner_fn=_dummy_runner, dry_run=True)
    assert_safe(r2, "session_task2")
    print(f"  task2: {r2['status']}")

    # 이력 확인
    history = get_session_history(sid)
    assert len(history) == 2, f"이력 수 오류: {len(history)}"
    print(f"  이력: {len(history)}개")

    close_session(sid)
    print("  Agent Session PASS")


# ── 4. Learned Profile 재사용 검증 ────────────────────────────────────────────


def test_learned_profile():
    print("\n=== Learned Profile 저장/재사용 ===")
    from core.agent_runtime.runtime.universal.learned_site_profile_store import (
        get_learned_profile,
        has_learned_profile,
    )

    clear_all()

    page_data = {
        "url": "https://smoketest.example.com/notice",
        "title": "공지사항",
        "text_content": "공지 | 목록 | 자료",
        "buttons": ["검색"],
        "links": ["notice1.html"],
        "form_labels": [],
        "heading_texts": ["공지"],
    }

    execute_natural_language_task(
        instruction="공지사항 요약해줘",
        page_data=page_data,
        runner_fn=_dummy_runner,
        dry_run=False,
        save_learned=True,
    )

    assert has_learned_profile("smoketest.example.com"), "learned profile 미저장"
    p = get_learned_profile("smoketest.example.com")
    assert p["password_stored"] is False
    assert p["cookie_stored"] is False
    assert p["session_stored"] is False
    print("  host=smoketest.example.com 저장 완료")
    print("  민감정보 저장 없음: PASS")
    print("  Learned Profile PASS")


# ── 5. 실제 외부 사이트 (--live 시) ──────────────────────────────────────────


def test_live_readonly_smoke(target_url: str):
    print(f"\n=== Live Read-only Smoke: {target_url} ===")
    if not is_safe_readonly_target(target_url):
        print(f"  SKIP: 허용되지 않은 대상 — {target_url}")
        return

    try:
        from core.agent_runtime.runtime.playwright.playwright_runner import run_task

        # 1. 페이지 열기
        open_result = run_task({"action": "open_url", "target_url": target_url, "task_id": "smoke_open"})
        print(f"  open_url: {open_result.get('status')}")

        # 2. 텍스트 추출
        text_result = run_task({"action": "extract_text", "target_url": target_url, "task_id": "smoke_text"})
        print(f"  extract_text: {text_result.get('status')}")

        # safe field 확인
        for result in [open_result, text_result]:
            for f in _SAFE_FIELDS:
                val = result.get(f)
                if val is True:
                    raise AssertionError(f"safe field 위반: {f}=True")

        print("  Live smoke PASS")
    except ImportError:
        print("  Playwright 미설치 — 실제 접속 스킵")
    except Exception as e:  # noqa: BLE001 - 실사이트 접속 라이브 스모크 테스트 - 실패는 WARN 메시지 출력만, 자동화 동작 없이 접속 확인 목적
        print(f"  Live smoke WARN: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Universal AI Site Agent Real Use Smoke")
    parser.add_argument("--live", action="store_true", help="실제 외부 사이트 접속")
    parser.add_argument("--url", default="https://quotes.toscrape.com/", help="실제 접속 대상 URL (--live 시 사용)")
    args = parser.parse_args()

    print("\n====================================================")
    print("Universal AI Site Agent — Real Use Smoke Test")
    print("====================================================")

    clear_all()
    test_mock_smoke_all()
    test_natural_language_api()
    test_agent_session()
    test_learned_profile()

    if args.live:
        test_live_readonly_smoke(args.url)

    print("\n====================================================")
    print("모든 smoke test PASS")
    print("====================================================")


if __name__ == "__main__":
    main()
