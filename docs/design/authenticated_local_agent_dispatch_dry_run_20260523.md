# 인증 기반 로컬 에이전트 브라우저 Dispatch 설계서

문서 ID: HAEHAN-AUTHED-LOCAL-AGENT-DISPATCH-DRY-RUN-01  
작성일: 2026-05-23  
범위: 서버와 로컬 에이전트의 인증된 연결, 로컬 Playwright 실행, 결과 회수 검증  
비범위: installer build, desktop UI 변경, GitHub push, 서버 재배포, secret 출력

## 1. 목표

`AUTH_ENABLED=true` 상태에서 서버가 로컬 에이전트에 `web_open_url_readonly` 작업을 전달하고, 실제 Playwright 브라우저 실행은 사용자 로컬 PC에서만 수행되도록 검증한다.

이번 단계는 실제 실행 전 설계와 dry-run 검측 단계다. 서버 배포나 live task 실행은 다음 승인 단계에서 별도 수행한다.

## 2. 실행 원칙

- 서버는 작업 등록, 인증, 큐, 결과 저장만 담당한다.
- 브라우저 실행은 `local_agent` 프로세스가 로컬 PC에서 수행한다.
- 로컬 에이전트 등록은 admin/owner 인증으로 발급한 registration-code 흐름을 사용한다.
- 무인증 `/api/v1/local-agents/register` 호출은 `AUTH_ENABLED=true`에서 401이어야 한다.
- device token, registration code, Authorization header, OpenAI key는 로그와 보고서에 원문 출력하지 않는다.
- `web_open_url_readonly`는 read-only 작업만 허용하며 submit/write/download/upload/credential 입력은 포함하지 않는다.
- Playwright sync API는 WebSocket asyncio loop 밖에서 실행한다.

## 3. 기대 흐름

1. 서버 런타임 확인
   - `AUTH_ENABLED=true`
   - `/api/v1/health` 정상
   - `HTTP_USERS_PATH` 또는 `/run/secrets/api/http_users.json` 존재

2. 인증된 등록 준비
   - admin/owner 인증으로 registration-code 발급
   - registration-code 원문은 1회만 사용하고 출력 금지
   - 로컬 에이전트는 `register-with-code`로 `agent_id`와 `device_token`을 수신
   - `device_token`은 Windows Credential Manager 또는 허용된 로컬 저장소에 저장

3. WebSocket 연결
   - 로컬 에이전트가 저장된 token으로 서버 WebSocket 인증
   - 서버는 token hash만 비교하고 원문 저장/로그 출력 금지

4. 작업 전달
   - 서버가 해당 `agent_id`에 `web_open_url_readonly` task 생성
   - 로컬 에이전트가 task를 수신하고 `asyncio.to_thread(process_task, task)` 경로로 실행

5. 로컬 브라우저 실행
   - Playwright는 로컬 에이전트 프로세스에서 실행
   - 서버 컨테이너 내부에서 Playwright/브라우저 실행 금지
   - 결과는 summary/audit 중심으로 sanitize 후 서버에 반환

6. 완료 판정
   - task status `completed`
   - result summary에 title/link/button/form/table counts 포함
   - observe summary 수신
   - raw HTML, token, cookie, password, session 값 미포함

## 4. Dry-run 검측 항목

감리 dry-run은 다음을 정적으로 확인한다.

- `docker-compose.yml`의 `AUTH_ENABLED` 기본값이 `"true"`인지
- 서버 `config.py`의 `AUTH_ENABLED` 기본값이 `true`인지
- local-agent register endpoint가 `require_role("admin", "owner")`로 보호되는지
- registration-code endpoint와 register-with-code endpoint가 존재하는지
- `web_open_url_readonly`가 local-agent 자동 실행 목록과 low-risk 정책에 등록되어 있는지
- `core/agent_runtime/connection/websocket_client.py`가 `process_task`를 event loop 밖에서 실행하는지
- live 검증 스크립트가 token 원문을 출력하지 않고 agent id를 masking하는지
- 금지 명령이 dry-run 스크립트 안에 없는지

## 5. 다음 live 실행 전 중단 조건

다음 중 하나라도 발견되면 live 실행을 중단한다.

- `AUTH_ENABLED=false`
- 무인증 registration이 200으로 성공
- registration-code 없이 legacy register 흐름을 사용해야만 하는 상태
- WebSocket 인증 실패가 mock success로 처리됨
- 서버 컨테이너에서 브라우저/Playwright가 실행됨
- task 결과에 token, cookie, session, password, raw HTML 원문이 포함됨
- OUT_OF_SCOPE 5개 파일이 stage 또는 수정됨

## 6. 감리 판정 코드

- `PASS_AUTHED_LOCAL_AGENT_DISPATCH_DRY_RUN_READY`
- `WARN_AUTHED_LOCAL_AGENT_DISPATCH_NEEDS_LIVE_SECRET_INPUT`
- `FAIL_AUTHED_LOCAL_AGENT_DISPATCH_SECURITY_RISK`
- `FAIL_OUT_OF_SCOPE_MUTATED`

이번 문서 기준으로 dry-run이 PASS이면, 다음 단계에서만 인증값을 비출력 방식으로 주입해 registration-code 발급부터 live dispatch까지 진행한다.
