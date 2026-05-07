# G2B 공개 공고 Dry-Run Workflow Integration 설계

작성일: 2026-05-07  
태스크: G2B_PUBLIC_NOTICE_WORKFLOW_DRYRUN_INTEGRATION_1

---

## 이번 단계 목적

`g2b_public_notice_workflow.py`를 기존 browser action/gate 계층에 dry-run 전용으로 연결한다.  
G2B 공개 공고 URL 요청이 들어왔을 때 기존 정책 gate와 workflow plan이 함께 동작하는지 검증하는 통합 계층까지만 구현한다.

> **이번 단계는 실제 브라우저 실행이 아니다.**  
> **실제 G2B 접속도 아니다.**  
> **browser_worker/task_executor live 연결은 하지 않았다.**  
> **click/type/fill/submit/download는 계속 BLOCK이다.**  
> **다음 단계에서만 승인 후 read-only browser execution gate를 검토한다.**

---

## dry-run adapter 위치

```
ai_orchestrator/browser_tool/g2b_public_notice_dryrun_adapter.py
```

---

## 입력/출력 Schema

### 입력

| 필드 | 타입 | 설명 |
|---|---|---|
| url | str | 대상 G2B URL |
| operation | str | read / navigate / open_url |
| workflow_run_id | str | 워크플로우 추적 ID (선택) |
| tenant_id | str | 테넌트 ID (선택) |
| user_id | str | 사용자 ID (선택) |
| agent_id | str | 에이전트 ID (선택) |

### 출력

| 필드 | 타입 | 고정값 | 설명 |
|---|---|---|---|
| action_type | str | G2B_PUBLIC_NOTICE_DRYRUN | 액션 타입 |
| dry_run | bool | **항상 True** | dry-run 여부 |
| safe_to_execute | bool | **항상 False** | 실행 안전 여부 |
| execution_dispatched | bool | **항상 False** | 실제 dispatch 여부 |
| live_browser_worker_called | bool | **항상 False** | live 브라우저 호출 여부 |
| download_auto_allowed | bool | **항상 False** | 자동 다운로드 허용 여부 |
| adapter_decision | str | | G2B_DRYRUN_READONLY_READY / G2B_DRYRUN_BLOCKED / G2B_DRYRUN_NEEDS_VERIFICATION |
| policy_verdict | str | | ALLOWED / BLOCKED / NEEDS_VERIFICATION |
| workflow_steps | list | | 실행 계획 (계획만, 실행 아님) |
| execution_planned | bool | | True = 계획 수립됨 (실행 아님) |
| canonical_url | str | | apex domain 정규화 URL |
| allowed_operations | list | | read / navigate / open_url |
| forbidden_operations | list | | submit / type / fill / click / download ... |

---

## 정책 판정 순서

```
1. operation block check (adapter 레벨)
   → click/type/fill/submit/download/upload/login/cert/payment/contract/bid_submit → 즉시 BLOCKED
2. build_g2b_public_notice_workflow() 호출
   2-1. URL normalize
   2-2. G2B domain classification
   2-3. path block check
   2-4. operation block check (workflow 레벨)
   2-5. allowlist/site compliance preflight (g2b_domain_policy 내부)
   2-6. workflow plan build
3. validate workflow result
4. dry-run result 구성 및 반환
   → BLOCKED 상태에서 workflow_steps 생성 없음
```

---

## live dispatch 금지 보증

| 항목 | 보증 방법 | 결과 |
|---|---|---|
| task_executor 호출 없음 | import 라인 정적 검사 | 없음 확인 |
| browser_worker 호출 없음 | import 라인 정적 검사 | 없음 확인 |
| Playwright/Selenium 없음 | import 라인 정적 검사 | 없음 확인 |
| requests/httpx G2B 접속 없음 | import 라인 정적 검사 | 없음 확인 |
| page.click/type/fill/goto 없음 | 소스 코드 검사 | 없음 확인 |
| cookie/session/token 추출 없음 | 소스 코드 검사 | 없음 확인 |
| DB write 없음 | import 라인 정적 검사 | 없음 확인 |

---

## 허용 operation

- `read`
- `navigate`
- `open_url`

---

## 차단 operation

- `click`, `type`, `fill`, `submit`, `click_submit`
- `download`, `upload`, `post`, `write`, `delete`
- `update`, `login`, `cert`, `payment`, `contract`
- `bid_submit`, `auto_login`, `contract_submit`

---

## 테스트 결과

| 파일 | 통과 |
|---|---|
| test_g2b_public_notice_workflow_dryrun_integration_20260507.py | 39/39 |
| test_g2b_public_notice_workflow_20260507.py | 38/38 |
| test_g2b_domain_normalization_policy_20260507.py + matrix | 51/51 |
| browser gate 관련 5개 파일 | 206/206 |

---

## 다음 단계 후보

- `G2B_PUBLIC_NOTICE_READ_EXECUTION_GATE_1`: 승인 후 실제 read-only browser execution gate 검토
- `G2B_PUBLIC_NOTICE_PREFLIGHT_CHAIN_INTEGRATION_1`: preflight chain(allowlist → compliance → boundary → workflow)과 직접 통합
- `G2B_PUBLIC_NOTICE_RESULT_SCHEMA_1`: read 결과 파싱 및 구조화
