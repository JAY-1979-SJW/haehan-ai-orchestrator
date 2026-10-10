"""tests/test_user_intent_parser_20260508.py"""

from core.agent_runtime.runtime.universal.user_intent_parser import (
    INTENT_DELETE_POST,
    INTENT_DOWNLOAD_ATTACHMENTS,
    INTENT_FIND_NOTICE,
    INTENT_GENERATE_BLOG_DRAFT,
    INTENT_PREPARE_FORM,
    INTENT_PUBLISH_POST,
    INTENT_READ_PAGE,
    INTENT_SEARCH_SITE,
    INTENT_SEND_MESSAGE,
    INTENT_SUMMARIZE_CONTENT,
    INTENT_UNKNOWN,
    INTENT_UPDATE_POST,
    INTENT_WRITE_COMMENT,
    INTENT_WRITE_POST,
    is_auto_allowed_intent,
    parse_intent,
    requires_permission,
)


def test_find_notice_intent():
    r = parse_intent("공지사항 찾아서 요약해줘")
    assert r["intent"] == INTENT_FIND_NOTICE


def test_download_intent():
    r = parse_intent("첨부파일 받아서 정리해줘")
    assert r["intent"] == INTENT_DOWNLOAD_ATTACHMENTS


def test_blog_draft_intent():
    r = parse_intent("이 페이지 내용을 블로그 글로 만들어줘")
    assert r["intent"] == INTENT_GENERATE_BLOG_DRAFT


def test_prepare_form_intent():
    r = parse_intent("이 폼에 회사정보 입력하고 제출 전까지 준비해줘")
    assert r["intent"] == INTENT_PREPARE_FORM


def test_write_post_intent():
    r = parse_intent("이 카페에 글 써줘")
    assert r["intent"] in (INTENT_WRITE_POST, INTENT_WRITE_COMMENT)


def test_publish_intent():
    r = parse_intent("글을 발행해줘")
    assert r["intent"] == INTENT_PUBLISH_POST


def test_update_intent():
    r = parse_intent("이 글을 수정해서 다시 올려줘")
    assert r["intent"] == INTENT_UPDATE_POST


def test_delete_intent():
    r = parse_intent("이 게시글 삭제해줘")
    assert r["intent"] == INTENT_DELETE_POST


def test_send_message_intent():
    r = parse_intent("이 메시지 전송해줘")
    assert r["intent"] == INTENT_SEND_MESSAGE


def test_summarize_intent():
    r = parse_intent("이 페이지 내용 요약해줘")
    assert r["intent"] == INTENT_SUMMARIZE_CONTENT


def test_search_intent():
    r = parse_intent("이 사이트에서 데이터 검색해줘")
    assert r["intent"] == INTENT_SEARCH_SITE


def test_unknown_intent():
    r = parse_intent("xyz123 완전 모르는 명령")
    assert r["intent"] == INTENT_UNKNOWN


def test_empty_instruction():
    r = parse_intent("")
    assert r["intent"] == INTENT_UNKNOWN


def test_auto_allowed_intents():
    for intent in [
        INTENT_READ_PAGE,
        INTENT_FIND_NOTICE,
        INTENT_DOWNLOAD_ATTACHMENTS,
        INTENT_SUMMARIZE_CONTENT,
        INTENT_GENERATE_BLOG_DRAFT,
    ]:
        assert is_auto_allowed_intent(intent), f"{intent}이 AUTO_ALLOWED가 아님"


def test_permission_required_intents():
    for intent in [
        INTENT_WRITE_POST,
        INTENT_WRITE_COMMENT,
        INTENT_PUBLISH_POST,
        INTENT_UPDATE_POST,
        INTENT_DELETE_POST,
        INTENT_SEND_MESSAGE,
    ]:
        assert requires_permission(intent), f"{intent}이 permission required가 아님"


def test_recent_constraint():
    r = parse_intent("오늘 새로 올라온 자료 확인해줘")
    assert r["constraints"].get("recent_only") is True


def test_auto_allowed_field():
    r = parse_intent("공지사항 찾아줘")
    assert r["auto_allowed"] is True

    r2 = parse_intent("글을 발행해줘")
    assert r2["auto_allowed"] is False
