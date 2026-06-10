"""gonobi 포스트 AI 분류기 (L5 Site Module).

Claude API로 포스트 본문을 읽고 우리 기준으로 재분류.
분류 기준: 소방기구 / LED조명 / 센서조명 / 인테리어조명 / 산업조명 / 시공사례 / 기타
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

OUR_CATEGORIES = [
    "소방기구",
    "LED조명",
    "센서조명",
    "인테리어조명",
    "산업조명",
    "시공사례",
    "기타",
]


def classify_post(title: str, body: str) -> str:
    """포스트를 우리 카테고리로 분류. 키워드 규칙 기반."""
    return _rule_based(title, body)


def _rule_based(title: str, body: str) -> str:
    """키워드 기반 분류."""
    text = (title + " " + body).lower()
    if any(k in text for k in ["소방", "감지기", "스프링클러", "유도등", "경보", "소화기", "방재"]):
        return "소방기구"
    if any(k in text for k in ["시공", "설치 완료", "현장", "공사", "시공사례"]):
        return "시공사례"
    if any(k in text for k in ["센서", "동작감지", "인체감지", "자동점등"]):
        return "센서조명"
    if any(k in text for k in ["공장", "산업", "작업등", "투광", "가로등", "보안등"]):
        return "산업조명"
    if any(k in text for k in ["펜던트", "벽등", "카페", "인테리어", "거실", "주방", "식탁", "무드"]):
        return "인테리어조명"
    if any(k in text for k in ["배선", "차단기", "스위치", "콘센트", "배선기구", "누전"]):
        return "배선기구"
    if any(k in text for k in ["led", "조명", "등기구", "직부", "매입", "형광"]):
        return "LED조명"
    return "기타"
