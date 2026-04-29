# Stage 13F-3A Local Agent Operational Connection Plan

## 1. 개요

### 목적
Stage 13F-3A는 로컬 에이전트(local-agent)의 운영 서버 연결을 위한 준비 단계입니다. 이 단계에서는:
- 운영 서버 연결 전 필요한 절차, 승인 기준, 중단 조건을 문서화
- 테스트 에이전트 등록 절차의 초안 작성
- device_token 발급, 보관, 폐기 정책의 승인안 제시
- 최초 운영 연결 시 허용 action 범위 확정
- dry_run/test_mode 유지 기준 명시

### 중요 공지
**이 단계는 실제 운영 서버 연결을 수행하지 않습니다.**
- 운영 서버 WebSocket 연결 금지
- task 생성, approve/reject POST 금지
- 실제 device_token 발급/사용 금지

### Stage 13F-3B 진행 전 승인 필요
다음 섹션의 모든 정책과 절차에 대한 명시적 승인이 필요합니다.

---

## 2. 현재 완료 기준

| Stage | Commit | 내용 | 판정 |
|-------|--------|------|------|
| 13F-2A | c27b0c0 | local-agent 최소 실행체 | PASS |
| 13F-2B | 519fb70 | mock WebSocket lifecycle | PASS |
| 13F-2C | 4ade74e | server-agent contract 검증 | PASS |
| 13F-2D | a4bebfc | running/status/safe action skeleton | PASS |
| 13F-2E | d893179 | local WebSocket smoke coverage | PASS |
| 13F-2F | 808fb37 | server router local-only gate | PASS |
| 13F-2G | 653077f | readiness gate 문서화 | PASS |
| 13F-2H | — | read-only verification | PASS |

---

## 3. 운영 연결 원칙

운영 서버 연결은 다음 원칙을 엄격히 준수합니다:

### 3.1 연결 제한
- **승인 전 금지**: Stage 13F-3B 승인 질문에 대한 명시적 동의 없이 연결 진행 금지
- **테스트 에이전트 제한**: 최초 연결은 테스트 에이전트 1개만 허용
- **시간 제한**: 최초 연결은 최대 5분 단위로 제한하며, 필요시 연장 승인
- **Mode 유지**: 모든 초기 연결은 `dry_run=true` 또는 `test_mode=true` 유지

### 3.2 Action 범위 제한
- **초기 허용 action**: `ping`, `system_info`, `list_allowed_apps`만 허용
- **초기 차단 action**: 다음 action은 계속 차단
  - `open_url` (브라우저 실행 위험)
  - `list_files_readonly` (파일 시스템 접근 위험)
  - `capture_screenshot` (화면 노출 위험)

### 3.3 Token 관리 원칙
- **외부 노출 금지**: device_token은 auth payload 외부에서 노출 금지
- **로그 보호**: 운영 로그에 token, raw_params, raw URL, raw path 출력 금지
- **Hash 저장**: device_token_hash만 서버에 저장, raw token 저장 금지

### 3.4 실패 대응
- **즉시 중단**: 이상 현상 감지 시 즉시 연결 종료
- **Token 폐기**: 노출 의심 시 즉시 token 폐기 또는 agent unregister 수행
- **원인 파악 후 재시작**: 중단 후 원인 파악이 완료되어야만 재연결 진행

---

## 4. 테스트 Agent 등록 절차 초안

### 4.1 등록 실행 (Stage 13F-3B)
운영 서버에 테스트 에이전트 1개만 등록합니다:

1. **사전 확인**
   - 운영 서버 health 확인 (read-only)
   - `/orchestrator/api/v1/local-agents` API 접근 가능 확인
   - register endpoint 존재 확인

2. **에이전트 등록**
   - 테스트 에이전트 정보 준비 (이름, 설명, 최소 권한만)
   - POST `/orchestrator/api/v1/local-agents/register`
   - 응답에서 device_token 1회 수신

3. **Token 처리**
   - device_token을 환경변수에 저장 (코드/문서/git/log 기록 금지)
   - token 값 자체는 문서화하지 않음
   - token_hash가 서버에 저장되었는지 확인

4. **등록 확인**
   - GET `/orchestrator/api/v1/local-agents` 조회
   - 등록된 에이전트 확인
   - token_hash, raw token 등 민감 정보 노출 확인
   - 노출 시 즉시 unregister 및 재등록

### 4.2 등록 후 금지 사항
- **WebSocket 연결 금지**: 이 단계에서는 연결 금지
- **Task 생성 금지**: 운영 서버의 task 생성 금지
- **Action 실행 금지**: 어떤 action도 실행 금지

