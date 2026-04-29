# Stage 13F-3C Operational WebSocket Smoke Plan

## 1. 개요

### 목적
Stage 13F-3C는 운영 서버에 등록된 테스트 에이전트를 대상으로, 다음 단계 Stage 13F-3D에서 수행할 최초 WebSocket 연결 smoke 절차를 문서화합니다.

### 중요 공지
**이 단계는 실제 WebSocket 연결을 수행하지 않습니다.**
- WebSocket 연결 금지
- heartbeat 전송 금지
- task 생성 금지
- ping/system_info/list_allowed_apps 실행 금지
- 본 문서는 **준비 및 절차 정의**만 수행

### Stage 13F-3D 진행 전 준비
- 이 문서의 절차 및 승인 질문에 대한 명시적 동의 필요
- device_token 보관 방식 확정 필요
- 실패 시 중단 기준 동의 필요

---

## 2. 현재 운영 등록 상태

### Stage 13F-3B 완료 결과

| 항목 | 상태 | 비고 |
|------|------|------|
| 테스트 agent_id | `la-b6dd527a9472` | 운영 서버에서 수신 |
| agent_status | offline | WebSocket 미연결 |
| registered_at | 2026-04-29T07:02:18.699334+00:00 | 등록 시각 |
| active_task_count | 0 | task 미생성 |
| current_task_id | "" (empty) | 진행 중인 task 없음 |
| host | test-agent-stage13f3b | 테스트용 호스트명 |
| os_name | Windows | 테스트 플랫폼 |
| version | stage13f3b-readiness | 테스트 버전 |

### 보안 상태

| 항목 | 상태 | 확인 |
|------|------|------|
| WebSocket 연결 | 없음 | ✓ |
| heartbeat | 없음 | ✓ |
| task 생성 | 없음 | ✓ |
| device_token 원문 노출 | 없음 | ✓ |
| token_hash 노출 | 없음 | ✓ |
| secret 계열 노출 | 없음 | ✓ |
| raw URL/path 노출 | 없음 | ✓ |

### 중요 공지
**device_token은 Stage 13F-3B에서 수신했으나:**
- 코드/문서/git에 저장하지 않음
- 로그에 출력하지 않음
- 환경변수로만 보관하도록 정책화
- 이 문서에서도 token 값, 길이, prefix, suffix 언급하지 않음

---

## 3. Stage 13F-3D 최초 연결 목표

Stage 13F-3D에서는 다음 목표만 달성합니다:

### 허용 목표

**최초 WebSocket 연결 (smoke only)**
```
1. 운영 WebSocket endpoint에 테스트 agent 1개만 연결
2. auth payload 전송
3. auth_ok 수신 확인
4. heartbeat 1회 전송
5. heartbeat_ack 수신 확인
6. agent_status online 또는 last_seen 갱신 확인
7. 연결 즉시 종료
8. 전체 소요 시간: 최대 5초
```

### 금지 목표

**다음 항목은 Stage 13F-3D에서도 실행하지 않습니다:**
- ping action 실행 금지
- system_info action 실행 금지
- list_allowed_apps action 실행 금지
- task 생성 금지
- 연결 유지 금지 (즉시 종료)

---

## 4. Stage 13F-3D 금지 범위

Stage 13F-3D에서 절대 수행하면 안 되는 작업:

### 작업 금지

| 항목 | 상태 | 비고 |
|------|------|------|
| task 생성 | ✗ | POST /api/v1/agents/{id}/tasks |
| approve/reject POST | ✗ | action 승인/거부 금지 |
| open_url | ✗ | 브라우저 실행 금지 |
| list_files_readonly | ✗ | 파일 시스템 접근 금지 |
| capture_screenshot | ✗ | 화면 캡처 금지 |
| 브라우저 실행 | ✗ | 어떤 형태든 금지 |
| 파일 시스템 접근 | ✗ | 읽기 포함 금지 |
| CAD/HWP/Excel | ✗ | 실행 금지 |
| 외부 업무 사이트 접속 | ✗ | 의도치 않은 외부 접속 금지 |
| screenshot 실행 | ✗ | 부작용 위험 |
| 장시간 연결 유지 | ✗ | 최대 5초 후 종료 |
| background service 등록 | ✗ | 자동 실행 설정 금지 |
| 자동시작 등록 | ✗ | startup script 추가 금지 |
| docker 작업 | ✗ | restart/build/up/down 금지 |
| git pull/push | ✗ | repo 수정 금지 |
| 파일 수정 | ✗ | 로컬/운영 파일 변경 금지 |
| DB/schema 변경 | ✗ | 데이터 변경 금지 |

