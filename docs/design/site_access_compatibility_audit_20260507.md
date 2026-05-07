# Site Access Compatibility Audit

**문서 버전:** 1.0  
**작성일:** 2026-05-07  
**대상:** Browser Automation Workflow System  
**목적:** 은행, 공공기관, 조달/세무/보험/인증서 기반 사이트의 브라우저 접속성, 인증 방식, 자동화 가능 범위 감사

---

## 1. 목적

이 감사는 다음을 명시합니다:

1. **실제 접속 가능성 확인**: Read-only로 사이트 접속 확인
2. **인증 방식 분류**: 공동인증서, 금융인증서, 간편인증, 비밀번호 등 분류
3. **제약사항 파악**: 원격접속 차단, 보안프로그램 설치, CAPTCHA 등 제약 기록
4. **자동화 범위 판정**: 서버 브라우저 가능 범위 결정
5. **안전성 강제**: read-only 감사만, 로그인 완료/입력/제출 금지

---

## 2. 감사 대상 사이트 카테고리

### 2.1 카테고리 분류

| 카테고리 | 설명 | 대표 사이트 | 우선순위 |
|---------|------|-----------|--------|
| Google 계열 | 구글 서비스 | accounts.google.com, mail.google.com 등 | 1 |
| 은행/금융 | 인터넷뱅킹, 증권 | KB국민은행, 우리은행, 신한은행 등 | 2 |
| 카드/결제 | 신용카드, 직불카드 | KB국민카드, 비자, 마스터카드 등 | 3 |
| 정부24/민원 | 정부 민원 | gov.kr, 정부24 등 | 4 |
| 세무 (홈택스) | 세무신고 | hometax.go.kr, 손택스 | 5 |
| 4대보험 | 보험료 조회 | 국민건강보험, 국민연금, 고용보험, 산재 | 6 |
| 조달/G2B | 정부 조달 | g2b.go.kr, 나라장터 | 7 |
| 전자문서 | 세금계산서, 계약서 | 홈택스 전자세금계산서, 전자계약 | 8 |
| 공동인증서 기반 | 공인인증서 로그인 | 은행, 정부, 법원 등 | 9 |
| 금융인증서 기반 | 금융인증서 로그인 | 은행, 증권 등 | 10 |
| 회사 내부 | 관리자 사이트 | 내부 조직 정보 시스템 | 11 |

### 2.2 감사 대상 최소 범위 (1차)

1. **Google 계열**: accounts.google.com, mail.google.com, drive.google.com, calendar.google.com, docs.google.com, sheets.google.com
2. **은행 Generic**: 공동인증서/금융인증서 로그인 버튼 감지
3. **카드 Generic**: 신용카드 로그인 페이지
4. **정부 Generic**: gov.kr 로그인 페이지
5. **세무 Generic**: hometax.go.kr 로그인 페이지
6. **보험 Generic**: 국민건강보험, 국민연금, 고용보험, 산재 로그인 페이지
7. **조달 Generic**: g2b.go.kr, 나라장터 로그인 페이지
8. **인증서 기반**: 공동인증서/금융인증서 요구 페이지

---

## 3. 감사 항목

### 3.1 사이트별 감사 필드

| 필드 | 타입 | 설명 | 예시 |
|------|------|------|------|
| site_id | string | 사이트 고유 ID | bank_generic_kbbank |
| site_name | string | 사이트 한글명 | KB국민은행 |
| base_domain | string | 기본 도메인 | ibankx.kbbank.com |
| login_url | string | 로그인 페이지 URL | https://ibankx.kbbank.com/main |
| category | string | 카테고리 | bank_login |
| requires_login | boolean | 로그인 필요 여부 | true |
| auth_methods | list[string] | 인증 방식 | ["공동인증서", "금융인증서", "PASS"] |
| requires_certificate | boolean | 공동인증서 필요 | true |
| requires_financial_certificate | boolean | 금융인증서 필요 | true |
| requires_simple_auth | boolean | 간편인증 필요 | false |
| requires_otp | boolean | OTP 필요 | true |
| requires_captcha | boolean | CAPTCHA 필요 | false |
| requires_security_plugin | boolean | 보안프로그램 필요 | true |
| blocks_remote_access | boolean | 원격접속 차단 | true |
| server_browser_allowed | boolean | 서버 브라우저 가능 | false |
| local_agent_required | boolean | 로컬 PC agent 필수 | true |
| user_present_required | boolean | 사용자 직접 조작 필요 | true |
| official_api_available | boolean | 공식 API 가능 | false |
| automation_capability | string | 자동화 능력 | USER_PRESENT_LOCAL_ONLY |
| allowed_operations | list[string] | 허용된 작업 | ["read", "navigate"] |
| blocked_operations | list[string] | 차단된 작업 | ["type", "submit", "click"] |
| recommended_route | string | 권장 경로 | USER_DIRECT_LOCAL |
| final_verdict | string | 최종 판정 | USER_PRESENT_REQUIRED |
| notes | string | 추가 기록 | "보안카드 요구" |

