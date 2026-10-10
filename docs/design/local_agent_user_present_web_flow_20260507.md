# 로컬 Agent + 사용자 직접 인증 웹 흐름 설계
작성일: 2026-05-07

---

## 1. 목적

- 원격접속 제한(키보드보안, 보안프로그램, IP 차단) 사이트를 우회하지 않고 사용자 PC에서 처리
- 사용자 직접 인증(공동인증서, 금융인증서, OTP, 비밀번호)을 중심으로 은행/카드/홈택스/4대보험 지원
- AI는 인증 준비, 안내, 상태 확인, read-only 보조만 수행
- 비밀번호, OTP, 인증서 비밀번호를 AI가 보거나 저장하거나 입력하지 않음
- 제출, 결제, 이체, 전자서명을 자동 실행하지 않음

---

## 2. 구성요소

### 중앙 서버 (haehan-ai-orchestrator API)
- 작업 지시 발행
- 승인 게이트 (approval/preflight)
- audit 로그 수집/저장 (redaction 적용)
- 결과 수집
- tenant/user/site 격리

### 로컬 Agent (사용자 PC 실행)
- 사용자 PC에서 실행되는 보조 프로세스
- 중앙 서버로부터 작업 지시 수신 (WebSocket)
- 사이트 브라우저 열기 (read-only 준비)
- 사용자 직접 인증 대기 상태 관리
- read-only 상태 확인 및 결과 요약 전송
- 민감정보 입력/저장/전송 차단

### 로컬 웹 UI (사용자 PC 브라우저)
- 현재 작업 상태 표시
- 사용자 직접 인증 필요 여부 안내
- 인증 완료 / 중단 버튼 제공
- 사용자 본인 작업만 표시
- 내부 정책, secret, audit 원문 미표시

### 실제 사용자 브라우저
- 사용자가 직접 조작하는 브라우저
- 공동인증서, 금융인증서, OTP, 비밀번호 직접 입력
- AI가 접근하지 않음

### audit/approval/preflight 연계
- gate_approval_preflight → 작업 허가 확인
- allowlist_preflight → 도메인 허용 여부 확인
- action_registry_preflight → 허용 action 확인
- site_access_compatibility_auditor → 사이트별 실행 위치 판정
- workflow_audit_writer → 작업 전후 audit 기록

---

## 3. 실행 위치 분류

| 위치 코드 | 설명 | 예시 |
|---|---|---|
| SERVER_BROWSER_READONLY_OK | 서버 브라우저로 read-only 가능 | G2B 공개 입찰 조회 |
| LOCAL_AGENT_REQUIRED | 로컬 Agent 필수, 사용자 조작 없어도 됨 | 4대보험 공개 조회 |
| USER_PRESENT_REQUIRED | 사용자 직접 조작 필수 | 은행/카드/홈택스 인증 |
| API_REQUIRED | REST API로 처리 | Google Workspace |
| AUTOMATION_BLOCKED | 자동화 전면 차단 | CAPTCHA, 키보드보안 |

---

## 4. 로컬 Agent 역할

- 사용자 PC에서 실행 (desktop/local_runner.py 기반)
- 중앙 서버 WebSocket 연결 (core/agent_runtime/connection/websocket_client.py)
- 사이트 열기: 브라우저를 read-only로 실행, 인증 화면까지만 탐색
- USER_PRESENT_REQUIRED 상태 감지 및 사용자 대기
- 사용자가 인증 완료 버튼 클릭 후 read-only 상태 확인
- 결과 요약(민감정보 제거 후) 중앙 서버 전송
- 민감정보 입력/저장/전송 차단 (blocked_for_ai_input 목록 준수)

### 로컬 Agent 금지 항목
- 비밀번호 입력
- OTP 입력
- 공동인증서/금융인증서 비밀번호 입력
- 전자서명 자동화
- 쿠키/session/token/localStorage 추출
- 제출/결제/이체/신청 자동화
- CAPTCHA 우회
- 키보드보안 우회
- 원격접속 차단 우회

---

## 5. 로컬 웹 UI 역할

### 표시 허용 정보
- 현재 작업명
- 현재 사이트명 (redacted domain만)
- 현재 단계
- 인증 방식 안내 (공동인증서/금융인증서/OTP 등)
- AI가 입력하지 않는 항목 안내
- 상태: WAITING_FOR_USER / USER_CONFIRMED / CANCELLED / BLOCKED
- 인증 완료 버튼
- 중단 버튼
- 사용자 본인 작업 상태

