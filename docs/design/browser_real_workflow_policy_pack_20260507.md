# Browser Real Workflow Policy Pack 설계

**작성일:** 2026-05-07  
**단계:** BROWSER_REAL_WORKFLOW_POLICY_PACK_1  
**기준 HEAD:** c9254ee  
**상태:** 설계 완료 (구현 전)

---

## 1. 목적

실제 업무 단위로 browser action을 묶는 정책을 설계한다.

- workflow 단위로 allowlist / gate / audit / approval을 연결한다.
- 단일 action 기준이 아니라 **업무 목적 기준**으로 위험도와 승인 조건을 판단한다.
- 1차 범위: G2B/나라장터 공고 조회, 상세 열람, 첨부파일 다운로드 계획, 내부 관리자 상태 조회
- 로그인, 비밀번호 입력, 인증서, OTP, 입찰 제출, 신청 제출, 결제, 삭제/변경/등록은 명시적으로 차단 설계

---

## 2. 1차 실무 workflow 목록

### A. g2b_notice_search_readonly

| 항목 | 값 |
|---|---|
| 목적 | G2B/나라장터 공고 검색 결과 조회 |
| 허용 operation | read, navigate |
| 금지 operation | click, type, submit |
| approval_required | false |
| audit_required | optional |
| production_allowed | false |
| safe_to_execute | false |
| 비고 | 화면 조회만. 어떠한 입력도 없음 |

### B. g2b_notice_detail_readonly

| 항목 | 값 |
|---|---|
| 목적 | G2B 공고 상세 열람 (공고번호, 품명, 금액, 마감일 등 read-only 조회) |
| 허용 operation | read, navigate, open_url |
| 금지 operation | click, type, submit |
| approval_required | false |
| audit_required | optional |
| production_allowed | false |
| safe_to_execute | false |
| 비고 | URL 접근만. DOM 조작 없음 |

### C. g2b_attachment_download_plan

| 항목 | 값 |
|---|---|
| 목적 | 공고 첨부파일 다운로드 계획 수립 (실제 다운로드 실행 금지) |
| 허용 operation | read (파일 목록 확인만) |
| 금지 operation | click, type, submit, navigate(다운로드 URL) |
| approval_required | true (다운로드 실행 승인 별도 필요) |
| audit_required | true |
| production_allowed | false |
| safe_to_execute | false |
| 비고 | 파일 목록/링크 확인만. 실제 다운로드 실행은 이번 단계 차단 |

### D. internal_admin_status_readonly

| 항목 | 값 |
|---|---|
| 목적 | 내부 관리자 시스템 상태 조회 (대시보드 read-only) |
| 허용 operation | read, navigate |
| 금지 operation | click, type, submit |
| approval_required | false |
| audit_required | optional |
| production_allowed | false |
| safe_to_execute | false |
| 비고 | 내부 도메인 한정. 외부 공개 URL 접근 금지 |

### E. future_login_blocked

| 항목 | 값 |
|---|---|
| 목적 | 향후 로그인 입력 workflow 차단 정책 |
| type 포함 시 | BLOCK |
| 금지 입력 패턴 | password, otp, certificate, session, credential, cookie, token |
| 조건 | approval UI / gate / audit / 업무 승인 전까지 실행 금지 |
| safe_to_execute | false |
| 비고 | 현 단계에서 type operation은 전면 BLOCK |

### F. future_submit_blocked

| 항목 | 값 |
|---|---|
| 목적 | 향후 제출 workflow 차단 정책 |
| gate_decision | DENY_BY_DEFAULT |
| 차단 대상 | 입찰 제출, 신청 제출, 민원 제출, 결제, 등록, 삭제, 변경 모두 차단 |
| safe_to_execute | false |
| 비고 | submit은 gate_module 구현 완료 + 별도 승인 후에만 검토 가능 |

---

## 3. site allowlist 정책 스키마

```python
@dataclass
class SitePolicy:
    site_policy_id: str          # 고유 식별자
    site_type: str               # "government" | "internal" | "public" | "blocked"
    business_domain: str         # 업무 도메인 설명

    allowed_domains: list[str]   # 허용 도메인 목록 (실제 도메인은 검증 후 확정)
    blocked_domains: list[str]   # 명시적 차단 도메인

    allowed_paths: list[str]     # 허용 경로 패턴 (빈 목록 = 전체 차단)
    blocked_paths: list[str]     # 명시적 차단 경로 (로그인, 입찰, 제출 등)

    allowed_operation_types: list[str]   # 허용 operation_type
    blocked_operation_types: list[str]   # 차단 operation_type

    requires_tenant_context: bool   # tenant_scope 필수 여부
    requires_user_context: bool     # submitted_by 필수 여부
    requires_site_context: bool     # site_id 필수 여부

    approval_required_operations: list[str]  # 승인 필요 operation 목록
    audit_required_operations: list[str]     # 감사 필요 operation 목록

    production_allowed: bool   # 항상 false (현 단계)
    dry_run_only: bool         # 항상 true (현 단계)

    notes: str                 # 정책 설명
```

---

## 4. G2B 사이트 정책 (read-only 조회 한정)

