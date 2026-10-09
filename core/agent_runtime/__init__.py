"""haehan-ai 로컬 에이전트 (Windows PC, Stage 1).

사용자가 자신의 PC 에 명시적으로 설치/실행한 후 서버 오케스트레이터와
연결되어 read-only 안전 작업만 수행한다. 자세한 설계는
docs/local_agent_architecture.md 참고.

구성(2026-10-08 폴더 정리): 이 폴더 루트에는 진입점 `agent.py`(Electron 이 `python -m core.agent_runtime.agent` 로 실행)만 둔다.
`connection/` 서버 WS 연결·등록·토큰·상태·진단·요청 실행 디스패치(actions), `browser/` 로컬 브라우저 실행·읽기·세션·로그인 탐지
(`approval/` 승인 저장·검증, `bridge/` WS 브리지), `user_present/` 사용자 직접 로그인 상태·UI, `policy/` 사이트 진입·준수 정책,
`common/` 공용 잎(audit·config·desktop_config·redaction), `gui/` 데스크톱 GUI 상태, `tools/` 개별 도구(KRAS·파일 스캐너),
`runtime/` PC 쪽 자동화 라이브러리(범용 AI 사이트 에이전트 universal·사이트 프로파일 site_profile·보안 프로그램 security_program·
위임 권한 permission·인증 대기 auth·다운로드 download·Playwright 실행 playwright·사용자 알림 notify).
서버 쪽 에이전트 관리는 `ai_orchestrator/agent_hub/`, CDP 브라우저 엔진은 `scripts/browser/agent/`.
"""

__version__ = "0.1.0"
