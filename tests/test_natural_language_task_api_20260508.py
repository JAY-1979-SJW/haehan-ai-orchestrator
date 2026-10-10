"""tests/test_natural_language_task_api_20260508.py"""

from core.agent_runtime.runtime.universal.natural_language_task_api import (
    build_task_summary,
    check_result_safety,
    execute_natural_language_task,
)
from core.agent_runtime.runtime.universal.universal_safe_result import STATUS_FAILED

_SAFE_FIELDS = [
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
]

_BASE_PAGE = {
    "url": "https://notice.example.com/list",
    "title": "공지사항",
    "text_content": "공지사항 | 목록 | 검색 | 자료",
    "buttons": ["검색"],
    "links": ["notice1.html", "report.pdf"],
    "form_labels": [],
    "heading_texts": ["공지사항"],
}

_BLOG_PAGE = {
    "url": "https://blog.example.com/new",
    "title": "글쓰기",
    "text_content": "블로그 | 발행 | 임시저장",
    "buttons": ["발행", "임시저장"],
    "links": [],
    "form_labels": ["제목", "내용"],
    "heading_texts": ["새 글"],
}


def _dummy(action, domain="", **kwargs):
    return {"ok": True, "action": action}


def _assert_safe(result, label=""):
    violations = check_result_safety(result)
    assert not violations, f"[{label}] safe field 위반: {violations}"


def test_notice_intent_parsed():
    r = execute_natural_language_task(
        "공지사항 찾아서 요약해줘",
        page_data=_BASE_PAGE,
        runner_fn=_dummy,
        dry_run=True,
    )
    assert r.get("intent") in ("FIND_NOTICE", "SUMMARIZE_CONTENT", "SEARCH_SITE")
    _assert_safe(r, "notice_intent")


def test_download_manifest_intent():
    r = execute_natural_language_task(
        "첨부파일 후보를 찾아서 다운로드 manifest 만들어줘",
        page_data=_BASE_PAGE,
        runner_fn=_dummy,
        dry_run=True,
    )
    _assert_safe(r, "download_manifest")
    assert r.get("intent") == "DOWNLOAD_ATTACHMENTS"


def test_blog_draft_auto_allowed():
    r = execute_natural_language_task(
        "이 글을 블로그 초안으로 바꿔줘",
        page_data=_BASE_PAGE,
        runner_fn=_dummy,
        dry_run=True,
    )
    _assert_safe(r, "blog_draft")
    assert r.get("intent_auto_allowed") is True


def test_form_prepare_auto_allowed():
    page = {**_BASE_PAGE, "url": "https://apply.com/form", "title": "신청서", "form_labels": ["회사명"]}
    r = execute_natural_language_task(
        "이 폼은 제출 전까지 작성 준비만 해줘",
        page_data=page,
        runner_fn=_dummy,
        dry_run=True,
    )
    _assert_safe(r, "form_prepare")


def test_publish_permission_required():
    r = execute_natural_language_task(
        "이 글을 발행해줘",
        page_data=_BLOG_PAGE,
        permission_map={},
        runner_fn=_dummy,
        dry_run=True,
    )
    _assert_safe(r, "publish_perm")
    assert r["status"] in ("WARN_PERMISSION_REQUIRED", "WARN_AUTH_REQUIRED", "COMPLETED")


def test_publish_with_permission_executable():
    r = execute_natural_language_task(
        "이 글을 발행해줘",
        page_data=_BLOG_PAGE,
        permission_map={"publish_post": True},
        runner_fn=_dummy,
        dry_run=True,
    )
    _assert_safe(r, "publish_with_perm")


def test_all_safe_fields_false():
    r = execute_natural_language_task(
        "공지사항 요약해줘",
        page_data=_BASE_PAGE,
        runner_fn=_dummy,
        dry_run=True,
    )
    for f in _SAFE_FIELDS:
        assert r.get(f) is False, f"{f} != False"


def test_server_browser_used_false():
    r = execute_natural_language_task(
        "페이지 읽어줘",
        page_data=_BASE_PAGE,
        runner_fn=_dummy,
        dry_run=True,
    )
    assert r.get("server_browser_used") is False


def test_empty_instruction_returns_failed():
    r = execute_natural_language_task("", url="https://example.com")
    assert r["status"] == STATUS_FAILED


def test_no_page_data_and_no_url_returns_failed():
    r = execute_natural_language_task("공지 찾아줘")
    assert r["status"] == STATUS_FAILED


def test_url_only_works():
    r = execute_natural_language_task(
        "페이지 읽어줘",
        url="https://example.com",
        runner_fn=_dummy,
        dry_run=True,
    )
    _assert_safe(r, "url_only")
    assert "status" in r


def test_raw_instruction_in_result():
    r = execute_natural_language_task(
        "공지사항 찾아줘",
        page_data=_BASE_PAGE,
        runner_fn=_dummy,
        dry_run=True,
    )
    assert r.get("raw_instruction") == "공지사항 찾아줘"


def test_build_task_summary():
    r = execute_natural_language_task(
        "공지사항 요약해줘",
        page_data=_BASE_PAGE,
        runner_fn=_dummy,
        dry_run=True,
    )
    summary = build_task_summary(r)
    assert isinstance(summary, str)
    assert len(summary) > 0


def test_check_result_safety_clean():
    r = execute_natural_language_task(
        "공지사항 요약해줘",
        page_data=_BASE_PAGE,
        runner_fn=_dummy,
        dry_run=True,
    )
    violations = check_result_safety(r)
    assert violations == []


def test_check_result_safety_detects_violation():
    r = execute_natural_language_task(
        "페이지 읽어줘",
        page_data=_BASE_PAGE,
        runner_fn=_dummy,
        dry_run=True,
    )
    r["cookie_exported"] = True
    violations = check_result_safety(r)
    assert len(violations) > 0


def test_write_comment_permission_required():
    r = execute_natural_language_task(
        "댓글 달아줘",
        page_data={**_BASE_PAGE, "url": "https://forum.example.com/post"},
        permission_map={},
        runner_fn=_dummy,
        dry_run=True,
    )
    _assert_safe(r, "write_comment")
    assert r["status"] in ("WARN_PERMISSION_REQUIRED", "COMPLETED")


def test_delete_post_permission_required():
    r = execute_natural_language_task(
        "이 게시글 삭제해줘",
        page_data=_BLOG_PAGE,
        permission_map={},
        runner_fn=_dummy,
        dry_run=True,
    )
    _assert_safe(r, "delete_post")
    assert r["status"] in ("WARN_PERMISSION_REQUIRED", "COMPLETED")
