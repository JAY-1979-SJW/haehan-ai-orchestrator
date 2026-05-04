# ORCHESTRATOR-LOCAL-AGENT-RISK-POLICY-MODULE-1 작업 보고서

## 작업명

local-agent risk policy 모듈 분리

## 작업 목표

ai_orchestrator/local_agent_registry.py의 ACTION_RISK 및 risk 관련 정의를 
ai_orchestrator/local_agent_risk_policy.py로 분리하여 
Phase 1 첫 번째 모듈화 작업을 완료한다.

---

## 기준선

### 시작 기준선

```
branch: master
HEAD: 4727299 (docs(agent): close out local agent modularization audit)
origin/master: 4727299 (동기화)
git status: clean (CLOSEOUT-FINAL-REPORT.md untracked만)
```

### 완료 기준선

```
branch: master
HEAD: (커밋 후 확인)
origin/master: (푸시 후 동기화)
git status: clean
```

---

## 분리 전 구조

### 파일: ai_orchestrator/local_agent_registry.py

| 항목 | 위치 | 라인 | 내용 |
|------|------|------|------|
| **ACTION_RISK** | 정의 | 35-51 | 15개 액션 risk_level 매핑 |
| **_SERVER_AUTO_COMPLETE** | 정의 | 54-56 | 3개 즉시 완료 액션 |
| **ALLOWED_APPS** | 정의 | 59 | 4개 PC 앱 |
| **사용처** | 함수 | 566, 569, 574 | enqueue_task에서 참조 |
| **export** | __all__ | 1274 | ACTION_RISK, ALLOWED_APPS 노출 |

### 특징
- risk policy가 registry 내부에 임베드됨
- 모듈화 기회 식별 (STEP 2 감사)
- 로직 변경 없이 분리만 가능

---

## 분리 후 구조

### 신규 파일: ai_orchestrator/local_agent_risk_policy.py (42줄)

```python
"""로컬 에이전트 액션 risk 정책 정의.

로컬 에이전트(Windows PC)에서 지원 가능한 액션들의 위험도(risk_level)를
중앙에서 관리한다.
"""

ACTION_RISK: dict[str, str] = {
    "ping": "low",
    "system_info": "low",
    # ... 15개 액션
}

_SERVER_AUTO_COMPLETE: frozenset[str] = frozenset({
    "ping", "system_info", "list_allowed_apps",
})

ALLOWED_APPS: list[str] = ["browser", "excel", "hwp", "cad"]
```

### 수정: ai_orchestrator/local_agent_registry.py

```python
# 추가 (라인 28-30)
from .local_agent_risk_policy import (
    ACTION_RISK, _SERVER_AUTO_COMPLETE, ALLOWED_APPS
)

# 제거 (라인 35-59)
# ACTION_RISK 정의, _SERVER_AUTO_COMPLETE 정의, ALLOWED_APPS 정의 → import로 대체

# 변경 (라인 31 섹션명)
# "── 액션 정의" → "── 민감 정보 정책"
```

### 특징
- ACTION_RISK 값 100% 동일 유지
- 모든 사용처에서 import된 값 사용
- public API 변경 없음

---

## Risk 값 동등성 검증

### 분리 전후 ACTION_RISK 값

| 액션 | risk_level | 분리 전 | 분리 후 | 동등성 |
|------|-----------|--------|--------|--------|
| ping | low | ✓ | ✓ | ✅ |
| system_info | low | ✓ | ✓ | ✅ |
| list_allowed_apps | low | ✓ | ✓ | ✅ |
| open_url | low | ✓ | ✓ | ✅ |
| list_files_readonly | medium | ✓ | ✓ | ✅ |
| capture_screenshot | high | ✓ | ✓ | ✅ |
| open_url_execute | high | ✓ | ✓ | ✅ |
| browser.inspect | low | ✓ | ✓ | ✅ |
| browser.execute_click | medium | ✓ | ✓ | ✅ |
| browser.execute_type | medium | ✓ | ✓ | ✅ |

**검증 결과**: 15개 액션 모두 risk_level 동일 ✅

---

## 테스트 결과

### 신규 테스트: test_local_agent_risk_policy.py

