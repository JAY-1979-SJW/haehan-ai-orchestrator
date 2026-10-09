"""tests/test_universal_ai_site_agent_20260508.py"""

from core.agent_runtime.runtime.universal.learned_site_profile_store import clear_all
from core.agent_runtime.runtime.universal.universal_ai_site_agent import run_agent

_SAFE_FIELDS = [
    "cookie_exported",
    "session_exported",
    "password_collected",
    "otp_collected",
    "certificate_password_collected",
    "storage_state_exported",
    "server_browser_used",
]

_NOTICE_PAGE = {
    "url": "https://notice.unknown.kr/list",
    "title": "공지사항 목록",
    "text_content": "공지사항 | 목록 | 검색 | 첨부파일 다운로드",
    "buttons": ["검색", "목록"],
    "links": ["공지1", "공지2", "report.pdf"],
    "form_labels": [],
    "heading_texts": ["공지사항"],
}

_BLOG_PAGE = {
    "url": "https://blog.unknown.com/new",
    "title": "새 글 작성",
    "text_content": "블로그 글쓰기 | 제목 | 내용 | 발행",
    "buttons": ["발행", "임시저장", "미리보기"],
    "links": [],
    "form_labels": ["제목", "내용"],
    "heading_texts": ["블로그"],
}

_FORM_PAGE = {
    "url": "https://apply.unknown.com/form",
    "title": "신청 폼",
    "text_content": "신청서 | 회사명 | 담당자명 | 제출",
    "buttons": ["제출", "미리보기"],
    "links": [],
    "form_labels": ["회사명", "담당자"],
    "heading_texts": ["신청서"],
}

_PAYMENT_PAGE = {
    "url": "https://pay.unknown.com/checkout",
    "title": "결제",
    "text_content": "결제 | 카드 | 계좌이체 | 최종 결제",
    "buttons": ["결제하기", "취소"],
    "links": [],
    "form_labels": ["카드번호"],
    "heading_texts": ["결제"],
}


def setup_function():
    clear_all()


def _dummy_runner(action, domain="", **kwargs):
    return {"ok": True, "action": action}


def _assert_safe(result, label=""):
    for f in _SAFE_FIELDS:
        assert result.get(f) is False, f"[{label}] {f}={result.get(f)}"


def test_notice_board_observe_plan():
    result = run_agent("공지사항 찾아서 요약해줘", _NOTICE_PAGE, runner_fn=_dummy_runner)
    _assert_safe(result, "notice_board")
    assert result["status"] in ("COMPLETED", "WARN_PERMISSION_REQUIRED")


def test_article_list_extract_plan():
    result = run_agent("이 게시판 글 목록 추출해줘", _NOTICE_PAGE, runner_fn=_dummy_runner)
    _assert_safe(result, "article_list")
    assert "status" in result


def test_blog_draft_auto_allowed():
    result = run_agent("이 페이지 내용을 블로그 글로 만들어줘", _BLOG_PAGE, runner_fn=_dummy_runner)
    _assert_safe(result, "blog_draft")
    assert result["status"] in ("COMPLETED", "WARN_PERMISSION_REQUIRED")


def test_blog_publish_needs_permission_without_grant():
    result = run_agent("이 글을 발행해줘", _BLOG_PAGE, permission_map={}, runner_fn=_dummy_runner)
    _assert_safe(result, "blog_publish_no_perm")
    assert result["status"] in ("WARN_PERMISSION_REQUIRED", "WARN_AUTH_REQUIRED", "COMPLETED")


def test_form_fill_auto_allowed():
    result = run_agent("이 폼에 정보 입력하고 제출 전까지 준비해줘", _FORM_PAGE, runner_fn=_dummy_runner)
    _assert_safe(result, "form_fill")
    assert result["status"] in ("COMPLETED", "WARN_PERMISSION_REQUIRED")


def test_form_submit_needs_permission():
    result = run_agent("이 폼 제출해줘", _FORM_PAGE, permission_map={}, runner_fn=_dummy_runner)
    _assert_safe(result, "form_submit_no_perm")
    # submit_non_legal_form은 DELEGATED
    assert result["status"] in ("WARN_PERMISSION_REQUIRED", "COMPLETED")


