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

구조:
  collection/  — inbox_collector, smart_folder_collector, folder_discovery, folder_profile, folder_policy, background_runner
  processing/  — body_pipeline_v2, batch_runner, read_state_guard, unread_audit
  analysis/    — business_report, action_item_dashboard, unknown_classification_rules
  utilities/   — pii_mask, time_parser, settings_panel
"""
from scripts.naver.mail.collection import (
    inbox_collector,
    smart_folder_collector,
    folder_discovery,
    folder_profile,
    folder_policy,
    background_runner,
)
from scripts.naver.mail.utilities import (
    time_parser,
    pii_mask,
    settings_panel,
)
from scripts.naver.mail.processing import (
    read_state_guard,
    unread_audit,
    body_pipeline_v2,
    batch_runner,
)
from scripts.naver.mail.analysis import (
    business_report,
    action_item_dashboard,
    unknown_classification_rules,
)

__all__ = [
    "time_parser", "read_state_guard", "inbox_collector",
    "folder_discovery", "smart_folder_collector",
    "folder_policy", "folder_profile", "settings_panel",
    "pii_mask", "unread_audit", "body_pipeline_v2",
    "batch_runner", "business_report", "action_item_dashboard",
    "unknown_classification_rules", "background_runner",
]
