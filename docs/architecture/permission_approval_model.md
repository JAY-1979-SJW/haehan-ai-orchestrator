# 권한/승인 모델 (Permission & Approval Model)

고정일: 2026-05-15  
작업 ID: APP_FOUNDATION_GOVERNANCE_LOCK_01  
상태: LOCKED — 모든 신규 기능은 이 모델 안에서만 동작한다.

---

## 1. 역할 (Roles)

| 역할 | 설명 | 허용 범위 |
|------|------|----------|
| owner | 계정 소유자 (대표) | 모든 실행 허용. 결제·서명·최종 등록 직접 수행. |
| admin | 시스템 관리자 | approval 처리, gate 설정 변경, report 확인 |
| operator | 운영 담당자 | read, draft, approval 요청 가능. 최종 실행은 owner/admin 승인 필요. |
| viewer | 조회 전용 | read-only. 초안 생성, 실행 불가. |
| local_agent_user | 로컬 에이전트 사용자 | PC에서 local_agent_required 작업만 실행. |
| system_readonly | 시스템 자동화 | read-only + draft 생성. 실행·제출·결제 불가. |

---

## 2. 실행 결정 (Gate Decisions)

| 결정 | 코드 | 설명 |
|------|------|------|
| 허용 | ALLOWED | 즉시 실행 가능 |
| 읽기 허용 | READ_ONLY_ALLOWED | 조회만 가능, 변경 불가 |
| 초안 허용 | DRAFT_ALLOWED | 초안 생성만 가능. 실제 적용 불가. |
| 승인 필요 | APPROVAL_REQUIRED | 지정 권한자 명시적 승인 후 실행 가능 |
| 사용자 직접 | USER_DIRECT_REQUIRED | AI/시스템 불가. 사용자가 외부 사이트에서 직접 수행. |
| 로컬 에이전트 | LOCAL_AGENT_REQUIRED | 서버 불가. 사용자 PC 로컬 에이전트에서만 실행. |
| 차단 | BLOCKED | 실행 불가. 실행계획 생성도 금지. |

---

## 3. 위험도 분류 (Risk Types)

| 위험도 | 코드 | 예시 | 기본 정책 |
|--------|------|------|----------|
| 읽기 | READ | DNS 조회, 상태 확인 | READ_ONLY_ALLOWED |
| 초안 | DRAFT | 등록 초안 생성, DNS 초안 | DRAFT_ALLOWED |
| 쓰기 | WRITE | DB insert, 파일 저장 | APPROVAL_REQUIRED |
| 삭제 | DELETE | DNS 레코드 삭제, 파일 삭제 | APPROVAL_REQUIRED |
| 제출 | SUBMIT | 폼 제출, API POST | APPROVAL_REQUIRED |
| 서명 | SIGN | 전자서명, 공동인증서 | USER_DIRECT_REQUIRED |
| 결제 | PAYMENT | 카드 결제, 청구, 환불 | USER_DIRECT_REQUIRED |
| 비밀 | SECRET | API key, 비밀번호 접근 | BLOCKED |
| 세션 | SESSION | cookie, session, token 추출 | BLOCKED |
| 관리자 변경 | ADMIN_CHANGE | 권한 변경, schema 변경 | APPROVAL_REQUIRED (owner만) |
| 외부 로그인 | EXTERNAL_LOGIN | 외부 사이트 자동 로그인 | BLOCKED (서버) / LOCAL_AGENT_REQUIRED (PC) |
| 로컬 전용 | LOCAL_AGENT_ONLY | CAD, HWPX, Excel COM | LOCAL_AGENT_REQUIRED |

---

## 4. 절대 금지 (BLOCKED) — 예외 없음

```
비밀번호 자동 입력
OTP/2FA 자동 입력
공동인증서 비밀번호 자동 입력
session/cookie/token 추출
API key/secret 값 출력/로깅
환경변수 원문 출력
결제/송금 자동 실행
투찰/낙찰 자동 제출
전자서명 자동 실행
서버 사이드 외부 사이트 로그인 브라우저 실행
data/sessions/*.json 내용 읽기/파싱/재사용
운영 DB update/delete/drop/truncate (별도 승인 없이)
schema 변경 (별도 승인 없이)
chmod/chown 자동 변경
docker/nginx/systemctl 자동 재시작
```

---

## 5. 승인 필요 (APPROVAL_REQUIRED) — 명시적 승인 후 실행

```
DNS 레코드 추가
DNS 레코드 수정
DNS 레코드 삭제
도메인 갱신/이전/취소 제출
호스팅/메일 설정 변경 제출
외부 콘텐츠 업로드 (YouTube, 블로그 등)
외부 콘텐츠 발행
외부 메일 발송
운영 DB 쓰기 (승인 후)
```

---

## 6. 사용자 직접 (USER_DIRECT_REQUIRED) — AI 불가, 사용자 외부 사이트 직접

```
도메인 최종 등록
결제 최종 수행
약관 동의
전자서명
공동인증 로그인
2FA 입력
```

---

## 7. 로컬 에이전트 (LOCAL_AGENT_REQUIRED) — 서버 불가, PC에서만

```
로그인 필요한 외부 사이트 데이터 조회 (my.gabia.com 등)
Excel COM 자동화
HWP/HWPX COM 자동화
CAD 파일 자동화
로컬 파일 맵 실행
```

---

## 8. 게이트 연동

이 모델의 모든 결정은 `scripts/site_engine/execution_gate.py`의  
`evaluate_execution_gate(ExecutionGateInput, profile)` 함수로 평가된다.

- `SiteCapability.SIGN` → profile BLOCKED 정책 → `BLOCKED`
- `SiteCapability.SUBMIT` + profile → `APPROVAL_REQUIRED`
- `SiteCapability.READ` + is_server_forbidden_site → `LOCAL_AGENT_REQUIRED`
- `SiteCapability.READ` → `READ_ONLY_ALLOWED`
