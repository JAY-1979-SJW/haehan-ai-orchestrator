# Universal AI Site Agent — Real Use Flow 설계 문서

작성일: 2026-05-08

## 개요

Universal AI Site Agent를 실제 사용 흐름과 연결하는 3개 모듈을 추가한다.

- **Natural Language Task API** — 자연어 지시 → agent 실행 단일 진입점
- **Universal Agent Session** — 연속 지시 세션 관리 (권한 재사용)
- **Real Site Smoke Runner** — 7개 시나리오 mock + 선택적 live 검증

## 모듈 구조

```
ai_orchestrator/local_agent/
  natural_language_task_api.py    ← 진입점 (execute_natural_language_task)
  universal_agent_session.py      ← 세션 관리 (create/run/grant/close)
  real_site_smoke_runner.py       ← smoke 시나리오 정의 및 실행
```

## Natural Language Task API

### 핵심 함수

```python
execute_natural_language_task(
    instruction, url=None, page_data=None,
    permission_map=None, runner_fn=None, page_fetch_fn=None,
    task_id=None, dry_run=False, save_learned=True
) -> dict
```

### 보안 정책

- 7개 safe field 항상 False 강제: `cookie_exported`, `session_exported`, `password_collected`, `otp_collected`, `certificate_password_collected`, `storage_state_exported`, `server_browser_used`
- 빈 지시문 → STATUS_FAILED 즉시 반환
- url/page_data 모두 없음 → STATUS_FAILED 즉시 반환

### 결과 추가 필드

| 필드 | 설명 |
|------|------|
| intent | 파싱된 사용자 의도 |
| intent_auto_allowed | AUTO_ALLOWED 여부 |
| raw_instruction | 원본 지시문 |

## Universal Agent Session

### 세션 생명주기

```
create_session → run_task_in_session (반복) → close_session
                      ↑
              grant_session_permission (선택)
```

### 권한 재사용

- 세션의 `granted_permissions` 목록에서 ACTIVE 권한 자동 수집
- `execute_natural_language_task` 호출 시 `permission_map`으로 전달

### Thread Safety

- `threading.Lock` 사용
- `_SESSIONS` dict 접근 항상 lock 내에서 수행

## Real Site Smoke Runner

### 7개 시나리오

| ID | 설명 | expected_status |
|----|------|-----------------|
| s01 | 공개 목록 읽기 | COMPLETED / WARN_PERMISSION |
| s02 | 텍스트/표 추출 | COMPLETED / WARN_PERMISSION |
| s03 | 다운로드 manifest | COMPLETED / WARN_PERMISSION |
| s04 | 블로그 초안 (AUTO_ALLOWED) | COMPLETED / WARN_PERMISSION |
| s05 | 폼 작성 준비 | COMPLETED / WARN_PERMISSION |
| s06 | 발행 권한 필요 | WARN_PERMISSION / WARN_AUTH / COMPLETED |
| s07 | 결제 USER_DIRECT | WARN_AUTH / WARN_PERMISSION / COMPLETED |

### 차단 패턴

```python
_BLOCKED_PATTERNS = (
    "go.kr", "gov.kr", "hometax", "g2b", "bank", "card",
    "naver.com/login", "kakao.com/login",
)
```

## 테스트 파일

| 파일 | 테스트 수 | 범위 |
|------|-----------|------|
| test_natural_language_task_api_20260508.py | 17 | NL API |
| test_universal_agent_session_20260508.py | 14 | 세션 CRUD + 권한 |
| test_universal_ai_real_site_smoke_contract_20260508.py | 14 | 시나리오 계약 |

**전체: 45 PASS**
