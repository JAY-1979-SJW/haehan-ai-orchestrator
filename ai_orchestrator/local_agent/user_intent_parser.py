"""User Intent Parser — 자연어 지시를 실행 가능한 intent로 변환한다."""
from __future__ import annotations

from typing import Any

# intent 상수
INTENT_READ_PAGE            = "READ_PAGE"
INTENT_SEARCH_SITE          = "SEARCH_SITE"
INTENT_FIND_NOTICE          = "FIND_NOTICE"
INTENT_DOWNLOAD_ATTACHMENTS = "DOWNLOAD_ATTACHMENTS"
INTENT_SUMMARIZE_CONTENT    = "SUMMARIZE_CONTENT"
INTENT_EXTRACT_TABLE        = "EXTRACT_TABLE"
INTENT_GENERATE_BLOG_DRAFT  = "GENERATE_BLOG_DRAFT"
INTENT_PREPARE_FORM         = "PREPARE_FORM"
INTENT_WRITE_POST           = "WRITE_POST"
INTENT_WRITE_COMMENT        = "WRITE_COMMENT"
INTENT_PUBLISH_POST         = "PUBLISH_POST"
INTENT_UPDATE_POST          = "UPDATE_POST"
INTENT_DELETE_POST          = "DELETE_POST"
INTENT_SEND_MESSAGE         = "SEND_MESSAGE"
INTENT_SUBMIT_FORM          = "SUBMIT_FORM"
INTENT_UNKNOWN              = "UNKNOWN"

_ALL_INTENTS = [
    INTENT_READ_PAGE, INTENT_SEARCH_SITE, INTENT_FIND_NOTICE,
    INTENT_DOWNLOAD_ATTACHMENTS, INTENT_SUMMARIZE_CONTENT, INTENT_EXTRACT_TABLE,
    INTENT_GENERATE_BLOG_DRAFT, INTENT_PREPARE_FORM, INTENT_WRITE_POST,
    INTENT_WRITE_COMMENT, INTENT_PUBLISH_POST, INTENT_UPDATE_POST,
    INTENT_DELETE_POST, INTENT_SEND_MESSAGE, INTENT_SUBMIT_FORM, INTENT_UNKNOWN,
]

# intent별 AUTO_ALLOWED 여부
_INTENT_AUTO_ALLOWED = frozenset([
    INTENT_READ_PAGE, INTENT_SEARCH_SITE, INTENT_FIND_NOTICE,
    INTENT_DOWNLOAD_ATTACHMENTS, INTENT_SUMMARIZE_CONTENT, INTENT_EXTRACT_TABLE,
    INTENT_GENERATE_BLOG_DRAFT, INTENT_PREPARE_FORM,
])

# keyword → intent 매핑 (순서 중요: 구체적인 것 먼저)
_INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    (INTENT_FIND_NOTICE,          ["공지사항", "공지", "notice", "announcement", "알림"]),
    (INTENT_DOWNLOAD_ATTACHMENTS, ["첨부파일", "다운로드", "download", "파일 받", "자료 받"]),
    (INTENT_EXTRACT_TABLE,        ["표", "table", "목록 추출", "리스트 추출", "데이터 추출"]),
    (INTENT_SUMMARIZE_CONTENT,    ["요약", "summarize", "정리", "핵심", "요점"]),
    (INTENT_GENERATE_BLOG_DRAFT,  ["블로그 글", "blog 글", "블로그 초안", "블로그로", "포스팅"]),
    (INTENT_PREPARE_FORM,         ["폼", "form", "입력 준비", "작성 준비", "제출 전까지"]),
    (INTENT_WRITE_COMMENT,        ["댓글", "comment", "답글", "reply"]),
    (INTENT_DELETE_POST,          ["삭제", "delete", "지워", "제거"]),
    (INTENT_UPDATE_POST,          ["수정", "edit", "업데이트", "update", "고쳐", "편집"]),
    (INTENT_PUBLISH_POST,         ["발행", "publish", "게시", "올려", "올려줘", "등록"]),
    (INTENT_WRITE_POST,           ["글 써", "글쓰기", "글 작성", "post 작성", "글을 써"]),
    (INTENT_SEND_MESSAGE,         ["메시지", "message", "메일", "mail", "전송", "보내줘"]),
    (INTENT_SUBMIT_FORM,          ["제출", "submit", "신청", "apply"]),
    (INTENT_SEARCH_SITE,          ["검색", "search", "찾아줘", "찾아", "find"]),
    (INTENT_READ_PAGE,            ["읽어", "페이지", "page", "내용 확인", "확인해줘", "보여줘"]),
]


def _extract_target(instruction: str) -> str:
    """지시문에서 대상을 간단히 추출."""
    for kw in ["에서", "의", "을", "를", "이", "가"]:
        idx = instruction.find(kw)
        if idx > 2:
            return instruction[:idx].strip()
    return instruction[:30].strip()


def _extract_constraints(instruction: str) -> dict[str, Any]:
    constraints: dict[str, Any] = {}
    inst_lower = instruction.lower()

    if any(kw in inst_lower for kw in ["읽기만", "읽어만", "read-only", "readonly", "조회만"]):
        constraints["readonly"] = True

    for num_str in ["10", "20", "5", "3", "1"]:
        if num_str in instruction:
            try:
                constraints["count"] = int(num_str)
                break
            except ValueError:
                pass

    if any(kw in inst_lower for kw in ["오늘", "today", "최신", "새로", "new", "recent"]):
        constraints["recent_only"] = True

    return constraints


def parse_intent(instruction: str) -> dict[str, Any]:
    """
    자연어 지시를 intent dict로 변환.
    반환:
      intent: str
      target: str
      constraints: dict
      auto_allowed: bool
      raw_instruction: str
    """
    if not instruction or not instruction.strip():
        return {
            "intent": INTENT_UNKNOWN,
            "target": "",
            "constraints": {},
            "auto_allowed": False,
            "raw_instruction": instruction,
        }

    inst_lower = instruction.lower()
    matched_intent = INTENT_UNKNOWN

    for intent, keywords in _INTENT_PATTERNS:
        if any(kw.lower() in inst_lower for kw in keywords):
            matched_intent = intent
            break

    return {
        "intent": matched_intent,
        "target": _extract_target(instruction),
        "constraints": _extract_constraints(instruction),
        "auto_allowed": matched_intent in _INTENT_AUTO_ALLOWED,
        "raw_instruction": instruction,
    }


def is_auto_allowed_intent(intent: str) -> bool:
    return intent in _INTENT_AUTO_ALLOWED


def requires_permission(intent: str) -> bool:
    return intent in (
        INTENT_WRITE_POST, INTENT_WRITE_COMMENT, INTENT_PUBLISH_POST,
        INTENT_UPDATE_POST, INTENT_DELETE_POST, INTENT_SEND_MESSAGE, INTENT_SUBMIT_FORM,
    )
