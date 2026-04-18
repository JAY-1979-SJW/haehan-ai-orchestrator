# 승인형 AI 비서 오케스트레이터

## 왜 이 구조가 필요한가

AI가 직접 파일을 삭제하거나 서버를 재시작하거나 외부에 메시지를 보내면 사람이 통제권을 잃는다.
이 프로젝트는 **AI는 계획만, 실행은 사람의 승인 후 프로그램이** 담당하는 구조를 강제한다.

---

## AI와 프로그램의 역할 분리

| 역할 | 담당 |
|------|------|
| 작업 의도 해석 / 계획 생성 / 요약 | AI (OpenAI GPT) |
| 위험도 분류 / 승인 여부 판정 | 프로그램 (risk_classifier, policy) |
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
  [low]  → DRY_RUN_ONLY (자동 허용, 현재 단계는 드라이런만)
  [medium/high] → PENDING_APPROVAL (사람 승인 대기)
  [critical]    → BLOCKED (기본 차단)
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

## 현재 단계 (1단계 — 드라이런)

- 실제 AI 연결 없음
- 실제 파일 수정/삭제/명령 실행 없음
- 모든 executor 결과는 `DRY_RUN_ONLY` / `PENDING_APPROVAL` / `BLOCKED`

---

## 실행 방법

```bash
pip install -r requirements.txt

# 드라이런 실행
python -m ai_orchestrator.app

# 테스트
python ai_orchestrator/tests/test_risk_classifier.py
python ai_orchestrator/tests/test_policy_gate.py
```

---

## 다음 단계에서 추가할 항목

- [ ] 승인 토큰 (HMAC 서명 기반 일회성 토큰)
- [ ] 감사 로그 (모든 요청/승인/거부 기록)
- [ ] 실제 OpenAI 연동 (계획 생성 어댑터)
- [ ] 화이트리스트 명령 실행기
- [ ] PC / 서버 분리 실행기
- [ ] 웹 승인 UI (Slack 또는 간단한 웹훅)
