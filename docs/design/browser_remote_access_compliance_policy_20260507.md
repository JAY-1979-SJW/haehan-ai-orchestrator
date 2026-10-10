# Browser Remote Access Compliance Policy

**문서 버전:** 1.0  
**작성일:** 2026-05-07  
**대상:** Browser Automation Workflow System  
**목적:** 사이트별 원격 접속/자동화 허용 정책 분류 및 공식 허용 방식 설계

---

## 1. 목적

이 정책은 다음을 명시합니다:

1. **우회하지 않기**: 사이트가 자동화를 금지하면 금지한다. 우회 설계는 금지.
2. **공식 허용 방식**: API, OAuth, 관리자 승인, 사용자 직접 조작 방식만 사용.
3. **역할 분리**: Browser automation, API connector, Local agent, Manual approval 명확히 구분.
4. **안전성 강제**: safe_to_execute=false, production_allowed=false, 민감 데이터 마스킹 유지.
5. **기존 정책 연계**: allowlist/gate/approval/audit/action_registry preflight과 통합.

---

## 2. 사이트 자동화 Capability 분류

### 2.1 Capability Enum

사이트별 자동화 허용 정책을 다음으로 분류합니다:

| Capability | 설명 | Browser Automation | API Connector | Local Agent | 비고 |
|-----------|------|------------------|---------------|------------|------|
| `API_ONLY` | 공식 API만 지원 | ❌ BLOCK | ✓ ALLOW | - | Google Drive, Calendar 등 |
| `OAUTH_API_ONLY` | OAuth + API만 지원 | ❌ BLOCK | ✓ ALLOW | - | Gmail, Google 서비스 |
| `WORKSPACE_ADMIN_DELEGATED_API` | Workspace 관리자 위임 API | ❌ BLOCK | ✓ ALLOW | - | Google Workspace 내부 |
| `USER_PRESENT_LOCAL_ONLY` | 사용자 현재 + 로컬만 | ❌ BLOCK (Server) | ❌ BLOCK | ✓ ALLOW | 2FA/MFA 필수 사이트 |
| `OFFICIAL_REMOTE_SUPPORT_ONLY` | 공식 원격지원 도구 | ❌ BLOCK | ❌ BLOCK | ✓ (Chrome RD 등) | remotedesktop.google.com |
| `BROWSER_READONLY_ALLOWED` | 브라우저 읽기만 허용 | ✓ READ | ✓ READ | ✓ READ | inspect, 정보수집 가능 |
| `BROWSER_CONTROLLED_CLICK_ALLOWED` | 브라우저 controlled click 허용 | ✓ CLICK | - | - | 클릭만, 입력 불가 |
| `CONTRACT_ALLOWLIST_REQUIRED` | 계약/파트너 허용 필요 | ✓ (승인 시) | ✓ (승인 시) | ✓ (승인 시) | 사이트 소유자 승인 필수 |
| `AUTOMATION_BLOCKED` | 자동화 전면 차단 | ❌ BLOCK | ❌ BLOCK | ❌ BLOCK | 사이트 정책 상 금지 |
| `NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL` | 법률/사이트 소유자 승인 필요 | ❌ BLOCK (자동) | ❌ BLOCK (자동) | ❌ BLOCK (자동) | 소유자 승인 후 CONTRACT_ALLOWLIST_REQUIRED로 전환 |

---

## 3. Google 정책

### 3.1 Google 서비스 기본 분류

