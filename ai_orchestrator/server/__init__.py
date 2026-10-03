# server 패키지 — 서버 보조 모듈(작업 큐·정책·스토어) 모음.
# FastAPI 앱 본체는 ai_orchestrator/asgi.py 이다 (진입점 표기: ai_orchestrator.asgi:app).
#
# 이 패키지는 asgi 를 import 하지 않는다. asgi → router → server.* 방향이 유일한 방향이며,
# 반대 방향(server → asgi)을 두면 ai_orchestrator ↔ ai_orchestrator/server 순환이 생긴다.
# (과거에는 server.py 가 이 패키지에 가려져 우회 로더로 앱을 불러왔다 — 2026-09-30 정리.)
