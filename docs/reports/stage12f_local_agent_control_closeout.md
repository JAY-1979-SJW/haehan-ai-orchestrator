# Stage 12F local-agent approval/control closeout

Stage 12A~12E에서 진행한 local-agent approval/control 안정화 흐름의 마감 보고서.  
이 단계는 문서 작성만 수행하며 코드/테스트/서버/docker/local-agent/브라우저 실행은 없다.

---

## 1. 마감 범위

| 단계 | 커밋 | 내용 | 판정 |
|---|---|---|---|
| 12A | `8042ce0` | local-agent control surface audit (docs) | WARN |
| 12B | `5565022` | admin-web에 approve/reject UI 추가 | PASS |
| 12C | `5565022` server reflected | approval UI 서버 반영 및 무실행 smoke | PASS |
| 12D | `dbc33a3` | no-exec smoke 스크립트 추가 | WARN exit 0 |
| 12E | `a31732d` | approval 상태 전이 fixture 테스트 (28 passed) | PASS |

origin/master 최신 = `a31732d`.

---

## 2. 최종 안정화 결과

| 항목 | 결과 | 판정 |
|---|---|---|
| approval UI | admin-web `LocalAgentsClient.tsx` 에 approve/reject 추가, '승인 확인' / '거절 확인' 마커 존재 | PASS |
| token_id 처리 | 개별 task 조회(`getLocalAgentTask`) 후 token_id 사용 | PASS |
| 권한 제한 | viewer / unknown_role → `forbidden` (fixture 검증) | PASS |
| token 재사용 차단 | approved/rejected 상태 토큰 재시도 → `already_used` | PASS |
| invalid token 차단 | 존재하지 않는 uuid → `not_found` | PASS |
| task mismatch 차단 | token_id ↔ task_id 불일치 → `task_mismatch` | PASS |
| audit 이벤트 | JSONL에 `token_approved` / `token_rejected` 기록 확인 | PASS |
| no-exec smoke | Total 39 / PASS 37 / WARN 2 / FAIL 0 | WARN |
| 실제 action 실행 | 미수행 (subprocess/os.system 패치로 0건 검증) | PASS |
| 실제 브라우저 실행 | 미수행 | PASS |

---

## 3. 12D WARN 유지 사유

| WARN | 사유 | 운영 영향 |
|---|---|---|
| `audit` marker in `approval.py` | `approval.py` 는 `_append_event` 자체 JSONL 기록을 수행하고, 광역 audit log(`log_event`)는 `local_agent_router.py` 레이어에서 호출하는 역할 분리 구조. "audit" 문자열 부재는 검사 marker 한정 이슈 | 차단 없음 |
| `preview` marker in `local_agent_router.py` | 현재 정책은 `preview` 용어 대신 `dry_run` 중심으로 표준화됨 | 차단 없음 |

스크립트 검사 기준은 약화하지 않고 WARN 유지(B안). FAIL 0건.

---

## 4. 다음 실제 실행 전 필수 조건

실제 local-agent 또는 브라우저 실행 전 아래 조건을 고정한다.

- `dry_run` 기본값(True) 유지
- low risk 읽기/관찰 작업부터 시작 (ping, system_info, list_allowed_apps 등)
- high/critical 실제 실행 금지
- 로그인/결제/송금/삭제/권한 변경 작업 금지
- 쿠키/session/token 수집 금지
- 승인형(high) 작업은 반드시 `waiting_approval` → `approve_token` 경유
- audit log 기록 필수 (`LOCAL_AGENT_TASK_*`, `APPROVAL_*` 이벤트)
- 실행 전 `python scripts/check_local_agent_noexec_smoke.py` 통과 필수
- 실행 후 결과/로그에서 secret/token/cookie 노출 여부 확인 필수

---

## 5. 다음 단계 제안

**Stage 12G — controlled browser open/observe dry-run 설계**

목표:
- 실제 사이트 로그인/입력/POST 없이
- 허용된 URL만 열기 (whitelist 기반)
- title / url / status 코드 관찰
- 결과를 audit log + 결과 파일로 회수
- audit 기록 확인
- local-agent 또는 브라우저 실제 실행 여부는 대표님 승인 후 진행

12G도 설계/문서 단계로 시작하며, 실제 실행 전 별도 승인 게이트를 둔다.

---

## 6. 금지 작업 준수 확인

- 코드 수정: 없음
- 테스트 수정: 없음
- 서버 접속: 없음
- docker 실행: 없음
- local-agent 실행: 없음
- 브라우저 실행: 없음
- 실제 POST: 없음
- 다른 앱 접근: 없음
- secret 출력: 없음

---

## 7. 최종 판정

**PASS**

Stage 12 전 단계(12A~12E)에서 approval/control 안정화 목표를 달성하였고, no-exec smoke의 WARN 2건은 운영 차단이 아닌 선택 marker 부재로 분류되어 유지한다. 다음 단계(12G)는 controlled dry-run 설계로 진입한다.