### 4.3 검증 체크리스트
- [ ] 운영 서버 health 정상
- [ ] register API 응답 스키마 예상과 일치
- [ ] device_token 1회 수신
- [ ] token 환경변수 저장 완료
- [ ] server에 token_hash만 저장됨 확인
- [ ] local-agents list에 token_hash/raw token 미노출 확인
- [ ] WebSocket 연결 없음 확인
- [ ] 다른 API 호출 없음 확인

---

## 5. Device Token 발급/보관/폐기 승인안

### 5.1 발급 정책

**발급 방식**
- 운영 서버 register API에서 1회 발급
- 테스트 에이전트 1개만 발급
- token 값은 response에서만 확인

**발급 검증**
- token format 확인 (expected pattern match)
- token length 검증
- token_hash가 별도로 저장되는지 확인

### 5.2 보관 정책

**선호 순서**
1. **환경변수** (Stage 13F-3B~13F-3D)
   - 로컬 개발 환경: `LOCAL_AGENT_DEVICE_TOKEN`
   - 테스트 실행 시에만 설정
   - 테스트 종료 후 즉시 삭제

2. **Windows Credential Manager** (운영화 검토)
   - 추후 단계에서 검토
   - 도입 시 별도 초안 작성

3. **Key Vault/Safe Storage** (장기 운영화)
   - 추후 단계에서 검토
   - 현 단계에서는 미정책

**금지 저장소**
- `.env` 파일 (git 커밋 위험)
- `config.json` 또는 설정 파일
- 코드 주석 또는 hardcoded 값
- 로그 파일 또는 debug output
- 문서 또는 README
- Git history

### 5.3 사용 정책

**허용 사용처**
- WebSocket auth payload `device_token` 필드

**금지 사용처**
- `heartbeat` response에 포함 금지
- `running`, `result`, `diagnostics` response에 포함 금지
- admin web UI 페이로드에 포함 금지
- 운영 로그에 출력 금지
- 에러 메시지에 포함 금지

### 5.4 폐기 정책

**폐기 시점**
- 테스트 종료 후 폐기 또는 agent unregister 수행
- 노출 의심 시 즉시 재발급
- 에이전트 삭제 시 함께 폐기

**폐기 절차**
1. DELETE `/orchestrator/api/v1/local-agents/{agent_id}` 호출
2. 환경변수에서 token 삭제
3. 로그 및 문서에서 token_hash 제거
4. 폐기 확인

**Token 회전**
- 현 단계에서는 정책 미정 (별도 단계에서 확정)
- 보안 위반 시에만 긴급 재발급

---

## 6. 최초 운영 연결 허용 Action 범위

| Action | Risk Level | 13F-3 최초 연결 허용 | 처리 방식 | 비고 |
|--------|-----------|-------------------|----------|------|
| ping | low | ✓ 허용 | completed | 네트워크/파일/브라우저 없음, safe |
| system_info | low | ✓ 허용 | completed | 최소 시스템 정보만, 실제 실행 무 |
| list_allowed_apps | low | ✓ 허용 | completed | 등록된 앱 목록만, 실제 앱 실행 무 |
| open_url | low* | ✗ 불허 | DRY_RUN_ONLY 유지 | 실제 브라우저 실행 금지, 테스트 완료 후 허용 검토 |
| list_files_readonly | medium | ✗ 불허 | DRY_RUN_ONLY 유지 | 파일 시스템 접근 금지, 별도 승인 후 진행 |
| capture_screenshot | high | ✗ 불허 | BLOCKED 또는 waiting_approval | 화면 노출 위험, 최소 1주 후 검토 |

**주의**: `*low`는 분류상 낮지만 운영 연결 초기에는 불허합니다.

### Action별 처리 상세

#### Allowed Actions

**ping**
```
Request: GET /orchestrator/api/v1/local-agents/{agent_id}/ping
Response: {"status": "pong", "timestamp": "2026-04-29T..."}
```
- 부작용 없음
- 네트워크 연결만 확인
- 로그에 민감 정보 무

**system_info**
```
Request: POST /orchestrator/api/v1/agents/{agent_id}/actions/system_info
Response: {"os": "...", "cpu_count": N, "memory_mb": N, "timestamp": "..."}
```
- 시스템 정보 조회만
- 실제 시스템 명령 실행 무 (mocked)
- 로그에 path, url, raw_params 무

