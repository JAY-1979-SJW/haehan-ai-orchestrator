"""LTX 영상 제작 큐 PoC 패키지 (F-4S-6).

목적:
- F-4S-5 의 ltx_video_briefs 를 LTX 영상 제작 지시서(queue) 형태로 변환.
- 실제 LTX API 호출 / 영상 생성 / 업로드는 절대 수행하지 않는다.

금지:
- LTX API 실호출
- 브라우저 자동화 / playwright / requests
- OAuth / 쿠키 접근
- 네이버/유튜브 write 액션 (댓글/가입/글쓰기/업로드/수정/삭제)
- API key / client_secret 의 큐/리포트/로그 노출
"""
