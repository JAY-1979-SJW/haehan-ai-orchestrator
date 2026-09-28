"""
scripts/hanafax/kst_date.py

영업문서(팩스/이메일)에 찍는 발신일자는 항상 **발송 시점의 실제 한국시간(KST)
날짜**여야 한다 — 소스 파일에 박제된 고정 날짜를 그대로 쓰면 하루 이상
걸리는 캠페인(예: KRAS 팩스 1,840건, 약 30시간)에서 날짜가 하루 이틀 전
그대로 찍혀 나간다(2026-09-07 실측 발견·수정).

이 모듈이 정본(SoT) — 문서에 날짜를 찍는 모든 코드는 datetime.now()를
직접 쓰지 말고 여기 함수를 통해서만 쓴다. tzinfo를 explicit하게 KST로
고정해서, 이 스크립트가 다른 시간대의 서버에서 실행되더라도(예: UTC 서버)
항상 한국 날짜 기준으로 찍히게 한다.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    """현재 시각을 KST(tz-aware)로 반환."""
    return datetime.now(KST)


def today_kr_str(fmt: str = "%Y. %m. %d.") -> str:
    """영업문서 상단 발신일자용 — 기본 포맷 '2026. 09. 08.' (기존 문서 양식과 동일)."""
    return now_kst().strftime(fmt)
