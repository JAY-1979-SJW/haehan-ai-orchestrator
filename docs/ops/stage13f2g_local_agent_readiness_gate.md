# Stage 13F-2G Local Agent Readiness Gate

## 1. 개요

이 문서는 `local-agent client`의 운영 서버 연결 전 최종 local-only gate 결과를 기록한다.

- **목적**: Stage 13F-2A~2F에서 완료된 local-only 구현이 운영 연결 기준을 충족하는지 명확히 잠근다.
- **현재 상태**: 운영 서버 연결은 아직 금지. 모든 WS 연결은 localhost in-process 전용.
- **다음 단계**: 이 문서의 PASS 조건이 모두 충족된 이후, 별도 승인 절차를 거쳐 Stage 13F-3로 진입한다.

---

## 2. 완료 단계 현황

| Stage   | Commit    | 내용                                          | 판정  |
|---------|-----------|-----------------------------------------------|-------|
| 13F-2A  | c27b0c0   | minimal local agent client skeleton           | PASS  |
| 13F-2B  | 519fb70   | mock websocket task lifecycle coverage        | PASS  |
| 13F-2C  | 4ade74e   | server websocket contract coverage            | PASS  |
| 13F-2D  | a4bebfc   | running status and safe action skeletons      | PASS  |
| 13F-2E  | d893179   | local websocket smoke coverage                | PASS  |
| 13F-2F  | 808fb37   | local-only server router integration gate     | PASS  |

---

## 3. 현재 가능한 기능

| 기능                     | 구현 위치                        | 비고                         |
|--------------------------|----------------------------------|------------------------------|
| auth payload 생성        | `build_auth()`                   | device_token은 auth에만 포함 |
| heartbeat 생성           | `build_heartbeat()`              | token 미포함                 |
| running payload 생성     | `build_running()`                | task_id만 포함               |
| result payload 생성      | `build_result()`                 | 민감정보 strip 후 포함       |
| heartbeat_ack 처리       | `process_server_message()`       | None 반환 (응답 없음)        |
| running_ack 처리         | `process_server_message()`       | None 반환                    |
| result_ack 처리          | `process_server_message()`       | None 반환                    |
| ping 처리                | `handle_task()` → completed      | 실제 실행 없음               |
| system_info 처리         | `handle_task()` → completed      | 최소 OS 정보만               |
| list_allowed_apps 처리   | `handle_task()` → completed      | 앱 목록 dry 반환             |
| open_url                 | `handle_task()` → DRY_RUN_ONLY  | 브라우저 미실행              |
| list_files_readonly      | `handle_task()` → DRY_RUN_ONLY  | 파일 시스템 미접근           |
| capture_screenshot       | `handle_task()` → BlockedAction  | 실행 없음                    |
| localhost URL 검증       | `assert_local_ws_url()`          | 외부 URL 차단                |

---

## 4. 아직 금지된 기능

다음 기능은 이번 단계에서 구현하지 않았으며, 별도 승인 없이 활성화 금지다.

- 운영 서버 WebSocket 연결 (`wss://`, 외부 도메인)
- 브라우저 실제 실행 (`open_url` 실제 실행)
- 외부 URL 접속
- 실제 파일 시스템 탐색 (`list_files_readonly` 실제 실행)
- screenshot 실행 (`capture_screenshot` 실제 실행)
- CAD / HWP / Excel 실행
- shell command 실행
- background service 등록
- startup 자동 실행
- 실제 업무 사이트 접속
- 운영 approve/reject POST

---

## 5. device_token 정책 초안

### 발급
- 서버 `POST /api/v1/local-agents/register` 응답에서 **1회만** 발급
- 서버는 `SHA-256(device_token)` 해시만 저장; raw token은 서버에 저장하지 않는다

### 보관
| 환경           | 허용 방식                                    | 금지                         |
|----------------|----------------------------------------------|------------------------------|
| 로컬 개발/테스트 | 환경변수(`LA_DEVICE_TOKEN`) 또는 테스트 더미  | 코드 하드코딩, git commit    |
| 운영 예정      | Windows Credential Manager 또는 별도 secure storage 검토 | 평문 파일 저장, 공유 폴더    |

