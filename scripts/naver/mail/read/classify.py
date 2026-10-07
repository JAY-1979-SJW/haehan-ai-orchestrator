"""발신자/제목 기반 메일 분류 — 순수 규칙 기반.

분류 라벨은 액션 우선순위와 연계:
  ACTION_REQUIRED — 판매자 대응/계정 유지 필수
  REVIEW         — SEO/약관 등 확인 필요
  INFO           — 단순 보안 알림/등록 알림
  CARD_NOTICE    — 카드사 약관/한도 안내
  PROMO          — 광고/뉴스레터
  OTHER          — 그 외
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClassifyResult:
    label: str
    priority: int  # 0(=긴급) ~ 9
    reason: str


# (label, priority, sender_substr, subject_kw)
_RULES = [
    ("ACTION_REQUIRED", 0,
     ["sp_improve@coupang.com", "smartstore_noreply@navercorp.com"],
     ["노출 정지", "휴면", "정지", "복원", "계정 정지"]),
    ("ACTION_REQUIRED", 1,
     ["@coupang.com", "@smartstore"], ["답변지연", "미답변", "확약서"]),
    ("REVIEW", 2,
     ["sc-noreply@google.com", "@google.com"],
     ["색인", "indexing", "Search Console", "수동 조치"]),
    ("INFO", 5,
     ["account_noreply@navercorp.com", "no-reply@accounts.google.com",
      "security@facebookmail.com", "verify@x.com"],
     ["보안 알림", "새로운 환경", "새로운 기기", "로그인", "Security alert", "간편 로그인"]),
    ("CARD_NOTICE", 6,
     ["kbmail.kbcard.com", "kbcard.com", "hyundaicard.com", "shinhancard.com",
      "lottecardmailcenter.net", "kgfinancial"],
     ["약관", "수수료율", "포인트", "결제", "매출실적", "마일리지"]),
    ("PROMO", 7,
     ["newsletter", "promotion@", "notify@", "news.miricanvas"],
     ["뉴스레터", "이벤트", "할인", "쿠폰", "프로모션", "안내"]),
]


def classify(sender_blob: str, subject: str) -> ClassifyResult:
    s = (sender_blob + " " + subject).lower()
    for label, prio, sender_kws, sub_kws in _RULES:
        for kw in sender_kws:
            if kw.lower() in s:
                return ClassifyResult(label, prio, f"sender~{kw}")
        for kw in sub_kws:
            if kw.lower() in s:
                return ClassifyResult(label, prio, f"subject~{kw}")
    return ClassifyResult("OTHER", 8, "no_match")
