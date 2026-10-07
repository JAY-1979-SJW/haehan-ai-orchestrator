# CDP 부트스트랩 + 세션 저장 + 감사 통제 — Haiku 실행 가이드

본 문서는 Haiku 4.5가 그대로 따라 실행할 수 있도록 작성된 단계별 가이드입니다.
각 Step의 **검증 조건**이 충족되지 않으면 **즉시 중단하고 한글로 보고**합니다.

---

## 0. 헌장 (반드시 준수)

| 규칙 | 내용 |
|---|---|
| **한글 보고** | 모든 사용자 대면 출력은 한글 |
| **직렬 실행** | Phase/Step 순서 엄수, 병렬 금지 (Phase 1 내부 파일 작성만 병렬 허용) |
| **이상 발견 시** | 즉시 중단하고 §10 형식으로 보고 |
| **코드 무단 변경 금지** | 본 문서에 없는 파일/내용은 절대 수정 금지 |
| **repo boundary** | `C:\Users\skyjw\OneDrive\03. PYTHON\35. haehan-ai-orchestrator` 외부 접근 금지 |
| **사용자 자격증명** | 절대 자동 입력 금지. 첫 로그인은 사용자 수동 |

---

## 1. 사전 조건 체크 (Step 0)

다음을 모두 확인. 하나라도 불일치 시 §10 형식으로 중단 보고:

| 항목 | 확인 명령 | 기대값 |
|---|---|---|
| 작업 디렉토리 | `pwd` | `...\haehan-ai-orchestrator` |
| Chrome 설치 | `Test-Path "C:\Program Files\Google\Chrome\Application\chrome.exe"` | `True` |
| Python | `python --version` | 3.10+ |
| Playwright | `python -c "import playwright; print(playwright.__version__)"` | 정상 출력 |
| git 깨끗함 (선택) | `git status --short` | (참고용, 차단 아님) |

이상 시 보고 후 사용자 지시 대기.

---

## 2. 정지 조건 (이상 발견 시 즉시 중단)

다음 중 하나라도 발생하면 즉시 멈추고 §10 형식 보고:

1. **본 문서에 없는 파일 수정 요구가 발생** — 예: 기존 `audit_logger.py` 변경 제안 등
2. **검증 명령이 예상과 다른 출력** — exit code, 파일 부재, 에러 메시지
3. **권한 거부** — Task Scheduler 등록, 파일 쓰기 실패
4. **이미 동일 이름의 Task/파일이 존재**하지만 내용이 본 설계와 다름
5. **Chrome 프로세스 25개 이상 실행 중** — 사용자 작업 중일 가능성
6. **`data/cdp_profile/` 또는 `data/audit/`에 예상치 못한 데이터 존재**
7. **사용자가 응답한 적 없는 승인을 요구하는 상황**
8. **import 에러, ModuleNotFoundError** — 구조 불일치
9. **본 가이드의 어떤 step도 모호하다고 판단되면** — 추측 금지, 보고 후 대기

---

## 3. Phase 1 — 파일 작성

### Step 1.1 — `.gitignore` 보강

**도구:** Edit

**대상:** `C:\Users\skyjw\OneDrive\03. PYTHON\35. haehan-ai-orchestrator\.gitignore`

**작업:** 파일 끝에 다음 블록이 없으면 추가. 이미 있으면 skip.

```
# Haehan CDP — 자격증명/감사 로그 절대 커밋 금지
data/cdp_profile/
data/cdp_profile_backups/
data/audit/
```

**검증:** `Select-String "data/cdp_profile" .gitignore` 결과 1줄 이상.

---

### Step 1.2 — `cdp_audit.py` 작성

**도구:** Write

**대상:** `scripts/common/cdp_audit.py`

**내용:** 본 가이드 §A 부록 그대로 (한 글자도 변경 금지).

**검증:** `python -c "from scripts.common.cdp_audit import L1, L2, L3, emit, rotate; print('ok')"` → `ok`.