### 사용 규칙
- `build_auth()` 호출 시 **auth payload에만** 포함
- heartbeat / running / result / summary / diagnostics / admin-web 출력에 포함 금지
- 로그 출력 금지 (로거에 token 원문 전달 금지)
- 테스트 출력(`print`, `assert` 메시지)에 실제 token 값 노출 금지
- `AgentConfig.__repr__` / `__str__`에 token 미포함 (현재 구현 확인됨)

### 폐기
- token 분실 또는 노출 의심 시 즉시 서버 재등록 및 신규 token 발급
- 구 token은 서버 측에서 자동 무효화 (재등록 시 token_hash 교체)
- 문서, 슬랙, 이메일에 실제 token 값 공유 금지

---

## 6. local-agent 실행 방식 초안

운영 연결 전 단계적 활성화 기준:

| 단계 | 방식                              | 허용 범위                                          |
|------|-----------------------------------|----------------------------------------------------|
| 1차  | 수동 foreground 실행              | `python -m agent.local_agent_client` 직접 실행     |
| 2차  | `dry_run=True` / `test_mode` 유지 | 실제 WS 연결 없이 로컬 검증                        |
| 3차  | ping / system_info / list_allowed_apps만 허용 | completed 처리, 실제 실행 없음         |
| 4차  | open_url / list_files_readonly    | DRY_RUN_ONLY 유지, 실제 실행 금지                  |
| 5차  | capture_screenshot                | 승인 전까지 BLOCKED 유지                           |
| 6차  | background service / 자동시작    | 별도 단계에서만 검토, 이번 scope 아님              |
| 7차  | 로그                              | 민감정보 제거 후 최소화, token 원문 미기록         |

---

## 7. action별 정책표

| action                 | risk_level | 현재 처리        | 실제 실행 여부      | 운영 연결 전 허용 | 비고                          |
|------------------------|------------|------------------|---------------------|-------------------|-------------------------------|
| ping                   | low        | completed        | 실행 없음           | 허용              | pong 응답만                   |
| system_info            | low        | completed        | 최소 OS 정보만      | 허용              | platform/socket만 사용        |
| list_allowed_apps      | low        | completed        | 앱 실행 없음        | 허용              | 허용 앱 목록 dry 반환         |
| open_url               | low        | DRY_RUN_ONLY     | 실행 없음           | **불허**          | 브라우저 실행 차단            |
| list_files_readonly    | medium     | DRY_RUN_ONLY     | 파일 접근 없음      | **불허**          | 파일 시스템 접근 차단         |
| capture_screenshot     | high       | BLOCKED / waiting_approval | 실행 없음 | **불허**      | 승인 전 WS 전달 안 됨         |

---

## 8. 운영 연결 전 PASS 조건

### PASS (필수 충족)

| 항목                                     | 검증 방법                                  |
|------------------------------------------|--------------------------------------------|
| repo boundary 확인                       | 대상 repo만 사용, 타 앱 접근 없음          |
| working tree clean                       | `git status --short` 출력 없음             |
| Stage 13F-2A~2F 커밋 존재               | `git log --oneline` 확인                   |
| agent 테스트 PASS                        | pytest agent/tests/ -q                     |
| server local-agent 테스트 PASS           | pytest ai_orchestrator/tests/test_local_agent*.py -q |
| token 하드코딩 없음                      | grep 또는 코드 리뷰                        |
| auth payload 외 token 노출 없음          | 테스트 + 코드 리뷰                         |
| localhost 외 WebSocket 차단              | `assert_local_ws_url()` + 테스트 확인      |
| open_url 실제 실행 없음                  | DRY_RUN_ONLY 테스트 PASS                   |
| list_files_readonly 실제 실행 없음       | DRY_RUN_ONLY 테스트 PASS                   |
| capture_screenshot 실행 없음             | BLOCKED 테스트 PASS                        |
| 운영 서버 연결 없음                      | 외부 WS 연결 코드 없음 확인               |

### WARN (주의, 비차단)