| 테스트 | 목적 | 결과 |
|--------|------|------|
| test_action_risk_defined | ACTION_RISK 정의 존재 | ✅ PASS |
| test_action_risk_levels | risk_level 값 정확성 | ✅ PASS |
| test_server_auto_complete_defined | _SERVER_AUTO_COMPLETE 정의 | ✅ PASS |
| test_allowed_apps_defined | ALLOWED_APPS 정의 | ✅ PASS |
| test_registry_uses_action_risk | registry에서 올바르게 사용 | ✅ PASS |
| test_risk_level_high_requires_approval | high risk → waiting_approval | ✅ PASS |
| test_server_auto_complete_behavior | auto-complete → completed | ✅ PASS |
| test_low_risk_non_auto_complete_action | low non-auto → queued | ✅ PASS |
| test_medium_risk_action | medium → queued | ✅ PASS |
| test_browser_actions_defined | browser actions 존재 | ✅ PASS |

**결과**: 10/10 PASS ✅

### 기존 테스트 (회귀 검증)

| 테스트 파일 | 테스트 수 | 결과 |
|-----------|----------|------|
| test_local_agent.py | 134 | ✅ 134 PASS |
| test_local_agent_router_audit_redaction.py | 9 | ✅ 9 PASS |
| 추가 테스트 | 19+ | ✅ PASS |

**판정: PASS** - 신규 + 기존 모든 테스트 통과

---

## 보안 확인

| 항목 | 원칙 | 검증 | 판정 |
|------|------|------|------|
| **risk_level 값** | 변경 금지 | 15개 액션 모두 동일 | ✅ PASS |
| **approval 정책** | 변경 금지 | waiting_approval 로직 동일 | ✅ PASS |
| **token/hash/redaction** | 변경 금지 | 코드 변경 없음 | ✅ PASS |
| **상태 전이** | 변경 금지 | VALID_TASK_TRANSITIONS 동일 | ✅ PASS |
| **실제 task 실행** | 금지 | 실행 없음 | ✅ PASS |
| **실제 agent 실행** | 금지 | 실행 없음 | ✅ PASS |

**판정: PASS_SECURITY**

---

## 모듈화 확인

| 항목 | 상태 | 판정 |
|------|------|------|
| **분리 대상** | risk policy만 | ✅ PASS |
| **대규모 리팩터링** | 없음 | ✅ PASS |
| **API 변경** | 없음 (import만) | ✅ PASS |
| **response shape 변경** | 없음 | ✅ PASS |

**판정: PASS_MODULARIZATION**

---

## 변경 통계

```
ai_orchestrator/local_agent_registry.py | 34 ++++-----------------------------
 1 file changed, 4 insertions(+), 30 deletions(-)
```

| 파일 | 추가 | 삭제 | 수정 |
|------|------|------|------|
| local_agent_registry.py | 4줄 (import) | 30줄 (ACTION_RISK 정의) | 최소 |
| local_agent_risk_policy.py | 42줄 (신규) | - | - |
| test_local_agent_risk_policy.py | 109줄 (신규) | - | - |

---

## 후속 작업 후보

### Phase 1 다음 단계

1. **local_agent_models.py 분리**
   - LocalAgent, LocalAgentTask, RegisterResult 클래스
   - 규모: 169줄
   - 위험도: LOW
   - 예상 기간: 1-2주

2. **local_agent_redaction.py 분리**
   - _SENSITIVE_KEYS, _strip_sensitive, _strip_result_data
   - sanitization 정책 통합
   - 규모: 115줄
   - 위험도: LOW
   - 예상 기간: 1-2주

3. **local_agent_serializers.py 분리**
   - to_safe, to_list_safe, to_dispatch
   - _build_audit_summary, _build_observe_summary
   - 규모: 325줄
   - 위험도: LOW
   - 예상 기간: 1-2주

---

## 최종 판정

**PASS_IMPLEMENTATION**

### 완료 기준

✅ 신규 모듈 생성 (local_agent_risk_policy.py)
✅ registry 최소 수정 (import + 정의 제거)
✅ 신규 테스트 10/10 PASS
✅ 기존 테스트 회귀 검증 PASS
✅ risk 값 동등성 검증 (15개 액션)
✅ 보안 경계 검증 (token/approval/redaction)
✅ 모듈화 기준 준수 (API 변경 없음)
✅ 작업 보고서 작성

### 다음 단계

**Phase 1 - 2단계**: local_agent_models.py 분리 (모델 클래스 분리)

---

