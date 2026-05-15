# Local Agent On-Demand Controller 정책 (2026-05-15)

## 핵심 원칙

### 1. 상시 데몬 금지
- Windows 서비스 등록 금지
- 시작프로그램 등록 금지
- 무한 while-loop 상시 데몬 금지
- 백그라운드 자동 재시작 금지

### 2. AI On-Demand Start/Stop
- AI가 승인된 작업 시작 시 `start_local_agent()` 호출
- 작업 완료 → `stop_local_agent(reason="completed")` 자동 호출
- 작업 실패 → `stop_local_agent(reason="failed")` 자동 호출
- 작업 취소 → `stop_local_agent(reason="cancelled")` 자동 호출
- 한 번에 하나의 작업만 실행 (중복 start 방지)

### 3. 사용자 승인 필요 조건
다음 조건 중 하나라도 해당하면 사용자 명시 승인 필수:
- `user_direct_required = True`인 action
- 비가역 작업 (제출/서명/결제/송금)
- 외부 공개 발행 (블로그/카페 게시)
- 결제/과금 발생 작업

### 4. Local-Only 실행 원칙
- 로컬 에이전트는 반드시 사용자 PC에서만 실행
- 서버 사이드 실행 금지
- AI 전용 브라우저 프로필은 로컬 PC에만 보관

### 5. Server-Side Browser 금지
- 서버에서 외부 로그인 브라우저 실행 금지
- 서버에서 auth/session이 필요한 브라우저 자동화 금지
- 서버에서는 공개 read-only 작업만 허용

### 6. Cookie/Session/Token/Password 금지
- 쿠키/세션/토큰/비밀번호 값 추출 금지
- `data/sessions/*.json` 읽기/파싱/재사용 금지
- 자격증명 전송/저장/로깅 금지

## 생명주기

```
[AI] → start_local_agent(task_id, domain, approved_scope)
          ↓ approval gate 검사
          ↓ lock 획득
          ↓ status 파일 기록
       ← {ok: True, task_id, started_at}

[AI] → get_local_agent_status()
       ← {running: bool, task_id, domain, elapsed_s, idle_timeout_s}

[작업 완료/실패/취소]
[AI] → stop_local_agent(reason)
          ↓ lock 해제
          ↓ status 파일 업데이트
          ↓ evidence/report 저장
       ← {ok: True, stopped_at, reason}
```

## Idle Timeout 정책
- 기본 idle_timeout: 1800초 (30분)
- timeout 초과 시 stale 상태로 전환
- `cleanup_stale_processes()` 호출 시 보고
- 실제 프로세스 kill은 사용자 확인 후 수행 (dry_run 기본)

## Stale Process Cleanup
- cleanup은 기본 `dry_run=True`
- dry_run: 목록만 보고, 실제 kill 없음
- 실제 kill: `dry_run=False` 명시 + 사용자 승인 필요
- stale 기준: lock 파일 존재 + 프로세스 없음, 또는 idle_timeout 초과

## Evidence/Report 저장
- 작업 결과는 `data/local_agent/evidence/` 저장
- 감사 로그는 `data/local_agent/audit/` 저장
- status 파일: `data/local_agent/status.json`
- lock 파일: `data/local_agent/agent.lock`

## 상태 파일 구조
```json
{
  "running": true,
  "task_id": "...",
  "domain": "...",
  "action": "...",
  "approved_scope": [...],
  "started_at": "ISO8601",
  "idle_timeout_s": 1800
}
```
※ password/token/cookie/session 값 절대 기록 금지

## 실패/취소 시 종료 규칙
1. 예외 발생 → stop_local_agent(reason="failed") 자동 호출
2. 승인 만료 → stop_local_agent(reason="approval_expired") 자동 호출
3. 범위 초과 시도 → stop_local_agent(reason="scope_exceeded") + 감사 기록
4. lock 파일 남으면 → cleanup_stale_processes(dry_run=True)로 보고