| 서비스 | Domain | Capability | Browser Automation | 대체 경로 |
|--------|--------|-----------|------------------|---------|
| Google 로그인 | accounts.google.com | `AUTOMATION_BLOCKED` | ❌ BLOCK | OAuth consent (사용자 직접) |
| Gmail | mail.google.com | `OAUTH_API_ONLY` | ❌ BLOCK | Gmail API + OAuth |
| Google Drive | drive.google.com | `OAUTH_API_ONLY` | ❌ BLOCK | Drive API + OAuth |
| Google Calendar | calendar.google.com | `OAUTH_API_ONLY` | ❌ BLOCK | Calendar API + OAuth |
| Google Docs | docs.google.com | `OAUTH_API_ONLY` | ❌ BLOCK | Docs API + OAuth |
| Google Sheets | sheets.google.com | `OAUTH_API_ONLY` | ❌ BLOCK | Sheets API + OAuth |
| Google Chrome RD | remotedesktop.google.com | `OFFICIAL_REMOTE_SUPPORT_ONLY` | ❌ BLOCK | Chrome Remote Desktop (공식) |
| Google Workspace (Admin) | workspace.google.com | `WORKSPACE_ADMIN_DELEGATED_API` | ❌ BLOCK | Admin API + Service Account |

### 3.2 Google 금지 항목 (명시적)

다음은 어떤 상황에서도 금지:

- ❌ Google 로그인 폼 자동 입력 (브라우저)
- ❌ 비밀번호 자동 입력
- ❌ OTP/2FA 자동 처리
- ❌ 쿠키/session 추출 및 재사용
- ❌ 보안 경고 우회 (예: "unusual activity" 무시)
- ❌ CAPTCHA 우회 (예: CAPTCHA 자동 해결)
- ❌ 계정 위험 감지 우회
- ❌ headless/bot 탐지 회피
- ❌ User-Agent 위장
- ❌ IP/Proxy 우회
- ❌ Fingerprint 우회

### 3.3 Google 허용 경로

다음만 허용:

1. **OAuth Consent**: 사용자가 직접 Google 로그인 → 승인 → token 발급
   - 워크플로우에서 OAuth flow 시작, 사용자 직접 승인
   - Browser automation 불가 (사용자 직접만)

2. **Google API + OAuth Token**:
   - Gmail API, Drive API, Calendar API, Docs API, Sheets API 사용
   - 이전 OAuth consent로 획득한 token 사용
   - API connector route로 처리

3. **Google Workspace Service Account** (관리자 위임):
   - Workspace 조직 내부
   - 관리자가 service account에 역할 위임
   - Admin API + Workspace APIs 사용
   - API connector route로 처리

4. **Chrome Remote Desktop** (공식 원격지원):
   - 공식 remotedesktop.google.com 도구
   - 사용자가 직접 접속 및 승인
   - 원격 컴퓨터를 직접 조작
   - Browser automation 미사용

---

## 4. 특정 사이트 원격 접속/자동화 제한 처리

### 4.1 원격 접속 금지 사이트

사이트가 원격 접속(Remote access) 또는 자동화(Automation)를 금지하는 경우:

**기본 분류**: `AUTOMATION_BLOCKED`

**확인 포인트**:
1. 사이트 이용약관에 "자동화 금지" 명시?
2. 로봇 정책 (robots.txt)에 제한?
3. 보안 정책상 비정상 접속 탐지 및 차단?
4. MFA/OTP 강제?
5. 공식 API 제공?

**처리**:
- 공식 API 있음 → `API_ONLY` 또는 `OAUTH_API_ONLY`로 재분류
- API 없음 → `AUTOMATION_BLOCKED` 유지
- 예외 가능 (계약) → `CONTRACT_ALLOWLIST_REQUIRED`로 전환

### 4.2 API 우선 원칙

사이트가 공식 API를 제공하면:

- Browser automation은 원칙적으로 `BLOCK`
- API connector route로 전환
- 예외: 공식 API가 필요한 기능을 제공하지 않을 때만 검토

### 4.3 사용자 직접 조작 필수

MFA/OTP가 강제되는 사이트:

- Server browser automation: `BLOCK`
- Local user-present agent: 허용 (사용자가 직접 OTP 입력)
- Capability: `USER_PRESENT_LOCAL_ONLY`

### 4.4 계약/파트너 허용

특정 사이트가 계약 파트너에게 자동화 허용:

- Capability: `CONTRACT_ALLOWLIST_REQUIRED`
- 조건: 사이트 소유자 승인 레코드 필수
- Approval 레코드: `site_owner_approval_id` 필드에 저장
- 승인 없음 → `BLOCK`

