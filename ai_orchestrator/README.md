# 승인형 AI 비서 오케스트레이터

## 왜 이 구조가 필요한가

AI가 직접 파일을 삭제하거나 서버를 재시작하거나 외부에 메시지를 보내면 사람이 통제권을 잃는다.
이 프로젝트는 **AI는 계획만, 실행은 사람의 승인 후 프로그램이** 담당하는 구조를 강제한다.

---

## AI와 프로그램의 역할 분리

| 역할 | 담당 |
|------|------|
| 작업 의도 해석 / 계획 생성 / 요약 / 승인 사유 문안 | AI (OpenAI GPT) |
| 위험도 분류 / 승인 여부 판정 | 프로그램 (risk_classifier, policy) |
| 승인 토큰 발급/검증 | 프로그램 (approval) |
| 감사 로그 기록 | 프로그램 (audit_logger) |
| 실제 실행 (파일/명령/서비스) | 프로그램 (executor) — 승인 후에만 |
| 최종 승인 | 사람 |

AI는 절대 직접 시스템을 건드리지 않는다.

---

## 승인형 구조 흐름

```
사용자/시스템 → TaskRequest
      ↓
  risk_classifier (위험도 분류)
      ↓
  policy gate (허용/차단/승인 판정)
      ↓
  ExecutionPlan 생성
      ↓
  [low]      → AI summary 생성 → DRY_RUN_ONLY
  [medium]   → approval token 발급 → AI 승인 사유 생성 → 사람 승인 → APPROVED_DRY_RUN
  [high]     → approval token 발급 → 사람 승인 → APPROVED_DRY_RUN
  [critical] → BLOCKED (토큰 발급 안 함)
      ↓
  audit_logger (모든 단계 JSONL 기록)
```

---

## 위험도 단계

| 단계 | 설명 | 예시 |
|------|------|------|
| **LOW** | 읽기 전용. 자동 허용 | read_file, list_dir, inspect_logs |
| **MEDIUM** | 파일/설정 수정. 승인 필요 | write_file, edit_config |
| **HIGH** | 시스템 명령/배포/외부 전송. 승인 필수 | restart_service, deploy_app, push_git |
| **CRITICAL** | 삭제/파괴. 기본 차단 | delete_file, drop_table, rm_recursive |

---

## 2단계 목표 (현재 단계)

1. **OpenAI 연동** — 계획 요약/승인 사유 문안 생성
2. **승인 토큰** — medium/high 작업의 발급/검증/만료 흐름
3. **감사 로그** — 모든 이벤트를 JSONL로 append-only 기록

---

## OpenAI 연동 방식

- `openai_client.py`가 단일 진입점
- `OPENAI_API_KEY` 환경변수가 있으면 실제 API 호출
- 없으면 **mock 모드** 자동 전환 (결정론적 문자열 반환)
- 예외 발생 시에도 fallback mock 반환 (서비스 중단 없음)
- 모델: `gpt-4o-mini` (빠르고 저비용)
- AI 역할: 요약 / 승인 사유 / 계획 설명만. 실행 명령 생성 금지

```bash
# 실제 OpenAI 연결
export OPENAI_API_KEY=sk-...
python -m ai_orchestrator.app

# mock 모드 (키 없이)
python -m ai_orchestrator.app
```

---

## mock 모드 설명

- `OPENAI_API_KEY`가 없거나 빈 문자열이면 mock 모드 자동 활성화
- 반환값 앞에 `[MOCK]` 표시
- 테스트/개발 환경에서 API 키 없이도 전체 흐름 검증 가능

---

## 승인 토큰 수명주기

```
issue_token()  →  status: "issued"
     ↓
approve_token() →  status: "approved"
     ↓
validate_token() → True (만료 전, task_id 일치)
     ↓
(만료 시) status: "expired", validate → False
(취소 시) revoke_token() → status: "revoked"
```

- 기본 TTL: 30분
- 저장: `storage/approval_tokens.json` (인메모리 + 파일 동기화)
- critical 작업은 토큰 발급 자체 안 함

---

## 감사 로그 구조

파일: `storage/audit_logs.jsonl` (append-only, 삭제 기능 없음)

```json
{
  "timestamp": "2026-04-18T10:00:00+00:00",
  "event_type": "APPROVAL_GRANTED",
  "task_id": "S-B-001",
  "risk_level": "medium",
  "action_type": "edit_config",
  "target": "/var/www/haehan/config.yaml",
  "allowed": true,
  "requires_approval": true,
  "decision": "approved",
  "actor": "대표님",
  "note": "token_id=abc123..."
}
```

event_type 목록: TASK_RECEIVED, RISK_ASSESSED, PLAN_CREATED,
APPROVAL_ISSUED, APPROVAL_GRANTED, APPROVAL_REJECTED,
EXECUTION_BLOCKED, EXECUTION_PENDING, DRY_RUN_RETURNED

---

## 실행 방법

```bash
pip install -r requirements.txt

# 2단계 드라이런 (시나리오 A~D)
python -m ai_orchestrator.app

# 테스트 전체
python tests/server_core/test_risk_classifier.py
python tests/server_core/test_policy_gate.py
python tests/approval/test_approval.py
python tests/server_core/test_audit_logger.py
python ai_orchestrator/tests/test_openai_client.py
```

---

## 아직 실제 작업 실행은 안 함

현재 executor는 항상 아래만 반환:
- `DRY_RUN_ONLY` — low 자동 허용
- `PENDING_APPROVAL` — 승인 대기
- `APPROVED_DRY_RUN` — 승인 완료 후에도 실제 실행 없음
- `BLOCKED` — critical / 정책 차단

---

## 다음 단계 예정

- [ ] 화이트리스트 명령 실행기 (allowed_commands만 실행)
- [ ] 파일/명령 어댑터 (read_file 실제 구현)
- [ ] 서버/PC 분리 실행기 (source 기반 라우팅)
- [ ] 다중 승인 (2인 이상 승인 필요)
- [ ] 텔레그램 승인 연동 (승인 요청 메시지 발송)
