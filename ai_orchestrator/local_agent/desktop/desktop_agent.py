"""카카오 데스크톱 모니터링·요약·분류 에이전트."""
from __future__ import annotations

from .mixins import KakaoworkMixin, KakaotalkMixin
from .download_watcher import DownloadWatcher, scan_existing


class DesktopAgent(KakaoworkMixin, KakaotalkMixin):
    """카카오워크/카카오톡 모니터링·요약·분류 전담.

    송수신은 사용자가 직접 담당. AI는 읽기·분석만.
    """

    def __init__(self, watch_downloads: bool = True):
        self._watcher: DownloadWatcher | None = None
        self._watch_downloads = watch_downloads

    def __enter__(self):
        if self._watch_downloads:
            self._watcher = DownloadWatcher()
            self._watcher.start()
        return self

    def __exit__(self, *_):
        if self._watcher:
            self._watcher.stop()

    def full_report(self) -> dict:
        """전체 상태 리포트."""
        kw_rooms = self.kakaowork_list_rooms()
        kw_unread = [r for r in kw_rooms if r["unread_count"] > 0]

        kt_data = self.kakaotalk_load_export()
        kt_msgs = kt_data.get("messages", [])
        kt_summary = ""
        if kt_msgs:
            try:
                from .summarizer import summarize_messages
                kt_summary = summarize_messages(kt_msgs[-50:])
            except Exception:
                kt_summary = f"메시지 {len(kt_msgs)}건"

        recent_downloads = scan_existing()[:20]

        return {
            "kakaowork_rooms": kw_rooms,
            "kakaowork_unread": kw_unread,
            "kakaotalk_room": kt_data.get("room_name", ""),
            "kakaotalk_message_count": len(kt_msgs),
            "kakaotalk_summary": kt_summary,
            "recent_downloads": recent_downloads,
        }