### 4.5 미지의 사이트

처음 보는 사이트:

- 기본 Capability: `NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL`
- 처리: 법률검토 또는 사이트 소유자 승인 대기
- 승인 완료 후: 해당 capability로 업그레이드 (CONTRACT_ALLOWLIST_REQUIRED 등)

---

## 5. allowlist_preflight와 Compliance 정책 연계

### 5.1 평가 순서

다음 순서로 직렬 평가:

```
site_compliance_check (신규)
  ↓
action_registry_preflight (기존)
  ↓
gate_approval_preflight (기존)
  ↓
allowlist_preflight (기존)
  ↓
dry_run_dispatcher_preflight (미래)
  ↓
real_browser_execution (미래)
```

### 5.2 Site Compliance 정책 적용

**모든 browser automation 요청은 먼저 site compliance check를 통과해야 함.**

#### Case 1: AUTOMATION_BLOCKED

```
site_compliance_decision = "BLOCK"
block_reason = "AUTOMATION_NOT_ALLOWED_BY_SITE_POLICY"
↓ (allowlist/action/gate preflight 평가 안 함)
dry_run_dispatcher → BLOCK
```

#### Case 2: OAUTH_API_ONLY

```
site_compliance_decision = "REQUIRE_API_CONNECTOR"
browser_automation_allowed = false
↓ (browser automation 건 차단, API route로 전환)
action_registry_preflight에서도 BLOCK
↓
(사용자는 API connector를 사용해야 함)
```

#### Case 3: USER_PRESENT_LOCAL_ONLY

```
site_compliance_decision = "REQUIRE_USER_PRESENT_LOCAL"
server_browser_automation_allowed = false
↓
production_mode인지 확인
  - production: BLOCK (서버 browser 금지)
  - local with user_present=true: 허용 (사용자 입력 대기)
```

#### Case 4: BROWSER_READONLY_ALLOWED

```
site_compliance_decision = "ALLOW_BROWSER_READONLY"
allowed_operations = {read, navigate, open_url}
blocked_operations = {type, click, submit, select_option}
↓
allowlist_preflight 평가 (기존 정책 적용)
→ domain allowed → action_registry_preflight 평가
  → browser.inspect, browser.plan_click (read만) 가능
  → browser.plan_open_url (navigate만) 가능
  → browser.execute_click, browser.execute_type BLOCK
```

#### Case 5: CONTRACT_ALLOWLIST_REQUIRED

```
site_compliance_decision = "REQUIRE_SITE_OWNER_APPROVAL"
site_owner_approval_required = true
↓
gate_approval_preflight에서 site_owner_approval_id 확인
  - 승인 있음: ALLOW_DRY_RUN_DISPATCH
  - 승인 없음: REQUIRE_APPROVAL 또는 BLOCK
```

#### Case 6: NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL

```
site_compliance_decision = "BLOCK"
block_reason = "NEEDS_LEGAL_OR_SITE_OWNER_APPROVAL"
↓ (모든 기능 차단)
dry_run_dispatcher → BLOCK
(법률검토/사이트 소유자 승인 대기 메시지)
```

---

## 6. 금지된 우회 방식 (명시적)

다음은 어떤 상황에서도 구현 불가:

### 6.1 인증 우회

- ❌ Proxy를 통한 원격 접속 금지 우회
- ❌ VPN/IP 회피 (다른 IP로 위장)
- ❌ User-Agent 위장 (Chrome 아님으로 속이기)
- ❌ Fingerprint 우회 (브라우저 특성 숨기기)
- ❌ Headless 탐지 회피
- ❌ 봇 탐지 회피
- ❌ 비정상 접속 탐지 무시

### 6.2 인증 강제 우회

- ❌ 2FA/MFA 자동 처리 (OTP 자동 입력, 보안 질문 자동 답변)
- ❌ CAPTCHA 우회 (CAPTCHA 자동 해결 서비스 사용)
- ❌ 쿠키/session 추출 및 재사용
- ❌ token 탈취 및 재사용 (정당한 OAuth 외)
- ❌ 보안 경고 무시 (예: "unusual activity" 자동 승인)
- ❌ 계정 위험 감지 회피