**list_allowed_apps**
```
Request: GET /orchestrator/api/v1/local-agents/{agent_id}/allowed_apps
Response: [{"name": "...", "path": "...", ...}]
```
- 등록된 앱 목록만 반환
- 실제 파일 시스템 접근 무
- 로그에 민감 정보 무

#### Blocked Actions (Stage 13F-3 초기)

**open_url**: browser 실행 금지 → DRY_RUN_ONLY 유지
**list_files_readonly**: 파일 접근 금지 → DRY_RUN_ONLY 유지
**capture_screenshot**: 화면 노출 금지 → BLOCKED 유지

---

## 7. 운영 연결 전 승인 질문 목록

다음 질문에 대한 명시적 동의가 필요합니다.

### Q1. 운영 서버 테스트 에이전트 등록 승인
**질문**: 운영 서버에 테스트 에이전트 1개를 등록하는 것을 승인하시겠습니까?
- **범위**: Stage 13F-3B에서 register API 호출 1회
- **영향**: 운영 DB에 에이전트 레코드 1개 추가
- **롤백**: unregister API로 즉시 삭제 가능
- **검토**: 등록 후 심사 의견 수렴 후 WebSocket 연결 진행

**예상 응답**: [ ] 승인 / [ ] 검토 후 재협의

---

### Q2. Device Token 발급 방식 승인
**질문**: device_token을 운영 register API에서 1회 발급하는 방식을 승인하시겠습니까?
- **방식**: POST response에서 token 수신 → 환경변수 저장
- **검증**: server에 token_hash만 저장되는지 확인
- **보안**: token 값은 코드/문서/log에 기록하지 않음

**예상 응답**: [ ] 승인 / [ ] 대체 방식 제안

---

### Q3. Token 보관 방식 승인
**질문**: 테스트 단계에서 device_token을 환경변수로 보관하는 것을 승인하시겠습니까?
- **방식**: `LOCAL_AGENT_DEVICE_TOKEN` 환경변수에 저장
- **기간**: Stage 13F-3B~13F-3D 테스트 기간만
- **삭제**: 테스트 종료 후 환경변수 즉시 삭제

**예상 응답**: [ ] 승인 / [ ] Windows Credential Manager 우선 검토 요청

---

### Q4. dry_run/test_mode 유지 승인
**질문**: 최초 WebSocket 연결 시 `dry_run=true` 또는 `test_mode=true`를 계속 유지할 것인가요?
- **목적**: 실제 action 실행 차단
- **결과**: action은 검증되지만 실행되지 않음
- **해제**: 추가 테스트 완료 후 승인 시 해제

**예상 응답**: [ ] 계속 유지 / [ ] 특정 조건에서 해제

---

### Q5. 최초 허용 Action 범위 승인
**질문**: 최초 운영 연결 시 `ping`, `system_info`, `list_allowed_apps`만 허용하는 것을 승인하시겠습니까?
- **이유**: 부작용 최소화 및 네트워크 검증
- **제한**: `open_url`, `list_files_readonly`, `capture_screenshot` 차단
- **해제**: 각 action별 추가 테스트 후 승인

**예상 응답**: [ ] 승인 / [ ] 추가 action 포함 요청

---

### Q6. 차단 Action 유지 승인
**질문**: `open_url`, `list_files_readonly`, `capture_screenshot`는 계속 차단할 것인가요?
- **이유**: 보안 및 부작용 위험
- **기간**: 최소 1주 별도 테스트 후 해제 검토
- **조건**: 각 action별 위험 평가 및 모니터링 계획 수립 후 해제

**예상 응답**: [ ] 계속 차단 / [ ] 조건부 해제 제안

---

### Q7. 연결 테스트 시간과 중단 기준 승인
**질문**: 최초 WebSocket 연결을 최대 5분 단위로 제한하고, 이상 현상 시 즉시 중단하는 것을 승인하시겠습니까?
- **시간**: 첫 연결 5분, 필요시 연장 승인
- **중단**: 이상 현상 감지 시 즉시 연결 종료
- **검토**: 중단 후 원인 파악 및 대응안 수립 후 재연결

**예상 응답**: [ ] 승인 / [ ] 시간 조정 제안

---

### Q8. 실패 시 폐기 및 원인 파악 승인
**질문**: 실패 또는 이상 현상 발생 시 즉시 token 폐기 및 agent unregister를 수행하고, 원인 파악 후 재시작하는 것을 승인하시겠습니까?
- **절차**: 즉시 중단 → token 폐기 → 원인 파악 → 재등록
- **보고**: 중단 사유 및 조치 결과 문서화
- **재시작**: 원인 해결 확인 후 Stage 13F-3B 재진행

