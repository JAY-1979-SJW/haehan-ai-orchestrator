# 다음 구현 작업 추천: ORCHESTRATOR-LOCAL-AGENT-RISK-POLICY-MODULE-1

## 📝 작업 개요

**작업명**: ORCHESTRATOR-LOCAL-AGENT-RISK-POLICY-MODULE-1

**목표**: local_agent_registry.py에서 ACTION_RISK 정책을 local_agent_risk_policy.py로 분리

**위험도**: **LOW** ✅

**예상 소요시간**: 30분 ~ 1시간

---

## 📊 분리 대상

### 현재 위치: ai_orchestrator/local_agent_registry.py

```python
# 라인 33-59: 분리 대상
ACTION_RISK: dict[str, str] = {
    "ping": "low",
    "system_info": "low",
    "list_allowed_apps": "low",
    "open_url": "low",
    "open_url_execute": "high",
    "list_files_readonly": "medium",
    "capture_screenshot": "high",
    "ws_noop": "low",
    "browser.inspect": "low",
    "browser.plan_click": "low",
    "browser.plan_type": "low",
    "browser.plan_submit": "low",
    "browser.execute_click": "medium",
    "browser.execute_type": "medium",
}

_SERVER_AUTO_COMPLETE: frozenset[str] = frozenset({
    "ping", "system_info", "list_allowed_apps",
})

ALLOWED_APPS: list[str] = ["browser", "excel", "hwp", "cad"]
```

### 신규 파일: ai_orchestrator/local_agent_risk_policy.py

```python
"""로컬 에이전트 액션 risk 정책 정의.

로컬 에이전트(Windows PC)에서 지원 가능한 액션들의 위험도(risk_level)를 
중앙에서 관리한다. 미등록 액션은 UNKNOWN_ACTION으로 거절된다.

risk_level 분류:
  - low: 즉시 실행 가능, 승인 불필요 (ping, system_info, list_allowed_apps, open_url)
  - medium: 큐 대기, 기본 검증 (list_files_readonly, browser.execute_*)
  - high: 승인 대기, approval token 필수 (capture_screenshot, open_url_execute)
"""

# 액션 → risk_level 매핑
ACTION_RISK: dict[str, str] = {
    "ping":               "low",
    "system_info":        "low",
    "list_allowed_apps":  "low",
    "open_url":           "low",
    "open_url_execute":   "high",
    "list_files_readonly": "medium",
    "capture_screenshot": "high",
    "ws_noop":            "low",
    # browser automation actions (BROWSER-4E)
    "browser.inspect":    "low",
    "browser.plan_click": "low",
    "browser.plan_type":  "low",
    "browser.plan_submit": "low",
    "browser.execute_click": "medium",
    "browser.execute_type": "medium",
}

# 서버가 즉시 응답 가능한 액션 (PC 의존 없음)
_SERVER_AUTO_COMPLETE: frozenset[str] = frozenset({
    "ping", "system_info", "list_allowed_apps",
})

# 허용된 PC 측 앱 (실제 실행은 browser/open_url 만 가능)
ALLOWED_APPS: list[str] = ["browser", "excel", "hwp", "cad"]
```

---

## 🔄 변경 사항

### local_agent_registry.py

```python
# 변경 전 (라인 28)
from .local_agent_actions import AUTO_EXECUTE_VIA_AGENT

# 추가 (라인 28 다음)
from .local_agent_risk_policy import (
    ACTION_RISK, _SERVER_AUTO_COMPLETE, ALLOWED_APPS
)

# 제거: 라인 33-59 (ACTION_RISK, _SERVER_AUTO_COMPLETE, ALLOWED_APPS 정의)
```

### enqueue_task 함수 영향 없음

```python
# 라인 550-595: enqueue_task 함수
def enqueue_task(...) -> LocalAgentTask:
    # 변경 전
    if action not in ACTION_RISK:
        raise UnknownActionError(...)
    risk_level = ACTION_RISK[action]
    
    # 변경 후 (동일, import만 변경)
    if action not in ACTION_RISK:
        raise UnknownActionError(...)
    risk_level = ACTION_RISK[action]
```

---

## ✅ 검증 체크리스트

### 코드 수정 (코드 로직 변경 없음)

- [ ] local_agent_risk_policy.py 신규 생성
- [ ] ACTION_RISK 복사 (라인 35-51)
- [ ] _SERVER_AUTO_COMPLETE 복사 (라인 54-56)
- [ ] ALLOWED_APPS 복사 (라인 59)
- [ ] import 추가: from .local_agent_risk_policy import (...)
- [ ] 원본 정의 제거 (라인 33-59)

### 테스트 검증

- [ ] test_action_registry_approval_policy.py 실행 ✅ PASS
- [ ] test_action_registry_unit.py 실행 ✅ PASS
- [ ] test_local_agent_running_and_safe_actions.py 실행 ✅ PASS
- [ ] 기존 registry unit test 실행 ✅ PASS

### 보안 검증

- [ ] ACTION_RISK 정의 값 일치 확인
- [ ] high/medium/low 값 오타 없음 확인
- [ ] _SERVER_AUTO_COMPLETE 값 일치 확인
- [ ] ALLOWED_APPS 값 일치 확인

### API/Response 검증

- [ ] response 형식 변경 없음 ✅
- [ ] endpoint path 변경 없음 ✅
- [ ] risk_level 값 변경 없음 ✅

---

## 🎯 성공 기준

✅ **완료 조건**:
1. local_agent_risk_policy.py 신규 파일 생성
2. ACTION_RISK, _SERVER_AUTO_COMPLETE, ALLOWED_APPS 이전
3. import 경로 변경 (registry → risk_policy)
4. 기존 test suite 전부 통과
5. git diff로 논리적 변경 없음 확인

❌ **실패 조건**:
- test 실패
- response shape 변경
- endpoint path 변경
- API 호환성 깨짐

---

## 📌 주의사항

**절대 금지**:
- ACTION_RISK 값 수정 (정책 변경 아님)
- risk_level 재분류 (현재 분류 유지)
- _SERVER_AUTO_COMPLETE 추가/삭제 (정책 유지)
- ALLOWED_APPS 수정 (정책 유지)

**필수 확인**:
- 모든 test 통과 확인
- 기존 router 호출 확인 (enqueue_task → ACTION_RISK 참조)
- 기존 registry 호출 확인 (없음)

---

## 📚 참고 파일

- ai_orchestrator/local_agent_registry.py (라인 35-59)
- agent/action_registry.py (requires_approval 정책 비교)
- agent/tests/test_action_registry_approval_policy.py (approval 정책 테스트)

---

