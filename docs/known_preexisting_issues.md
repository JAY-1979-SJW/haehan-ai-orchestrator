# 기존(pre-existing) 결함 목록 — STD-02/STD-04 작업 중 발견

이 문서는 STD-02(pathlib)/STD-04(예외 처리) 정리 작업을 하며 서브에이전트들이 "이번 변경과
무관함"을 확인하려고 원인까지 조사한 기존 결함을 모은 것이다. 직접 고치지는 않았고, 각자
`git stash`/원본 대조로 "우리 변경 때문이 아니다"만 확인하고 넘어갔다. **타인 PC 설치**
목표에 맞춰 "치명 등급 재검증" 단계에서 이 목록부터 확인한다.

형식: `- [발견 chunk] 증상 — 원인 (관련 파일)`

## 존재하지 않는 속성/함수 참조 (설치 시 바로 깨질 수 있는 종류)
- [STD-02] `tests/test_eum_auth_selectors.py` — 존재하지 않는 `_TERMINAL_COMPANY_SUBTYPE_SELECTOR` 속성을 요구
- [STD-02] `scripts.naver.mail` 모듈에 `attach_files`/`send_mail` 함수 자체가 없음 (`tests/test_naver_excel_and_mail_attach.py`)
- [STD-02] `scripts.browser.navigator.navigator` 모듈에 `get_page` 없음 (`tests/test_popup_watcher.py`)
- [STD-04 chunk01] `member_collect._filtered_links` 속성 없음
- [STD-02 chunk03(예상)] `ai_orchestrator/agent_hub/router/ws.py`의 `__all__`에 `local_agent_router` 미정의 (F822)
- [STD-04] `scripts/archive/debug/audit_dev_reg_approvals.py` 모듈 자체가 git에 없음 — import 시도하는 테스트가 collection 단계에서부터 실패
- [STD-02] `/api/v1/dev-reg/approvals/*` 라우트가 소스코드 어디에도 없음(테스트만 존재) — `test_approval_read_api.py` 14건

## 환경/의존성 버전 불일치 (다른 PC에서도 재현될 가능성 높음)
- [STD-04 chunk03] fastapi 0.141.1의 지연 라우트 등록(`_IncludedRouter`)과 레거시 `audit_backend_runtime_contract.py`의 APIRoute 카운트 로직이 안 맞음 — `app.routes`가 0/5개로 보임
- [STD-02] `httpx` 0.28.1이 `Client.__init__(app=...)` 인자를 제거해 starlette 0.35.1 `TestClient`가 깨짐 — auth 관련 다수 테스트 collection 실패
- [STD-02/04 다수] `fastapi`/`python-dotenv`/`starlette`/`httpx`가 `py -3.14`(프로젝트 공식 인터프리터) 환경엔 설치 안 돼 있어 여러 세션이 `py -3.13`으로 대체 검증함 — **설치 스크립트/requirements 점검 시 최우선 확인 대상**
- [STD-02] `pyperclip`, `keyring` 등 일부 선언된 의존성이 로컬에 미설치 상태로 발견된 사례 다수

## API 계약/상태 drift
- [STD-02] `test_dashboard_routes.py` 6건 — `jinja2.exceptions.TemplateNotFound: dashboard.html`, 만료 토큰 처리 status 200≠410
- [STD-02] `test_router_smoke.py` — 401 vs 404 불일치
- [STD-04 chunk01] kakao webhook 401, 엔드포인트 카운트 고정값(route count) drift 다수
- [STD-04 chunk02] route count 계약 테스트, 문서 문구 검사(`google_workflows`, `tenant_scope_design`, `backend_runtime_contract_gate`) 다수 실패

## 기타
- [STD-02] `test_local_agent_connection_repair.py` 7건 — `tools/audits/agent/audit_local_desktop_agent_connection.py` 코드 매칭 문제
- [STD-04 chunk03] `test_google_workflows.py` 6건 — tmp 디렉터리 미생성(경로 fixture) 문제

## 집계 메모
- 위 항목들은 전부 **최소 1회 이상 "원본 코드로 재현해도 동일하게 실패함"이 확인된** 것들이다(추측 아님).
- 완전한 목록은 아니다 — STD-02/04 작업 중 우연히 마주친 것만 모았고, 전수 조사는 아니다.
- 다음 단계(치명 등급 재검증)에서 audit-kit ERR-01/ERR-02 결과와 이 목록을 대조해 우선순위를 정한다.