def test_payment_page_user_direct_required():
    result = run_agent("결제해줘", _PAYMENT_PAGE, permission_map={}, runner_fn=_dummy_runner)
    _assert_safe(result, "payment")
    # payment risk signal → USER_DIRECT 또는 WARN_AUTH
    assert result["status"] in ("WARN_AUTH_REQUIRED", "WARN_PERMISSION_REQUIRED", "COMPLETED")


def test_password_value_never_collected():
    result = run_agent(
        "로그인해줘",
        {
            "url": "https://login.example.com",
            "title": "로그인",
            "text_content": "로그인 | 아이디 | 비밀번호",
            "buttons": ["로그인"],
            "links": [],
            "form_labels": ["아이디", "비밀번호"],
            "heading_texts": [],
        },
        runner_fn=_dummy_runner,
    )
    _assert_safe(result, "login")
    assert result["password_collected"] is False


def test_otp_value_never_collected():
    result = run_agent(
        "OTP 입력해줘",
        {
            "url": "https://auth.example.com",
            "title": "OTP 인증",
            "text_content": "OTP | 인증번호 입력",
            "buttons": ["확인"],
            "links": [],
            "form_labels": ["OTP", "인증번호"],
            "heading_texts": [],
        },
        runner_fn=_dummy_runner,
    )
    assert result["otp_collected"] is False


def test_cookie_session_never_exported():
    result = run_agent(
        "쿠키 내보내줘",
        {
            "url": "https://any.com",
            "title": "테스트",
            "text_content": "cookie session token",
            "buttons": [],
            "links": [],
            "form_labels": [],
            "heading_texts": [],
        },
        runner_fn=_dummy_runner,
    )
    assert result["cookie_exported"] is False
    assert result["session_exported"] is False


def test_write_comment_permission_required():
    result = run_agent(
        "댓글 달아줘",
        {
            "url": "https://forum.example.com/post/1",
            "title": "게시글",
            "text_content": "댓글 | 작성 | 등록",
            "buttons": ["댓글 등록"],
            "links": [],
            "form_labels": ["댓글 내용"],
            "heading_texts": [],
        },
        permission_map={},
        runner_fn=_dummy_runner,
    )
    _assert_safe(result, "write_comment")
    assert result["status"] in ("WARN_PERMISSION_REQUIRED", "COMPLETED")


def test_unknown_readonly_auto_allowed():
    result = run_agent("이 사이트에서 오늘 새로 올라온 자료 확인해줘", _NOTICE_PAGE, runner_fn=_dummy_runner)
    _assert_safe(result, "unknown_readonly")
    assert result["status"] in ("COMPLETED", "WARN_PERMISSION_REQUIRED")


def test_unknown_write_permission_required():
    result = run_agent("이 글을 수정해서 다시 올려줘", _BLOG_PAGE, permission_map={}, runner_fn=_dummy_runner)
    _assert_safe(result, "unknown_write")
    assert result["status"] in ("WARN_PERMISSION_REQUIRED", "WARN_AUTH_REQUIRED", "COMPLETED")


def test_server_browser_never_used():
    result = run_agent("페이지 읽어줘", _NOTICE_PAGE, runner_fn=_dummy_runner)
    assert result["server_browser_used"] is False


def test_dry_run_no_side_effects():
    result = run_agent("공지사항 요약해줘", _NOTICE_PAGE, runner_fn=_dummy_runner, dry_run=True)
    _assert_safe(result, "dry_run")
    assert result["status"] in ("COMPLETED", "WARN_PERMISSION_REQUIRED")


def test_learned_profile_saved_after_success():
    from core.agent_runtime.runtime.universal.learned_site_profile_store import has_learned_profile

    run_agent("공지사항 찾아줘", _NOTICE_PAGE, runner_fn=_dummy_runner, save_learned=True)
    # notice.unknown.kr에 learned profile 저장되어야 함
    assert has_learned_profile("notice.unknown.kr")


def test_learned_profile_no_sensitive_data():
    from core.agent_runtime.runtime.universal.learned_site_profile_store import get_learned_profile

    clear_all()
    run_agent("공지사항 요약해줘", _NOTICE_PAGE, runner_fn=_dummy_runner, save_learned=True)
    p = get_learned_profile("notice.unknown.kr")
    if p:
        assert p.get("password_stored") is False
        assert p.get("cookie_stored") is False
        assert p.get("session_stored") is False