**예상 응답**: [ ] 승인 / [ ] 추가 검토 요청

---

## 8. Stage 13F-3B 범위 제한

이 섹션은 Stage 13F-3B 작업의 **정확한 범위**를 명시합니다.

### 8.1 Stage 13F-3B에서만 수행하는 것

**허용 작업**
- [ ] 운영 서버 상태 확인 (read-only)
  - GET `/orchestrator/api/v1/health`
  - GET `/orchestrator/api/v1/system-info`
- [ ] local-agent register API 존재 확인
  - POST `/orchestrator/api/v1/local-agents/register` 엔드포인트 확인
- [ ] 테스트 에이전트 1개 등록
  - 등록 정보: 이름, 설명, 최소 권한
  - 응답에서 device_token 1회 수신
- [ ] local-agents list에서 등록 확인
  - GET `/orchestrator/api/v1/local-agents` 조회
  - 등록된 에이전트 존재 확인
- [ ] Token 노출 방지 확인
  - token_hash만 저장 확인
  - raw token 저장 여부 점검

### 8.2 Stage 13F-3B에서 금지되는 것

**절대 금지 작업**
- [ ] WebSocket 연결 ❌
- [ ] Task 생성 ❌
- [ ] approve/reject POST ❌
- [ ] 브라우저 실행 ❌
- [ ] 외부 URL 접속 ❌
- [ ] 파일 시스템 접근 ❌
- [ ] screenshot 실행 ❌
- [ ] CAD/HWP/Excel 실행 ❌
- [ ] 운영 설정 변경 ❌
- [ ] Docker 작업 (restart, build, up, down) ❌

### 8.3 다음 단계로의 명시적 전환

**Stage 13F-3B 완료 후**
- 등록 결과를 검토하고 보고서 작성
- 승인 질문 7개에 대한 최종 답변 수집
- 이상 현상이 없으면 Stage 13F-3C로 전환

**Stage 13F-3C에서 수행** (별도 승인 필요)
- 운영 WebSocket 연결 smoke 준비
- dry_run=true로 첫 ping 테스트
- 연결 로그 수집 및 분석

---

## 9. 실패 시 즉시 중단 기준

다음 조건 중 **하나라도 발생**하면 즉시 작업을 STOP하고 원인을 파악한 후 재시작합니다.

### 9.1 Token/Secret 노출 (즉시 STOP)

**체크 항목**
- [ ] device_token 값이 로그에 출력됨
- [ ] device_token 값이 HTTP response에 노출됨
- [ ] device_token 값이 에러 메시지에 포함됨
- [ ] device_token 값이 문서에 기록됨
- [ ] raw token이 운영 서버 DB에 저장됨

**발견 시 조치**
1. 즉시 에이전트 unregister
2. 환경변수에서 token 삭제
3. 로그 파일 정리
4. 원인 분석 문서화
5. 재등록 시 중단 사유 검토

---

### 9.2 서버 응답 스키마 오류 (즉시 STOP)

**체크 항목**
- [ ] register API 응답이 expected schema와 불일치
- [ ] device_token field 누락
- [ ] token_hash field 누락
- [ ] agent_id 형식 오류
- [ ] timestamp format 예상과 불일치

**발견 시 조치**
1. 즉시 연결 종료
2. API specification 검토
3. server-side 코드 확인
4. 스키마 호환성 분석
5. 수정 후 재진행

---

### 9.3 운영 서버 이상 (즉시 STOP)

**체크 항목**
- [ ] `/orchestrator/api/v1/health` 5xx 응답
- [ ] connection timeout
- [ ] DNS resolution failure
- [ ] SSL/TLS certificate error
- [ ] 예상치 못한 3xx 리다이렉트

**발견 시 조치**
1. 즉시 연결 종료
2. 운영 인프라 팀에 보고
3. 서버 로그 확인 (필요시)
4. 상태 회복 대기
5. 재진행 전 운영 팀 승인

---

### 9.4 권한/범위 위반 (즉시 STOP)

**체크 항목**
- [ ] 다른 앱 폴더 접근 시도
- [ ] repo boundary 밖 파일 접근
- [ ] 미승인 API endpoint 호출
- [ ] 미승인 action 실행 시도
- [ ] 운영 기타 리소스 변경 시도

