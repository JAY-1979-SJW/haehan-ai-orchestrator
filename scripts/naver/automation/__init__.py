"""네이버 서비스 공용 자동화 패키지(여러 도구가 함께 쓰는 부분만).

하위 패키지:
  - content: seo_optimizer(SEO 최적화)
  - integration: ai_responder(AI 자동 응답), notification_hub(다중 채널 알림)
  - (이 폴더 바로 아래) session_manager·error_recovery·scheduler·image_processor — platform 하위 폴더는 표준 모듈 이름을 가려(A005) 올렸다

스마트스토어 전용 자동화(주문·재고·분석·CSV·경쟁사·리뷰 답변·워크플로)는
scripts/naver/smartstore/automation/ 에 있다. 재수출은 하지 않는다 — 실제 모듈 경로로 import 한다.
예: from scripts.naver.automation.integration.ai_responder import AIResponder

(MailAutomation 은 호출처가 없어 scripts/archive/naver/automation/ 로 보관했다 — 도구 지도 B1·결정 ⑤)
"""
