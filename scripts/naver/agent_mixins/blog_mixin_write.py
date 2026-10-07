"""blog_mixin 블로그 쓰기/상호작용 기능 (BlogWriteMixin).

write/edit/delete_post, upload_image, comment, like, neighbor 추가/삭제,
guestbook 작성, scrap. [docs/module_separation_standard.md]

DOM 구조 확인 (2026-06-23 실검증):
  - 상세 내용은 scripts/naver/blog/page_selectors.py 참고.
  - blog.naver.com/ID/logNo 는 mainFrame iframe 내부 렌더링.
    → 반드시 self._blog_frame() 사용 (BlogCommonMixin 제공).
  - 방명록·스크랩: 네이버 서비스 종료 (selectors.DEPRECATED 참고).

NOTE: blog_write_post / blog_edit_post 는 scripts.naver.blog.core.writer.BlogWriter 에
위임한다. 셀렉터는 scripts/naver/blog/page_selectors.py 에서 중앙 관리한다.
"""

from __future__ import annotations

import contextlib
import re
import time
from typing import TYPE_CHECKING, Any, ClassVar


class BlogWriteMixin:
    if TYPE_CHECKING:
        # 다른 믹스인의 메서드·속성(go, _page …)을 self(MRO)로 쓴다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

    # 사이트 계층(scripts.naver.blog 패키지)이 셀렉터 상수와 글쓰기 구현을 넣어 준다 — 엔진 쪽 믹스인(L4)이 사이트 모듈(L5)을 import 하지 않는다(T4: 주입)
    _blog_selectors: ClassVar[Any] = None
    _blog_writer: ClassVar[Any] = None

    @classmethod
    def configure_blog_write(cls, *, selectors: Any, writer: Any) -> None:
        """selectors: 셀렉터 상수 모듈(scripts/naver/blog/selectors.py), writer: write_post·BlogWriter 를 가진 모듈(core/writer.py)."""
        cls._blog_selectors = selectors
        cls._blog_writer = writer

    @property
    def _sel(self) -> Any:
        if self._blog_selectors is None:
            raise RuntimeError("블로그 셀렉터가 주입되지 않았다 — scripts.naver.blog 패키지를 통해 불러와야 한다")
        return self._blog_selectors

    @property
    def _writer(self) -> Any:
        if self._blog_writer is None:
            raise RuntimeError("블로그 글쓰기 구현이 주입되지 않았다 — scripts.naver.blog 패키지를 통해 불러와야 한다")
        return self._blog_writer

    # _blog_frame() 은 BlogCommonMixin 에서 상속

    def blog_write_post(
        self,
        title: str,
        body: str,
        category_no: str = "",
        tags: list[str] | None = None,
        image_paths: list[str] | None = None,
        is_public: bool = True,
    ) -> dict:
        """포스트 작성 — BlogWriter 에 위임."""
        visibility = "public" if is_public else "private"
        return self._writer.write_post(
            self._page,
            title=title,
            body=body,
            category=category_no or None,
            tags=tags,
            auto_tags=False,
            images=image_paths,
            visibility=visibility,
            require_approval=False,
        )

    def blog_edit_post(
        self, blog_id: str, log_no: str, title: str = "", body: str = "", tags: list[str] | None = None
    ) -> dict:
        """포스트 수정 — BlogWriter 에 위임."""
        url = f"https://blog.naver.com/PostModify.naver?blogId={blog_id}&logNo={log_no}"
        self.go(url)

        bw = self._writer.BlogWriter(self._page)
        # 임시저장 다이얼로그 처리 후 편집기 준비 대기
        try:
            self._page.wait_for_selector(".se-section-documentTitle", timeout=15000, state="visible")
        except Exception as e:  # noqa: BLE001 - 네이버 블로그 글쓰기/삭제/댓글/이웃추가/공감 자동화 믹스인 - 모든 except가 ok:False,error:str(e) 반환(성공 위장 없음), 실행은 상위 승인 흐름을 거친 뒤 호출됨
            return {"ok": False, "log_no": log_no, "error": f"편집기 로드 실패: {e}"}
        bw._handle_draft_dialog()

        try:
            if title:
                bw.set_title(title)
            if body:
                bw.write_body(body)
            if tags:
                bw.set_tags(tags)

            result = bw.save_draft()
            result["log_no"] = log_no
            return result
        except Exception as e:  # noqa: BLE001 - 네이버 블로그 글쓰기/삭제/댓글/이웃추가/공감 자동화 믹스인 - 모든 except가 ok:False,error:str(e) 반환(성공 위장 없음), 실행은 상위 승인 흐름을 거친 뒤 호출됨
            return {"ok": False, "log_no": log_no, "error": str(e)}

    def blog_delete_post(self, blog_id: str, log_no: str) -> dict:
        """포스트 삭제.

        실 DOM 확인(2026-06): PostView.naver 에서 sendPostLayer(confirm)는 존재하나
        삭제 트리거 버튼이 구형 게시글 뷰에서는 렌더링되지 않는 경우 있음.
        → PostDelete.naver 직접 POST 방식으로 폴백.
        """
        url = f"https://blog.naver.com/{blog_id}/{log_no}"
        self.go(url)
        time.sleep(2)

        fr = self._blog_frame()
        try:
            self._page.on("dialog", lambda dialog: dialog.accept())
            trigger = fr.locator(self._sel.DELETE_TRIGGER)
            if trigger.count() > 0:
                trigger.first.click(timeout=3000)
                time.sleep(0.5)
                fr.locator(self._sel.DELETE_CONFIRM).first.click(timeout=3000)
            else:
                fr.locator(self._sel.DELETE_CONFIRM).first.click(timeout=3000)
            time.sleep(1)
            return {"ok": True, "error": ""}
        except Exception as e:  # noqa: BLE001 - 네이버 블로그 글쓰기/삭제/댓글/이웃추가/공감 자동화 믹스인 - 모든 except가 ok:False,error:str(e) 반환(성공 위장 없음), 실행은 상위 승인 흐름을 거친 뒤 호출됨
            return {"ok": False, "error": str(e)}

    def blog_upload_image(self, image_path: str) -> dict:
        """이미지 업로드 (SE3 글쓰기 에디터 내).

        SE3 에디터가 열린 상태에서 호출해야 함.
        실 DOM(2026-06): input[type=file] 은 에디터 내부에 존재.
        """
        try:
            self._page.locator('input[type="file"]').first.set_input_files(image_path)
            time.sleep(2)
            img_url = self._page.evaluate("document.querySelector('.se-image-resource')?.src || ''")
            if img_url:
                return {"ok": True, "image_url": img_url, "error": ""}
            return {"ok": False, "image_url": "", "error": "이미지 URL 추출 실패"}
        except Exception as e:  # noqa: BLE001 - 네이버 블로그 글쓰기/삭제/댓글/이웃추가/공감 자동화 믹스인 - 모든 except가 ok:False,error:str(e) 반환(성공 위장 없음), 실행은 상위 승인 흐름을 거친 뒤 호출됨
            return {"ok": False, "image_url": "", "error": str(e)}

    def blog_write_comment(self, post_url: str, text: str) -> dict:
        """댓글 작성.

        실 DOM 확인(2026-09-11):
          - .commentbox_header(댓글쓰기 버튼을 담은 영역)는 기본 display:none —
            COMMENT_LIST_TOGGLE(._cmtList, "댓글 N개" 링크)을 먼저 클릭해야 열린다.
          - 댓글 입력창은 그 후 COMMENT_WRITE_BTN 클릭으로 동적 로드됨.
          - 입력창은 <input>이 아니라 contenteditable div — class: u_cbox_text
            (구 COMMENT_INPUT=".u_cbox_input" 는 이 위젯에 존재하지 않아 항상 timeout 났음).
          - placeholder 안내문(.u_cbox_guide)이 입력창 위에 겹쳐 pointer 이벤트를
            가로채므로 일반 click()은 실패 — dispatchEvent 방식 사용.
          - 제출 버튼 class: u_cbox_btn_upload (동일하게 overlay 이슈 있어 dispatch 사용).
        """
        self.go(post_url)
        time.sleep(3)

        fr = self._blog_frame()
        try:
            # 페이지 하단으로 스크롤하여 댓글 영역 노출
            fr.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

            fr.evaluate(
                f"() => {{ const l = document.querySelector('{self._sel.COMMENT_LIST_TOGGLE}'); "
                "if (l) l.dispatchEvent(new MouseEvent('click', {bubbles:true})); }"
            )
            time.sleep(2)

            fr.evaluate(
                f"() => {{ const b = document.querySelector('{self._sel.COMMENT_WRITE_BTN}'); "
                "if (b) b.dispatchEvent(new MouseEvent('click', {bubbles:true})); }"
            )
            time.sleep(1.5)

            comment_input = fr.locator(self._sel.COMMENT_INPUT).first
            comment_input.wait_for(state="visible", timeout=8000)
            comment_input.click(force=True)
            comment_input.type(text, delay=25)
            time.sleep(0.5)

            fr.locator(self._sel.COMMENT_SUBMIT).first.click(force=True)
            time.sleep(1.5)

            return {"ok": True, "error": ""}
        except Exception as e:  # noqa: BLE001 - 네이버 블로그 글쓰기/삭제/댓글/이웃추가/공감 자동화 믹스인 - 모든 except가 ok:False,error:str(e) 반환(성공 위장 없음), 실행은 상위 승인 흐름을 거친 뒤 호출됨
            return {"ok": False, "error": str(e)}

    def blog_delete_comment(self, post_url: str, comment_index: int = 0) -> dict:
        """댓글 삭제.

        실 DOM 확인(2026-06): u_cbox_btn_delete 는 댓글 로드 후 나타남 (동적).
        """
        self.go(post_url)
        time.sleep(3)

        fr = self._blog_frame()
        try:
            fr.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

            delete_btns = fr.locator(self._sel.COMMENT_DELETE).all()
            if comment_index < len(delete_btns):
                self._page.on("dialog", lambda dialog: dialog.accept())
                delete_btns[comment_index].click()
                time.sleep(1)
                return {"ok": True, "error": ""}
            return {"ok": False, "error": f"댓글 인덱스 초과 (총 {len(delete_btns)}개)"}
        except Exception as e:  # noqa: BLE001 - 네이버 블로그 글쓰기/삭제/댓글/이웃추가/공감 자동화 믹스인 - 모든 except가 ok:False,error:str(e) 반환(성공 위장 없음), 실행은 상위 승인 흐름을 거친 뒤 호출됨
            return {"ok": False, "error": str(e)}

    def blog_like_post(self, post_url: str) -> dict:
        """공감(좋아요) 클릭.

        실 DOM 확인(2026-06):
          - <A class="u_likeit_list_button _button off">공감/칭찬/감사...</A>
          - 첫 번째 요소 = "공감" 반응.
          - mainFrame iframe 내부에 있으므로 _blog_frame() 사용.
        """
        self.go(post_url)
        time.sleep(2)

        fr = self._blog_frame()
        try:
            like_btn = fr.locator(self._sel.LIKE_BUTTON).first
            like_btn.click()
            time.sleep(1)

            body_text = fr.evaluate("() => document.body.innerText")
            m = re.search(r"공감\s*\(?\s*(\d+)", body_text)
            like_count = int(m.group(1)) if m else 0

            return {"ok": True, "is_liked": True, "like_count": like_count, "error": ""}
        except Exception as e:  # noqa: BLE001 - 네이버 블로그 글쓰기/삭제/댓글/이웃추가/공감 자동화 믹스인 - 모든 except가 ok:False,error:str(e) 반환(성공 위장 없음), 실행은 상위 승인 흐름을 거친 뒤 호출됨
            return {"ok": False, "is_liked": False, "like_count": 0, "error": str(e)}

    def blog_unlike_post(self, post_url: str) -> dict:
        """공감 취소 (토글 방식 — 이미 공감된 상태에서 재클릭)."""
        return self.blog_like_post(post_url)

    def blog_add_neighbor(self, target_blog_url: str, is_mutual: bool = False) -> dict:
        """이웃 추가.

        실 DOM 확인(2026-06):
          - 사이드바 버튼: <a class="btn btn_add_nb _addBuddyPop ...">이웃추가</a>
          - 팝업 확인:    <a class="btn_add_buddy _addBuddy _param(blogId)">이웃추가</a>
          - mainFrame iframe 내부 위치.
        """
        self.go(target_blog_url)
        time.sleep(2)

        fr = self._blog_frame()
        try:
            fr.locator(self._sel.NEIGHBOR_ADD_BTN).first.click()
            time.sleep(1.5)

            if is_mutual:
                with contextlib.suppress(Exception):
                    fr.locator(self._sel.NEIGHBOR_MUTUAL).first.click()

            fr.locator(self._sel.NEIGHBOR_ADD_CONFIRM).first.click()
            time.sleep(1)

            return {"ok": True, "error": ""}
        except Exception as e:  # noqa: BLE001 - 네이버 블로그 글쓰기/삭제/댓글/이웃추가/공감 자동화 믹스인 - 모든 except가 ok:False,error:str(e) 반환(성공 위장 없음), 실행은 상위 승인 흐름을 거친 뒤 호출됨
            return {"ok": False, "error": str(e)}

    def blog_remove_neighbor(self, target_blog_url: str) -> dict:
        """이웃 삭제.

        실 DOM 확인(2026-06): 이웃 상태일 때만 btn_del_nb 버튼 노출.
        """
        self.go(target_blog_url)
        time.sleep(2)

        fr = self._blog_frame()
        try:
            self._page.on("dialog", lambda dialog: dialog.accept())
            fr.locator(self._sel.NEIGHBOR_DEL_BTN).first.click()
            time.sleep(1)
            return {"ok": True, "error": ""}
        except Exception as e:  # noqa: BLE001 - 네이버 블로그 글쓰기/삭제/댓글/이웃추가/공감 자동화 믹스인 - 모든 except가 ok:False,error:str(e) 반환(성공 위장 없음), 실행은 상위 승인 흐름을 거친 뒤 호출됨
            return {"ok": False, "error": str(e)}

    def blog_write_guestbook(self, blog_url: str, message: str) -> dict:
        """방명록 작성.

        ⚠ 네이버 블로그 방명록(GuestBook.naver) 기능은 서비스 종료됨 (2026-06 확인).
        GuestBook.naver 접근 시 "이전 화면으로" 페이지만 반환.
        이 메서드는 항상 ok=False 를 반환한다.
        """
        return {"ok": False, "error": self._sel.DEPRECATED["guestbook"]}

    def blog_scrap_post(self, post_url: str) -> dict:
        """포스트 스크랩.

        ⚠ 네이버 블로그 스크랩 버튼은 UI에서 제거됨 (2026-06 확인).
        공유 패널에 URL 복사만 남아 있음.
        이 메서드는 항상 ok=False 를 반환한다.
        """
        return {"ok": False, "error": self._sel.DEPRECATED["scrap"]}
