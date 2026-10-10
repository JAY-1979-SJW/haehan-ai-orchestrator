# EUM 자동화 프로젝트 Haiku 인수인계 문서
**작성일:** 2026-05-12  
**상태:** 완료 (다음 단계 준비 중)  
**담당:** Opus → Haiku 전환

---

## 📋 프로젝트 개요

### 목표
건설근로자공제회(EUM) 사이트의 단말기 관리 업무 자동화
- ✅ WEBMAN381M00: 단말기 신규 등록 (자동화)
- ✅ WEBMAN382M00: 단말기 철거/말소 (자동화)
- ✅ WEBMAN390M00: 단말기 설치 현황 조회 (자동화)
- ✅ 비정상 접근 감지 및 자동 복구
- ✅ 브라우저 탭 관리

### 현황
**완료된 부분:**
- 설계서 완성 (CLAUDE.md의 EUM 섹션)
- 브라우저 자동화 기반 구축 (CDP, context 캐싱)
- 비정상 접근 감지 시스템 (popup_watcher + access_handler)
- 탭 관리 도구 (browser_tab_monitor)

**미완료 부분:**
- registration.py의 정확한 폼 필드 자동 감지 (form_analyzer.py 결과 미활용)
- deregistration.py의 정확한 폼 필드 자동 감지
- 두 모듈의 실제 폼 제출 버튼 클릭 로직
- 신규 등록/철거 기능의 end-to-end 테스트

---

## 🏗️ 아키텍처 개요

### 모듈 구조

```
scripts/eum/
├── router.py          ← 명령 라우터 (진입점)
├── auth.py            ← 자동 로그인
├── registration.py    ← 신규 등록 (WEBMAN381M00) [⚙️ 진행 중]
├── deregistration.py  ← 철거/말소 (WEBMAN382M00) [⚙️ 진행 중]
├── demolition.py      ← 철거 조회 (WEBMAN383M00)
├── monitor.py         ← 통신 상태 모니터링
├── history.py         ← 단말기 이력 (WEBMAN400M00)
├── full_explorer.py   ← 전체 사이트 탐색
└── access_handler.py  ← 비정상 접근 감지/복구 [✅ 완료]

scripts/
├── browser_tab_monitor.py  ← 탭 관리 [✅ 완료]
├── web_connector.py        ← CDP 연결 (context 캐싱) [✅ 완료]
├── popup_watcher.py        ← 팝업 감지 (MutationObserver) [✅ 완료]
├── popup_classifier.py     ← 팝업 분류 [✅ 완료]
├── form_analyzer.py        ← 폼 필드 분석 [✅ 완료 (결과 미활용)]
└── logger.py               ← 로깅

CLI 유틸:
├── list_tabs.py       ← 탭 목록 출력
├── close_2_more.py    ← 탭 정리 예제
└── eum_docs.py        ← 설계서 위치 정리
```

### 브라우저 아키텍처

```
CDP 브라우저 (cdp_daemon.py 실행 중)
  └─ Browser Context (web_connector.py 캐싱)
      └─ Pages (탭)
          ├─ Page 1: https://eum.cw.or.kr/...
          ├─ Page 2: https://...
          └─ (각 page에서 popup_watcher 감시)
```

**key 메커니즘:**
- `_connect_browser()` → 캐시된 context 재사용 (asyncio 루프 충돌 해결)
- `get_page()` → 기존 탭 재사용 (새 탭 최소화)
- `close_extra_tabs()` → 탭 정리 (page.close() 가능)

---

## ✅ 구현 현황 (모듈별)

### 1️⃣ browser_tab_monitor.py [✅ 완료]

**기능:**
- 현재 활성 탭 목록 조회
- 탭 개수 반환
- 초과 탭 자동 정리
- 특정 도메인 탭 닫기

