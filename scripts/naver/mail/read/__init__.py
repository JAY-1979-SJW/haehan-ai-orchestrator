"""Naver Mail 읽기 전용 파이프라인 (CDP 기반).

기존 scripts/naver/mail.py (Playwright compose/send) 는 보존.
본 패키지는 main-page-first 정책을 따르는 읽기 흐름:
  entry      — 세션 확인 + login_wait
  list_collector — 페이지네이션으로 안읽은 메일 전수 수집
  body_reader    — 본문 + PII 마스킹 + 링크/피싱 판정
  classify       — 발신자/제목 규칙 기반 분류
  pipeline       — 위 단계 직렬 오케스트레이션

CDP 포트는 자동화 Chrome 9222 고정. user_browser_session 정책 준수.
"""

from scripts.naver.mail.read import body_reader, classify, entry, list_collector, pipeline

__all__ = ["body_reader", "classify", "entry", "list_collector", "pipeline"]