### 3.2 automation_capability Enum

- `API_ONLY`: 공식 API만 지원
- `OAUTH_API_ONLY`: OAuth + API 지원
- `SERVER_BROWSER_READONLY_ALLOWED`: 서버 브라우저 읽기만
- `LOCAL_AGENT_READONLY_ALLOWED`: 로컬 agent 읽기만
- `LOCAL_AGENT_USER_APPROVED_CLICK_ALLOWED`: 로컬 agent click (사용자 승인)
- `USER_PRESENT_LOCAL_ONLY`: 사용자 직접 조작만
- `CONTRACT_ALLOWLIST_REQUIRED`: 계약 필요
- `AUTOMATION_BLOCKED`: 완전 차단
- `NEEDS_MANUAL_REVIEW`: 수동 검토 필요

### 3.3 final_verdict Enum

- `SERVER_READONLY_OK`: 서버 브라우저 읽기 가능
- `LOCAL_AGENT_REQUIRED`: 로컬 PC agent 필요
- `USER_PRESENT_REQUIRED`: 사용자 직접 조작 필요
- `API_REQUIRED`: 공식 API 필요
- `OFFICIAL_REMOTE_SUPPORT_REQUIRED`: 공식 원격지원 필요
- `CONTRACT_APPROVAL_REQUIRED`: 계약 승인 필요
- `AUTOMATION_BLOCKED`: 자동화 차단
- `NEEDS_URL_VERIFICATION`: URL 확정 필요
- `NEEDS_MANUAL_SITE_TEST`: 수동 테스트 필요

---

## 4. 인증 방식 분류

### 4.1 감지 키워드

| 인증 방식 | 감지 키워드 | 특성 |
|---------|----------|------|
| 공동인증서 | 공동인증서, 공인인증서, 범용인증서 | 정부/은행, 서명 기능 |
| 금융인증서 | 금융인증서, 금융공동인증서 | 은행/증권, 서명 기능 |
| 간편인증 | PASS, 간편인증, 핸드폰인증 | 사용자 선호, 로컬 필수 |
| 카카오 | 카카오톡, 카카오 로그인 | 간편, OAuth 가능 |
| 네이버 | 네이버, 네이버 로그인 | 간편, OAuth 가능 |
| 아이디/비밀번호 | 아이디, 비밀번호, ID, PASSWORD | 기본, 자동화 위험 |
| OTP | OTP, 일회용비밀번호, 보안카드 | 필수 인증, 사용자 입력 |
| CAPTCHA | reCAPTCHA, 인증문자, 이미지 인증 | 봇 방지, 자동화 불가 |
| 보안프로그램 | 보안프로그램, 키보드보안, 가상키보드 | 보안, 자동화 어려움 |

### 4.2 분류 규칙

```
사이트 로그인 페이지 GET
  ↓
페이지 텍스트 스캔
  ↓
인증 방식 키워드 감지
  ↓
requires_certificate = true/false
requires_financial_certificate = true/false
requires_simple_auth = true/false
requires_otp = true/false
requires_captcha = true/false
requires_security_plugin = true/false
  ↓
final_verdict 판정
```

---

## 5. 접속 제약 분류

### 5.1 감지 키워드

| 제약 | 감지 키워드 | 영향 |
|------|----------|------|
| 원격접속 차단 | 원격접속 차단, 원격지원 불가, 로컬만 | USER_PRESENT_LOCAL_ONLY |
| 보안프로그램 | 설치 필요, 다운로드 | 자동화 어려움 |
| 방화벽 | 방화벽, 특정 IP | 네트워크 제약 |
| 키보드보안 | 가상키보드, 보안 입력 | 자동화 불가 |
| 보안카드 | 보안카드, 카드 인증 | 사용자 직접 |
| Multi-device | 다중기기 차단, 동시접속 제한 | 서버 브라우저 불가 |

---

## 6. 자동화 가능 범위 판정 규칙

### 6.1 Rule-based 판정