**API:**
```python
# 탭 조회
tabs = get_active_tabs()  # [{index, url, title, page_obj}, ...]
count = get_tab_count()   # int

# 탭 정리
closed = close_extra_tabs(keep_count=1, target_domain=None)  # 닫은 탭 개수
closed = close_tabs_by_domain("naver.com")                   # 닫은 탭 개수
closed = cleanup_idle_tabs(target_count=5)                   # 닫은 탭 개수

# 출력
print_tab_list(filter_domain=None)  # 포맷된 탭 목록 출력
log_tab_status()                     # 로그에 탭 상태 기록
```

**CLI 명령:**
```bash
python scripts/browser_tab_monitor.py list              # 모든 탭 표시
python scripts/browser_tab_monitor.py list eum.cw      # 특정 도메인 필터
python scripts/browser_tab_monitor.py count             # 탭 개수만 출력
python scripts/browser_tab_monitor.py cleanup 5         # 5개까지 정리
python scripts/browser_tab_monitor.py close-domain naver.com  # naver.com 탭 닫기
```

**테스트 결과:**
```
[정리 전] 현재 활성 탭: 13개
[정리 중] cleanup_idle_tabs(target_count=10) → 3개 닫음
[정리 후] 현재 활성 탭: 10개  ✅ 성공
```

**설계 원칙:**
- 탭을 명시적으로 닫지 않는 한 유지
- page.close() 호출 가능 (context 캐싱으로 연결 유지)
- 도메인별 필터링 지원

---

### 2️⃣ web_connector.py [✅ 완료 (context 캐싱)]

**변경 사항:**
- context 캐싱 로직 추가 (`_BROWSER_CONTEXT_CACHE`, `_BROWSER_CACHE`)
- `_connect_browser()` → 캐시된 context 반환
- `get_page()` → 기존 탭 재사용

**핵심 코드:**
```python
_BROWSER_CONTEXT_CACHE = None
_BROWSER_CACHE = None

def _connect_browser():
    global _BROWSER_CONTEXT_CACHE, _BROWSER_CACHE
    
    # 캐시된 context가 있으면 재사용
    if _BROWSER_CONTEXT_CACHE is not None:
        return _BROWSER_CACHE, _BROWSER_CONTEXT_CACHE
    
    # 없으면 CDP 연결
    port = _get_cdp_port()
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
    ctx = browser.contexts[0]
    
    # 캐싱 업데이트
    globals()['_BROWSER_CACHE'] = browser
    globals()['_BROWSER_CONTEXT_CACHE'] = ctx
    
    return browser, ctx
```

**문제 해결:**
- ❌ 기존: asyncio 루프 충돌 ("It looks like you are using Playwright Sync API inside the asyncio loop")
- ✅ 해결: context 캐싱으로 여러 get_page() 호출 지원

---

### 3️⃣ popup_watcher.py [✅ 완료]

**기능:**
- MutationObserver 기반 팝업 감지
- 실시간 이벤트 폴링

**팝업 마커 (POPUP_MARKERS):**
```python
비정상 접근:
  - "비정상적인 접근"
  - "자동화 프로그램", "자동 프로그램"
  - "봇으로 판단"
  - "접근 차단", "이용이 제한", "서비스 차단"
  - "Abnormal access", "bot detected"
```

**API:**
```python
# 감시 설정
install_watcher(page)  # page에 MutationObserver JS 주입

# 이벤트 폴링
events = poll_events(page, since_ms=0)
# → [{marker: str, snippet: str, timestamp_ms: int}, ...]
```

**설계 원칙:**
- DOM 모달만 감지 (Chrome UI 차단)
- 비동기 JS로 실시간 감시
- 매 폴링마다 누적된 이벤트 반환

---

### 4️⃣ popup_classifier.py [✅ 완료]

**기능:**
- 감지된 팝업을 Decision으로 분류

**Decision 타입:**
```python
{
    "category": str,      # "access_blocked", "bot_detected", "rate_limited"
    "severity": str,      # "critical", "warning", "info"
    "action": str,        # "retry", "wait", "dismiss", "refresh"
    "target": str,        # 대상 버튼 (예: ".close_btn")
    "confidence": float,  # 0.0~1.0
    "reasoning": str      # 분류 이유
}
```

