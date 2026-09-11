"""QThread 기반 폴링 워커 — 설정된 간격마다 최근 게시물의 댓글을 확인해 키워드 매칭 시 DM 발송."""

from __future__ import annotations

from dataclasses import dataclass

from connectors.ig_api import IgApiError, get_comments, get_recent_media, send_private_reply
from PyQt6.QtCore import QThread, pyqtSignal

from core.keyword_matcher import KeywordRule, find_matching_rule
from core.processed_store import is_processed, mark_processed


@dataclass
class PollerConfig:
    ig_user_id: str
    token: str
    interval_seconds: int
    media_limit: int
    rules: list[KeywordRule]
    dm_message: str


class CommentPoller(QThread):
    log_message = pyqtSignal(str)
    dm_sent = pyqtSignal(str, str)  # (username, comment_text)
    error_occurred = pyqtSignal(str)

    def __init__(self, config: PollerConfig):
        super().__init__()
        self.config = config
        self._running = False

    def run(self) -> None:
        self._running = True
        while self._running:
            try:
                self._poll_once()
            except IgApiError as e:
                self.error_occurred.emit(str(e))
            except Exception as e:  # 폴링 루프는 예외로 죽지 않고 계속 돈다
                self.error_occurred.emit(f"예상치 못한 오류: {e}")

            self._sleep_interruptible(self.config.interval_seconds)

    def stop(self) -> None:
        self._running = False

    def _sleep_interruptible(self, seconds: int) -> None:
        for _ in range(seconds * 10):
            if not self._running:
                return
            self.msleep(100)

    def _poll_once(self) -> None:
        cfg = self.config
        self.log_message.emit("새 댓글 확인 중...")
        media_list = get_recent_media(cfg.ig_user_id, cfg.token, limit=cfg.media_limit)

        checked = 0
        sent = 0
        for media in media_list:
            comments = get_comments(media["id"], cfg.token)
            for comment in comments:
                checked += 1
                comment_id = comment["id"]
                if is_processed(comment_id):
                    continue

                rule = find_matching_rule(comment.get("text", ""), cfg.rules)
                if rule is None:
                    continue

                try:
                    send_private_reply(cfg.ig_user_id, comment_id, cfg.dm_message, cfg.token)
                    mark_processed(comment_id, rule.keyword)
                    sent += 1
                    self.dm_sent.emit(comment.get("username", "?"), comment.get("text", ""))
                except IgApiError as e:
                    # 7일 경과 댓글 등 개별 발송 실패는 다음 댓글로 넘어간다(전체 폴링을 죽이지 않음)
                    self.log_message.emit(f"DM 발송 실패 (댓글 {comment_id}): {e}")

        self.log_message.emit(f"확인 완료 — 댓글 {checked}개 중 {sent}건 DM 발송")
