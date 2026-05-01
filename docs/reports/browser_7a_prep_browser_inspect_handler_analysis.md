# BROWSER-7A-PREP: browser.inspect Handler 구현 흐름 분석 보고서

**작성일**: 2026-05-01  
**현재 커밋**: 365b1d9 (fix(ws): reconcile auto execute action sets)  
**대상**: browser.inspect action handler 경로 분석 및 구현 전략

---

## 1. Repo 상태 확인

| 항목 | 상태 |
|------|------|
| 저장소 경로 | `/home/ubuntu/apps/haehan-ai-orchestrator` |
| 브랜치 | `master` |
| HEAD 커밋 | `365b1d9` ✓ |
| origin/master | `365b1d9` ✓ |
| 기준선 | BROWSER-6D 완료, BROWSER-6C 운영 성공 |

---

## 2. 현재 task 처리 흐름 분석

### 2.1 클라이언트 흐름 (local_agent/)

**경로**: `local_agent/websocket_client.py`

```
WebSocket task (JSON)
    ↓
process_task() [101줄]
    ├─ task.action 읽음 [112줄]
    ├─ _AUTO_EXECUTE_VIA_AGENT 확인 [140줄]
    │   └─ browser.inspect 포함됨 ✓ (local_agent/websocket_client.py 43줄)
    ├─ execute_action(action, enriched_params) 호출 [181줄]
    └─ _build_result_message() 로 응답 [186줄]
```

**현재 상태**:
- `_AUTO_EXECUTE_VIA_AGENT` (32-49줄): browser.inspect 포함 ✓
- `_APPROVAL_REQUIRED_ACTIONS` (55-58줄): capture_screenshot, open_url_execute만 포함
  - → browser.inspect는 approval 불필요 (low risk 액션)

### 2.2 action dispatcher (local_agent/actions.py)

**execute_action() 함수** [1095-1115줄]:
```
execute_action(action, params)
    ├─ FORBIDDEN_ACTIONS 확인 [1097줄]
    ├─ _ACTIONS.get(action) [1103줄]
    │   └─ 딕셔너리에 없으면:
    │       return ActionResult(success=False, error_code="UNKNOWN_ACTION") [1105-1109줄]
    └─ fn(params) 호출
```

**_ACTIONS 딕셔너리** [1069-1087줄]:
```python
_ACTIONS = {
    "ping": action_ping,
    "system_info": action_system_info,
    # ... 외 action들 ...
    # browser.inspect는 여기에 없음! ← ❌ 구현 누락
}
```

### 2.3 서버 쪽 정의 (ai_orchestrator/)

**local_agent_actions.py** [21-34줄]:
```python
AUTO_EXECUTE_VIA_AGENT: frozenset[str] = frozenset({
    # ...
    "browser.inspect",
    # ... 외 browser.* actions ...
})
```

**local_agent_registry.py** [35-51줄]:
```python
ACTION_RISK: dict[str, str] = {
    "browser.inspect":    "low",  # ← 정의됨 ✓
    "browser.plan_click": "low",
    # ... 외 browser.* actions ...
}
```

---

## 3. UNKNOWN_ACTION 발생 원인

**근본 원인**: `local_agent/actions.py`의 `_ACTIONS` 딕셔너리에 `browser.inspect` handler가 등록되지 않음.

**실행 경로**:
1. WebSocket task 도착: `action="browser.inspect"`
2. `process_task()`: AUTO_EXECUTE_VIA_AGENT 확인 → **통과**
3. `execute_action("browser.inspect", params)` 호출
4. `_ACTIONS.get("browser.inspect")` → `None` 반환
5. **ActionResult(success=False, error_code="UNKNOWN_ACTION")** 반환

---

## 4. 기존 browser 모듈 인벤토리

### 4.1 이미 구현된 모듈들

| 모듈 | 용도 | 특징 |
|------|------|------|
| `browser_actions.py` | click, type_text, select_option, scroll 구현 | read/write 위험도 분류 포함 |
| `browser_reader.py` | 페이지 read-only 조사 | Playwright 기반 |
| `browser_controller.py` | 브라우저 조작 추상화 | 실제 Playwright 호출 |
| `browser_login_probe.py` | 수동 로그인 관찰 | read-only 관찰 전용 |
| `browser_task_handler.py` | 각 task 실행 핸들러 | BrowserTaskPayload ↔ 실행 |
| `browser_approval_verifier.py` | approval 검증 | token 검증 로직 |
| `browser_action_contract.py` | 액션 정의 | browser.inspect 포함 (schema 정의) |
| `browser_websocket_schema.py` | WS payload schema | browser.inspect 포함 |
| `browser_websocket_handshake.py` | WS 초기화 | browser.inspect 열거형 정의 |