**발견 시 조치**
1. 즉시 중단
2. git status로 파일 변경 확인
3. 의도치 않은 변경 원복
4. 원인 분석
5. 사용자 승인 후 재시작

---

### 9.5 WebSocket/Task 오류 (즉시 STOP)

**체크 항목**
- [ ] WebSocket 연결이 발생 (13F-3B에서는 금지)
- [ ] task 생성 API 호출 발생
- [ ] approve/reject POST 발생
- [ ] 예상치 못한 action 실행 시도

**발견 시 조치**
1. 즉시 중단
2. 연결 로그 수집
3. 의도치 않은 호출 원인 파악
4. 코드 검토 및 수정
5. 로그 정리 후 재진행

---

### 9.6 외부 연결/접속 (즉시 STOP)

**체크 항목**
- [ ] 외부 URL 접속 발생
- [ ] 브라우저 실행 발생
- [ ] screenshot 실행 발생
- [ ] CAD/HWP/Excel 실행 발생
- [ ] shell command 실행 발생

**발견 시 조치**
1. 즉시 중단
2. 운영 서버 연결 종료
3. 외부 접속 로그 확인
4. 의도치 않은 명령 원인 파악
5. 권한 설정 재검토 후 재시작

---

## 10. 다음 단계 로드맵

### 승인 후 진행 순서

| Stage | 내용 | 의존성 | 비고 |
|-------|------|--------|------|
| 13F-3B | 운영 서버 테스트 agent 등록만 수행 | Q1-Q3 승인 | Stage 13F-3A 완료 후 진행 |
| 13F-3C | 운영 WebSocket 연결 smoke 준비 문서 | Q4-Q5 승인 | 13F-3B 등록 확인 후 |
| 13F-3D | 운영 WebSocket 연결 smoke (dry_run=true) | Q6 승인 | ping 성공 후 |
| 13F-3E | ping/system_info/list_allowed_apps 제한 실행 | Q7 승인 | 연결 안정화 확인 후 |
| 13F-3F | 운영 연결 후 read-only 마감 확인 | 13F-3E 완료 | final checkpoint |
| — | open_url/list_files 추가 승인 | separate Q | 1주 후 검토 |

### 단계별 주요 게이트

**13F-3B 완료 게이트**
- 운영 서버에 에이전트 등록 확인
- token_hash 저장 확인
- local-agents list에서 조회 가능 확인
- 이상 현상 무

**13F-3D 완료 게이트**
- WebSocket 연결 성공
- dry_run=true 유지 확인
- ping action 완료 (실제 no-op 확인)
- 로그 민감 정보 무

**13F-3F 최종 게이트**
- read-only 정책 유지 확인
- 미승인 action 차단 확인
- 토큰 노출 무
- 장기 운영 준비 완료

### 추가 고려 사항

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

## 부록 A. 검증 체크리스트

### 문서 검증

- [ ] 10개 섹션 모두 포함
- [ ] 표 형식이 markdown 호환
- [ ] 실제 token/secret/password 값 없음
- [ ] 실제 운영 URL/IP 없음
- [ ] 승인 질문 8개 명확
- [ ] Stage 13F-3B 범위 명확
- [ ] 중단 기준 구체적
- [ ] 다음 단계 명확

### 민감 정보 확인

grep 명령으로 아래를 검증합니다:
```bash
grep -niE "token|secret|password|cookie|authorization|api_key|session" \
  docs/ops/stage13f3a_operational_connection_plan.md
```

**허용** (정책/문맥): `device_token`, `token_hash`, `api_key` (개념적 언급)
**불허** (실제 값): 실제 token 값, 실제 secret, 실제 비밀번호

---

## 부록 B. 참고 자료

### 관련 문서
- [Stage 13F-2G Readiness Gate](stage13f2g_local_agent_readiness_gate.md)
- [Repo Boundary Lock](../policies/repo_boundary_lock.md)
- [Local Agent Architecture](../local_agent_architecture.md)

### 용어 정의
- **device_token**: 로컬 에이전트가 운영 서버에 인증할 때 사용하는 credentials
- **token_hash**: device_token을 SHA-256 등으로 hash한 값 (서버 저장용)
- **dry_run**: action을 검증하지만 실행하지 않는 모드
- **test_mode**: 테스트용 제한 모드 (real DB 접근 금지 등)
- **smoke test**: 최소한의 기능만 검증하는 빠른 테스트

---

**문서 작성일**: 2026-04-29  
**문서 버전**: 1.0  
**상태**: Stage 13F-3A 완료 후 Stage 13F-3B 진행 전 검토 필요