---

## 5. Device Token 주입 방식

### 5.1 Token 보관 정책

**절대 금지**
- 문서에 token 값 기록
- 코드에 hardcode
- git에 commit
- 로그 파일에 출력
- 보고서에 노출

**권장 방식: 환경변수 (Stage 13F-3D 실행 직전만)**

### 5.2 Token 주입 명령 (예시)

Stage 13F-3D를 로컬에서 실행할 때만 다음과 같이 환경변수를 설정합니다:

```bash
# 옵션 1: 명령줄에서 직접 지정
LOCAL_AGENT_DEVICE_TOKEN=<REDACTED_DEVICE_TOKEN> python -m local_agent.client

# 옵션 2: 환경변수 파일 (추천 - .env.local은 .gitignore에 포함)
# .env.local 파일에만 저장
# 사용 전에 .env.local이 .gitignore에 있는지 확인
source .env.local
python -m local_agent.client

# 옵션 3: Windows PowerShell
$env:LOCAL_AGENT_DEVICE_TOKEN="<REDACTED_DEVICE_TOKEN>"
python -m local_agent.client
```

**주의사항**
- `<REDACTED_DEVICE_TOKEN>` 부분에 실제 token 값을 넣지 않음
- 실제 token은 Stage 13F-3B에서 수신한 환경변수만 사용
- 테스트 완료 후 즉시 환경변수 삭제

### 5.3 Token 분실/노출 시 조치

**분실된 경우**
```
1. Stage 13F-3B의 테스트 agent 폐기
2. 새 테스트 agent 재등록 (Stage 13F-3B 절차 재수행)
3. 새 token 수신
4. 환경변수 재설정
5. Stage 13F-3D 재진행
```

**노출 의심 시**
```
1. 즉시 연결 종료
2. 기존 agent 폐기 (unregister)
3. token 재발급 (Stage 13F-3B 절차)
4. 로그/보고서 민감정보 정리
5. 원인 분석 후 재시작
```

---

## 6. Stage 13F-3D 실행 전 승인 질문

다음 질문에 대한 명시적 동의가 필요합니다.

### Q1. 운영 WebSocket 연결 승인
**질문**: 운영 서버의 WebSocket endpoint에 테스트 agent 1개를 연결하는 것을 승인하시겠습니까?
- **범위**: auth → auth_ok → heartbeat → heartbeat_ack → 즉시 종료
- **시간**: 최대 5초
- **영향**: agent_status가 일시적으로 online으로 전환됨
- **롤백**: 즉시 연결 종료 후 offline 복귀

**예상 응답**: [ ] 승인 / [ ] 보안 검토 요청

---

### Q2. 짧은 smoke 제한 승인
**질문**: 연결 시간을 짧은 smoke(최대 5초)로 제한하는 것을 승인하시겠습니까?
- **이유**: 최초 안정성 확인 목적
- **절차**: heartbeat_ack 수신 후 즉시 종료
- **장점**: 부작용 최소화, 빠른 실패 감지

**예상 응답**: [ ] 승인 / [ ] 시간 조정 요청

---

### Q3. auth/heartbeat만 허용 승인
**질문**: Stage 13F-3D에서 auth/heartbeat만 허용하고, task/action은 금지하는 것을 승인하시겠습니까?
- **허용**: auth, auth_ok, heartbeat, heartbeat_ack
- **금지**: ping, system_info, list_allowed_apps, task 생성
- **이유**: 네트워크 안정성 확인 후 추가 action 진행

**예상 응답**: [ ] 승인 / [ ] task 생성 포함 요청

---

### Q4. Task 생성 금지 승인
**질문**: Stage 13F-3D에서 task를 생성하지 않는 것을 승인하시겠습니까?
- **금지**: POST /api/v1/agents/{id}/tasks
- **이유**: ping/system_info 테스트는 별도 단계에서 수행
- **대안**: Stage 13F-3E에서 ping task 1개 테스트

**예상 응답**: [ ] 승인 / [ ] task 생성 포함 요청

---

### Q5. 초기 action 연기 승인
**질문**: ping/system_info/list_allowed_apps 실행을 아직 하지 않고, 다음 단계로 연기하는 것을 승인하시겠습니까?
- **단계 구분**:
  - 13F-3D: auth/heartbeat only (연결 확인)
  - 13F-3E: ping (read-only 테스트)
  - 13F-3F: system_info/list_allowed_apps (정보 조회)
