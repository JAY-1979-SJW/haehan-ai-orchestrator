# Local Agent WebSocket User-Present Integration

날짜: 2026-05-07

## 1. 목적

routing dry-run 결과가 `LOCAL_SYSTEM_BROWSER_USER_PRESENT`인 경우,
서버 → 로컬 Agent로 전달하는 WebSocket message contract와
로컬 Agent → 서버로 반환하는 status event schema를 정의한다.

실제 운영 WebSocket 송신 없음. 테스트는 in-memory transport만 사용.

## 2. 메시지 흐름

```
1. routing dry-run 결과 dispatch_decision =
   DRYRUN_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED

2. 서버가 USER_PRESENT_TASK message를 생성
   (raw target_url 미포함, redacted/hash만 포함)

3. 로컬 Agent ws_adapter가 message 수신 및 검증

4. local user_present_state_store에 TASK_RECEIVED → WAITING_FOR_USER 상태 생성

5. user_present_ui_server 웹 UI에 인증 대기 화면 표시

6. 사용자가 직접 인증 완료 후 UI에서 확인 클릭

7. state_store가 USER_CONFIRMED로 전이

8. ws_adapter가 USER_PRESENT_STATUS event를 생성

9. 서버는 USER_CONFIRMED 상태를 수신할 수 있는 contract만 확보
   (실제 WebSocket 수신 연결은 이번 단계에서 구현하지 않음)
```

## 3. 서버 → 로컬 Agent task message schema (USER_PRESENT_TASK)

| 필드 | 타입 | 설명 |
|---|---|---|
| message_type | str | "USER_PRESENT_TASK" (고정) |
| workflow_run_id | str | 워크플로우 실행 ID (필수) |
| workflow_id | str | 워크플로우 ID |
| tenant_id | str | 테넌트 ID (필수) |
| user_id | str | 사용자 ID (필수) |
| site_id | str | 사이트 ID |
| site_category | str | 사이트 분류 (bank/card/hometax 등) |
| target_domain | str | 대상 도메인 |
| target_url_redacted | str | redacted URL (raw URL 미포함) |
| target_url_hash | str | SHA-256 hash of original URL |
| auth_method_label | str | 한글 인증 수단 설명 |
| user_message_ko | str | 사용자에게 표시할 한글 안내 |
| required_user_actions | list[str] | 사용자가 해야 할 작업 목록 |
| blocked_ai_actions | list[str] | AI가 하면 안 되는 작업 목록 |
| safe_to_execute | bool | 항상 False |
| created_at | str | ISO8601 생성 시각 |

### 금지 필드 (절대 포함 불가)
- password, otp, certificate_password, financial_certificate_password
- token, access_token, refresh_token, api_key, device_token
- cookie, session, localStorage, sessionStorage
- raw target_url (원문)
- raw audit log, internal_policy
- 다른 user/tenant의 task 데이터

## 4. 로컬 Agent → 서버 status event schema (USER_PRESENT_STATUS)

| 필드 | 타입 | 설명 |
|---|---|---|
| message_type | str | "USER_PRESENT_STATUS" (고정) |
| workflow_run_id | str | 워크플로우 실행 ID (필수) |
| tenant_id | str | 테넌트 ID |
| user_id | str | 사용자 ID |
| site_id | str | 사이트 ID |
| status | str | 상태값 (아래 허용값 참조) |
| status_reason | str | 상태 변경 이유 |
| safe_to_execute | bool | 항상 False |
| created_at | str | ISO8601 생성 시각 |

### status 허용값
- WAITING_FOR_USER: 사용자 인증 대기 중
- USER_CONFIRMED: 사용자 인증 완료 확인
- CANCELLED: 사용자 취소
- BLOCKED: 정책상 차단
- FAILED: 오류 발생

## 5. 사용자 직접 인증 상태 전이

```
TASK_RECEIVED
    → WAITING_FOR_USER (mark_waiting_for_user)
    → USER_CONFIRMED   (mark_user_confirmed, WAITING_FOR_USER일 때만)
    → CANCELLED        (mark_user_cancelled)
    → BLOCKED          (오류/정책 차단)
    → FAILED           (처리 실패)
```

USER_CONFIRMED 이후 상태 전이 불가 (FINAL 상태).
USER_CONFIRMED는 상태 전이만 수행하며 browser action/click/type/submit을 실행하지 않는다.

## 6. 민감정보 미전송 정책

- raw target_url: 서버→로컬 전송 금지. target_url_redacted와 target_url_hash만 허용
- password/otp/certificate_password: 저장/전송/입력 모두 금지
- token/cookie/session: 추출/전송 금지
- cross-tenant 데이터: message에 타 테넌트 데이터 혼입 금지
- sanitize_user_present_ws_payload()를 통해 전송 전 필터링 필수

## 7. 테스트 transport 정책

- 실제 WebSocket (ws://, wss://) 연결 금지
- InMemoryTestTransport: send/receive를 list로만 시뮬레이션
- 운영 서버/로컬 Agent WebSocket 서버에 접속하지 않음
- 테스트 케이스는 transport를 통한 메시지 흐름만 검증

## 8. 실제 운영 송신 전 남은 조건

- local_agent/websocket_client.py에 USER_PRESENT_TASK 수신 핸들러 연결
- 서버 측 USER_PRESENT_STATUS 수신 endpoint 구현
- 서버 승인 후 실제 WebSocket 채널을 통한 end-to-end 통신
- USER_CONFIRMED 이후 실제 작업 위임 흐름 (별도 단계에서 구현)