### 표시 금지 정보
- 내부 프롬프트
- API key / access token / refresh token
- cookie / session
- raw audit log
- 전체 preflight 상세 정책
- action registry 내부 정책 원문
- 다른 사용자 작업
- 다른 tenant/site 정보
- 서버 내부 경로
- secret / password / credential
- 인증서 비밀번호
- OTP
- localStorage / sessionStorage 값

### 사용자 화면 안내 문구
- "이 단계는 공동인증서/OTP/비밀번호가 필요합니다."
- "AI는 민감정보를 입력하거나 볼 수 없습니다."
- "사용자가 직접 인증을 완료한 뒤 인증 완료 버튼을 눌러주세요."
- "제출/결제/이체는 자동 실행되지 않습니다."
- "현재 화면에는 사용자 본인 작업 정보만 표시됩니다."

---

## 6. 정보 노출 분리 정책

### 사용자 화면 (로컬 웹 UI)
- 작업명, 사이트명(redacted), 현재 단계, 인증 안내, 버튼, 본인 상태

### 관리자 화면
- workflow_id, workflow_run_id, tenant_id, user_id, site_id
- approval 상태, audit 상태
- preflight 결과 요약 (원문 아님)
- block_reason, 성공/실패 상태
- redacted URL, target_url_hash

### 내부 시스템 전용
- full internal policy 원문
- action metadata 상세
- raw validation errors
- system trace
- detailed audit event (redaction 적용 후 저장)

### audit redaction 정책
- 저장 전 password, otp, credential, token, cookie, session 필드 redaction 처리
- URL은 hash 또는 domain만 저장
- 다른 tenant/user 정보는 격리

---

## 7. 금지 원칙

1. 비밀번호/OTP/인증서 비밀번호 입력 금지
2. 쿠키/session/token/localStorage 추출 금지
3. 전자서명 자동화 금지
4. 제출/결제/이체 자동화 금지
5. 원격접속 차단 우회 금지
6. CAPTCHA 우회 금지
7. 키보드보안 우회 금지
8. 사용자 화면에 내부 정책/audit raw/secret 노출 금지
9. 다른 사용자/tenant 정보 노출 금지
10. playwright fill/type/submit 호출 금지 (인증 구간)

---

## 8. 사이트별 처리 정책

| 사이트 | 실행 위치 | 인증 방식 |
|---|---|---|
| 은행 (공동인증서) | USER_PRESENT_REQUIRED | 사용자 직접 |
| 은행 (금융인증서) | USER_PRESENT_REQUIRED | 사용자 직접 |
| 카드사 | USER_PRESENT_REQUIRED | 사용자 직접 |
| 홈택스 | USER_PRESENT_REQUIRED | 공동인증서/간편인증 |
| 정부24 | LOCAL_AGENT_REQUIRED 또는 USER_PRESENT_REQUIRED | 공동인증서/간편인증 |
| 4대보험 | LOCAL_AGENT_REQUIRED | 공동인증서 |
| G2B (나라장터) | SERVER_BROWSER_READONLY_OK | 없음 (공개 read-only) |
| Google Workspace | API_REQUIRED | OAuth (API 처리) |
| CAPTCHA 사이트 | AUTOMATION_BLOCKED | 차단 |

---

## 9. 시퀀스 다이어그램 (텍스트)

```
중앙서버 → 로컬Agent: 작업 지시 발송 (WebSocket)
로컬Agent → 브라우저: 사이트 열기 (read-only 준비)
로컬Agent → 로컬웹UI: USER_PRESENT_REQUIRED 상태 전달
로컬웹UI → 사용자: 인증 안내 화면 표시
사용자 → 브라우저: 직접 인증 수행 (비밀번호/OTP/인증서)
사용자 → 로컬웹UI: 인증 완료 버튼 클릭
로컬웹UI → 로컬Agent: USER_CONFIRMED 상태 전달
로컬Agent → 브라우저: read-only 결과 확인
로컬Agent → 중앙서버: 결과 요약 전송 (민감정보 제거)
중앙서버 → audit: 감사 로그 기록 (redaction 적용)
```

---

## 10. 파일 위치

| 역할 | 경로 |
|---|---|
| 사용자 직접 인증 모듈 | ai_orchestrator/agent_hub/user_present_flow.py |
| 테스트 | tests/test_local_agent_user_present_web_flow_20260507.py |
| fixture | tests/fixtures/local_agent_user_present_web_flow_20260507.json |
| 이 문서 | docs/design/local_agent_user_present_web_flow_20260507.md |
