# haehan-ai-orchestrator

승인형 AI 오케스트레이터 — 사람이 최종 승인하는 안전한 AI 작업 실행 시스템

---

## 단계별 구조

### 1단계: 모델 + 정책 정의
- `models.py` — TaskRequest, RiskAssessment, ExecutionPlan
- `policies/default_policy.yaml` — 위험도별 정책, 허용/차단 경로·명령

### 2단계: 위험도 평가 + 승인 토큰
- `risk_assessor.py` — action_type 기반 위험도 산출
- `approval_manager.py` — 승인 토큰 발급/검증/만료 처리
- `policy_engine.py` — YAML 정책 로드 및 경로·명령 검사

### 3단계: 화이트리스트 실행기 + 어댑터 + 텔레그램 승인
> 이번 단계: "안전한 실제 실행의 최소 단위"만 개방

---

## 3단계 목표

저위험(low) 읽기 작업 일부를 실제 실행 가능하게 열고,
중위험(medium)은 preview만 허용하며,
high/critical은 계속 실행 금지.

---

## 실제 실행 가능 범위

| risk_level | action_type          | 결과         |
|------------|----------------------|--------------|
| low        | read_file            | EXECUTED     |
| low        | list_dir             | EXECUTED     |
| low        | inspect_logs         | EXECUTED     |
| low        | status_check         | EXECUTED     |
| low        | summarize_text       | BLOCKED (AI 처리, executor 대상 아님) |
| medium     | edit_config 등       | PREVIEW_ONLY |
| high       | restart_service 등   | BLOCKED      |
| critical   | delete_file 등       | BLOCKED      |

---

## preview_only 정책

- medium 작업은 승인 토큰이 유효해도 실제 파일 저장 금지
- `file_adapter.preview_patch()` 로 diff만 반환
- 감사 로그에 `preview_only: true` 기록

---

## command/file adapter 범위

### file_adapter
- 허용: `read_file`, `list_dir`, `file_exists`, `preview_patch`
- 금지: 실제 `write_file`, `delete_file`, `rename`, `chmod`
- 바이너리 파일 읽기 거부
- 파일 크기 1MB 초과 시 BLOCKED
- blocked_paths 우선 차단, allowed_paths 외 접근 차단

