# Browser Engine Routing Dispatch Dryrun Integration

날짜: 2026-05-07

## 1. 목적

preflight chain 결과를 받아 dry-run dispatcher 응답을 구성한다.
실제 브라우저/Playwright/API 실행 없이 응답만 반환한다.

- 실제 브라우저/Playwright/사이트 접근 없음
- click/type/fill/submit 코드 없음
- cookie/session/token 추출 없음
- dispatcher/task_executor 실제 연결 없음
- safe_to_execute: 모든 케이스에서 항상 False
- dry_run: 항상 True

## 2. Module API

### 함수 목록

| 함수 | 설명 |
|---|---|
| `build_dryrun_dispatch_context(payload)` | payload → chain 결과 포함 dispatch 컨텍스트 구성 |
| `evaluate_browser_engine_routing_dispatch_dryrun(payload)` | 전체 dry-run dispatch 평가 (chain 포함) |
| `build_dryrun_dispatch_response(chain_result)` | chain 결과 → dry-run dispatch 응답 구성 |
| `validate_dryrun_dispatch_result(result)` | 결과 필드/정책 준수 검증 |

### 입력 필드 (payload)

| 필드 | 타입 | 설명 |
|---|---|---|
| site_category | str | 사이트 분류 |
| target_domain | str | 대상 도메인 |
| target_url | str | 대상 URL |
| operation_type | str | 작업 유형 (read/navigate 등) |
| action_name | str | 액션 이름 |
| production_mode | bool | 운영 모드 여부 |
| failure_reason | str | 실패 이유 (fallback 판단용) |
| approval_required | bool | 승인 필요 여부 |
| approval_id | str | 승인 ID |
| tenant_id | str | 테넌트 ID |
| user_id | str | 사용자 ID |
| site_id | str | 사이트 ID |
| workflow_run_id | str | 워크플로우 실행 ID |
| workflow_id | str | 워크플로우 ID |
| dry_run | bool | dry_run 플래그 (항상 True) |

### 출력 필드 (result)

| 필드 | 타입 | 설명 |
|---|---|---|
| ok | bool | 정상 완료 여부 |
| dry_run | bool | 항상 True |
| dispatch_decision | str | dispatch 결정값 (아래 enum 참조) |
| chain_decision | str | preflight chain 결정값 |
| engine_capability | str | engine capability 분류값 |
| routing_decision | str | 라우팅 결정값 |
| selected_engine | str | 선택된 엔진 |
| next_step | str | 다음 단계 |
| next_step_instruction | dict | 다음 단계 실행 지침 |
| safe_to_dispatch | bool | dispatch 가능 여부 |
| safe_to_execute | bool | 항상 False |
| should_write_audit | bool | 감사 로그 작성 여부 |
| block_reason | str | 차단 이유 |
| user_message_ko | str | 사용자용 한글 메시지 |
| admin_message_ko | str | 관리자용 한글 메시지 |
| result | dict | chain 전체 결과 요약 |

## 3. Dispatch Decision Enum

| 값 | 설명 |
|---|---|
| DRYRUN_SERVER_PLAYWRIGHT_READONLY_READY | 서버 Playwright read-only 준비 완료 |
| DRYRUN_LOCAL_AGENT_PLAYWRIGHT_READY | 로컬 Agent Playwright read-only 준비 완료 |
| DRYRUN_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED | 사용자 직접 브라우저 접근 필요 |
| DRYRUN_API_CONNECTOR_REQUIRED | 공식 API/OAuth 경로 필요 |
| DRYRUN_APPROVAL_REQUIRED | 승인 대기 필요 |
| DRYRUN_DOMAIN_VERIFICATION_REQUIRED | 도메인 실사 필요 |
| DRYRUN_BLOCKED | 차단 |
| DRYRUN_MANUAL_REVIEW_REQUIRED | 수동 실사 필요 |

## 4. next_step → dispatch_decision 매핑

| next_step | dispatch_decision |
|---|---|
| SERVER_PLAYWRIGHT_READONLY_PREFLIGHT | DRYRUN_SERVER_PLAYWRIGHT_READONLY_READY |
| LOCAL_AGENT_PLAYWRIGHT_READONLY | DRYRUN_LOCAL_AGENT_PLAYWRIGHT_READY |
| LOCAL_SYSTEM_BROWSER_USER_PRESENT | DRYRUN_LOCAL_SYSTEM_BROWSER_USER_PRESENT_REQUIRED |
| API_CONNECTOR | DRYRUN_API_CONNECTOR_REQUIRED |
| APPROVAL_REQUIRED | DRYRUN_APPROVAL_REQUIRED |
| DOMAIN_VERIFICATION_REQUIRED | DRYRUN_DOMAIN_VERIFICATION_REQUIRED |
| BLOCKED | DRYRUN_BLOCKED |
| MANUAL_REVIEW_REQUIRED | DRYRUN_MANUAL_REVIEW_REQUIRED |

## 5. 보안 원칙

- safe_to_execute: 항상 False
- dry_run: 항상 True
- click/type/fill/submit 코드 없음
- cookie/session/token 추출 없음
- 인증서 비밀번호/OTP 입력 코드 없음
- dispatcher/task_executor 실제 연결 없음
- should_write_audit: BLOCK/APPROVAL_REQUIRED 케이스에서 true