```
Step 1: 접속 가능성
- 접속 불가 → AUTOMATION_BLOCKED
- 로그인 필요 → Step 2

Step 2: 인증 방식
- 공동인증서 필요 → USER_PRESENT_LOCAL_ONLY
- 금융인증서 필요 → USER_PRESENT_LOCAL_ONLY
- PASS/간편인증만 → LOCAL_AGENT_REQUIRED 가능
- 아이디/비밀번호 + OTP → USER_PRESENT_REQUIRED
- API 가능 → API_REQUIRED 또는 OAUTH_API_ONLY

Step 3: 접속 제약
- 원격접속 차단 감지 → USER_PRESENT_LOCAL_ONLY
- 보안프로그램 필수 → USER_PRESENT_LOCAL_ONLY
- 방화벽/IP 제약 → USER_PRESENT_REQUIRED

Step 4: 최종 판정
- 모든 제약 통과 → SERVER_BROWSER_READONLY_ALLOWED (가능하면)
- 일부 제약 있음 → LOCAL_AGENT_REQUIRED 또는 USER_PRESENT_REQUIRED
```

### 6.2 사이트 유형별 기본 정책

| 사이트 유형 | 기본 판정 | 공식 API | 비고 |
|-----------|---------|--------|------|
| Google 서비스 | API_REQUIRED | ✓ Gmail/Drive API | OAuth 필수 |
| 은행 (공동인증서) | USER_PRESENT_REQUIRED | ✗ | 로컬 필수 |
| 은행 (금융인증서) | USER_PRESENT_REQUIRED | ✗ | 로컬 필수 |
| 정부24 | LOCAL_AGENT_REQUIRED | ✗ | 공동인증서 |
| 홈택스 | LOCAL_AGENT_REQUIRED | ✗ | 공동인증서 |
| 보험 사이트 | LOCAL_AGENT_REQUIRED | ✗ | 공동인증서 |
| G2B/나라장터 | SERVER_READONLY_OK | ✓ OpenAPI | Read-only만 |
| 공공 로그인 페이지 | LOCAL_AGENT_REQUIRED | ✗ | 공동인증서 |

---

## 7. 감사 수행 방식

### 7.1 허용 범위

**허용:**
- 메인 페이지 GET 요청
- 로그인 페이지 GET 요청
- 페이지 title/url 읽기
- 페이지 body text snippet 읽기
- 인증 방식 문구 감지
- 제약사항 문구 감지
- Read-only 정보 수집

**금지:**
- Input에 값 입력
- 버튼 클릭
- 폼 제출
- 로그인 완료 시도
- 다운로드 실행
- 보안프로그램 설치 실행
- 인증서 선택
- 비밀번호/OTP 입력
- 공동인증서/금융인증서 비밀번호 입력

### 7.2 감사 순서 (Read-only 가능한 경우만)

1. **내부 관리자 사이트** (사용자 승인 필수)
2. **공공 사이트 로그인 페이지**
3. **은행 Generic 로그인 페이지** (사용자 승인 필수)
4. **카드 로그인 페이지**
5. **보험 사이트 로그인 페이지**
6. **조달/G2B 공개 페이지** (Read-only 가능)

### 7.3 각 사이트마다

- 한 사이트씩 직렬 진행
- Title/URL/Snippet만 기록
- Screenshot 저장 금지
- 로그인 버튼 클릭 금지
- 제약 감지되면 STOP 기록

---

## 8. 감사 결과 리포트

### 8.1 리포트 포함 내용

각 사이트마다:
- 접속 가능 여부
- 인증 방식
- 인증서 요구 여부
- 원격접속 차단 여부
- 서버 브라우저 가능 여부
- 로컬 PC agent 필요 여부
- 사용자 직접 조작 필요 여부
- 공식 API 가능 여부
- 최종 판정
- 다음 단계

### 8.2 집계

- 사이트별 감사 결과
- 카테고리별 요약
- 인증 방식 집계
- 제약사항 집계
- 자동화 가능 범위 집계
- 필요한 대체 경로 제안

---

## 9. 안전성 강제

모든 감사는 다음을 지켜야 함:

1. **Safe to Execute = False**: 감사는 데이터 조회만, 변경 없음
2. **Production = False**: Test/감사 환경만
3. **Input/Submit 차단**: 자동화 입력/제출 금지
4. **Credential 보호**: 비밀번호/인증서 비밀번호/OTP 저장 금지
5. **Cookie/Token 미추출**: Session 유지 금지
6. **사용자 승인**: 실제 사이트는 사용자 승인 목록 확인

---

**문서 마지막 수정:** 2026-05-07
