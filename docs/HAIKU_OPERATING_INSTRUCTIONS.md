# Haiku 운영 지시문 — 브라우저 자동화 표준 절차 (SOP)

본 지시문은 Haiku 4.5가 사용자 요청을 처리할 때 따라야 할 표준 운영 절차입니다.
모든 브라우저 관련 작업은 본 SOP를 따릅니다. 어긋나는 상황 발견 시 §7 형식으로 중단 보고.

---

## 0. 핵심 원칙 (절대 규칙)

| 규칙 | 내용 |
|---|---|
| **한글 보고** | 모든 사용자 대면 출력은 한글 |
| **수동 안내 금지** | 사용자에게 "URL 입력해주세요 / Chrome 창 찾아주세요 / 완료라고 답해주세요" 절대 금지 |
| **자동 감지 우선** | 로그인은 쿠키 폴링으로 자동 감지, 사용자 회신 대기 금지 |
| **CDP 단일 경로** | 브라우저 작업은 `cdp_launcher` + `BrowserAgent` 조합만 사용 |
| **이상 시 중단** | 추측 금지. 모호하면 즉시 §7 형식 보고 |
| **repo boundary** | `C:\Users\skyjw\OneDrive\03. PYTHON\35. haehan-ai-orchestrator` 외부 접근 금지 |
| **자격증명 자동 입력 금지** | 첫 로그인은 사용자 수동, 이후 세션 영구 유지 |

---

## 1. 사용자 요청 분류 — 의사결정 트리

```
사용자 발화 도착
   │
   ├─ 사이트 접속/탐색/확인/방문 요청?
   │     예: "네이버 가봐", "블로그 열어", "G2B 탐색해"
   │     → §2 사이트 접속 SOP
   │
   ├─ 데이터 추출/분석 요청?
   │     예: "이 블로그 포스트 다 가져와", "댓글 수집해"
   │     → §3 데이터 추출 SOP
   │
   ├─ 글 작성/제출 요청?
   │     예: "블로그에 글 올려", "카페에 댓글 달아"
   │     → §4 작성/제출 SOP (사용자 승인 필수)
   │
   └─ 코드/도구 개발 요청?
         → §5 개발 SOP
```

---

## 2. 사이트 접속 SOP

### Step A — 도메인 추출

사용자 발화에서 도메인 직접 추출. 모호하면 1회 확인.

| 사용자 발화 | 추출 URL |
|---|---|
| "네이버 가봐" | `https://www.naver.com` |
| "네이버 블로그 열어" | `https://blog.naver.com` |
| "G2B 탐색해" | `https://www.g2b.go.kr` |
| "한컴 개발자 사이트" | `https://developer.hancom.com` |

### Step B — 자동 탭 열기 + 로그인 감지

```python
from scripts.browser.agent.cdp_launcher import open_and_wait_login
result = open_and_wait_login("<url>", timeout=300)
```

또는 CLI:
```
python -m scripts.browser.agent.cdp_launcher <url> --wait-login [domain] [timeout_s]
```

### Step C — 결과 분기

| `result["logged_in"]` | `result["already"]` | 다음 액션 |
|---|---|---|
| `True` | `True` | 이미 로그인됨 — 즉시 작업 진행 |
| `True` | `False` | 사용자 로그인 감지됨 — 작업 진행 |
| `False` | `False` | 타임아웃 — §7 형식 중단 보고 |

### Step D — 사용자 보고 (한글)

```
✓ <사이트명> 접속 완료 (logged_in=<bool>, elapsed=<N>s)
다음 작업: <사용자 요청한 후속 작업>
```

**금지 표현:**
- ❌ "Chrome 창에서 직접 URL 입력해주세요"
- ❌ "로그인 후 '완료'라고 답해주세요"
- ❌ "http://127.0.0.1:9222 접속해주세요"

**허용 표현:**
- ✓ "<사이트명> 탭이 자동으로 열렸습니다. 로그인하시면 자동 감지됩니다."
- ✓ "이미 로그인 상태입니다. 작업 진행합니다."

---

## 3. 데이터 추출 SOP

### Step A — 사이트 접속 (§2 적용)

### Step B — BrowserAgent 사용

```python
from scripts.browser.agent.agent import BrowserAgent
with BrowserAgent() as agent:
    agent.go("<url>")
    # CafeMixin / BlogMixin 메서드 활용
    posts = agent.blog_posts("https://blog.naver.com/<id>")
    info  = agent.blog_info("https://blog.naver.com/<id>")
    # ...
```

`connect()`가 자동으로 `ensure_cdp()` 호출 → CDP 미기동 시 Task Scheduler로 자동 부트.

### Step C — 결과 보고

추출 건수, 핵심 필드, 저장 위치만 한글로 간결하게.

---

## 4. 작성/제출 SOP (사용자 승인 필수)

### Step A — 작성 의도 명시

```
[작성 요청 확인]
대상: <사이트>
내용: <제목/본문 요약>
파일/이미지: <첨부>
승인 시 진행합니다. (예/아니오)
```

### Step B — 사용자 "예" 응답 후만 진행

`browser_prepare_submit.py` / `browser_submit_with_user_approval.py` 활용.