---

### Step 1.3 — `cdp_launcher.py` 작성

**도구:** Write

**대상:** `scripts/browser/agent/cdp_launcher.py`

**내용:** 본 가이드 §B 부록 그대로.

**검증:** `python -c "from scripts.browser.agent.cdp_launcher import probe_cdp, ensure_cdp, is_task_registered; print('ok')"` → `ok`.

---

### Step 1.4 — `cdp_session_manager.py` 작성

**도구:** Write

**대상:** `scripts/browser/agent/cdp_session_manager.py`

**내용:** 본 가이드 §C 부록 그대로.

**검증:** `python -c "from scripts.browser.agent.cdp_session_manager import get_profile_dir, is_session_initialized, get_logged_in_sites; print('ok')"` → `ok`.

---

### Step 1.5 — `install_cdp_chrome_task.ps1` 작성

**도구:** Write

**대상:** `scripts/local_agent/install_cdp_chrome_task.ps1`

**내용:** 본 가이드 §D 부록 그대로.

**검증:** `Test-Path scripts\local_agent\install_cdp_chrome_task.ps1` → `True`.

---

### Step 1.6 — `agent.py` 수정

**도구:** Edit (replace)

**대상:** `scripts/browser/agent/agent.py`

**작업 1:** 파일 상단의 import 블록 끝에 다음 추가 (이미 있으면 skip):

```python
import uuid
```

**작업 2:** `connect()` 메서드를 다음으로 교체:

찾을 문자열 (정확히):
```python
    def connect(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(self._cdp_url)
        self._ctx = self._browser.contexts[0]
        self._page = self._ctx.pages[0]
        # 새탭 자동 흡수
        self._ctx.on("page", self._on_new_page)
        return self
```

교체할 문자열:
```python
    def connect(self):
        from scripts.browser.agent.cdp_launcher import ensure_cdp
        from scripts.common.cdp_audit import L2
        self._session_id = str(uuid.uuid4())
        self._connect_t0 = time.time()
        ensure_cdp()
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(self._cdp_url)
        self._ctx = self._browser.contexts[0]
        self._page = self._ctx.pages[0]
        # 새탭 자동 흡수
        self._ctx.on("page", self._on_new_page)
        L2("CDP_CONNECT", "browser_agent",
           session_id=self._session_id,
           contexts_count=len(self._browser.contexts),
           pages_count=len(self._ctx.pages))
        return self
```

**작업 3:** `close()` 메서드를 다음으로 교체:

찾을 문자열 (정확히):
```python
    def close(self):
        if self._pw:
            self._pw.stop()
```

교체할 문자열:
```python
    def close(self):
        from scripts.common.cdp_audit import L2
        if self._pw:
            self._pw.stop()
        L2("CDP_DISCONNECT", "browser_agent",
           session_id=getattr(self, "_session_id", ""),
           duration_ms=int((time.time() - getattr(self, "_connect_t0", time.time())) * 1000))
```

**검증:** `python -c "from scripts.browser.agent.agent import BrowserAgent; print('ok')"` → `ok` (실행은 안 함, import만).

**※ 만약 `connect()` 또는 `close()`의 기존 코드가 위 "찾을 문자열"과 정확히 일치하지 않으면 — 즉시 중단하고 §10 형식으로 보고.**

---

### Step 1.7 — 운영규칙 보강

**도구:** Edit

**대상:** `C:\Users\skyjw\.claude\projects\C--Users-skyjw-OneDrive-03--PYTHON-35--haehan-ai-orchestrator\memory\feedback_user_browser_session_default.md`

**작업:** 파일 끝에 다음 블록이 없으면 추가:

```markdown
## 로그/감사 통제
- 모든 CDP/세션/BrowserAgent 활동은 `cdp_audit.emit()` 기록 (L1/L2/L3)
- 저장: `data/audit/{L1_runtime,L2_audit,L3_session}/*.jsonl`
- 민감정보(쿠키 값, password 키, 이메일/주민번호) 자동 마스킹
- 보존: L1 30일, L2/L3 1년 — `cdp_audit.rotate()` 호출
- `data/audit/`, `data/cdp_profile/` 는 .gitignore — 커밋 금지

## CDP 자동 부트스트랩
- `BrowserAgent.connect()` 진입 시 `cdp_launcher.ensure_cdp()` 자동 호출
- 9222 포트 미응답 시 Task Scheduler('HaehanCdpChrome') 자동 기동
- Task 등록은 1회 사용자 승인:
  `powershell -ExecutionPolicy Bypass -File scripts\local_agent\install_cdp_chrome_task.ps1`
- CDP 호스트 고정: `127.0.0.1` (IPv6 ::1 회피)
- 전용 프로필: `data/cdp_profile/` (사용자 평소 Chrome과 격리)
```

---

## 4. Phase 2 — Task Scheduler 등록 (사용자 승인 1회)

### Step 2.1 — Chrome 종료 (충돌 방지)

**Phase 2 진입 전 사용자에게 확인 메시지 출력 후 응답 대기:**

> "Chrome을 모두 종료합니다 (열려 있는 탭은 잃지 않도록 미리 저장 부탁드립니다). 진행할까요? (예/아니오)"

사용자 "예" 응답 시에만 진행.

**명령:** `taskkill /f /im chrome.exe`

**검증:** `tasklist /fi "imagename eq chrome.exe"` 결과에 chrome.exe 없음.

---

### Step 2.2 — Task 등록 스크립트 실행

**명령:**
```
powershell -ExecutionPolicy Bypass -File scripts\local_agent\install_cdp_chrome_task.ps1
```

**기대 출력:** `[OK] Task 'HaehanCdpChrome' 등록 완료`

**검증:** `schtasks /query /tn HaehanCdpChrome` exit code 0.

**실패 시:** 즉시 중단 + 보고. 권한 부족이면 사용자에게 관리자 PowerShell 실행 안내.

---

## 5. Phase 3 — CDP 자동 기동 검증

### Step 3.1 — Task 기동

**명령:** `schtasks /run /tn HaehanCdpChrome`

**기대 출력:** `SUCCESS: Attempted to run...`

---

### Step 3.2 — CDP probe (최대 15초 대기)

**명령:**
```
python -c "import time; from scripts.browser.agent.cdp_launcher import probe_cdp; t=time.time()+15;
while time.time()<t:
  if probe_cdp(): print('OK'); break
  time.sleep(1)
else: print('FAIL')"
```

**기대 출력:** `OK`

**FAIL 시 즉시 중단 + 보고.**

---

### Step 3.3 — 세션 초기화 확인 + 자동 탭 열기

**명령 1 (세션 상태 확인):**
```
python -c "from scripts.browser.agent.cdp_session_manager import is_session_initialized, get_logged_in_sites; print('init=', is_session_initialized()); print('sites=', get_logged_in_sites()[:10])"
```

**케이스 A: `init= False`** — 첫 실행.

**명령 2 (자동 탭 열기 + 로그인 자동 감지 — 사용자 수동 입력/'완료' 회신 절대 금지):**

```
python -m scripts.browser.agent.cdp_launcher <url> --wait-login [domain] [timeout_s]
```

또는 Python 모듈:
```python
from scripts.browser.agent.cdp_launcher import open_and_wait_login
result = open_and_wait_login("https://blog.naver.com", timeout=300)
# result["logged_in"]이 True가 될 때까지 자동 폴링 (2초 간격)
```

동작:
1. 새 탭 즉시 열림
2. 인증 쿠키(NID_AUT 등) 등장까지 폴링
3. 감지되면 즉시 반환 / 타임아웃 시 False

사용자에게는 다음만 안내:
> "<사이트명> 탭이 자동으로 열렸습니다. 로그인하시면 자동 감지됩니다."

**"로그인 후 '완료' 답해달라"는 안내 절대 금지** — 쿠키로 자동 감지.

`logged_in=False` 타임아웃 시 중단 + 보고.

**케이스 B: `init= True`** — Step 3.4로 진행.

---

### 일반 원칙 — 사용자 자연어 사이트 요청 처리

본 인프라가 갖춰진 이후, 사용자가 어떤 사이트를 요청하든 동일 패턴 적용:

1. 사용자 발화에서 도메인 추출 (예: "한컴 개발자 사이트 열어" → `developer.hancom.com`)
2. `open_url(<url>)` 호출
3. 자동 탭 열림 → 즉시 보고
4. (필요 시) 로그인 안내 → 완료 대기

추측이 어려우면 사용자에게 1회만 도메인 확인.

---

### Step 3.4 — BrowserAgent 통합 검증

**명령:** 임시 검증 스크립트 실행 (파일 작성하지 말고 인라인):

```
python -c "
from scripts.browser.agent.agent import BrowserAgent
with BrowserAgent() as a:
    a.go('https://blog.naver.com')
    print('TITLE:', a._page.title()[:80])
    print('URL:', a._page.url)
"
```

**기대 출력:** TITLE에 '네이버 블로그' 포함, URL에 `blog.naver.com` 포함.

---

### Step 3.5 — 감사 로그 생성 검증

**명령:**
```
Get-ChildItem data\audit\L2_audit -Filter "*.jsonl" | Select-Object Name, Length
```

**기대:** 1개 이상의 jsonl 파일, Length > 0.

추가 검증:
```
Get-Content data\audit\L2_audit\*.jsonl | Select-Object -Last 5
```

마지막 5줄에 `CDP_BOOT_OK`, `CDP_CONNECT`, `CDP_DISCONNECT` 이벤트 중 최소 1개 포함.

---

## 6. Phase 4 — 최종 보고

### Step 4.1 — 사용자 보고 (한글)

다음 형식으로 보고:

```
✓ CDP 부트스트랩 + 세션 + 감사 통제 적용 완료

[Phase 1] 파일 작성: 7개 step 완료
  - cdp_audit.py / cdp_launcher.py / cdp_session_manager.py 신규
  - install_cdp_chrome_task.ps1 신규
  - agent.py connect/close 통합 수정
  - .gitignore / 운영규칙 보강

[Phase 2] Task Scheduler: HaehanCdpChrome 등록 완료
[Phase 3] CDP 자동 기동: 9222 응답 OK
[Phase 3] 세션: <도메인 N개> 로그인 확인
[Phase 3] BrowserAgent: 네이버 블로그 접속 성공

[감사] data/audit/L2_audit/<파일> 생성 (<라인 수>개 이벤트)

다음 작업: 블로그 도구 탐색/개발 진행 가능
```

---

## 7. 작업 추적

Phase 1 시작 시 TaskCreate로 다음 task 등록, 각 step 완료 시 TaskUpdate.

```
[ ] Phase 1.1  .gitignore 보강
[ ] Phase 1.2  cdp_audit.py
[ ] Phase 1.3  cdp_launcher.py
[ ] Phase 1.4  cdp_session_manager.py
[ ] Phase 1.5  install_cdp_chrome_task.ps1
[ ] Phase 1.6  agent.py 수정
[ ] Phase 1.7  운영규칙 보강
[ ] Phase 2.1  Chrome 종료 (사용자 승인)
[ ] Phase 2.2  Task 등록
[ ] Phase 3.1  Task 기동
[ ] Phase 3.2  CDP probe
[ ] Phase 3.3  세션 초기화
[ ] Phase 3.4  BrowserAgent 검증
[ ] Phase 3.5  감사 로그 검증
[ ] Phase 4.1  최종 보고
```

---

## 8. 사용자 승인 필요 지점 (3개소)

| 지점 | 내용 |
|---|---|
| **Phase 2.1 직전** | "Chrome 모두 종료해도 될까요?" — 응답 대기 |
| **Phase 2.2 실행 시** | PowerShell 권한 프롬프트 (자동) |
| **Phase 3.3 케이스 A** | "사이트 로그인 후 '완료' 회신해주세요" |

---

## 9. 롤백 절차 (실패 시)

| 실패 위치 | 롤백 |
|---|---|
| Phase 1 | `git checkout` 으로 변경 파일 원복 + 신규 파일 삭제 |
| Phase 2 | `schtasks /delete /tn HaehanCdpChrome /f` |
| Phase 3 | `data/cdp_profile/` 삭제 (또는 `cdp_session_manager.reset_session(True)`) |

롤백 후 사용자에게 진단 결과 한글 보고.

---

## 10. 중단 보고 형식

이상 발견 시 즉시 다음 형식으로 보고하고 작업 중단:

```
⚠ 작업 중단 — <Phase X.Y> <Step 이름>

[발견 이상]
<구체적 증상 1줄>

[정지 조건]
§2 항목 #<N>: <해당 조건>

[관찰 데이터]
<명령>
<출력>

[권장 다음 액션]
<옵션 A: ...>
<옵션 B: ...>

사용자 지시를 기다립니다.
```

---

# 부록 §A — `cdp_audit.py` 전체 내용

```python
"""CDP/세션 감사 로거.

L1 운영, L2 감사, L3 세션 이벤트 분리 저장. JSONL append-only.
민감정보 자동 마스킹.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
AUDIT_ROOT = Path(__file__).resolve().parents[3] / "data" / "audit"
SCHEMA_VERSION = 1

_SENSITIVE_KEYS = re.compile(r"(password|token|auth|secret|apikey|api_key|cookie)", re.I)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RRN_RE = re.compile(r"\d{6}-\d{7}")


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=2)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _mask_value(v: Any) -> Any:
    if isinstance(v, str):
        v = _EMAIL_RE.sub("***@***", v)
        v = _RRN_RE.sub("******-*******", v)
        return v[:8000]
    if isinstance(v, dict):
        return {k: ("***" if _SENSITIVE_KEYS.search(k) else _mask_value(val))
                for k, val in v.items()}
    if isinstance(v, list):
        return [_mask_value(x) for x in v]
    return v


def _path_for(level: str) -> Path:
    today = datetime.now(KST).strftime("%Y%m%d")
    yyyymm = datetime.now(KST).strftime("%Y%m")
    if level == "L1":
        return AUDIT_ROOT / "L1_runtime" / f"browser_runtime_{today}.jsonl"
    if level == "L2":
        return AUDIT_ROOT / "L2_audit" / f"browser_audit_{today}.jsonl"
    if level == "L3":
        return AUDIT_ROOT / "L3_session" / f"session_events_{yyyymm}.jsonl"
    raise ValueError(f"unknown level: {level}")


def emit(level: str, event: str, actor: str, **fields) -> None:
    rec = {
        "ts": datetime.now(KST).isoformat(timespec="milliseconds"),
        "level": level,
        "event": event,
        "actor": actor,
        "session_id": fields.pop("session_id", None) or str(uuid.uuid4()),
        "user": os.environ.get("USERNAME") or os.environ.get("USER", ""),
        "host_pid": os.getpid(),
        "git_sha": _git_sha(),
        "schema_version": SCHEMA_VERSION,
        **_mask_value(fields),
    }
    p = _path_for(level)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def L1(event: str, actor: str, **fields): emit("L1", event, actor, **fields)
def L2(event: str, actor: str, **fields): emit("L2", event, actor, **fields)
def L3(event: str, actor: str, **fields): emit("L3", event, actor, **fields)


def rotate(retention_days: dict[str, int] | None = None) -> dict:
    retention_days = retention_days or {"L1_runtime": 30, "L2_audit": 365, "L3_session": 365}
    deleted = {}
    for sub, days in retention_days.items():
        d = AUDIT_ROOT / sub
        if not d.exists():
            continue
        cutoff = datetime.now(KST) - timedelta(days=days)
        n = 0
        for f in d.glob("*.jsonl"):
            if datetime.fromtimestamp(f.stat().st_mtime, KST) < cutoff:
                f.unlink()
                n += 1
        deleted[sub] = n
    return deleted
```

---

# 부록 §B — `cdp_launcher.py` 전체 내용

```python
"""CDP 부트스트랩 — Chrome 9222 포트 보장 기동.

흐름: probe → 미연결 시 Task Scheduler 기동 → retry probe.
"""
from __future__ import annotations

import subprocess
import time
import urllib.request
import urllib.error

from scripts.common.cdp_audit import L1, L2

CDP_HOST = "127.0.0.1"
CDP_PORT = 9222
TASK_NAME = "HaehanCdpChrome"
PROBE_TIMEOUT = 15
PROBE_INTERVAL = 1
ACTOR = "cdp_launcher"


def probe_cdp(host: str = CDP_HOST, port: int = CDP_PORT, timeout: float = 1.5) -> bool:
    t0 = time.time()
    url = f"http://{host}:{port}/json/version"
    ok = False
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            ok = r.status == 200
    except (urllib.error.URLError, ConnectionError, OSError):
        ok = False
    L1("CDP_PROBE", ACTOR, host=host, port=port, result=ok,
       elapsed_ms=int((time.time() - t0) * 1000))
    return ok


def is_task_registered(task_name: str = TASK_NAME) -> bool:
    try:
        r = subprocess.run(["schtasks", "/query", "/tn", task_name],
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def start_via_scheduler(task_name: str = TASK_NAME) -> tuple[bool, str]:
    try:
        r = subprocess.run(["schtasks", "/run", "/tn", task_name],
                           capture_output=True, text=True, timeout=10)
        ok = r.returncode == 0
        msg = ((r.stdout or "") + (r.stderr or "")).strip()
        L2("CDP_TASK_TRIGGER", ACTOR, task_name=task_name, exit_code=r.returncode)
        return ok, msg
    except Exception as e:
        L2("CDP_TASK_TRIGGER", ACTOR, task_name=task_name, exit_code=-1, error=str(e))
        return False, str(e)


def ensure_cdp(host: str = CDP_HOST, port: int = CDP_PORT,
               task_name: str = TASK_NAME, timeout: float = PROBE_TIMEOUT) -> str:
    t0 = time.time()
    base = f"http://{host}:{port}"

    if probe_cdp(host, port):
        L2("CDP_BOOT_OK", ACTOR, host=host, port=port, retries=0,
           total_ms=0, reason="already_up")
        return base

    if not is_task_registered(task_name):
        L2("CDP_BOOT_FAIL", ACTOR, reason="task_not_registered", task=task_name)
        raise RuntimeError(
            f"Task '{task_name}' 미등록. 다음 명령으로 등록 필요:\n"
            f"  powershell -ExecutionPolicy Bypass -File "
            f"scripts/local_agent/install_cdp_chrome_task.ps1"
        )

    ok, msg = start_via_scheduler(task_name)
    if not ok:
        L2("CDP_BOOT_FAIL", ACTOR, reason="schtasks_run_failed", message=msg[:500])
        raise RuntimeError(f"schtasks /run 실패: {msg}")

    deadline = time.time() + timeout
    retries = 0
    while time.time() < deadline:
        retries += 1
        if probe_cdp(host, port):
            L2("CDP_BOOT_OK", ACTOR, host=host, port=port,
               retries=retries, total_ms=int((time.time() - t0) * 1000))
            return base
        time.sleep(PROBE_INTERVAL)

    L2("CDP_BOOT_FAIL", ACTOR, reason="probe_timeout",
       retries=retries, total_ms=int((time.time() - t0) * 1000))
    raise RuntimeError(
        f"CDP {base} 응답 없음 ({timeout}초 대기). Chrome 기동 확인 필요."
    )
```

---

# 부록 §C — `cdp_session_manager.py` 전체 내용

```python
"""CDP 프로필 세션 관리 — 진단/백업/리셋."""
from __future__ import annotations

import os
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from scripts.common.cdp_audit import L2, L3

PROFILE_ROOT = Path(__file__).resolve().parents[3] / "data" / "cdp_profile"
ACTOR = "session_manager"


def get_profile_dir() -> Path:
    return PROFILE_ROOT


def is_session_initialized() -> bool:
    cookies_db = PROFILE_ROOT / "Default" / "Cookies"
    if not cookies_db.exists():
        return False
    try:
        with sqlite3.connect(f"file:{cookies_db}?mode=ro", uri=True) as con:
            cur = con.execute("SELECT COUNT(*) FROM cookies")
            return cur.fetchone()[0] > 0
    except Exception:
        return False


def get_logged_in_sites() -> list[str]:
    cookies_db = PROFILE_ROOT / "Default" / "Cookies"
    if not cookies_db.exists():
        return []
    try:
        with sqlite3.connect(f"file:{cookies_db}?mode=ro", uri=True) as con:
            cur = con.execute("SELECT DISTINCT host_key FROM cookies ORDER BY host_key")
            return [row[0].lstrip(".") for row in cur.fetchall()]
    except sqlite3.OperationalError:
        return []


def backup_session(dest_dir: Path | None = None) -> Path:
    dest_dir = dest_dir or (PROFILE_ROOT.parent / "cdp_profile_backups")
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = dest_dir / f"cdp_profile_{ts}.zip"
    size = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in PROFILE_ROOT.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(PROFILE_ROOT))
                size += p.stat().st_size
    L2("SESSION_BACKUP", ACTOR, dest=str(out), size_bytes=size)
    return out


def reset_session(confirm: bool = True) -> None:
    if not confirm:
        raise ValueError("reset_session은 confirm=True 명시 필요")
    size_before = (
        sum(p.stat().st_size for p in PROFILE_ROOT.rglob("*") if p.is_file())
        if PROFILE_ROOT.exists() else 0
    )
    L3("SESSION_RESET", ACTOR,
       confirmed_by=os.environ.get("USERNAME", ""),
       profile_size_before=size_before)
    if PROFILE_ROOT.exists():
        shutil.rmtree(PROFILE_ROOT)
```

---

# 부록 §D — `install_cdp_chrome_task.ps1` 전체 내용

```powershell
# Haehan AI Orchestrator — CDP Chrome Task Scheduler 등록
# 1회 실행으로 'HaehanCdpChrome' Task 등록.

param(
    [string]$ChromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe",
    [int]$Port = 9222,
    [string]$ProfileDir = "C:\Users\skyjw\OneDrive\03. PYTHON\35. haehan-ai-orchestrator\data\cdp_profile",
    [string]$TaskName = "HaehanCdpChrome"
)

if (-not (Test-Path $ChromePath)) {
    Write-Error "Chrome 미발견: $ChromePath"
    exit 1
}

New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null

$argLine = "--remote-debugging-port=$Port --user-data-dir=`"$ProfileDir`" --no-first-run --no-default-browser-check"

$action  = New-ScheduledTaskAction -Execute $ChromePath -Argument $argLine
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Limited

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $TaskName `
    -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Haehan AI Orchestrator: Chrome with CDP port $Port"

Write-Host "[OK] Task '$TaskName' 등록 완료"
Write-Host "    실행: schtasks /run /tn $TaskName"
Write-Host "    제거: schtasks /delete /tn $TaskName /f"
```

---

# 끝

본 문서를 그대로 따른 후 §6 형식 보고로 종료. 어떤 단계든 모호하거나 예상치 못한 출력이 나오면 즉시 §10 형식으로 중단 보고.
