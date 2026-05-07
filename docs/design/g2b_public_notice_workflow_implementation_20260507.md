# G2B 공개 공고 Read-Only 워크플로우 구현 설계

작성일: 2026-05-07  
태스크: G2B_PUBLIC_NOTICE_WORKFLOW_IMPLEMENTATION_1

---

## 목적

G2B(나라장터) 공개 공고 URL에 대해서만 read-only 공개 조회 워크플로우를 구현한다.
`g2b_domain_policy.py` 기반으로 URL을 분류하고, 허용된 경우에만 open/read/navigate 계획을 생성한다.

---

## 입력/출력 Schema

### 입력

| 필드 | 타입 | 설명 |
|---|---|---|
| url | str | 대상 G2B URL |
| operation | str | 요청 operation (read/navigate/open_url 등) |

### 출력 (workflow result)

| 필드 | 타입 | 설명 |
|---|---|---|
| input_url | str | 원본 URL |
| normalized_domain | str | 정규화된 도메인 (www 제거) |
| canonical_url | str | apex domain 기준 정규화 URL |
| operation | str | 요청 operation |
| domain_classification | str | G2B_PUBLIC_READONLY / NEEDS_URL_VERIFICATION 등 |
| compliance_decision | str | ALLOW_BROWSER_READONLY / BLOCK |
| readonly_allowed | bool | 읽기 전용 허용 여부 |
| download_auto_allowed | bool | 항상 False |
| blocked_reason | str | 차단 이유 |
| workflow_steps | list | 실행 계획 (계획만, 실행 아님) |
| allowed_operations | list | 허용 operation 목록 |
| forbidden_operations | list | 금지 operation 목록 |
| requires_url_verification | bool | URL 검증 필요 여부 |
| verdict | str | ALLOWED / BLOCKED / NEEDS_VERIFICATION |
| safe_to_execute | bool | 항상 False |
| message_ko | str | 한글 메시지 |

---

## 허용 operation

- `read`
- `navigate`
- `open_url`

---

## 금지 operation

- `submit`, `type`, `fill`, `click`, `click_submit`
- `download`, `upload`, `post`, `write`, `delete`
- `update`, `login`, `cert`, `payment`, `contract_submit`
- `bid_submit`, `auto_login`

---

## 도메인 정책

| 도메인 | 분류 | 결과 |
|---|---|---|
| g2b.go.kr | G2B_PUBLIC_READONLY | 공개 read-only 허용 |
| www.g2b.go.kr | G2B_PUBLIC_READONLY | g2b.go.kr로 정규화 후 허용 |
| shop.g2b.go.kr | READONLY_CANDIDATE | NEEDS_VERIFICATION |
| 기타 *.g2b.go.kr | NEEDS_URL_VERIFICATION | NEEDS_VERIFICATION |
| 비 G2B 도메인 | NOT_G2B | BLOCKED |

> wildcard `*.g2b.go.kr` 전체 허용 없음.

---

## 차단 경로

| 경로 키워드 | 차단 이유 |
|---|---|
| `/co/menu/EgovUserReqstLogin`, `login` | 로그인 |
| `/cert`, `/certificate`, `/sign`, `/esign` | 인증서/전자서명 |
| `/bid/`, `/bidding/`, `/ptb05` | 입찰 |
| `/ct/menu/ntn02`, `/contract`, `/ctb` | 계약 |
| `/pay`, `/payment`, `/checkout` | 결제 |

---

## download 정책

- `download_auto_allowed = False` 항상.
- `download` operation 자체가 FORBIDDEN_OPERATIONS에 포함.
- 파일 목록 **조회** (`read` operation)는 허용.
- 파일 **다운로드** 실행은 금지.

---

## workflow_steps 정의

허용된 케이스에서 반환되는 계획 예시 (read):

```json
[
  {"step": "normalize_url", "mode": "read_only"},
  {"step": "classify_domain", "mode": "read_only"},
  {"step": "preflight_policy", "mode": "read_only"},
  {"step": "open_url", "mode": "read_only"},
  {"step": "read_public_notice", "mode": "read_only"}
]
```

navigate:
```json
[
  {"step": "normalize_url", "mode": "read_only"},
  {"step": "classify_domain", "mode": "read_only"},
  {"step": "preflight_policy", "mode": "read_only"},
  {"step": "navigate_to_url", "mode": "read_only"}
]
```

금지 step: `click`, `type`, `fill`, `submit`, `download`, `login`, `cert`, `payment`, `contract_submit`, `bid_submit`

---

## 이번 단계에서 하지 않은 것

- click/type/fill/submit/download 자동 실행 구현 없음.
- 로그인/인증/입찰/계약/결제 경로 허용 없음.
- wildcard 도메인 허용 없음.
- task_executor/browser_worker live dispatch 없음.
- DB write 없음.
- 실제 브라우저 실행 없음.

---

## 다음 단계 후보

- `G2B_PUBLIC_NOTICE_PREFLIGHT_CHAIN_1`: preflight 체인 통합 (allowlist → compliance → boundary → workflow)
- `G2B_PUBLIC_NOTICE_READ_DISPATCH_1`: 실제 read dispatch 승인 흐름 (USER_PRESENT 필요 여부 판단 포함)
- `G2B_PUBLIC_NOTICE_RESULT_PARSER_1`: read 결과 파싱 및 구조화
