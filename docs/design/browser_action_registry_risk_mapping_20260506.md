# Browser Action Registry Risk Mapping

**문서 ID**: BROWSER_ACTION_REGISTRY_RISK_MAPPING_1  
**작성일**: 2026-05-06  
**기준 HEAD**: aae7bfe  
**상태**: DESIGN (연결 작업 아님)

---

## 1. 목적

- Risk Tier 정책(`BROWSER_ACTION_RISK_TIER_POLICY_1`)을 실제 registry 연결 전에 action별로 매핑한다.
- 모든 브라우저 행동을 GATE로 묶지 않는다.
- 고위험 상태 변경 action만 GATE 필수로 둔다.
- 이 문서는 다음 단계(연결 작업)의 설계 기준이 된다.

---

## 2. 현재 상태 요약

| 항목 | 현재 상태 |
|---|---|
| `browser.open_type_close_controlled` | ACTION_RISK `medium` 등록됨 |
| executor dispatcher | browser action 미연결 |
| submit 6개 모듈 | 완전 독립 상태 |
| production submit | 미연결 (`production_submit_enabled=False`) |
| local_agent_router browser_tool import | 없음 |

---

## 3. Action Mapping Matrix

| action_name | current_risk | risk_tier | read_only | requires_approval | requires_gate | requires_preview | requires_audit | production_allowed | next_dispatcher |
|---|---|---|---|---|---|---|---|---|---|
| browser.inspect | low | LOW_READ | true | false | false | false | recommended | false | executor.ALLOWED_ACTIONS 추가 |
| browser.plan_click | low | LOW_NAVIGATE | true | false | false | false | false | false | executor.ALLOWED_ACTIONS 추가 |
| browser.plan_type | low | MEDIUM_TYPE | true | false | false | false | recommended | false | executor.ALLOWED_ACTIONS 추가 |
| browser.plan_open_url | low | LOW_NAVIGATE | true | false | false | false | false | false | executor.ALLOWED_ACTIONS 추가 |
| browser.plan_submit | low | HIGH_STATE_CHANGE | false | true | true | recommended | true | false | risk_level 재검토 필요 (현재 low) |
| browser.execute_click | medium | LOW_NAVIGATE | false | true | false | false | recommended | false | medium 경로 dispatcher |
| browser.execute_type | medium | MEDIUM_TYPE | false | true | false | false | recommended | false | medium 경로 dispatcher (민감필드 차단 필요) |
| browser.open_url_controlled | medium | LOW_NAVIGATE | false | true | false | false | recommended | false | medium 경로 dispatcher |
| browser.open_click_close_controlled | medium | LOW_NAVIGATE | false | true | false | false | true | false | medium 경로 dispatcher |
| browser.open_type_close_controlled | medium | CRITICAL_SUBMIT | false | true | true | true | true | false | GATE+preview+audit 경로 (다음 단계 설계) |

---

## 4. GATE 적용 분류

### GATE 불필요 (LOW_READ / LOW_NAVIGATE)

- `browser.inspect`
- `browser.plan_click`
- `browser.plan_type`
- `browser.plan_open_url`
- `browser.execute_click`
- `browser.open_url_controlled`

### 조건부 GATE (MEDIUM_TYPE / MEDIUM_DOWNLOAD)

- `browser.execute_type` — 민감 필드 차단 필요, 업무 폼 입력 시 preview 권장
- `browser.open_click_close_controlled` — audit 필요

### GATE 필수 (HIGH_STATE_CHANGE)

- `browser.plan_submit` — risk_level 재검토 필요 (현재 low → high 상향 설계 필요)

### GATE 필수 + BLOCKED_CRITICAL (CRITICAL_SUBMIT)

- `browser.open_type_close_controlled` — GATE + preview_hash + user_confirmed + audit 필수
- production submit action 등록 **금지** — controlled internal only 유지

---

## 5. Risk Level 재정비 필요 항목

| action | 현재 ACTION_RISK | 권장 변경 | 이유 |
|---|---|---|---|
| `browser.plan_submit` | `low` | `high` | HIGH_STATE_CHANGE tier 해당 |
| `browser.open_type_close_controlled` | `medium` | `high` 또는 `critical` | CRITICAL_SUBMIT tier 해당, GATE 필수 |

---

## 6. Executor Dispatcher 연결 설계 (다음 단계 기준)

### LOW_READ / LOW_NAVIGATE 연결 우선순위

```
executor.ALLOWED_ACTIONS 추가 후보:
  "browser.inspect"
  "browser.plan_click"
  "browser.plan_type"
  "browser.plan_open_url"
```

dispatcher 분기: `_dispatch_allowed_action` 내 `browser_tool.router.dispatch` 호출

### CRITICAL_SUBMIT 연결 (별도 단계)

```
browser.open_type_close_controlled:
  → submit_execution_gate.evaluate()
  → GATE_ALLOW_CONTROLLED 판정 시
  → controlled_submit.build_controlled_submit_result()
  → submit_audit_log.append_submit_audit_event()
```

production_submit_enabled=False 유지 필수.

---

## 7. Production Submit 금지 명시

- `browser.submit.production` 등록 금지
- `browser.submit.real` 등록 금지
- `production_submit_enabled=True` 코드 추가 금지
- executor dispatcher에 실제 네트워크 submit 경로 추가 금지
