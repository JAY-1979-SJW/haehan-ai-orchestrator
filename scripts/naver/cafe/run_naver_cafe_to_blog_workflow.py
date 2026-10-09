"""
네이버 카페→블로그 콘텐츠 workflow 로컬 실행 스크립트

공통 LOCAL_PLAYWRIGHT task protocol만 사용.
네이버 전용 로그인 자동화 없음.
서버 외부 브라우저 없음.

허용:
- 카페 탐색/읽기 (AUTO_ALLOWED)
- 블로그 초안 생성 (AUTO_ALLOWED)
- 발행/댓글/글쓰기 (권한 부여 시 실행)

금지:
- 비밀번호 자동 입력
- OTP 자동 입력
- cookie/session export
- 무권한 발행
- 서버 외부 브라우저 실행

사용:
  python scripts/naver/cafe/run_naver_cafe_to_blog_workflow.py
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]  # scripts/naver/cafe/ → 저장소 루트(이동 전 scripts/local_agent/ 에서와 같은 값)
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.agent_runtime.runtime.playwright.playwright_bootstrap import (  # noqa: E402 - sys.path.insert 이후 로컬 import (레거시, 이번 작업과 무관)
    PLAYWRIGHT_READY,
    check_playwright_status,
)
from scripts.naver.cafe.naver_content_workflow_runner import (  # noqa: E402 - sys.path.insert 이후 로컬 import (레거시, 이번 작업과 무관)
    WORKFLOW_PASS,
    WORKFLOW_WARN_AUTH,
    WORKFLOW_WARN_PERMISSION,
    run_cafe_to_blog_workflow,
)

CAFE_URL = "https://cafe.naver.com/"
BLOG_DOMAIN = "blog.naver.com"
_REPORT_DIR = pathlib.Path(_REPO_ROOT) / "data" / "reports" / "local_agent"


def _save_report(report: dict) -> pathlib.Path:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _REPORT_DIR / f"naver_cafe_blog_workflow_{ts}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    return path


def main() -> None:
    print("=" * 60)
    print("네이버 카페→블로그 콘텐츠 workflow 실행")
    print(f"cafe: {CAFE_URL}")
    print("=" * 60)

    pw_status = check_playwright_status()
    if pw_status.get("status") != PLAYWRIGHT_READY:
        print(f"[WARN] Playwright 미설치: {pw_status}")
        report = {
            "run_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
            "final_status": "WARN_PLAYWRIGHT_NOT_INSTALLED",
            "playwright_status": pw_status,
            "server_browser_used": False,
            "blog_draft": None,
            "permission_required": ["blog_publish", "cafe_post_write", "cafe_comment_write"],
        }
    else:
        try:
            from core.agent_runtime.runtime.playwright.playwright_runner import run_task

            report = run_cafe_to_blog_workflow(
                cafe_url=CAFE_URL,
                cafe_search_query="",
                blog_domain=BLOG_DOMAIN,
                blog_permission_id=None,
                runner_fn=run_task,
                dry_run=True,
            )
        except Exception as exc:  # noqa: BLE001 - 네이버 카페→블로그 workflow 실행 - dry_run=True 고정, 비밀번호/OTP 자동입력·cookie export·무권한발행 전부 코드 docstring상 금지. except는 workflow 실행 자체의 실패를 WARN_EXCEPTION 상태로 리포트에 남기고 종료코드 2로 반영(숨기지 않음)
            report = {
                "run_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
                "final_status": f"WARN_EXCEPTION: {type(exc).__name__}: {str(exc)[:100]}",
                "server_browser_used": False,
                "blog_draft": None,
                "permission_required": [],
            }

    path = _save_report(report)
    print(f"\n[결과] final_status={report['final_status']}")
    print(f"[권한 필요] {report.get('permission_required', [])}")
    blog_draft = report.get("blog_draft")
    if isinstance(blog_draft, dict) and blog_draft:
        titles = blog_draft.get("title_candidates", [])
        print(f"[초안 제목 후보] {titles[:2]}")
    print(f"[리포트] {path}")

    status = report["final_status"]
    if status == WORKFLOW_PASS:
        sys.exit(0)
    elif status in (WORKFLOW_WARN_PERMISSION, WORKFLOW_WARN_AUTH):
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
