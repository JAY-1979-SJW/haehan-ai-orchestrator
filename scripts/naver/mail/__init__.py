"""naver_mail — P0 운영 가능 등급 받은편지함 수집/읽기.

기존 scripts/naver/mail/read 패키지의 CDP/PII/분류 헬퍼를 재사용.
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

from scripts.naver.mail.analysis import (
    action_item_dashboard,
    business_report,
    unknown_classification_rules,
)
from scripts.naver.mail.collection import (
    background_runner,
    folder_discovery,
    folder_policy,
    folder_profile,
    inbox_collector,
    smart_folder_collector,
)
from scripts.naver.mail.processing import (
    batch_runner,
    body_pipeline_v2,
    read_state_guard,
    unread_audit,
)
from scripts.naver.mail.utilities import (
    pii_mask,
    settings_panel,
    time_parser,
)


def send_mail(page, to: str = "", subject: str = "", body: str = "", *, force: bool = False, **metadata) -> None:
    """네이버 메일 발송 — 승인 게이트를 page 접근보다 먼저 통과해야 함.

    이 패키지는 설계상 발송을 모듈 차원에서 막는다(위 docstring "금지 동작" 참고).
    승인 게이트(naver_mail_send)를 통과하지 못하면 GateBlocked 로 여기서 끝나고,
    설령 강제 승인(force=True)돼도 실제 발송 로직은 아직 구현돼 있지 않다 —
    2026-09-29 defect_index #39(#37/#38 과 동일 계열: 이 함수 자체가 존재한 적이
    없어서 호출부가 AttributeError 로 죽던 걸, 존재는 하되 정직하게 막히도록 고침).
    """
    read_state_guard.assert_action_allowed("send", force=force, **metadata)
    raise NotImplementedError("naver_mail_send_not_implemented — 승인 게이트만 있고 실제 발송 로직은 미구현")


__all__ = [
    "action_item_dashboard",
    "background_runner",
    "batch_runner",
    "body_pipeline_v2",
    "business_report",
    "folder_discovery",
    "folder_policy",
    "folder_profile",
    "inbox_collector",
    "pii_mask",
    "read_state_guard",
    "send_mail",
    "settings_panel",
    "smart_folder_collector",
    "time_parser",
    "unknown_classification_rules",
    "unread_audit",
]
