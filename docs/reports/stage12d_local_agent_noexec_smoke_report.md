# Stage 12D local-agent no-exec smoke report

## 1. 목적
local-agent 실제 실행 없이 정책/API/UI 안전 상태를 정적 점검하는 smoke 스크립트 추가

## 2. 신규 파일

| 파일 | 역할 | 판정 |
|---|---|---|
| `scripts/check_local_agent_noexec_smoke.py` | Python 표준 라이브러리 전용 정적 smoke 스크립트 (7개 검사 영역, PASS/WARN/FAIL 출력, exit code 제어) | PASS |

## 3. smoke 검사 항목

| 항목 | 검사 방식 | 판정 |
|---|---|---|
| 필수 파일 존재 (8개) | `Path.exists()` 정적 확인 | PASS — 8/8 존재 |
| approval UI marker | `.tsx` / `.ts` 파일 문자열 검색 (`waiting_approval`, `approve`, `reject`, `token_id`, `승인 확인`, `거절 확인`, `approveLocalAgentTask`, `rejectLocalAgentTask`, `getLocalAgentTask`) | PASS — 9/9 확인 |
| policy/safety marker | `local_agent_router.py`, `default_policy.yaml`, `approval.py` 문자열 검색 | WARN — `audit` in approval.py 미확인, `preview` in router 미확인 (선택적 marker, 운영 차단 아님) |
| 위험 POST 미실행 — 스크립트 자체 | regex로 실제 `import requests/httpx/urllib` 및 `subprocess.*(` 호출 검사 (lookbehind로 문자열 리터럴 제외) | PASS — 7/7 금지 패턴 없음 |
| legacy URL 신규 노출 | `admin-web/src/**` 에서 `/api/v1/admin/local-agents` 직접 링크 검색 | PASS — 노출 없음 |
| secret/cookie/session 위험 문자열 | `document.cookie`, `sessionStorage`, `localStorage`, `"Authorization"`, `'Authorization'` 검색 | PASS — 5/5 위험 패턴 없음 |
| 기존 기능(capture/cancel) 유지 | `capture-screenshot`, `cancelTask` in `api.ts` | PASS — 2/2 존재 |

## 4. 실행 결과

| 명령 | 결과 |
|---|---|
| `python -m py_compile scripts/check_local_agent_noexec_smoke.py` | PASS |
| `python scripts/check_local_agent_noexec_smoke.py` | **WARN** (exit 0) — Total: 39, PASS: 37, WARN: 2, FAIL: 0 |

WARN 상세:
- `[WARN] safety marker MISSING: 'audit' in approval.py` — `approval.py` 내 `audit` 리터럴 없음. 실제 audit 기능은 `audit_logger.py`를 별도 모듈로 사용 중일 수 있음. 운영 차단 아님.
- `[WARN] safety marker MISSING: 'preview' in local_agent_router.py` — `preview` 문자열 미사용. dry_run이 동일 목적으로 사용 중. 운영 차단 아님.

## 5. 한계

- 실제 `waiting_approval` 작업 생성/승인/거절은 수행하지 않음
- 실제 `capture-screenshot` / `cancel` POST는 수행하지 않음
- 실제 브라우저/local-agent 실행은 수행하지 않음
- 이 smoke는 정적 안전 점검이며, E2E 테스트 대체가 아님
- Next.js 번들 내부 문자열 검사는 서버 빌드 결과물 기준 (Stage 12C에서 별도 확인 완료)
- 런타임 waiting_approval 작업이 없어 버튼 노출 상태를 런타임에서 직접 확인하지 못함

## 6. 다음 단계 제안

권장 다음 단계:
- **Stage 12E**: `waiting_approval` 테스트 fixture 기반 단위 검증 (실제 approve/reject 로직 단위 테스트)
- 또는 **Stage 12E**: local-agent controlled dry_run smoke 스크립트 설계 (실제 에이전트 없이 mock task 기반)

## 7. 금지 작업 준수 확인

- 서버 접속: 없음
- docker 실행: 없음
- local-agent 실행: 없음
- 브라우저 실행: 없음
- 실제 POST: 없음
- DB 접속: 없음
- 다른 앱 접근: 없음
- secret 출력: 없음