- **이유**: 단계별 격리를 통해 오류 격리 용이

**예상 응답**: [ ] 승인 / [ ] 13F-3D에서 ping 포함 요청

---

### Q6. 환경변수 주입 방식 승인
**질문**: device_token을 로컬 환경변수(`LOCAL_AGENT_DEVICE_TOKEN`)로만 주입하는 방식을 승인하시겠습니까?
- **방식**: `LOCAL_AGENT_DEVICE_TOKEN=<value> python ...`
- **대체안**: .env.local 파일 (단, .gitignore 포함 필수)
- **보안**: token 값은 메모리에만 유지, 파일/git에 저장 안 함

**예상 응답**: [ ] 환경변수 승인 / [ ] Credential Manager 검토 요청

---

### Q7. Token 값 미노출 승인
**질문**: device_token 실제 값을 보고서/로그/문서/git에 출력하지 않는 것을 승인하시겠습니까?
- **금지**: 실제 token 값, token 길이, token prefix/suffix
- **허용**: "token_received: YES", "token_length_verified: YES" 등 존재 여부만
- **이유**: 보안 정책 준수

**예상 응답**: [ ] 승인 / [ ] token 정보 포함 요청

---

### Q8. 실패 시 즉시 중단 승인
**질문**: 실패 또는 이상 현상 시 즉시 연결 종료 및 token 폐기하는 것을 승인하시겠습니까?
- **조건**: auth 실패, heartbeat_ack 미수신, 의도치 않은 task 생성 등
- **조치**: 
  1. 즉시 WebSocket 종료
  2. agent unregister (token 폐기)
  3. 원인 분석
  4. 승인 후 재진행
- **목표**: 안전성 우선

**예상 응답**: [ ] 승인 / [ ] 조건 수정 요청

---

## 7. Stage 13F-3D 절차 초안

### 7.1 사전 준비 (Stage 13F-3D 직전)

**체크리스트**
- [ ] 운영 서버 health OK
- [ ] local-agents list에 la-b6dd527a9472 존재 확인
- [ ] device_token이 환경변수로 설정되어 있는지 확인
- [ ] 로컬 repo가 clean 상태인지 확인
- [ ] 다른 WebSocket 연결이 없는지 확인

### 7.2 실행 절차

```
Step 1: 운영 서버 상태 확인 (read-only)
  - curl http://localhost:8400/api/v1/health
  - 응답: {"status":"ok"}

Step 2: Agent 존재 확인 (read-only)
  - curl http://localhost:8400/api/v1/local-agents
  - agent_id: la-b6dd527a9472 존재 확인
  - agent_status: offline 또는 online 상관없음

Step 3: Token 존재 확인 (환경변수만, 값은 출력 안 함)
  - echo $LOCAL_AGENT_DEVICE_TOKEN | wc -c (길이만 확인)
  - 또는 [[ -n "$LOCAL_AGENT_DEVICE_TOKEN" ]] (존재 여부만 확인)

Step 4: Token 값 출력 금지
  - 절대 echo $LOCAL_AGENT_DEVICE_TOKEN 실행 금지
  - 절대 echo $LOCAL_AGENT_DEVICE_TOKEN > file 금지

Step 5: Local-Agent Smoke 실행
  - 명령: LOCAL_AGENT_DEVICE_TOKEN=$LOCAL_AGENT_DEVICE_TOKEN \
           python -m local_agent.client \
           --server-url http://localhost:8400 \
           --agent-id la-b6dd527a9472 \
           --dry-run=true \
           --timeout=5s
  - 모드: foreground (background service 금지)
  - 로그: stdout/stderr 캡처

Step 6: WebSocket auth 확인
  - 로그에서 "auth sent" 또는 "auth_ok received" 확인
  - 실패 시 즉시 STOP

Step 7: Heartbeat 확인
  - 로그에서 "heartbeat sent" 또는 "heartbeat_ack received" 확인
  - ack 미수신 시 즉시 STOP

Step 8: Agent Status 확인 (read-only)
  - curl http://localhost:8400/api/v1/local-agents
  - agent_status가 "online"으로 전환되었는지 또는
  - last_seen_at이 갱신되었는지 확인

Step 9: 연결 종료
  - 5초 경과 또는 heartbeat_ack 수신 후 즉시 종료
  - 타임아웃으로 자동 종료

Step 10: 최종 상태 확인 (read-only)
  - curl http://localhost:8400/api/v1/local-agents
  - agent_status가 "offline"으로 복귀했는지 또는
  - disconnected_at이 갱신되었는지 확인

Step 11: 로그 검증
  - 로그에서 device_token 원문 노출 여부 확인
  - token, secret, password, cookie, authorization 값 미노출 확인
  - raw URL, raw path 미노출 확인

Step 12: Task 생성 확인 (read-only)
  - curl http://localhost:8400/api/v1/local-agents/la-b6dd527a9472/tasks
  - tasks: [] (empty) 확인
  - 의도치 않은 task 없음 확인

Step 13: 환경변수 정리
  - unset LOCAL_AGENT_DEVICE_TOKEN
  - 또는 터미널 종료

Step 14: 보고서 작성
  - auth: ok/fail
  - heartbeat: ok/fail
  - agent_status: online/offline/unknown
  - task: 0개 생성 확인
  - 민감정보 노출: 없음 확인
```