### 6.3 보안 정책 우회

- ❌ Rate limiting 우회
- ❌ API 할당량(Quota) 우회
- ❌ 사이트 이용약관 위반
- ❌ 로봇 정책(robots.txt) 위반
- ❌ 저작권/라이선스 위반

### 6.4 기술적 해킹

- ❌ JavaScript 주입/XSS
- ❌ SQL injection
- ❌ Path traversal
- ❌ 권한 상승
- ❌ 세션 하이재킹
- ❌ MITM (Man-in-the-middle) 공격

---

## 7. 기존 Preflight 정책과의 충돌 방지

### 7.1 안전성 정책 유지

다음 정책은 site compliance 이후에도 계속 유지:

| 정책 | 강제 방식 | 비고 |
|-----|---------|------|
| safe_to_execute=false | 모든 경로 | Dry-run만 허용, 실행 금지 |
| production_allowed=false | 모든 경로 | Production 환경 자동화 금지 |
| type operation blocked | 모든 경로 | 입력 자동화 전면 차단 |
| submit operation blocked | 모든 경로 | 폼 제출 자동화 전면 차단 |

### 7.2 allowlist와의 조합

Site compliance + allowlist:

```
site_compliance = "BROWSER_READONLY_ALLOWED" AND
allowlist = domain "example.com" is allowed
↓
결과: example.com의 read-only 브라우저 작업 허용

site_compliance = "OAUTH_API_ONLY" AND
allowlist = domain "mail.google.com" is allowed
↓
결과: 브라우저 작업 BLOCK (API connector로 전환)
      allowlist 일치 여부와 무관하게 BLOCK
```

### 7.3 Action Registry와의 조합

Site compliance + action registry:

```
site_compliance = "BROWSER_READONLY_ALLOWED" AND
action = "browser.execute_click"
↓
결과: action registry에서 이미 BLOCK (approval 필요)
      site compliance는 click 자체를 허용하지 않음
      → 이중 차단으로 더욱 안전

site_compliance = "CONTRACT_ALLOWLIST_REQUIRED" AND
action = "browser.open_url_controlled" AND
site_owner_approval = present
↓
결과: gate_approval_preflight에서 승인 확인
      → 허용
```

---

## 8. 구현 상세

### 8.1 Site Compliance Policy 모듈

**파일**: `ai_orchestrator/browser_tool/policy/site_compliance_policy.py`

**핵심 함수**:
```python
def get_site_compliance_policy(
    target_domain: str | None,
    site_type: str | None = None
) -> dict
```

**응답 포맷**:
```python
{
    "target_domain": "mail.google.com",
    "site_type": "google_service",
    "capability": "OAUTH_API_ONLY",
    "browser_automation_allowed": false,
    "api_connector_required": true,
    "user_present_required": false,
    "site_owner_approval_required": false,
    "official_remote_support_required": false,
    "block_reason": null,
}
```

### 8.2 Site Compliance Evaluation

**함수**:
```python
def evaluate_site_compliance(payload: dict) -> dict
```

**입력**:
```python
{
    "target_domain": "mail.google.com",
    "target_url": "https://mail.google.com/...",
    "action_name": "browser.inspect",
    "operation_type": "read",
    "user_present": false,
    "production_mode": false,
    "workflow_id": "workflow_123",
}
```

**출력**:
```python
{
    "compliance_decision": "REQUIRE_API_CONNECTOR",
    "site_capability": "OAUTH_API_ONLY",
    "browser_automation_allowed": false,
    "api_connector_required": true,
    "block_reason": "OAUTH_API_REQUIRED",
    "safe_to_dispatch": false,
    "safe_to_execute": false,
    "message_ko": "mail.google.com: OAuth API 필수, 브라우저 자동화 차단",
}
```

### 8.3 Compliance Decision Values