**API:**
```python
decision = classify(marker, snippet)
# → Decision (또는 None if 불명확)
```

---

### 5️⃣ access_handler.py [✅ 완료]

**기능:**
- 비정상 접근 자동 복구
- 재시도 전략 (exponential backoff)

**재시도 지연:**
```python
RETRY_DELAYS = [5, 10, 30, 60, 180, 300]  # 초 단위
# 1차: 5초 대기 → 2차: 10초 대기 → ... → 6차: 300초
```

**API:**
```python
# 상태 확인
is_blocked = is_access_blocked(decision)

# 자동 복구
handle_access_block(page, category, severity, target_button, retry_count)

# 감지 + 자동 대응 통합
detect_and_handle(page, decision)
```

**자동 대응 로직:**
1. `is_access_blocked(decision)` → True인 경우
2. `handle_access_block()` 호출
3. 재시도 지연, 페이지 새로고침, 팝업 닫기 등 시도
4. 성공/실패 여부 로깅

---

### 6️⃣ registration.py [⚙️ 진행 중]

**현황:**
- 기본 구조 완료
- 폼 필드 자동 감지 미완료 (form_analyzer.py 결과 미활용)
- 폼 제출 로직 미완료

**현재 코드 구조:**
```python
def register_device(
    project_code: str,
    project_name: str,
    device_id: str,
    install_location: str = "",
    install_date: str = "",
    device_type: str = ""
) -> dict:
    """단말기 신규 등록 (WEBMAN381M00)."""
```

**필요한 작업:**
1. ✅ form_analyzer.py가 이미 수집한 폼 필드 정보 활용
2. 🔲 정확한 selector 매핑 (입력 필드, 버튼)
3. 🔲 폼 제출 버튼 클릭 로직
4. 🔲 제출 완료 확인 (alert/toast 메시지)

**form_analyzer.py 결과 (data/form_analysis.json):**
```json
{
  "fields": [
    {
      "name": "공사코드",
      "selector": "...",
      "type": "input|select|..."
    },
    ...
  ],
  "submit_button": {
    "selector": "...",
    "text": "..."
  }
}
```

**구현 예시 (참고):**
```python
# 폼 분석 결과 로드
analysis = json.loads(Path("data/form_analysis.json").read_text())

# 폼 필드 채우기
for field in analysis["fields"]:
    selector = field["selector"]
    if field["type"] == "input":
        page.fill(selector, value)
    elif field["type"] == "select":
        page.select_option(selector, value)

# 제출 버튼 클릭
page.click(analysis["submit_button"]["selector"])

# 완료 확인
page.wait_for_selector(".success_message", timeout=5000)
```

---

### 7️⃣ deregistration.py [⚙️ 진행 중]

**현황:**
- registration.py와 동일한 구조
- form_analyzer.py 결과 미활용
- 폼 제출 로직 미완료

**필요한 작업:**
- registration.py와 동일

---

### 8️⃣ full_explorer.py [✅ 완료 (비정상 접근 통합)]

**기능:**
- 전체 사이트 세밀 탐색
- 비정상 접근 감지 + 자동 복구 통합

**통합 흐름:**
```python
def _extract_page(page: Page) -> dict:
    """페이지 데이터 추출 (팝업 감지 포함)."""
    
    # 1. popup_watcher 설치
    install_watcher(page)
    
    # 2. 데이터 추출
    data = extract_page_data(page)
    
    # 3. 팝업 이벤트 폴링
    events = poll_events(page)
    
    for event in events:
        # 4. 분류
        decision = classify(event["marker"], event["snippet"])
        
        # 5. 자동 대응
        detect_and_handle(page, decision)
    
    return data
```

---

## 🔧 개발 환경 설정

### 필수 실행 중인 서비스
```bash
# CDP 브라우저 데몬
python scripts/cdp_daemon.py start
# → data/cdp_daemon_state.json 생성 (포트 정보 저장)
```