### command_adapter
허용 명령 화이트리스트:
```
pwd, ls, ls -la, whoami, hostname, date
docker compose logs --tail 50
docker compose ps
```
- `shell=True` 절대 금지
- 화이트리스트 매칭 후 안전한 argv 리스트로 변환
- timeout 30초 적용
- high/critical action_type은 어댑터 호출 자체 차단
- `|`, `;`, `&&`, `||`, `` ` ``, `$(` 포함 시 차단

---

## 텔레그램 승인 요청 방식

환경변수:
```
TELEGRAM_BOT_TOKEN=<bot token>
TELEGRAM_CHAT_ID=<chat id>
```

- 환경변수 없으면 자동 mock 모드 (실패 없이 동작)
- medium/high/critical 작업 발생 시 승인 요청 메시지 자동 발송
- 메시지에 포함: task_id, action_type, target, risk_level, requires_approval, token_id

### 현재 승인 흐름 (3단계)
```
1. 작업 요청 → risk 평가
2. requires_approval=True → 토큰 발급
3. 텔레그램으로 승인 요청 메시지 발송
4. 관리자가 token_id 확인 후 approve_token() 호출
5. execution plan 재평가 → medium이면 PREVIEW_ONLY
```

---

## 로그 정책 (4단계)

### 로그 종류 4가지

| 종류 | 파일 | 목적 |
|------|------|------|
| 운영 로그 | `logs/orchestrator.log` | 흐름 추적 — 요청접수/판정/실행 단계 |
| 에러 로그 | `logs/orchestrator.error.log` | 실패 원인 추적 — ERROR 이상만 별도 보관 |
| 감사 로그 | `logs/audit.jsonl` | 승인·차단·판정 이력 — event_type 기준 JSONL |
| 실행 이력 | `storage/execution_history.jsonl` | 어댑터가 실제로 무엇을 했는지 기록 |

### Rotation 정책

| 파일 | 최대 크기 | 보관 개수 |
|------|----------|---------|
| orchestrator.log | 5MB | 5개 |
| orchestrator.error.log | 2MB | 3개 |
| audit.jsonl | 10MB | 10개 |

### 운영 로그 포맷

```
YYYY-MM-DD HH:MM:SS [LEVEL] logger_name event=EVENT_TYPE task=TASK_ID action=ACTION_TYPE actor=ACTOR | message
```

예:
```
2026-04-18 23:39:37 [INFO    ] orchestrator.app event=RISK_ASSESSED task=task-A-001 action=read_file actor=system | risk assessed: level=low
2026-04-18 23:39:37 [WARNING ] orchestrator.executor event=EXECUTION_BLOCKED task=task-D-001 action=restart_service actor=scenario_runner | execution blocked: risk level 'high' is always blocked
```

### 감사 로그 event_type 표준

```
TASK_RECEIVED       요청 최초 접수
RISK_ASSESSED       위험도 판정 완료
PLAN_CREATED        실행 계획 수립
APPROVAL_ISSUED     승인 토큰 발급
APPROVAL_GRANTED    승인 완료
APPROVAL_REJECTED   승인 거절
EXECUTION_ALLOWED   실행 허용 결정
EXECUTION_BLOCKED   실행 차단
EXECUTION_PREVIEW   preview_only 반환
EXECUTION_COMPLETED 실행 완료
EXECUTION_FAILED    실행 실패
```

### 민감정보 마스킹 정책

마스킹 대상 키: `api_key`, `token`, `bot_token`, `password`, `secret`, `authorization`, `cookie`, `session`

마스킹 방식: 원문 전체 노출 금지 — 앞 2자 + `***` + 뒤 2자 (4자 이하는 `***`)

- dict/list/nested 구조 재귀 적용
- 감사 로그 write 직전 `mask_sensitive()` 통과
- approval token은 앞 6자 + `***` 형태로만 로그에 기록

대용량 본문: 500자 초과 시 잘라내고 `+N chars truncated` 표시

### 운영 로그 vs 감사 로그 차이

| 항목 | 운영 로그 | 감사 로그 |
|------|---------|---------|
| 형식 | 텍스트 라인 | JSONL 구조화 |
| 목적 | 흐름 추적, 디버깅 | 승인/차단/판정 이력 증거 |
| 보관 | rotation 5개 | rotation 10개 |
| 필터 | 모든 INFO+ 이벤트 | event_type 강제 분류 |

### 로그 검색 시 핵심 필드

- `event_type` — 어떤 단계인지
- `task_id` — 특정 요청 전체 흐름 추적
- `action_type` — 어떤 작업인지
- `actor` — 누가 요청/처리했는지
- `risk_level` — 위험도
- `execution_status` — 최종 결과 (EXECUTED / PREVIEW_ONLY / BLOCKED)

### 로그 삭제 금지 원칙

- 로그 파일 수동 삭제 금지
- rotation 외 삭제 기능 구현 금지
- 감사 로그는 append-only — 수정/삭제 불가
- 로그 파일을 git에 커밋하지 않음 (`.gitignore` 처리 권장)

### 향후 가능한 확장

- 중앙 로그 수집 (ELK / Loki + Grafana)
- 감사 로그 기반 대시보드
- ERROR 발생 시 텔레그램 경보 알림
- 실패 패턴 분석 (EXECUTION_FAILED 빈도, 차단 패턴 통계)

---

## 실행 이력 로그 (execution_history.jsonl)

`storage/execution_history.jsonl` — append-only

필드:
```
timestamp, task_id, adapter, action_type, target,
execution_status, exit_code, preview_only, actor, note
```

---

## 시나리오 (app.py)

| 시나리오 | action_type      | 결과         |
|---------|------------------|--------------|
| A       | low read_file    | EXECUTED     |
| B       | low list_dir     | EXECUTED     |
| C       | medium edit_config | PREVIEW_ONLY |
| D       | high restart_service | BLOCKED  |
| E       | critical delete_file | BLOCKED  |

---

---

## 5단계: 로그 분석 + 운영 대시보드 + 내부 승인 UI

### 목표

기존 로그와 승인 구조를 활용해 최소 운영 콘솔을 제공합니다.
실행 범위를 넓히지 않습니다 — 조회/승인/분석만 담당합니다.

### 구성 요소

| 파일 | 역할 |
|------|------|
| `log_analyzer.py` | audit/execution_history 로그 집계 및 AI 운영 요약 |
| `dashboard.py` | Flask 운영 대시보드 + 승인/거절 라우트 |
| `ui/templates/dashboard.html` | 전체 요약·승인대기·에러·작업 목록 |
| `ui/templates/task_detail.html` | 단일 task 상세 + 감사 타임라인 + 승인 폼 |
| `ui/static/dashboard.css` | 최소 스타일 (카드, 표, 상태 배지) |
| `storage/dashboard_cache.json` | 마지막 요약 캐시 |
| `storage/approval_decisions.jsonl` | 대시보드 승인/거절 이력 (append-only) |

### 대시보드 실행

```bash
# 필요 패키지 추가 설치
pip install flask

# 1. 시나리오 먼저 실행해서 로그 생성 후 대시보드 시작
python app.py --dashboard --seed

# 2. 기존 로그가 있으면 바로 대시보드만 시작
python app.py --dashboard

# 3. 포트 변경
python app.py --dashboard --port 8080
```

브라우저에서 `http://127.0.0.1:5050/dashboard` 접속

### 승인 UI 기능 범위

| 역할 | 승인 가능 risk | 실제 실행 |
|------|--------------|---------|
| viewer   | 불가 | 불가 |
| operator | low / medium | low만 실행, medium은 PREVIEW_ONLY |
| admin    | low / medium / high | low만 실행, high는 승인해도 여전히 BLOCKED |
| 누구든 | critical | 불가 (항상 차단) |

> 승인 후에도 high/critical 실제 실행은 whitelist_executor에서 차단됩니다.
> 대시보드에서 직접 shell 입력 기능은 제공하지 않습니다.

### AI 운영 요약 카드

- `log_analyzer.generate_ai_ops_summary()` 호출
- `OPENAI_API_KEY` 환경변수가 있으면 GPT-4o-mini로 실제 분석
- 없으면 집계 수치 기반 deterministic mock 분석문 반환

### 승인/거절 API

```
POST /dashboard/approve
POST /dashboard/reject
Content-Type: application/json

{
  "token_id": "<approval token UUID>",
  "task_id": "<task ID>",
  "user_id": "<user ID>",  // viewer-1 / operator-1 / admin-1
  "reason": "사유 (선택)"
}
```

모든 승인/거절은:
- `storage/approval_decisions.jsonl` 에 append
- `logs/audit.jsonl` 에 APPROVAL_GRANTED / APPROVAL_REJECTED 이벤트 기록

### 현재 보안 한계

- **인증 없음**: 현재 로컬/내부 테스트 전용. `dashboard.py`의 `_USERS` dict는 하드코딩된 테스트 계정.
- **운영 배포 전**: 로그인/세션(Flask-Login, OAuth 등) 반드시 추가 필요.
- **동일 프로세스 의존**: approval_manager의 in-memory 토큰 상태가 대시보드와 동일 프로세스에서 공유됨. 별도 서버 분리 시 영속 저장소 필요.

### 다음 단계 예정

- 인증/세션 (Flask-Login, JWT)
- 서버/PC 분리 agent 구조
- 중앙 로그 수집 (Loki + Grafana)
- 다중 승인 (N of M)
- 텔레그램/웹훅 버튼 승인
- 규칙 추천 엔진

---

## 아직 미구현 항목

- 텔레그램 웹훅 승인 (버튼 클릭 → 자동 approve)
- 실제 medium write (현재 preview만)
- high 작업 이중 승인 플로우
- 서버/PC 분리 에이전트 구조
- 세션/사용자 인증 (요청자 검증)

---

## 테스트 실행

```bash
python -m pytest tests/ -v
```

필요 패키지:
```bash
pip install pytest pyyaml
```

---

## 파일 구조

```
ai_orchestrator/
├── models.py                       # 데이터 모델
├── policy_engine.py                # 정책 로드·검사
├── risk_assessor.py                # 위험도 평가
├── approval_manager.py             # 토큰 발급/검증
├── whitelist_executor.py           # 최종 실행 게이트
├── telegram_notifier.py            # 승인 요청 발송
├── logger.py                       # 공통 로거 (4단계)
├── logging_utils.py                # 마스킹·truncate 유틸 (4단계)
├── audit_logger.py                 # 감사 로그 전용 (4단계)
├── log_analyzer.py                 # 로그 집계 + AI 요약 (5단계)
├── dashboard.py                    # Flask 운영 대시보드 (5단계)
├── app.py                          # 시나리오 실행기 + --dashboard 옵션
├── policies/
│   └── default_policy.yaml
├── adapters/
│   ├── file_adapter.py
│   └── command_adapter.py
├── ui/                             # 대시보드 UI (5단계)
│   ├── templates/
│   │   ├── dashboard.html
│   │   └── task_detail.html
│   └── static/
│       └── dashboard.css
├── logs/                           # 로그 파일 (rotation)
│   ├── orchestrator.log
│   ├── orchestrator.error.log
│   └── audit.jsonl
├── storage/
│   ├── execution_history.jsonl     # 실행 이력 (append-only)
│   ├── approval_decisions.jsonl    # 대시보드 승인/거절 이력 (5단계)
│   └── dashboard_cache.json        # 마지막 요약 캐시 (5단계)
└── tests/
    ├── test_whitelist_executor.py
    ├── test_file_adapter.py
    ├── test_command_adapter.py
    ├── test_telegram_notifier.py
    ├── test_logger.py              # (4단계)
    ├── test_log_masking.py         # (4단계)
    ├── test_log_analyzer.py        # (5단계)
    └── test_dashboard_routes.py    # (5단계)
```