- `ALLOW_BROWSER_READONLY`: Read-only 브라우저 작업 허용
- `REQUIRE_API_CONNECTOR`: API connector로 전환 필요
- `REQUIRE_USER_PRESENT_LOCAL`: 사용자 직접 (로컬)만 허용
- `REQUIRE_OFFICIAL_REMOTE_SUPPORT`: 공식 원격지원 도구만 허용
- `REQUIRE_SITE_OWNER_APPROVAL`: 사이트 소유자 승인 필요
- `BLOCK`: 자동화 완전 차단

---

## 9. 정책 결정 매트릭스

| Capability | Read | Navigate | Click | Type | Submit | API | OAuth |
|-----------|------|----------|-------|------|--------|-----|-------|
| API_ONLY | ❌ | ❌ | ❌ | ❌ | ❌ | ✓ | - |
| OAUTH_API_ONLY | ❌ | ❌ | ❌ | ❌ | ❌ | ✓ | ✓ |
| WORKSPACE_ADMIN | ❌ | ❌ | ❌ | ❌ | ❌ | ✓ | - |
| USER_PRESENT_LOCAL | ✓ | ✓ | ✓ | ✓ | ✓ | - | - |
| OFFICIAL_REMOTE | - | - | - | - | - | - | - |
| BROWSER_READONLY | ✓ | ✓ | ❌ | ❌ | ❌ | - | - |
| BROWSER_CLICK | ✓ | ✓ | ✓ | ❌ | ❌ | - | - |
| CONTRACT_ALLOWED | ✓ | ✓ | ✓ | ✓ | ✓ | - | - |
| AUTOMATION_BLOCKED | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| NEEDS_APPROVAL | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## 10. 구현 원칙

### 10.1 읽기 전용

Site compliance policy 모듈은:
- ✓ 기존 allowlist/action/gate/approval 읽기
- ✓ Fixture/설정 읽기
- ❌ DB 쓰기
- ❌ Approval 레코드 쓰기
- ❌ Audit 레코드 자동 쓰기
- ❌ 실제 browser 실행

### 10.2 Dry-run 전용

모든 compliance 평가:
- ✓ dry-run dispatcher 입력으로 사용
- ❌ 실행 권한 부여 금지 (safe_to_execute=false)
- ❌ production 환경 자동화 승인 금지

### 10.3 감시 기록

Compliance block 또는 approval 필요 시:
- ✓ Audit 레코드에 decision 기록 (별도 handler)
- ✓ Compliance decision 정보 로깅
- ❌ 직접 audit append (dispatcher/handler에서)

---

## 11. 향후 확장

### 11.1 사이트 동적 정책 업데이트

```python
# Future: site_compliance_policy.json 외부 로드
def load_site_compliance_policies(config_path: str) -> dict
```

### 11.2 사이트 소유자 승인 통합

```python
# Future: site_owner_approval_id 검증
def verify_site_owner_approval(
    target_domain: str,
    approval_id: str,
    approval_store_path: str
) -> bool
```

### 11.3 법률 검토 기록

```python
# Future: legal review decision 저장
class LegalReviewRecord:
    review_id: str
    target_domain: str
    reviewed_by: str
    legal_decision: Literal["APPROVED", "REJECTED", "PENDING"]
    reasons: list[str]
    reviewed_at: datetime
```

---

## 12. 금지 항목 체크리스트

구현 시 다음 항목은 **절대 포함 금지**:

- ❌ Google 로그인 폼 자동 입력
- ❌ 비밀번호/OTP/2FA 자동 처리
- ❌ 쿠키/session/token 추출
- ❌ CAPTCHA 우회
- ❌ 보안 경고 무시
- ❌ Proxy/VPN/IP 우회
- ❌ User-Agent 위장
- ❌ Fingerprint 우회
- ❌ Headless 탐지 회피
- ❌ 봇 탐지 회피
- ❌ 실제 browser 실행
- ❌ 실제 사이트 접속
- ❌ dispatcher/action_registry/task_executor 연결

---

**문서 마지막 수정:** 2026-05-07