### 7.3 로그 수집 형식

**권장 로그 출력 (민감정보 제거)**
```
=== WebSocket Smoke Log ===
[2026-04-29 14:30:00] Connecting to ws://localhost:8400/ws
[2026-04-29 14:30:01] Auth message sent
[2026-04-29 14:30:01] Auth OK received
[2026-04-29 14:30:02] Heartbeat sent
[2026-04-29 14:30:02] Heartbeat ACK received
[2026-04-29 14:30:02] Closing connection (smoke complete)
[2026-04-29 14:30:03] Connection closed
Duration: 3.2 seconds
Status: PASS
```

**금지 로그 출력**
```
❌ Auth message: {"device_token":"<actual_value>"}  (token 값 노출)
❌ Connection trace: ...raw_params=... (파라미터 노출)
❌ Server URL: http://localhost:8400/... (raw URL)
```

---

## 8. 즉시 STOP 조건

다음 조건 중 **하나라도 발생**하면 즉시 작업을 중단합니다.

### 8.1 Token/Secret 노출

**체크 항목**
- [ ] device_token 값이 로그에 출력됨
- [ ] token이 환경변수에 없음
- [ ] 기존 token이 분실됨
- [ ] 새 token을 수신했으나 저장 방식 불명확
- [ ] token 값을 문서에 기록하려 함

**발생 시 조치**
1. 즉시 연결 종료
2. 로그 파일 검증
3. 기존 agent unregister
4. token 재발급 (Stage 13F-3B 절차)
5. 환경변수 초기화

---

### 8.2 운영 서버 오류

**체크 항목**
- [ ] health endpoint 5xx 응답
- [ ] local-agents endpoint timeout
- [ ] agent_id 없음
- [ ] API endpoint 변경됨
- [ ] WebSocket endpoint 찾을 수 없음

**발생 시 조치**
1. 즉시 연결 종료
2. 운영 인프라 팀 보고
3. 서버 복구 대기
4. 복구 후 Stage 13F-3D 재진행

---

### 8.3 WebSocket 오류

**체크 항목**
- [ ] auth 실패 (auth_ok 미수신)
- [ ] heartbeat_ack 미수신
- [ ] connection timeout
- [ ] SSL/TLS 오류
- [ ] 예상치 못한 message 수신

**발생 시 조치**
1. 즉시 연결 종료
2. 로그 수집
3. 원인 분석
4. 보안 이슈 확인
5. 재진행 또는 상향 보고

---

### 8.4 금지 작업 위반

**체크 항목**
- [ ] task 생성 발생
- [ ] approve/reject POST 발생
- [ ] open_url 실행 발생
- [ ] list_files_readonly 파일 접근 발생
- [ ] capture_screenshot 실행 발생
- [ ] 브라우저 실행 발생
- [ ] CAD/HWP/Excel 실행 발생
- [ ] 외부 URL 접속 발생

**발생 시 조치**
1. 즉시 중단
2. 연결 종료
3. 로그 수집
4. 원인 파악
5. 코드 수정 또는 정책 재검토
6. 승인 후 재진행

---

### 8.5 민감정보 출력

**체크 항목**
- [ ] token/secret/password/cookie/authorization 값 출력
- [ ] raw URL/path/audit 출력
- [ ] raw params/headers 출력
- [ ] database query 로깅
- [ ] 사용자 정보 노출

**발생 시 조치**
1. 즉시 작업 중단
2. 로그 파일 정리
3. 파일 권한 제한
4. 원인 분석
5. 로그 정책 재검토
6. 재진행

---