### 4.2 browser.inspect 관련 기존 레퍼런스

**browser_action_contract.py**:
- `browser.inspect` 열거형 정의됨

**browser_websocket_schema.py**:
- payload schema에 `browser.inspect` 포함

**test_browser_websocket_contract.py** [23-26줄]:
```python
def test_browser_inspect_action_is_registered(self):
    """browser.inspect should not be UNKNOWN_ACTION"""
    assert "browser.inspect" in _reg.ACTION_RISK
    assert _reg.ACTION_RISK["browser.inspect"] == "low"
```

---

## 5. browser.inspect Handler 후보 위치

### 5.1 Option A: `local_agent/actions.py`에 직접 추가

**장점**:
- 간단한 구현
- 기존 pattern 일관성

**단점**:
- 파일이 이미 1230줄 (매우 큼)
- browser 전용 logic이 분산됨

**코드 위치**:
- `execute_action()` 함수 [1095줄]
- `_ACTIONS` 딕셔너리 [1069줄]
- handler 함수 추가: ~1090줄 근처

### 5.2 Option B: `local_agent/browser_actions.py` 내 handler 추가 (권장)

**장점**:
- 기존 browser 관련 코드와 함께
- 모듈화 원칙 준수 (코드 모듈화 정책 2026-05-01 발효)
- 순환 import 위험 없음 (browser_actions는 이미 actions.py에서 import됨)

**단점**:
- browser_actions.py는 현재 `click`, `type_text` 등의 guarded 액션용
- browser.inspect는 동작 특성이 다름 (read-only, guarded 아님)

**코드 위치**:
- 새 함수: `action_browser_inspect(params: dict) -> ActionResult`
- `browser_actions.py`의 약 150줄 이후에 추가
- `actions.py`의 `_ACTIONS` 딕셔너리에 등록

### 5.3 Option C: 신규 모듈 `local_agent/browser_inspect_handler.py` 분리 (미래)

**장점**:
- 완전 분리, 향후 확장성
- BROWSER-8 이상에서 browser.inspect 관련 기능 확장 시 용이

**단점**:
- 현재는 overengineering
- browser.inspect가 단순 read-only 액션일 때는 불필요

---

## 6. Result Schema 추정

### 6.1 반환 ActionResult 구조

```python
ActionResult(
    success: bool,
    summary: str,           # "browser inspect ok" / "browser inspect 실패"
    data: dict,            # 안전 데이터만 포함
    error: str,            # 에러 메시지 (최대 500자)
    error_code: str,       # "UNKNOWN_ACTION" / "BROWSER_INSPECT_FAILED" 등
)
```

### 6.2 data 필드 화이트리스트 (local_agent_registry.py 81-96줄)

현재 `_RESULT_DATA_ALLOWED_KEYS`에 포함된 browser 관련 키:
- `status`, `selector`, `executed`, `element_found`, `risk_level`
- `final_approval_required`, `result`, `target_url_domain`, `text_length`
- `text_preview`, `error_message`, `screenshot_ref`

**browser.inspect 반환 후보 키**:
- `page_title`: 페이지 제목
- `page_url`: 현재 URL
- `element_found`: 조사 대상 element 발견 여부
- `element_text`: element 텍스트 (redacted)
- `element_attributes`: 주요 속성 (href, src, alt 등 safe 속성만)
- `page_structure_summary`: 페이지 구조 요약
- `screenshot_ref`: (optional) 스크린샷 참조

**금지 키**:
- HTML 원문
- 입력값 (value 속성)
- 숨김 필드값
- 쿠키, 토큰, 비밀값

---

## 7. Approval 게이트 분석

### 7.1 browser.inspect 승인 필요 여부

**현재 구성**:
- `ACTION_RISK["browser.inspect"] = "low"` (local_agent_registry.py 45줄)
- `_APPROVAL_REQUIRED_ACTIONS = {"capture_screenshot", "open_url_execute"}` 
  (websocket_client.py 55-58줄)
  - → browser.inspect 포함 안 됨 ✓