```
site_policy_id: G2B_READONLY_POLICY_1
site_type: government
business_domain: 나라장터(G2B) 공고 조회

주의:
- 실제 도메인(g2b.go.kr, www.g2b.go.kr 등)은 운영 검증 후 확정
- 현재 단계에서 도메인은 PLACEHOLDER로만 표기
- 기존 controlled_submit.py에서 G2B는 차단 대상으로 명시됨
- 이번 설계는 read/navigate 한정 조회만 허용하는 정책을 고정

allowed_operation_types: ["read", "navigate"]
blocked_operation_types: ["click", "type", "submit", "open_url"]

allowed_paths: ["/search/*", "/notice/*", "/detail/*"]
blocked_paths: ["/login*", "/bid*", "/submit*", "/apply*", "/pay*", "/delete*", "/update*", "/register*", "/cert*", "/otp*"]

approval_required_operations: []  (read/navigate는 승인 불필요)
audit_required_operations: []     (read/navigate는 감사 선택)

production_allowed: false
dry_run_only: true
```

---

## 5. allowlist → gate → audit → approval 연계 흐름

```
[workflow 요청]
      ↓
[SitePolicy 확인]         ← 이번 설계 대상
  site_type / allowed_domains / allowed_paths / allowed_operation_types
      ↓ PASS
[AllowlistPolicy]         ← BROWSER_ALLOWLIST_POLICY_DESIGN_1
  domain allowlist / operation_type 허용 여부
      ↓ policy_verdict=ALLOW
[SubmitExecutionGate]     ← BROWSER_GATE_MODULE_DESIGN_1
  preview_hash / validation_id / approval_id / tenant_scope
      ↓ gate_decision=ALLOW
[AuditModule]             ← BROWSER_AUDIT_MODULE_DESIGN_1
  audit_context / sensitive_field_redaction / append-only log
      ↓ event_stage=AUDIT_READY
[ApprovalCheck]           ← 설계 예정
  approval_status=approved 확인
      ↓
[Dispatcher]              ← 미연결 (다음 단계)
```

---

## 6. approval 정책 설계

### 승인 필요 기준

| operation_type | approval_required | 근거 |
|---|---|---|
| read | false | 상태 변경 없음 |
| navigate | false | 상태 변경 없음 |
| open_url | true | URL 접근 이력 기록 필요 |
| click | true | DOM 상태 변경 가능 |
| type | true | 입력값 형태 기록 필요 (sensitive 위험) |
| submit | true | 상태 변경 확정. DENY_BY_DEFAULT |

### 승인 단계 (향후 구현 예정)

1. **요청자 승인 (requester approval)**: 업무 담당자가 action 목적을 명시하고 요청
2. **관리자 승인 (admin approval)**: 내부 관리자가 요청 내용 검토 후 approval_id 발급
3. **감사 기록 (audit log)**: 승인 이력 append-only JSONL 기록
4. **gate 통과 (gate pass)**: approval_id + approval_status=approved → gate_decision=ALLOW

### 현재 단계 승인 정책

- approval UI 미구현 → click/type/submit 실행 불가
- approval_id 없음 → gate BLOCK
- approval_status=pending → gate BLOCK
- safe_to_execute=false 강제

---

## 7. 고위험 업무 명시적 차단 목록

| 업무 | 이유 | 현재 상태 |
|---|---|---|
| G2B 입찰 제출 | submit, 실제 입찰 결과에 영향 | DENY_BY_DEFAULT |
| G2B 신청 제출 | submit, 계약 관계 변경 | DENY_BY_DEFAULT |
| 민원 제출 | submit, 외부 기관 전달 | DENY_BY_DEFAULT |
| 결제/송금 | submit, 금전 거래 | DENY_BY_DEFAULT |
| 회원 등록/삭제 | submit, 계정 상태 변경 | DENY_BY_DEFAULT |
| 데이터 변경/삭제 | submit/click, DB 상태 변경 | DENY_BY_DEFAULT |
| 로그인 비밀번호 입력 | type + password hint | BLOCK |
| OTP/인증서 입력 | type + credential hint | BLOCK |
| 세션/쿠키 조작 | type + session/cookie hint | BLOCK |
| 파일 실제 다운로드 | click + download URL | BLOCK (이번 단계) |

---

## 8. 현재 단계 전역 제약

| 제약 | 값 | 이유 |
|---|---|---|
| production_allowed | false | dispatcher 미연결, audit writer 미구현 |
| safe_to_execute | false | dispatcher 미연결 |
| dry_run_only | true | 실제 browser 조작 없음 |
| submit | DENY_BY_DEFAULT | gate_module 미완성 |
| type | BLOCK (password 계열) | sensitive input 정책 |
| dispatcher_connected | false | 다음 단계 예정 |
| task_executor_connected | false | 다음 단계 예정 |

---

## 9. 실제 모듈 import 금지 (설계 단계)

이번 설계 단계에서 아래를 import하거나 호출하지 않는다:
- 실제 브라우저 모듈 (playwright, browser_worker)
- dispatcher 모듈
- task_executor 모듈
- audit log writer (append_audit_log)
- approval UI
- DB write 코드

테스트는 fixture/schema만 검증한다.

---

## 10. 다음 단계 제안

**BROWSER_AUDIT_WRITER_IMPLEMENTATION_1**

`submit_audit_log.py` 실제 구현 단계.  
AuditEntry 데이터클래스, append-only JSONL writer,  
sensitive field redaction 로직을 구현하고 단위 테스트로 고정한다.
