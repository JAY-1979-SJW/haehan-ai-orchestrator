# 실시간 팝업 감지 — `popup_watcher` 설계서 v1.0

작성일: 2026-05-11
대상 구현자: 최하위 모델 (Claude Haiku 등) — 단계별 그대로 따라 작성하면 동작해야 함
참조 기존 코드: `scripts/browser/navigator/navigator.py` (현재 `handle_draft_restore_popup` 함수)

---

## 1. 목적

브라우저 페이지에 팝업/모달이 등장하면 **즉시(수 ms 이내) 감지**하고, 알려진 팝업이면 자동 처리, 모르는 팝업이면 외부에 알린다. 이를 위해 페이지에 `MutationObserver`를 주입해 DOM 변화를 실시간 감시한다.

---

## 2. 산출물

| 파일 | 신규/수정 | 역할 |
|------|---------|------|
| `scripts/browser/popup/popup_watcher.py` | **신규** | 본체 — 주입/조회/처리 |
| `scripts/cdp_client.py` | 수정 | CLI 명령 3개 추가 |
| `tests/test_popup_watcher.py` | **신규** | 단위 테스트 |

기존 `handle_draft_restore_popup` 함수는 **그대로 보존**한다 (코드 보존 규칙).

---

## 3. 자료 구조

### 3.1 JS 측 (브라우저 내부)

페이지 `window` 객체에 다음 상태를 만든다:

```js
window.__hh_popup_state = {
  events: [],           // [{ ts, marker, snippet, frame_url }, ...]
  installed: false,     // 옵저버 설치 여부
};
```

### 3.2 Python 측 반환 객체

```python
PopupEvent = TypedDict('PopupEvent', {
    'ts_ms': int,          # 이벤트 발생 시각 (epoch ms)
    'marker': str,         # 매칭된 마커 (예: '작성 중인 글')
    'snippet': str,        # body.innerText 발췌 (최대 200자)
    'frame_url': str,      # 감지된 프레임의 URL
})
```

---

## 4. 알려진 팝업 마커 카탈로그

`POPUP_MARKERS` 상수로 정의:

```python
POPUP_MARKERS = {
    # 마커 텍스트 → 처리 액션 (자동 클릭할 버튼 이름)
    "작성 중인 글":   {"action": "click_button", "target": "취소"},
    "이어서 작성":    {"action": "click_button", "target": "취소"},
    "임시저장":      {"action": None},  # 정보용 토스트, 액션 없음
}
```

새 팝업이 발견되면 이 딕셔너리에 한 줄씩 추가.

---

## 5. 함수 명세 (4개)

### 5.1 `install_watcher(page=None) -> dict`

페이지에 MutationObserver JS 코드를 주입한다.

**Pseudo-code:**

```python
def install_watcher(page=None) -> dict:
    if page is None:
        page = get_page()
    js = build_watcher_js(POPUP_MARKERS)   # 5.5 참조
    for frame in page.frames:
        try:
            frame.evaluate(js)
        except Exception:
            continue
    return {"installed": True, "frame_count": len(page.frames)}
```

**JS 동작 요건:**
- 이미 설치되어 있으면 (`window.__hh_popup_state.installed === true`) 재설치 안 함
- `body` 전체에 대해 `MutationObserver({childList:true, subtree:true})` 등록
- DOM 노드 추가될 때마다 `document.body.innerText`에서 마커 검색
- 마커 발견 시 `window.__hh_popup_state.events.push(...)`
- 마커별 중복 push 방지: 같은 마커는 최근 5초 내 1개만 push

### 5.2 `poll_events(page=None, since_ms=0) -> list[PopupEvent]`

`window.__hh_popup_state.events`에서 `ts_ms > since_ms`인 이벤트를 읽어온다. 반환 후 JS 측 events는 그대로 둔다(여러 소비자 지원).

```python
def poll_events(page=None, since_ms=0) -> list[dict]:
    if page is None:
        page = get_page()
    for frame in page.frames:
        try:
            events = frame.evaluate("(s) => (window.__hh_popup_state?.events||[]).filter(e => e.ts_ms > s)", since_ms)
            if events:
                return events
        except Exception:
            continue
    return []
```

### 5.3 `clear_events(page=None) -> None`

처리 완료 후 호출. `window.__hh_popup_state.events = []`로 초기화.

### 5.4 `auto_handle(page=None) -> dict`

`poll_events` → 각 이벤트에 대해 `POPUP_MARKERS[marker].action` 실행 → `clear_events`.

```python
def auto_handle(page=None) -> dict:
    handled = []
    skipped = []
    unknown = []
    events = poll_events(page=page)
    for ev in events:
        spec = POPUP_MARKERS.get(ev["marker"])
        if spec is None:
            unknown.append(ev)
            continue
        if spec["action"] is None:
            skipped.append(ev)
            continue
        if spec["action"] == "click_button":
            # 기존 click_button 함수 재사용
            from scripts.browser.navigator.navigator import click_button
            ok = click_button(spec["target"])
            handled.append({"event": ev, "clicked": ok})
    if events:
        clear_events(page=page)
    return {"handled": handled, "skipped": skipped, "unknown": unknown}
```

### 5.5 `build_watcher_js(markers: dict) -> str`

