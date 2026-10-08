"""haehan-ai 로컬 에이전트 (Windows PC, Stage 1).

사용자가 자신의 PC 에 명시적으로 설치/실행한 후 서버 오케스트레이터와
연결되어 read-only 안전 작업만 수행한다. 자세한 설계는
docs/local_agent_architecture.md 참고.

구성(T4 이후): 이 폴더 = 데스크톱 에이전트 프로세스 + 온디맨드 컨트롤러(controller·process_guard·status_store),
`runtime/` = PC 쪽 자동화 라이브러리 57개(보안프로그램 설치·Playwright 실행·인증 대기·위임 권한·범용 AI 사이트 에이전트).
서버 쪽 에이전트 관리는 `ai_orchestrator/agent_hub/`, CDP 브라우저 엔진은 `scripts/browser/agent/`.
"""
__version__ = "0.1.0"