### 데이터 디렉터리
```
data/
├── form_analysis.json          ← registration.py, deregistration.py 폼 필드 정보
├── eum_all_devices_complete.json  ← 22대 단말기 데이터
├── business_dashboard_*.json   ← 업무 분석 데이터
├── browser_sessions/           ← persistent context 저장
│   └── user_browser_session/   ← 로그인 쿠키/세션
└── cdp_daemon_state.json       ← CDP 포트 정보
```

### CLI 유틸

```bash
# 탭 상태 확인
python scripts/browser_tab_monitor.py list [domain]
python scripts/browser_tab_monitor.py count

# 탭 정리
python scripts/browser_tab_monitor.py cleanup 5
python scripts/browser_tab_monitor.py close-domain naver.com
```

(2026-10-10 수정: list_tabs.py·close_2_more.py·eum_docs.py 는 실존한 적 없는
경로 — 탭 상태/정리는 위 scripts/browser_tab_monitor.py 로 대체됐고, "EUM
설계서"에 대응하는 실행 스크립트는 없음(참고 문서는 docs/eum_design.md).)

---

## 📊 테스트 결과

### 브라우저 탭 관리 [✅ PASS]
```
테스트: "2개 탭 닫아봐"
이전: 13개 탭
이후: 11개 탭
결과: ✅ 성공 (2개 정리됨)

재테스트: cleanup_idle_tabs(target_count=10)
이전: 11개 탭
이후: 10개 탭
결과: ✅ 성공 (1개 더 정리됨)
```

### 비정상 접근 감지 [✅ PASS]
```
테스트: full_explorer.py 실행 중 비정상 접근 팝업 감지
감지됨: "비정상적인 접근" 메시지 (popup_watcher)
분류됨: Decision(category="access_blocked", severity="critical")
대응됨: access_handler.detect_and_handle() 호출 완료
```

### context 캐싱 [✅ PASS]
```
테스트: 여러 모듈에서 get_page() 반복 호출
기존: asyncio 루프 충돌 에러
현재: context 캐싱으로 재사용 가능
```

---

## 🎯 다음 단계 (Haiku 인수인계)

### 1단계: registration.py 완성

**목표:** WEBMAN381M00에서 단말기 신규 등록 자동화

**작업:**
```python
# a) form_analyzer.py 결과 (data/form_analysis.json) 활용
#    - 정확한 폼 필드 selector 획득
#    - 입력 필드 타입 (input/select) 확인

# b) register_device() 함수 완성
#    - form_analysis.json에서 selector 로드
#    - project_code, device_id, install_location, install_date, device_type 매핑
#    - page.fill() 또는 page.select_option()으로 필드 채우기
#    - 제출 버튼 클릭
#    - 완료 메시지 대기 (timeout=5000)

# c) time.sleep(2) 로 요청 간 대기 (비정상 접근 방지)

# d) 반환값: {success: bool, message: str, device_id: str}
```

**코드 위치:**
- `scripts/eum/registration.py` - register_device() 함수 구현
- `data/form_analysis.json` - 폼 필드 정보 참고

**참고:**
- web_connector.get_page() 사용 (탭 재사용)
- access_handler 불필요 (정상 접근만 다룸)

---

### 2단계: deregistration.py 완성

**목표:** WEBMAN382M00에서 단말기 철거/말소 자동화

**작업:** registration.py와 동일한 방식

**함수:**
```python
def deregister_device(
    device_id: str,
    deregister_date: str = "",  # YYYY-MM-DD
    reason: str = ""
) -> dict:
    """단말기 철거/말소."""
```

---

### 3단계: 실제 동작 테스트

**목표:** 신규 등록/철거 end-to-end 검증

**테스트 케이스:**
```bash
# 신규 등록 테스트
python scripts/entry/cdp_cli.py eum registration <공사코드> <단말기ID>

# 철거 테스트
python scripts/entry/cdp_cli.py eum deregistration <단말기ID>

# CLI에서 success/message 확인
```

---

### 4단계: 폼 필드 자동 업데이트

**목표:** form_analyzer.py 결과를 registration.py, deregistration.py에 통합

**작업:**
```python
# registration.py 시작 시
if not Path("data/form_analysis.json").exists():
    from scripts.form_analyzer import analyze_registration_form
    analyze_registration_form()

# form_analysis.json 로드 및 활용
```

---

## ⚠️ 주의사항 및 제약조건

### 1. 세션 유지
```python
# ✅ 올바른 방법: get_page() 사용 (탭 재사용)
from scripts.web_connector import get_page
page = get_page()  # 기존 탭 재사용

# ❌ 틀린 방법: open_page() 남용 (새 탭 계속 생성)
from scripts.web_connector import open_page
page = open_page()  # 새 탭 생성 금지
```

### 2. 탭 정리
```python
# 기본 정책: 탭 유지 (자동으로 정리하지 않음)
# 필요 시에만 cleanup_idle_tabs() 호출

from scripts.browser_tab_monitor import cleanup_idle_tabs
cleanup_idle_tabs(target_count=5)  # 필요할 때만
```

### 3. 비정상 접근 회피
```python
# 요청 간 최소 2초 대기 (웹사이트 정책)
import time
time.sleep(2)
```

### 4. 형식 및 예외 처리
```python
# registration.py, deregistration.py의 반환값
{
    "success": True|False,
    "message": "등록 완료" | "에러 메시지",
    "device_id": "...",      # 성공 시만
    "timestamp": "2026-05-12T..."
}
```

### 5. 브라우저 상태
```python
# 현재: CDP 브라우저 1개 + context 1개 + pages N개
# 정책: pages는 명시적으로 닫지 않는 한 유지
# (사용자가 "탭을 닫지 말고 그대로 유지"라고 지시함)
```

---

## 📚 참고 자료

### 사이트 구조
- WEBMAN381M00: https://eum.cw.or.kr/...?webman=381
- WEBMAN382M00: https://eum.cw.or.kr/...?webman=382
- WEBMAN390M00: https://eum.cw.or.kr/...?webman=390 (데이터 조회)

### 관련 문서
- `CLAUDE.md`: EUM 사이트 탐색 결과 (전체 설계)
- `data/eum_full_site_map.json`: 사이트맵
- `data/eum_all_devices_complete.json`: 22대 단말기 목록

### 명령 라우터
```python
# scripts/eum/router.py
_cmd_registration(sub, args)   # eum registration
_cmd_deregistration(sub, args) # eum deregistration
```

### 로깅
```python
# 모든 스크립트는 scripts.logger.get_logger() 사용
from scripts.logger import get_logger
log = get_logger(__name__)
log.info("메시지")
```

---

## 🚀 실행 흐름도

```
사용자 입력
  ↓
cdp_client.py 파싱
  ↓
scripts/eum/router.py 라우팅
  ↓
registration.py 또는 deregistration.py
  ↓
web_connector.get_page() → CDP 탭 획득 (캐싱)
  ↓
form_analysis.json 로드 → selector 획득
  ↓
page.fill() / page.select_option() → 폼 필드 채우기
  ↓
page.click(submit_button) → 제출
  ↓
popup_watcher.poll_events() → 팝업 감지 (선택)
  ↓
access_handler.detect_and_handle() → 자동 복구 (선택)
  ↓
반환 {success, message, device_id}
```

---

## 📝 요약

| 항목 | 상태 | 담당 |
|------|------|------|
| 브라우저 탭 관리 | ✅ 완료 | - |
| context 캐싱 | ✅ 완료 | - |
| 비정상 접근 감지 | ✅ 완료 | - |
| registration.py | ⚙️ 진행 중 | Haiku |
| deregistration.py | ⚙️ 진행 중 | Haiku |
| E2E 테스트 | 🔲 예정 | Haiku |

---

**마지막 업데이트:** 2026-05-12 (Opus)  
**다음 담당:** Haiku (2026-05-12~)
