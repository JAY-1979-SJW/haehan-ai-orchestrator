"""네이버 블로그 UI 셀렉터 단일 관리 (독립 앱 사본, 원본: scripts/naver/blog/page_selectors.py, 0줄 변경).

Naver UI 변경 시 이 파일만 수정한다.
실검증 날짜를 각 섹션 주석에 명시한다.

적용 범위:
  - blog_mixin_write.py (PostView 상호작용)
  - blog_mixin_read.py  (PostView/PostList 읽기)
  - scripts.naver.blog.core.writer (SE3 에디터 글쓰기)
"""

from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════════
# 공통 — iframe
# ══════════════════════════════════════════════════════════════════════════════

# blog.naver.com/ID/logNo 는 mainFrame(name='mainFrame') iframe 내부 렌더링
# PostWriteForm.naver 는 iframe 미사용 (SE3 메인 문서 직접 렌더링)
MAINFRAME_NAME = "mainFrame"

# ══════════════════════════════════════════════════════════════════════════════
# SE3 에디터 (PostWriteForm.naver)  — 실검증 2026-05-19
# ══════════════════════════════════════════════════════════════════════════════

EDITOR_TITLE = ".se-section-documentTitle"
EDITOR_BODY = ".se-section-text"
EDITOR_DRAFT_POPUP = ".se-popup-alert"
EDITOR_DRAFT_CANCEL = ".se-popup-button-cancel"
EDITOR_PUBLISH_PANEL_BTN = "button[data-name='publish']"  # 발행 패널 열기
EDITOR_PUBLISH_CONFIRM = "[class*='confirm_btn']"  # 발행 최종 확인
EDITOR_TAG_INPUT = "input[placeholder*='태그']"
EDITOR_VISIBILITY_RADIO = "input[name='openType']"  # value=0~3

EDITOR_VISIBILITY_MAP = {
    "public": "2",  # 전체공개
    "neighbors": "1",  # 이웃공개
    "mutual": "3",  # 서로이웃
    "private": "0",  # 비공개
}

# ══════════════════════════════════════════════════════════════════════════════
# PostView — 공감(Like)  — 실검증 2026-06-23
# ══════════════════════════════════════════════════════════════════════════════

# <A class="u_likeit_list_button _button off">공감/칭찬/감사...</A>
# 첫 번째 요소 = "공감" 반응
LIKE_BUTTON = "a.u_likeit_list_button._button"

# ══════════════════════════════════════════════════════════════════════════════
# PostView — 댓글  — 실검증 2026-06-23
# ══════════════════════════════════════════════════════════════════════════════

# 댓글 목록/쓰기 영역 토글 ("댓글 N개" 링크) — 이걸 먼저 열어야 댓글쓰기 버튼이 노출됨
COMMENT_LIST_TOGGLE = "a._cmtList"
# 댓글쓰기 진입 버튼 (클릭 후 u_cbox_text 동적 로드) — COMMENT_LIST_TOGGLE 클릭 후에만 보임
COMMENT_WRITE_BTN = ".btn_write_comment"
# 댓글 입력창(contenteditable div, <input> 아님) / 제출 버튼 (naverComment 시스템, 동적 로드)
COMMENT_INPUT = ".u_cbox_text"
COMMENT_SUBMIT = ".u_cbox_btn_upload"
COMMENT_DELETE = ".u_cbox_btn_delete"

# ══════════════════════════════════════════════════════════════════════════════
# PostView — 게시글 삭제  — 실검증 2026-06-23
# ══════════════════════════════════════════════════════════════════════════════

# 삭제 트리거 (구형 UI — 새 SE3 게시글은 별도 확인 필요)
DELETE_TRIGGER = 'a[class*="_deletePost"]:not([class*="Confirm"]), a[class*="_openDelete"]'
# 삭제 확인 팝업 버튼
DELETE_CONFIRM = "#sendPostLayerBtn, a._deletePostConfirm"

# ══════════════════════════════════════════════════════════════════════════════
# PostView — 이웃 추가/삭제  — 실검증 2026-06-23
# ══════════════════════════════════════════════════════════════════════════════

# 사이드바 이웃추가 버튼: <a class="btn btn_add_nb _addBuddyPop ...">이웃추가</a>
NEIGHBOR_ADD_BTN = "a.btn_add_nb, a._addBuddyPop, a._buddy_popup_btn, a.btn_buddy"
# 팝업 내 확인 버튼:     <a class="btn_add_buddy _addBuddy _param(blogId)">이웃추가</a>
NEIGHBOR_ADD_CONFIRM = "a.btn_add_buddy._addBuddy:visible"
# 서로이웃 선택 (팝업 내)
NEIGHBOR_MUTUAL = 'input[value="서로이웃"], label:has-text("서로이웃")'
# 이웃삭제 버튼 (이웃 상태일 때만 노출)
NEIGHBOR_DEL_BTN = "a.btn_del_nb, a._delBuddyPop"

# ══════════════════════════════════════════════════════════════════════════════
# PostList / 블로그 홈 — 읽기
# ══════════════════════════════════════════════════════════════════════════════

PROFILE_IMG = ".profile_img img, .blog_profile img, .se-profile-image img"
VISITOR_TODAY = r"오늘\s*([\d,]+)"  # regex (body text)
VISITOR_TOTAL = r"전체\s*([\d,]+)"  # regex (body text)
NEIGHBOR_COUNT = r"전체\s*이웃\s*\n?([\d,]+)\s*명"  # regex (widget text)

# ══════════════════════════════════════════════════════════════════════════════
# 서비스 종료 확인 항목 (2026-06-23)
# ══════════════════════════════════════════════════════════════════════════════

DEPRECATED = {
    "guestbook": "GuestBook.naver — 방명록 서비스 종료 (2026-06-23 확인)",
    "scrap": "스크랩 버튼 — PostView UI에서 제거 (2026-06-23 확인)",
}