마커 카탈로그를 JS 코드 문자열로 변환. 다음 템플릿 사용:

```javascript
(() => {
  if (window.__hh_popup_state && window.__hh_popup_state.installed) return;
  const MARKERS = __MARKER_LIST__;  // [{key: '작성 중인 글', ...}, ...]
  window.__hh_popup_state = { events: [], installed: true, lastSeen: {} };
  const COOLDOWN_MS = 5000;
  const detect = () => {
    const text = (document.body && document.body.innerText) || '';
    const nowMs = Date.now();
    for (const m of MARKERS) {
      if (!text.includes(m.key)) continue;
      const last = window.__hh_popup_state.lastSeen[m.key] || 0;
      if (nowMs - last < COOLDOWN_MS) continue;
      window.__hh_popup_state.lastSeen[m.key] = nowMs;
      window.__hh_popup_state.events.push({
        ts_ms: nowMs,
        marker: m.key,
        snippet: text.slice(0, 200),
        frame_url: location.href,
      });
    }
  };
  const obs = new MutationObserver(detect);
  obs.observe(document.body, { childList: true, subtree: true });
  // 첫 감지: 페이지에 이미 있는 마커 1회 스캔
  setTimeout(detect, 100);
})();
```

`__MARKER_LIST__`는 Python에서 `json.dumps([{"key": k} for k in markers])`로 치환.

---

## 6. CLI 명령 3개 (`cdp_client.py`)

```
python scripts/entry/cdp_cli.py popup-install
python scripts/entry/cdp_cli.py popup-poll              # 이벤트 출력 (consume 안 함)
python scripts/entry/cdp_cli.py popup-auto              # poll + 자동 처리 + clear
```

각 case 분기는 기존 패턴(`case "is-ready":` 등) 따라간다.

---

## 7. 검증 요구사항 (반드시 수행)

구현자는 다음 5개 시나리오 모두 통과시켜야 한다.

### 검증 1: 설치 검증
```
python scripts/entry/cdp_cli.py goto naver
python scripts/entry/cdp_cli.py popup-install
# 기대: 성공 메시지, frame_count >= 1
python scripts/entry/cdp_cli.py popup-poll
# 기대: 빈 리스트 (이벤트 없음, 정상 상태)
```

### 검증 2: 알려진 팝업 감지
```
python scripts/entry/cdp_cli.py goto https://blog.naver.com/skyjwsin?Redirect=Write
python scripts/entry/cdp_cli.py popup-install
# 페이지 새로고침해서 '작성 중인 글' 팝업 띄움:
python scripts/entry/cdp_cli.py reload     # (있다면) 또는 navigator에 reload 명령 추가
sleep 3
python scripts/entry/cdp_cli.py popup-poll
# 기대: events 최소 1개, marker == '작성 중인 글'
```

### 검증 3: 자동 처리
```
# 검증 2와 동일 상태에서:
python scripts/entry/cdp_cli.py popup-auto
# 기대: handled에 1개 이상, 팝업 사라짐
python scripts/entry/cdp_cli.py popup-poll
# 기대: 빈 리스트 (clear됨)
```

### 검증 4: 미지의 팝업 unknown 보고
- `POPUP_MARKERS`에 없는 텍스트를 임의로 마커에 추가하지 말 것
- 새 마커가 unknown에 들어가는지 단위 테스트로만 확인 (tests/test_popup_watcher.py)

### 검증 5: 중복 push 방지
- 같은 팝업이 5초 안에 2번 떠도 events에 1개만 쌓이는지 확인
- 단위 테스트로 검증 (시간 mocking 사용 가능)

### 종합 회귀 검증
기존 통합 흐름이 망가지지 않았는지 확인:
```
python scripts/entry/cdp_cli.py write-post "watcher 후 회귀 테스트" "본문" data/test_image.png
# 기대: 모든 단계 ✓ 통과
```

---

## 8. 구현 순서 (단계별 지시)

1. `scripts/browser/popup/popup_watcher.py` 파일 생성 — `POPUP_MARKERS`, `build_watcher_js`, `install_watcher` 작성
2. 단위 테스트 `tests/test_popup_watcher.py` 작성 (모킹 기반, 실제 브라우저 없이 동작 검증)
3. `poll_events`, `clear_events`, `auto_handle` 작성
4. `cdp_client.py`에 3개 case 분기 추가
5. **검증 1~3 수행** — 실패하면 디버그
6. 통합 회귀 검증 수행
7. 메모리에 결과 보고 (성공 시: 통과, 실패 시: 막힘 지점)

---

## 9. 금지 사항

- 기존 `handle_draft_restore_popup` 함수 삭제/수정 금지 (보존)
- `POPUP_MARKERS`에 사용자 승인 없이 임의 마커 추가 금지
- 발행/삭제/전송 같은 비가역 액션을 `action` 필드에 등록 금지 — 자동 처리 위험
- `MutationObserver` 외 polling 백그라운드 스레드 생성 금지

---

## 10. 인수 기준 (Definition of Done)

- 위 검증 1~5 + 회귀 검증 모두 통과
- `git status` 상 신규 파일 2개(`popup_watcher.py`, `test_popup_watcher.py`), 수정 파일 1개(`cdp_client.py`)만 존재
- 기존 `write-post` 흐름이 새 코드 도입 후에도 동작
