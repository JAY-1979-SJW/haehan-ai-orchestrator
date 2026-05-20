"""naver_mail — P0 운영 가능 등급 받은편지함 수집/읽기.

기존 scripts/naver/mail_read 패키지의 CDP/PII/분류 헬퍼를 재사용.
본 패키지는 그 위에:
  - 전체 페이지네이션 종료 조건 (last-page 도달까지)
  - 안읽은 필터 모드
  - LIST_ONLY 기본 / FULL_READ 모드 + 안읽음 복구
  - 한국어 표시시간 → Asia/Seoul ISO 정규화
  - 영속 식별자(sn) 중복 제거
를 추가한다.

금지 동작 (모듈 차원에서 강제):
  - 발송/답장/삭제/이동/별표/라벨/첨부 다운로드/캡쳐 (정식 파이프라인)
"""
from . import (time_parser, read_state_guard, inbox_collector,
               folder_discovery, smart_folder_collector)

__all__ = ["time_parser", "read_state_guard", "inbox_collector",
           "folder_discovery", "smart_folder_collector"]
