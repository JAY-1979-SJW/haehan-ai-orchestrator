"""
Universal AI Site Agent — smoke test (fixture 기반)

실제 외부 사이트 접속 없이 mock page_data로 동작을 검증한다.
"""
from __future__ import annotations

import sys
import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ai_orchestrator.local_agent.universal_ai_site_agent import run_agent
from ai_orchestrator.local_agent.learned_site_profile_store import clear_all


def _dummy_runner(action: str, domain: str = "", **kwargs):
    return {"ok": True, "action": action, "domain": domain}


_SAFE_FIELDS = [
    "cookie_exported", "session_exported", "password_collected",
    "otp_collected", "certificate_password_collected",
    "storage_state_exported", "server_browser_used",
]


def _assert_safe(result: dict, label: str) -> None:
    for f in _SAFE_FIELDS:
        assert result.get(f) is False, f"[{label}] safe field 위반: {f}={result.get(f)}"


def smoke_unknown_notice_board():
    result = run_agent(
        instruction="공지사항 찾아서 요약해줘",
        page_data={
            "url": "https://notice.unknown-site.kr/list",
            "title": "공지사항 목록",
            "text_content": "공지사항 | 목록 | 검색 | 첨부파일",
            "buttons": ["검색", "목록"],
            "links": ["공지사항 1", "공지사항 2"],
            "form_labels": [],
            "heading_texts": ["공지사항"],
        },
        runner_fn=_dummy_runner,
    )
    _assert_safe(result, "unknown_notice_board")
    assert result["status"] in ("COMPLETED", "WARN_PERMISSION_REQUIRED"), result["status"]
    print("[PASS] unknown notice board")


def smoke_unknown_blog_editor():
    result = run_agent(
        instruction="이 페이지 내용을 블로그 글로 만들어줘",
        page_data={
            "url": "https://blog.unknown-site.com/new",
            "title": "글쓰기",
            "text_content": "블로그 글쓰기 | 제목 | 내용 | 발행",
            "buttons": ["발행", "임시저장", "미리보기"],
            "links": [],
            "form_labels": ["제목", "내용"],
            "heading_texts": ["새 글 작성"],
        },
        runner_fn=_dummy_runner,
    )
    _assert_safe(result, "unknown_blog_editor")
    print(f"[PASS] unknown blog editor — status: {result['status']}")


def smoke_unknown_form():
    result = run_agent(
        instruction="이 폼에 정보 입력하고 제출 전까지 준비해줘",
        page_data={
            "url": "https://apply.unknown-site.com/form",
            "title": "신청 폼",
            "text_content": "신청 폼 | 회사명 | 담당자 | 제출",
            "buttons": ["제출", "미리보기"],
            "links": [],
            "form_labels": ["회사명", "담당자"],
            "heading_texts": ["신청서"],
        },
        runner_fn=_dummy_runner,
    )
    _assert_safe(result, "unknown_form")
    print(f"[PASS] unknown form — status: {result['status']}")


def smoke_unknown_download():
    result = run_agent(
        instruction="첨부파일 받아서 정리해줘",
        page_data={
            "url": "https://docs.unknown-site.com/list",
            "title": "자료실",
            "text_content": "자료실 | 다운로드 | 첨부파일",
            "buttons": ["다운로드", "검색"],
            "links": ["report.pdf", "data.xlsx"],
            "form_labels": [],
            "heading_texts": ["자료실"],
        },
        runner_fn=_dummy_runner,
    )
    _assert_safe(result, "unknown_download")
    assert result["status"] in ("COMPLETED", "WARN_PERMISSION_REQUIRED"), result["status"]
    print("[PASS] unknown download")


def smoke_permission_required_write():
    result = run_agent(
        instruction="이 글을 수정해서 다시 올려줘",
        page_data={
            "url": "https://cafe.unknown-site.com/post/123",
            "title": "게시글",
            "text_content": "게시글 수정 | 글쓰기 | 발행",
            "buttons": ["수정", "발행", "삭제"],
            "links": [],
            "form_labels": ["제목", "내용"],
            "heading_texts": ["게시글"],
        },
        permission_map={},  # 권한 없음
        runner_fn=_dummy_runner,
    )
    _assert_safe(result, "permission_required_write")
    assert result["status"] in ("WARN_PERMISSION_REQUIRED", "WARN_AUTH", "COMPLETED"), result["status"]
    print(f"[PASS] permission required write — status: {result['status']}")


def smoke_blocked_credential_action():
    """password_save는 BLOCKED — 실행되지 않아야 함."""
    from ai_orchestrator.local_agent.unknown_site_fallback_policy import evaluate_unknown_site
    from ai_orchestrator.local_agent.site_capability_matrix import GRADE_BLOCKED
    eval_result = evaluate_unknown_site("password_save")
    assert eval_result["grade"] == GRADE_BLOCKED
    assert eval_result["executable"] is False
    print("[PASS] blocked credential action")


def main():
    clear_all()
    print("\n=== Universal AI Site Agent Smoke Test ===\n")
    smoke_unknown_notice_board()
    smoke_unknown_blog_editor()
    smoke_unknown_form()
    smoke_unknown_download()
    smoke_permission_required_write()
    smoke_blocked_credential_action()
    print("\n모든 smoke test PASS")


if __name__ == "__main__":
    main()
