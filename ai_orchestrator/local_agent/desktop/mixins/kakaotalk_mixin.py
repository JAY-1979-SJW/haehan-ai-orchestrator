"""카카오톡 대화 내보내기 기반 Mixin."""
from __future__ import annotations

from pathlib import Path

from ..kakaotalk_export import (
    latest_export,
    parse_export_file,
    find_export_files,
)


class KakaotalkMixin:
    _kt_export_cache: dict | None = None
    _kt_export_path: Path | None = None

    def kakaotalk_load_export(self, path: Path | None = None) -> dict:
        """export 파일 파싱. path=None이면 가장 최근 파일 사용."""
        if path is None:
            path = latest_export()
        if path is None:
            return {"room_name": "", "saved_at": "", "messages": []}
        self._kt_export_path = path
        self._kt_export_cache = parse_export_file(path)
        return self._kt_export_cache

    def kakaotalk_messages(self, max_n: int = 100,
                            sender: str | None = None) -> list[dict]:
        """최근 메시지 반환. sender 지정 시 해당 발신자만."""
        if self._kt_export_cache is None:
            self.kakaotalk_load_export()
        msgs = (self._kt_export_cache or {}).get("messages", [])
        if sender:
            msgs = [m for m in msgs if m.get("sender") == sender]
        return msgs[-max_n:]

    def kakaotalk_export_path(self) -> Path | None:
        """현재 로드된 export 파일 경로."""
        return self._kt_export_path

    def kakaotalk_room_name(self) -> str:
        """현재 로드된 채팅방 이름."""
        if self._kt_export_cache is None:
            self.kakaotalk_load_export()
        return (self._kt_export_cache or {}).get("room_name", "")

    def kakaotalk_summary(self, max_n: int = 50) -> str:
        """최근 N개 메시지를 Claude API로 요약."""
        from ..summarizer import summarize_messages
        msgs = self.kakaotalk_messages(max_n=max_n)
        if not msgs:
            return "메시지 없음"
        return summarize_messages(msgs)

    def kakaotalk_list_exports(self) -> list[Path]:
        """발견된 모든 export 파일 목록 (최신순)."""
        return find_export_files()