**결론**: browser.inspect는 **승인 불필요** (low risk)
- risk_level=low 이므로 websocket_client의 process_task에서:
  ```python
  if risk_level == "high":  # [127줄]
      if not (approved and action in _APPROVAL_REQUIRED_ACTIONS):
          # → browser.inspect는 여기 걸리지 않음
  ```

### 7.2 차단 지점

**차단 경로** (websocket_client.py 127-138줄):
- risk_level=high이고 approved=False → NOT_IMPLEMENTED_STAGE2 반환
- browser.inspect는 low risk이므로 차단 안 됨

**실제 동작**:
- task 도착
- risk_level=low (또는 기본값)
- AUTO_EXECUTE_VIA_AGENT 확인 → 통과
- execute_action() 호출 → **UNKNOWN_ACTION 반환** ← 지금 여기

---

## 8. 테스트 전략

### 8.1 Mock 기반 테스트

**기존 테스트 참고**:
- `tests/test_browser_websocket_contract.py` [23-26줄]
  - ACTION_RISK 등록 확인
- `tests/test_local_agent_ws.py`
  - WebSocket task 처리 흐름

**신규 테스트 작성 방향**:
```python
def test_browser_inspect_action_handler_registered():
    """browser.inspect handler가 _ACTIONS에 등록됨"""
    from local_agent.actions import _ACTIONS
    assert "browser.inspect" in _ACTIONS
    
def test_browser_inspect_basic_execution():
    """browser.inspect 기본 실행 (mock browser)"""
    # params = {"url": "...", "selector": "..."}
    # result = action_browser_inspect(params)
    # assert result.success == True
    # assert result.error_code == ""

def test_browser_inspect_missing_url():
    """browser.inspect URL 누락 시 실패"""
    # params = {}
    # result = action_browser_inspect(params)
    # assert result.success == False
    # assert result.error_code == "MISSING_URL"
```

### 8.2 실제 브라우저 없이 검증 가능한 항목

- ✓ Parameter validation (URL, selector 형식)
- ✓ ActionResult 구조 (success, error_code, data)
- ✓ Data whitelist 준수 (민감값 미포함)
- ✓ Error message 길이 제한 (500자)
- ✓ result schema matching (local_agent_registry의 whitelist)

### 8.3 실제 브라우저 필요한 항목

- ✗ 실제 페이지 로드
- ✗ selector 유효성 검증 (DOM 탐색)
- ✗ element 찾기 및 속성 추출
- ✗ 스크린샷 캡처

**전략**: dry_run 옵션 추가
```python
if params.get("dry_run", True):
    # 실제 브라우저 없이 구조만 검증
    return ActionResult(success=True, summary="browser.inspect dry_run ok", data={...})
```

---

## 9. 다음 구현 단계 제안

### Phase 1: Handler 구현 (BROWSER-7A)

**파일 수정**:
1. `local_agent/browser_actions.py` OR `local_agent/actions.py`
   - `action_browser_inspect(params: dict) -> ActionResult` 추가
   - 최소 구현: URL + selector 받아 ActionResult 반환

2. `local_agent/actions.py` - `_ACTIONS` 딕셔너리
   - `"browser.inspect": action_browser_inspect` 등록

**예상 구현**:
```python
def action_browser_inspect(params: dict) -> ActionResult:
    """페이지 element 읽기 (read-only) — dry_run 전용.
    
    - 실제 브라우저 실행 없이 URL/selector 유효성만 확인
    - 또는 Playwright 있을 시 실제 탐색 후 element 정보 반환
    - 민감값(password, token, cookie) 절대 반환 금지
    """
    url = str(params.get("url", "")).strip()
    if not url:
        return ActionResult(False, "browser.inspect 실패", {}, 
                          "url 누락", error_code="MISSING_URL")
    
    selector = str(params.get("selector", "")).strip()
    dry_run = bool(params.get("dry_run", True))
    
    if dry_run:
        # 실제 브라우저 없이 검증
        return ActionResult(True, "browser.inspect dry_run ok", 
                          {"url": url, "selector": selector, "dry_run": True})
    
    # Phase 2 이후: 실제 Playwright 호출
    ...
```

### Phase 2: 실제 브라우저 통합 (BROWSER-7B)

- Playwright 호출
- selector 유효성 검증
- element 정보 추출
- 스크린샷 참조

