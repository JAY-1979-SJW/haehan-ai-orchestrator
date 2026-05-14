"""네이버 블로그 자동화"""
from __future__ import annotations

from typing import Any

from ..base import task_context, page_goto, page_wait_visible


def run(task: str, args: list[str]) -> None:
    """블로그 작업 실행.

    task: write, session-check
    """
    match task:
        case "write":
            _task_write(args)
        case _:
            print(f"  [오류] 알 수 없는 작업: {task}")


def _task_write(args: list[str]) -> None:
    """블로그 글 작성."""
    print("\n[작업] 네이버 블로그 글 작성")
    with task_context("blog-write", args) as page:
        page_goto(page, "https://blog.naver.com/new")
        page_wait_visible(page, "iframe, .se-wrap, #writeFormView", timeout=30000)
        print("  ✓ 블로그 편집기 로드 완료")
        print("""
브라우저에서:
  1. 제목과 본문을 입력하세요
  2. "발행" 버튼을 클릭하세요
        """)
        input("👉 작성 완료 후 Enter를 누르세요: ")
        print("  ✓ 세션 저장 완료")