## 9. Stage 13F-3E 이후 로드맵

### 단계별 진행 계획

| Stage | 내용 | 의존성 | 비고 |
|-------|------|--------|------|
| 13F-3D | 운영 WebSocket auth/heartbeat smoke | Q1-Q8 승인 | 짧은 smoke (5초) |
| 13F-3E | ping task 1개 제한 실행 | 13F-3D 성공 | dry_run=true 유지 |
| 13F-3F | system_info/list_allowed_apps 테스트 | 13F-3E 성공 | 정보 조회만 |
| 13F-3G | 운영 연결 후 read-only 마감 | 13F-3F 완료 | final checkpoint |
| — | open_url/list_files_readonly 승인 | separate Q | 1주 후 검토 |

### 각 단계 게이트

**13F-3D 완료 게이트**
- auth OK, heartbeat ACK 수신
- task 미생성
- 민감정보 미노출
- 5초 이내 종료

**13F-3E 진행 조건**
- 13F-3D 모든 체크리스트 완료
- 별도 승인 질문 수집
- ping action 테스트 범위 확정

**13F-3F 진행 조건**
- 13F-3E ping action 성공
- system_info/list_allowed_apps action 범위 확정
- agent 상태 안정화 확인

### 추후 고려 사항

**조건부 해제 항목**
- `open_url` → 1주 smoke 후 재검토
- `list_files_readonly` → 파일 정책 정의 후
- `capture_screenshot` → 별도 보안 검토 후

**운영화 전 필수 항목**
- device_token secure storage 최종화 (Credential Manager or Key Vault)
- token rotation policy 확정
- monitoring & alerting 수립
- incident response procedure 정의
- audit logging 활성화

---

## 부록 A. WebSocket 프로토콜 참고

### Auth Message Format

```json
{
  "type": "auth",
  "device_token": "<REDACTED>",
  "agent_id": "la-b6dd527a9472"
}
```

### Auth Response

```json
{
  "type": "auth_ok",
  "status": "authenticated",
  "agent_id": "la-b6dd527a9472"
}
```

### Heartbeat Message

```json
{
  "type": "heartbeat",
  "agent_id": "la-b6dd527a9472",
  "timestamp": "2026-04-29T07:05:00Z"
}
```

### Heartbeat Response

```json
{
  "type": "heartbeat_ack",
  "status": "ok",
  "server_time": "2026-04-29T07:05:00Z"
}
```

---

## 부록 B. 검증 체크리스트

### 문서 검증

- [ ] 9개 섹션 모두 포함
- [ ] 테이블 형식이 markdown 호환
- [ ] 실제 token/secret/password 값 없음
- [ ] 실제 운영 URL/IP 없음
- [ ] 승인 질문 8개 명확
- [ ] 절차 초안 14 단계 명확
- [ ] 즉시 STOP 5개 카테고리 상세
- [ ] 다음 단계 로드맵 명확

### 민감 정보 확인

grep 명령으로 아래를 검증합니다:
```bash
grep -niE "token|secret|password|cookie|authorization|api_key|session|device_token" \
  docs/ops/stage13f3c_operational_ws_smoke_plan.md
```

**허용** (정책/문맥): `device_token`, `token_hash`, `api_key` (개념적 언급), `<REDACTED_DEVICE_TOKEN>` (placeholder)
**불허** (실제 값): 실제 token 값, 실제 secret, 실제 비밀번호, 실제 URL

---

## 부록 C. 참고 자료

### 관련 문서
- [Stage 13F-3A Operational Connection Plan](stage13f3a_operational_connection_plan.md)
- [Stage 13F-2G Local Agent Readiness Gate](stage13f2g_local_agent_readiness_gate.md)
- [Local Agent Architecture](../local_agent_architecture.md)

### 환경변수 정책
- `LOCAL_AGENT_DEVICE_TOKEN`: 운영 WebSocket auth용 token (메모리만 사용)
- `.env.local`: 로컬 개발용 환경변수 파일 (git ignore 필수)

### 보안 원칙
- **최소 권한**: auth/heartbeat만 허용
- **격리 실행**: 단계별로 기능을 나누어 테스트
- **즉시 중단**: 이상 현상 감지 시 연결 종료
- **민감정보 보호**: token/secret/password 절대 로깅

---

**문서 작성일**: 2026-04-29  
**문서 버전**: 1.0  
**상태**: Stage 13F-3D 진행 전 검토 필요  
**다음 단계**: Stage 13F-3D 운영 WebSocket smoke 실행
