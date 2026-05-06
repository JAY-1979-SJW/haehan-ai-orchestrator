# BROWSER_ACTION_REGISTRY_PREFLIGHT_1 보고서

**작성일**: 2026-05-06  
**기준 HEAD**: 560af75  
**단계**: read-only 감사 (연결 작업 아님)

---

## 1. 작업 목적

브라우저 action registry 연결 전 현재 구조를 read-only로 감사한다.  
action registry 수정, task_executor 수정, submit 연결, production submit은 이번 단계에서 금지.

---

## 2. action registry 위치

| 파일 | 역할 |
|---|---|
| `ai_orchestrator/local_agent_risk_policy.py` | `ACTION_RISK` dict — action별 risk_level 정의 (실질적 action registry) |
| `ai_orchestrator/local_agent_registry.py` | agent 등록/조회, `ACTION_RISK` import 후 risk_level 조회 |
| `ai_orchestrator/web_task_registry.py` | web task 등록 (task_key / action_type / risk_level / requires_approval) |
| `ai_orchestrator/browser_tool/policy.py` | browser action별 `BrowserTaskPolicy` (_ACTION_POLICIES dict) |
| `ai_orchestrator/browser_tool/schemas.py` | `BrowserActionName` Literal 타입 — 허용 action 목록 |

### ACTION_RISK 등록된 browser action 목록

```python
"browser.inspect":                 "low"
"browser.plan_click":              "low"
"browser.plan_type":               "low"
"browser.plan_submit":             "low"
"browser.plan_open_url":           "low"
"browser.execute_click":           "medium"
"browser.execute_type":            "medium"
"browser.open_url_controlled":     "medium"
"browser.open_click_close_controlled": "medium"
"browser.open_type_close_controlled":  "medium"
```

### BrowserActionName Literal (schemas.py)

```
"inspect", "plan_click", "plan_type", "plan_submit",
"execute_click", "execute_type", "open_type_close_controlled"
```

---

## 3. task_executor dispatch 위치

| 파일 | 역할 |
|---|---|
| `ai_orchestrator/executor.py` | `_dispatch_allowed_action` — whitelist 기반 read-only 실행 디스패처 |
| `ai_orchestrator/local_agent_router.py` | WS dispatch (`to_dispatch`) — task 상태 전송 |

### executor.py ALLOWED_ACTIONS (whitelist)

```python
ALLOWED_ACTIONS = [
    "get_server_status",
    "fetch_web_page",
]
```

**browser action은 executor whitelist에 미등록 상태.**  
`_dispatch_allowed_action`에 browser 분기 없음.

### local_agent_router browser 연결 상태

`local_agent_router.py`에서 `browser_tool` import 없음.  
browser action 처리 경로 미연결 상태.

---

## 4. open_type_close_controlled 현재 상태

| 위치 | 상태 |
|---|---|
| `local_agent_risk_policy.py` ACTION_RISK | `"medium"` 등록됨 |
| `browser_tool/schemas.py` BrowserActionName | Literal에 포함됨 |
| `browser_tool/policy.py` _ACTION_POLICIES | `requires_approval=True`, `risk_level="medium"` |
| `browser_tool/backends/mock_backend.py` | `_handle_open_type_close_controlled` 구현됨 |
| `executor.py` ALLOWED_ACTIONS | 미등록 |
| `local_agent_router.py` | browser_tool import 없음 — 미연결 |

---

## 5. submit 관련 6개 모듈 미연결 상태

| 모듈 | 위치 | 외부 연결 |
|---|---|---|
| `controlled_submit.py` | browser_tool/ | 미연결 (pure decision) |
| `submit_execution_gate.py` | browser_tool/ | 미연결 (pure validator) |
| `submit_policy.py` | browser_tool/ | 미연결 |
| `submit_preview.py` | browser_tool/ | 미연결 |
| `submit_audit_log.py` | browser_tool/ | 미연결 |
| `submit_approval_state.py` | browser_tool/ | 미연결 |

`local_agent_router.py`, `executor.py`, `app.py` 어디에서도 browser_tool import 없음.  
6개 모듈 모두 독립 상태 유지 확인.

---

## 6. production submit 연결 흔적

- `controlled_submit.py`: `"no actual network submit, no DB write, no browser execution"` 명시
- `submit_execution_gate.py`: `production_submit_enabled=False` 기본값, `production_submit_allowed=False`
- `executor.py`: browser 분기 없음, submit 분기 없음
- `local_agent_router.py`: browser_tool import 없음
- `web_task_registry.py`: `oauth_submit`, `app_register` 등 web task 있으나 browser controlled submit 아님

**production submit 연결 흔적 없음.**

---

## 7. GATE 강제 연결 후보

Risk Tier Policy(`BROWSER_ACTION_RISK_TIER_POLICY_1`)와 현재 registry 구조 대조:

| Risk Tier | GATE | registry 후보 이름 |
|---|---|---|
| LOW_READ | 불필요 | `browser.inspect` 계열 — 현재 등록됨 |
| LOW_NAVIGATE | 불필요 | `browser.plan_click`, `browser.plan_open_url` — 현재 등록됨 |
| MEDIUM_TYPE | 조건부 | `browser.plan_type`, `browser.execute_type` — 현재 등록됨 |
| MEDIUM_DOWNLOAD | 조건부 | 미등록 (download 계열 신규 필요) |
| HIGH_STATE_CHANGE | GATE 필수 | `browser.plan_submit` — 현재 low로 등록, 상향 필요 |
| CRITICAL_SUBMIT | GATE 필수 | `browser.open_type_close_controlled` — 현재 medium 등록, GATE 연결 미완 |

**다음 단계에서 수정할 후보 (현재 단계에서 수정 금지):**
- `browser.open_type_close_controlled`: executor dispatcher에 browser_tool 경로 연결
- `browser.plan_submit`: risk_level 재검토 (현재 low, HIGH_STATE_CHANGE에 해당)
- production submit action 이름 등록 **금지** — controlled internal only 유지

---

## 8. 금지 연결 검사 결과

| 항목 | 결과 |
|---|---|
| production submit 연결 | NONE |
| browser.submit.production | NONE |
| browser.submit.real | NONE |
| action_registry 등록 흔적 (submit controlled) | NONE |
| task_executor handler 연결 흔적 | NONE |
| fetch/API/DB/docker 연결 | NONE |
| 실제 업무 사이트 도메인 | NONE |
| secret/token/password 원문 | NONE |

---

## 9. 테스트 결과

| 스위트 | 결과 |
|---|---|
| risk tier policy (20개) | PASS |
| execution gate validator | PASS |
| gate controlled integration smoke | PASS |
| policy validator | PASS |
| **합계** | **118 passed** |

---

## 10. py_compile 결과

| 모듈 | 결과 |
|---|---|
| controlled_submit.py | PASS |
| submit_execution_gate.py | PASS |
| submit_policy.py | PASS |
| submit_preview.py | PASS |
| submit_audit_log.py | PASS |
| submit_approval_state.py | PASS |

---

## 11. 다음 단계 제안

**BROWSER_ACTION_REGISTRY_RISK_MAPPING_1**

- `local_agent_risk_policy.py` ACTION_RISK에서 browser action risk_level 재정비
  - `browser.plan_submit`: low → HIGH_STATE_CHANGE 상향 검토
  - `browser.open_type_close_controlled`: medium → CRITICAL_SUBMIT 분류 명시
- `executor.py` dispatcher에 browser_tool 경로 연결 설계 (연결 작업은 다음 단계)
- LOW_READ / LOW_NAVIGATE action은 GATE 없이 dispatcher 연결 허용 검토