### Phase 3: Approval 게이트 추가 (BROWSER-7C)

- medium/high risk 단계에서 승인 요구
- websocket_client의 _APPROVAL_REQUIRED_ACTIONS 확장

---

## 10. 코드 모듈화 원칙 준수

**정책** (project_modularization_policy.md, 2026-05-01 발효):
- 신규 feature 추가 시 "기능 추가 → 누적" 대신 "기능 전후 분리"
- 기존 API/schema 보존
- 대규모 리팩토링 금지

**이번 BROWSER-7A 준수 방안**:

1. **Option B (권장)**: browser_actions.py에 추가
   - 이유: browser.* 전용 액션들이 이미 모여있음
   - 순환 import 위험 없음 (actions.py → browser_actions import 이미 있음)
   - 기존 API 보존 (execute_action signature 변화 없음)

2. **기존 동작 보존**:
   - execute_action의 dispatcher 로직 불변
   - ActionResult 구조 불변
   - WebSocket 프로토콜 불변

3. **schema 변경 불필요**:
   - AUTO_EXECUTE_VIA_AGENT에 이미 포함됨
   - ACTION_RISK에 이미 정의됨
   - result whitelist (_RESULT_DATA_ALLOWED_KEYS)에 이미 포함됨

---

## 11. 금지 작업 준수 확인

| 금지 작업 | 상태 |
|----------|------|
| WebSocket 실제 연결 | ✓ 하지 않음 |
| 브라우저 실행 | ✓ 하지 않음 |
| task 생성 | ✓ 하지 않음 |
| result 전송 | ✓ 하지 않음 |
| approval 변경 | ✓ 하지 않음 |
| DB write | ✓ 하지 않음 |
| 컨테이너 재시작 | ✓ 하지 않음 |
| docker/nginx 변경 | ✓ 하지 않음 |
| secret 출력 | ✓ 하지 않음 |
| 다른 앱 접근 | ✓ 하지 않음 |
| 코드 수정 | ✓ 하지 않음 (분석만 수행) |

---

## 12. 핵심 요약

| 항목 | 결과 |
|------|------|
| **현재 문제** | execute_action()의 _ACTIONS에 browser.inspect handler 미등록 |
| **오류 코드** | UNKNOWN_ACTION (local_agent/actions.py 1108줄) |
| **이유** | 서버/클라이언트 schema는 정의됨 (AUTO_EXECUTE_VIA_AGENT) 하지만 handler 미구현 |
| **해결 경로** | local_agent/actions.py의 _ACTIONS 딕셔너리에 등록 |
| **권장 구현 위치** | local_agent/browser_actions.py 또는 local_agent/actions.py |
| **승인 필요** | 아니오 (low risk) |
| **dry_run 지원** | 권장 (실제 브라우저 없이 테스트 가능) |
| **schema 변경** | 불필요 (이미 모든 정의 완료) |

---

## 부록: 파일 참고 라인

### 서버 쪽 정의
- `ai_orchestrator/local_agent_actions.py:28` - AUTO_EXECUTE_VIA_AGENT 정의
- `ai_orchestrator/local_agent_registry.py:45` - ACTION_RISK 정의
- `ai_orchestrator/local_agent_registry.py:81-96` - result whitelist

### 클라이언트 쪽 흐름
- `local_agent/websocket_client.py:43` - _AUTO_EXECUTE_VIA_AGENT fallback
- `local_agent/websocket_client.py:101` - process_task()
- `local_agent/websocket_client.py:140` - AUTO_EXECUTE_VIA_AGENT 확인
- `local_agent/websocket_client.py:181` - execute_action() 호출

### 미구현 dispatch
- `local_agent/actions.py:1069` - _ACTIONS 딕셔너리 (browser.inspect 없음)
- `local_agent/actions.py:1095` - execute_action() 함수
- `local_agent/actions.py:1103` - _ACTIONS.get(action)
- `local_agent/actions.py:1105` - UNKNOWN_ACTION 반환

### 기존 browser 모듈
- `local_agent/browser_actions.py` - guarded 액션들 (click, type_text 등)
- `local_agent/browser_task_handler.py` - task 실행 추상화
- `local_agent/browser_action_contract.py` - schema 정의

### 테스트
- `tests/test_browser_websocket_contract.py:23-26` - browser.inspect registration test
