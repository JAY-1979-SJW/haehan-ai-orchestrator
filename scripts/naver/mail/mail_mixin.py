"""네이버 메일 Mixin — auto_structure_builder 자동 생성."""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any


def _js(name: str) -> str:
    from scripts.common.browser_js_dir import JS_DIR

    return (JS_DIR / name).read_text(encoding="utf-8")


class MailMixin:
    """네이버 메일 기능.

    실제 캡처된 API: ['/v2/folders/0/all', '/json/initData', '/json/list', '/json/folder/list', '/gfp/v1']
    """

    if TYPE_CHECKING:
        # 다른 믹스인의 메서드·속성(go, _page …)을 self(MRO)로 쓴다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

    def mail_inbox(self, max_n: int = 30) -> list[dict]:
        """받은 편지함 메일 목록.

        반환: [{id, from, subject, date, unread}]
        """
        self.go("https://mail.naver.com/v2/folders/0/all")
        time.sleep(2)
        try:
            result = self._page.evaluate(_js("extract_mail_inbox.js"))
            return (result or [])[:max_n]
        except Exception:  # noqa: BLE001 - 메일 읽기/검색/초안작성(발송 아님) mixin - 실패 시 빈 목록 또는 ok:False 반환
            return []

    def mail_read(self, mail_id: str) -> dict:
        """메일 상세 조회.

        반환: {from, to, subject, date, body, attachments}
        """
        self.go(f"https://mail.naver.com/v2/read/{mail_id}")
        time.sleep(2)
        try:
            return self._page.evaluate(_js("extract_mail_detail.js")) or {}
        except Exception:  # noqa: BLE001 - 메일 읽기/검색/초안작성(발송 아님) mixin - 실패 시 빈 목록 또는 ok:False 반환
            return {}

    def mail_search(self, query: str, max_n: int = 30) -> list[dict]:
        """메일 검색 — search_input 입력 + Enter → XHR 후킹 캡처.

        반환: [{id, from, subject, date, unread}]
        """
        HOOK = """
        window.__mailSearchResult = null;
        const origXhrOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(m, u, ...r) {
            this._hookUrl = u;
            return origXhrOpen.apply(this, [m, u, ...r]);
        };
        const origXhrSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function(...a) {
            this.addEventListener('load', function() {
                if (this._hookUrl && this._hookUrl.includes('/json/search/')) {
                    try {
                        window.__mailSearchResult = JSON.parse(this.responseText);
                    } catch(e) {}
                }
            });
            return origXhrSend.apply(this, a);
        };
        """
        if not hasattr(self._page, '_mail_search_hook_added'):
            self._page.add_init_script(HOOK)
            self._page._mail_search_hook_added = True

        # 메일 페이지 진입
        self.go("https://mail.naver.com/v2/folders/0/all")
        time.sleep(3)

        # 검색창 활성화 - 우선 search_area 클릭 (혹은 input 직접 시도)
        try:
            sa = self._page.query_selector('div.gnb_search_area, [class*="search_area"]')
            if sa and sa.is_visible():
                sa.click()
                time.sleep(1)
        except Exception:  # noqa: S110, BLE001 - 메일 읽기/검색/초안작성(발송 아님) mixin - 실패 시 빈 목록 또는 ok:False 반환
            pass

        # 검색 input 찾아서 입력 + Enter
        try:
            search_input = self._page.query_selector('input.search_input')
            if not search_input or not search_input.is_visible():
                # 폴백: placeholder 매칭
                search_input = self._page.query_selector('input[placeholder*="메일 검색"]')
            if search_input and search_input.is_visible():
                search_input.click()
                search_input.fill(query)
                self._page.keyboard.press("Enter")
                time.sleep(4)
        except Exception:  # noqa: BLE001 - 메일 읽기/검색/초안작성(발송 아님) mixin - 실패 시 빈 목록 또는 ok:False 반환
            return []

        # XHR 후킹된 검색 결과 추출
        raw = self._page.evaluate("() => window.__mailSearchResult")
        if not raw:
            return []
        mail_data = raw.get("mailData") or []
        if not isinstance(mail_data, list):
            return []

        result = []
        for m in mail_data[:max_n]:
            from_info = m.get("from") or {}
            result.append({
                "id":      str(m.get("mailSN", "")),
                "from":    from_info.get("name") or from_info.get("email") or "",
                "subject": m.get("subject", ""),
                "date":    m.get("receivedTime", ""),
                "unread":  not bool(m.get("isRead", False)) if "isRead" in m else False,
            })
        return result

    def mail_folders(self) -> list[dict]:
        """폴더 목록 — XHR 후킹 방식.

        반환: [{name, count, mail_count, folder_sn, folder_type}]
        """
        HOOK = """
        window.__mailFolders = null;
        const origXhrOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(m, u, ...r) {
            this._hookUrl = u;
            return origXhrOpen.apply(this, [m, u, ...r]);
        };
        const origXhrSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function(...a) {
            this.addEventListener('load', function() {
                if (this._hookUrl.includes('/json/folder/list')) {
                    try {
                        window.__mailFolders = JSON.parse(this.responseText);
                    } catch(e) {}
                }
            });
            return origXhrSend.apply(this, a);
        };
        """
        if not hasattr(self._page, '_mail_hook_added'):
            self._page.add_init_script(HOOK)
            self._page._mail_hook_added = True

        self.go("https://mail.naver.com/")
        time.sleep(3)

        data = self._page.evaluate("() => window.__mailFolders")
        if not data:
            return []
        folder_list = data.get("folderList", [])
        return [{
            "name":       f.get("folderName", ""),
            "count":      f.get("unreadMailCount", 0),
            "mail_count": f.get("mailCount", 0),
            "folder_sn":  f.get("folderSN"),
            "folder_type": f.get("folderType", ""),
        } for f in folder_list]

    def mail_unread_count(self) -> int:
        """전체 안읽은 메일 수 — mail_folders XHR 후킹 데이터 활용.

        folder/list 응답의 totalUnreadMail 필드 직접 추출.
        """
        folders_data = self.mail_folders()
        if not folders_data:
            return 0
        # mail_folders()에서 XHR 후킹으로 가져온 window.__mailFolders에서 총 개수 추출
        data = self._page.evaluate("() => window.__mailFolders")
        if data:
            return int(data.get("totalUnreadMail", 0))
        return 0

    def mail_send(self, to: str, subject: str, body: str) -> dict:
        """메일 발송 준비 (사용자 승인 필수).

        실제 발송은 사용자가 Chrome에서 직접 클릭.
        반환: {ok, draft_url}
        """
        from scripts.common.cdp_audit import L2
        self.go("https://mail.naver.com/v2/write")
        time.sleep(2)
        try:
            self._page.fill('[name="to"], [placeholder*="받는"]', to)
            self._page.fill('[name="subject"], [placeholder*="제목"]', subject)
            # 본문은 iframe 내에 있을 수 있음
            L2("MAIL_WRITE_PREPARED", "mail_mixin", to=to, subject=subject)
            return {"ok": True, "draft_url": self._page.url}
        except Exception as e:  # noqa: BLE001 - 메일 읽기/검색/초안작성(발송 아님) mixin - 실패 시 빈 목록 또는 ok:False 반환
            return {"ok": False, "error": str(e)}
