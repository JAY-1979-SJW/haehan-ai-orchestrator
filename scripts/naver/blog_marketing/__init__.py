"""건설 실무 블로그 AI 마케팅 파이프라인 - 섹션별 모듈 구성.

  topics.py   - 3중 검증(카페 빈도, 검색광고, 지식iN) 리서치 결과 로드, 주제 선정, 발행 캐시
  images.py   - Unsplash 이미지 수집/다운로드
  content.py  - AI 본문/제목 생성, SEO 점검
  publish.py  - CDP 로그인 + 발행 루프 (실제 네이버 블로그에 쓰는 유일한 지점)

리서치 원본: scripts/ops/research_blog_topics.py
커맨드라인 진입점: scripts/ops/blog_ai_batch_20.py (--dry-run, --count)
"""

from __future__ import annotations

TARGET_BLOG_ID = "skyjwsin"
