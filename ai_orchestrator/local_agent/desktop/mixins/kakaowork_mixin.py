"""카카오워크 ConversationListBox 모니터링 Mixin."""
from __future__ import annotations

import threading
import time

from ..ui_helpers import find_window_by_process, deep_walk


class KakaoworkMixin:
    def kakaowork_window(self):
        """카카오워크 메인 창 핸들."""
        return find_window_by_process("Kakaowork.exe")

    def kakaowork_list_rooms(self) -> list[dict]:
        """채팅방 목록 스냅샷.

        반환: [{name, last_msg, unread_count, last_time}]
        """
        window = self.kakaowork_window()
        if not window:
            return []
        try:
            import uiautomation as auto
            listbox = window.ListControl(searchDepth=20, AutomationId="ConversationListBox")
            if not listbox.Exists(maxSearchSeconds=3):
                return []
        except Exception:
            return []

        rooms = []
        try:
            items = listbox.GetChildren()
        except Exception:
            return []

        for item in items:
            try:
                nodes = deep_walk(item, max_depth=4)
                texts = [n["name"] for n in nodes
                         if n["type"] == "TextControl" and n["name"] and not n["off"]]
                name = texts[0] if texts else ""
                last_msg = texts[1] if len(texts) > 1 else ""
                # 숫자로만 이루어진 텍스트 = 미읽음 카운트 후보
                unread_count = 0
                last_time = ""
                for t in texts[2:]:
                    if t.isdigit():
                        unread_count = int(t)
                    elif ":" in t or "오전" in t or "오후" in t or "어제" in t:
                        last_time = t
                rooms.append({
                    "name": name,
                    "last_msg": last_msg,
                    "unread_count": unread_count,
                    "last_time": last_time,
                })
            except Exception:
                continue

        return rooms

    def kakaowork_unread_rooms(self) -> list[dict]:
        """미읽음이 있는 채팅방만."""
        return [r for r in self.kakaowork_list_rooms() if r["unread_count"] > 0]

    def kakaowork_poll(self, interval: int = 30, on_new_unread=None) -> None:
        """주기적 폴링 (블로킹). 미읽음 변화 시 on_new_unread(rooms) 호출."""
        prev_unread: dict[str, int] = {}
        while True:
            try:
                rooms = self.kakaowork_list_rooms()
                changed = []
                for r in rooms:
                    name = r["name"]
                    cnt = r["unread_count"]
                    if cnt > 0 and prev_unread.get(name, 0) != cnt:
                        changed.append(r)
                    prev_unread[name] = cnt
                if changed and on_new_unread:
                    on_new_unread(changed)
            except Exception:
                pass
            time.sleep(interval)

    def kakaowork_start_poll(self, interval: int = 30, on_new_unread=None) -> threading.Thread:
        """백그라운드 스레드로 폴링 시작."""
        t = threading.Thread(
            target=self.kakaowork_poll,
            kwargs={"interval": interval, "on_new_unread": on_new_unread},
            daemon=True,
        )
        t.start()
        return t