| 항목                                      | 비고                                          |
|-------------------------------------------|-----------------------------------------------|
| diagnostics 테스트 파일 부재             | `test_local_agent_diagnostics.py` 기존 부재   |
| `run_ws_protocol()`과 실제 router 흐름 차이 | 서버는 auth_ok 직후 task push; protocol 함수는 mock 전용 |
| asyncio 실제 WS client 미구현            | Starlette TestClient 동기 인터페이스만 구현됨 |
| 승인 후 high-risk 전달 경로 미검증       | capture_screenshot approved 흐름은 scope 밖  |

### FAIL (즉시 차단)

| 항목                          | 대응                                |
|-------------------------------|-------------------------------------|
| token 로그/테스트 출력        | 즉시 코드 수정 후 재검증            |
| 운영 서버 WS 연결             | 즉시 중단                           |
| 외부 URL 접속                 | 즉시 중단                           |
| 브라우저 실행                 | 즉시 중단                           |
| 파일 시스템 접근              | 즉시 중단                           |
| screenshot 실행               | 즉시 중단                           |
| repo boundary 위반            | 즉시 중단                           |
| 다른 앱 폴더 접근             | 즉시 중단                           |
| secret/raw_params/raw URL/raw path 노출 | 즉시 코드 수정 후 재검증 |

---

## 9. Stage 13F-3 진입 전 승인 항목

Stage 13F-3(운영 서버 연결)으로 진입하기 전, 아래 항목에 대해 명시적 승인이 필요하다.

| 항목                          | 결정 필요 내용                                              |
|-------------------------------|-------------------------------------------------------------|
| 운영 서버 연결 승인           | 연결 대상 서버, 경로, 인증 방식 확정                        |
| 테스트용 agent 등록 승인      | 등록 주체, 등록 시점, agent_id 명명 규칙                    |
| device_token 발급 방식        | 발급 주체, 발급 절차, 전달 방식                             |
| token 보관 방식               | Windows Credential Manager 또는 다른 secure storage 선택   |
| 최초 허용 action 범위         | ping만 / ping+system_info / 3종 low-risk 중 선택            |
| 운영 연결 시 dry_run 유지     | `dry_run=True`로 연결할지, 실제 결과 전송 여부              |
| 연결 시간 및 테스트 범위      | 1회성 smoke인지, 지속 연결인지                              |
| 실패 시 즉시 중단 기준        | auth 실패, result 오류, 네트워크 오류 시 중단 조건          |

---

## 10. 다음 단계 제안

운영 서버로 바로 진입하지 않고 아래 순서를 따른다.

| Stage   | 내용                                                             | 전제                         |
|---------|------------------------------------------------------------------|------------------------------|
| 13F-2H  | readiness gate 문서 기준 read-only 검증                          | 이 문서 완료                 |
| 13F-3A  | 운영 서버 연결 준비 문서 작성 (agent 등록 절차, token 보관 방식) | 13F-2H PASS                  |
| 13F-3B  | 운영 서버에 테스트 agent 등록만 수행 (HTTP, WS 연결 아직 없음)  | 13F-3A 승인                  |
| 13F-3C  | 운영 WebSocket 연결 smoke (auth → auth_ok → heartbeat만)         | 13F-3B 완료, device_token 보관 확인 |
| 13F-3D  | ping / system_info / list_allowed_apps 제한 실행                 | 13F-3C PASS                  |
| 이후    | open_url / list_files_readonly / capture_screenshot              | 별도 승인 후 단계적 진행     |

---

## 부록: 현재 테스트 수 요약

| 테스트 파일                              | 테스트 수 | 최종 확인 커밋 |
|------------------------------------------|-----------|----------------|
| test_local_agent_client.py               | 34        | 808fb37        |
| test_local_agent_ws_lifecycle.py         | 45        | 808fb37        |
| test_local_agent_contract.py             | 50        | 808fb37        |
| test_local_agent_running_and_safe_actions.py | 37    | 808fb37        |
| test_local_agent_ws_smoke.py             | 51        | 808fb37        |
| test_local_agent_server_router_gate.py   | 44        | 808fb37        |
| ai_orchestrator/test_local_agent.py      | 74        | 808fb37        |
| ai_orchestrator/test_local_agent_ws.py   | 76        | 808fb37        |
| **합계**                                 | **411+**  |                |

> `test_local_agent_diagnostics.py`는 기존 부재 (WARN 항목).