L2 `WRITE_INTENT` 감사 이벤트 자동 기록.

---

## 5. 개발 SOP

### 새 사이트 지원 추가 시

새 도메인의 인증 쿠키를 `LOGIN_MARKERS`에 등록:

```python
# scripts/browser/agent/cdp_session_manager.py
LOGIN_MARKERS = {
    ...,
    "<new_domain>": ["<auth_cookie_1>", "<auth_cookie_2>"],
}
```

쿠키명을 모르면 1회 로그인 후 `get_cdp_cookies()`로 확인:
```python
from scripts.browser.agent.cdp_session_manager import get_cdp_cookies
cookies = [c for c in get_cdp_cookies() if "<new_domain>" in c.get("domain","")]
print([c["name"] for c in cookies])
```

세션 만료 후 재발급되는 쿠키만 마커로 등록 (HttpOnly + Secure 표시 우선).

### 새 추출 기능 추가 시

`mixins/cafe_mixin.py` / `mixins/blog_mixin.py` 패턴 그대로 따름.
JS 추출 코드는 `_js/` 디렉토리에 분리.

---

## 6. 매 세션 시작 시 사전 점검

브라우저 작업 첫 진입 시 1회만 확인:

```
1. CDP 살아있는지: probe_cdp() → True
   (False면 ensure_cdp() 자동 호출됨)
2. Task 등록 여부: is_task_registered() → True
   (False면 §7 중단 보고 — install ps1 1회 실행 안내)
3. 세션 초기화 여부: is_session_initialized() → True
   (False면 사이트 첫 로그인 절차로 안내)
```

병렬 호출 가능. 모두 OK면 즉시 작업 진행, 메시지 출력 생략 (silent OK).

---

## 7. 중단 보고 형식

이상 발견 시 즉시 다음 형식으로 보고하고 작업 중단:

```
⚠ 작업 중단 — <컨텍스트>

[발견 이상]
<구체적 증상 1줄>

[원인 추정]
<가능성 1~2개>

[관찰 데이터]
<명령>
<출력>

[권장 다음 액션]
- 옵션 A: <...>
- 옵션 B: <...>

사용자 지시를 기다립니다.
```

### 정지 트리거 (즉시 중단)

1. CDP probe 15초 이상 실패
2. Task 'HaehanCdpChrome' 미등록 발견
3. 로그인 감지 타임아웃 (5분 기본)
4. `LOGIN_MARKERS` 미등록 도메인이면서 쿠키도 0개
5. BrowserAgent.connect() 시 contexts/pages 비정상
6. `data/cdp_profile/` 또는 `data/audit/`에 예상치 못한 변경
7. 본 SOP에 명시되지 않은 작업 패턴이 필요할 때

---

## 8. 작업 완료 보고 표준 형식

```
✓ <작업명> 완료

[수행]
- <Step 1 결과>
- <Step 2 결과>
- ...

[감사 로그]
data/audit/L2_audit/<파일> — <N>건 이벤트

[다음 단계]
<사용자 요청 가능한 후속 작업>
```

---

## 9. 자주 쓰는 명령 모음

| 목적 | 명령 |
|---|---|
| 사이트 자동 열기 | `python -m scripts.browser.agent.cdp_launcher <url>` |
| 사이트 + 로그인 감지 | `python -m scripts.browser.agent.cdp_launcher <url> --wait-login <domain> <timeout>` |
| CDP 살아있나 | `python -c "from scripts.browser.agent.cdp_launcher import probe_cdp; print(probe_cdp())"` |
| 로그인 도메인 보기 | `python -c "from scripts.browser.agent.cdp_session_manager import get_logged_in_sites; print(get_logged_in_sites())"` |
| Task 재기동 | `schtasks /run /tn HaehanCdpChrome` |
| 감사 로그 회전 | `python -c "from scripts.common.cdp_audit import rotate; print(rotate())"` |

---

## 10. 모듈 책임 매트릭스

| 모듈 | 책임 | 호출 시점 |
|---|---|---|
| `cdp_launcher` | CDP 부트, 새 탭, 로그인 대기 | 모든 진입점 |
| `cdp_session_manager` | 세션 진단, 쿠키, 마커 | 로그인 판정 시 |
| `cdp_audit` | L1/L2/L3 감사 로그 | 자동 (다른 모듈에서 호출) |
| `BrowserAgent` (`agent.py`) | 페이지 조작, 추출, 작성 | 사이트 접속 후 |
| `CafeMixin` / `BlogMixin` | 사이트별 도메인 로직 | BrowserAgent 통해 |
| Task Scheduler `HaehanCdpChrome` | Chrome 9222 기동 | 로그온 + on-demand |

---

## 11. 사용자가 새로운 패턴을 요구할 때

본 SOP에 없는 패턴은:
1. 추측 금지
2. §7 형식 중단 보고 + 1~2개 옵션 제안
3. 사용자 결정 후 진행
4. 진행 후 본 SOP에 패턴 추가 제안 (선택)

---

# 끝

본 지시문은 모든 브라우저 자동화 작업의 단일 진입점입니다.
세부 부트스트랩은 `docs/HAIKU_CDP_BOOTSTRAP_PLAN.md` 참조.
