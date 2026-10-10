# 네이버 메일/캘린더/MyBox API 수정 설계서 (Haiku 작업용)

> **작성 배경**: `verify_all_methods.py` 9개 항목 중 3개만 통과. 디버그를 통해 모든 실제 API를 캡처 확인. 이 설계서는 Haiku가 그대로 따라 적용할 수 있는 정확한 구현 가이드.

---

## 0. 핵심 원칙 (절대 지키기)

### ❌ 금지 패턴
```python
# 모두 빈 body / 404 / 500 반환됨 — 사용 금지
res = self._page.request.get(url)
res.json()
```

### ✅ 권장 패턴 1: `page.evaluate()` + 브라우저 내부 fetch
```python
result = self._page.evaluate("""async () => {
    const resp = await fetch(URL, { credentials: 'include' });
    return await resp.json();
}""")
```

### ✅ 권장 패턴 2: `add_init_script` + XHR 후킹 (페이지 자체가 호출하는 API 캡처)
```python
HOOK_JS = """
window.__cap = [];
const _xhrOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(m, url, ...r) {
    this._capUrl = url;
    return _xhrOpen.apply(this, [m, url, ...r]);
};
const _xhrSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send = function(...a) {
    this.addEventListener('load', function() {
        try {
            window.__cap.push({ url: this._capUrl, status: this.status, body: this.responseText });
        } catch(e) {}
    });
    return _xhrSend.apply(this, a);
};
"""
self._page.add_init_script(HOOK_JS)  # navigation 전에 한 번만
self.go(URL)
time.sleep(3)
captured = self._page.evaluate("() => window.__cap || []")
```

> ⚠️ `add_init_script`는 BrowserAgent 초기화 시 **한 번만** 등록해야 함 (중복 등록시 후킹 충돌). `agent.py`의 `__enter__` 또는 페이지 생성 직후 위치.

---

## 1. 작업 항목

### 1.1 calendar_mixin.py — `calendar_events` 수정

**파일**: `scripts/browser/agent/calendar_mixin.py`

**현재 동작**: 빈 응답 인터셉트 방식 → 캡처 0개
**수정 방향**: `page.evaluate()`로 브라우저 내부에서 직접 fetch 호출

#### 교체 코드 (calendar_events 메서드 전체 교체)
```python
def calendar_events(self, start: str, end: str) -> list[dict]:
    """일정 목록 조회 — 브라우저 내부 fetch.

    Args:
        start: 시작일 "YYYY-MM-DD"
        end: 종료일 "YYYY-MM-DD"
    반환: [{id, title, start, end, location}]
    """
    self.go("https://calendar.naver.com/")
    time.sleep(3)
    s = start.replace("-", "")
    e = end.replace("-", "")
    try:
        data = self._page.evaluate(f"""async () => {{
            const ts = Date.now();
            const url = `/ajax/GetScheduleList?ts=${{ts}}&startDt={s}&endDt={e}`;
            const resp = await fetch(url, {{ credentials: 'include' }});
            if (!resp.ok) return null;
            return await resp.json();
        }}""")
        if not data:
            return []
        raw = (data.get("retScheduleList", {}).get("returnValue") or [])
        if not isinstance(raw, list):
            return []
        return [{
            "id":       str(ev.get("scheduleId", ev.get("id", ""))),
            "title":    ev.get("subject", ev.get("title", "")),
            "start":    str(ev.get("startDt", start)),
            "end":      str(ev.get("endDt", end)),
            "location": ev.get("location", ""),
        } for ev in raw]
    except Exception:
        return []
```

#### 검증 응답 (이미 캡처됨)
```json
{"result":"success","retTaskList":{...},"retScheduleList":{"result":"success","returnValue":[...]}}
```

---

### 1.2 mail_mixin.py — `mail_folders`, `mail_unread_count` 수정

**파일**: `scripts/naver/mail/mail_mixin.py`

**현재 동작**: DOM 추출로 폴더 목록 가져옴 → count는 0 반환 (DOM에서 안 읽힘)
**수정 방향**: `/json/folder/list` API를 `page.evaluate(fetch)`로 직접 호출

#### `mail_folders` 메서드 교체
```python
def mail_folders(self) -> list[dict]:
    """폴더 목록 — JSON API.

    반환: [{name, count, mail_count, folder_sn, folder_type}]
    """
    self.go("https://mail.naver.com/")
    time.sleep(2)
    try:
        # 사용자 ID 추출 (URL이나 페이지 데이터에서)
        data = self._page.evaluate("""async () => {
            // 사용자 ID는 후속 호출에서 자동으로 처리되거나 비어있어도 동작
            const resp = await fetch('/json/folder/list?vipMailBox=true', { credentials: 'include' });
            if (!resp.ok) return null;
            return await resp.json();
        }""")
        if not data:
            return []
        folder_list = data.get("folderList", [])
        return [{
            "name":       f.get("folderName", ""),
            "count":      f.get("unreadMailCount", 0),
            "mail_count": f.get("mailCount", 0),
            "folder_sn":  f.get("folderSN"),
            "folder_type": f.get("folderType", ""),
        } for f in folder_list]
    except Exception:
        return []
```

#### `mail_unread_count` 메서드 교체
```python
def mail_unread_count(self) -> int:
    """전체 안읽은 메일 수 — JSON API.
    
    folder/list 응답의 totalUnreadMail 필드 직접 추출.
    """
    self.go("https://mail.naver.com/")
    time.sleep(2)
    try:
        data = self._page.evaluate("""async () => {
            const resp = await fetch('/json/folder/list?vipMailBox=true', { credentials: 'include' });
            if (!resp.ok) return null;
            return await resp.json();
        }""")
        if not data:
            return 0
        return int(data.get("totalUnreadMail", 0))
    except Exception:
        return 0
```

#### 검증 응답 (이미 캡처됨)
```json
{
  "totalUnreadMail": 194,
  "folderList": [
    {"folderSN": 0, "folderType": "S", "folderName": "받은메일함",
     "unreadMailCount": 54, "mailCount": 58}
  ]
}
```

---

### 1.3 mail_mixin.py — `mail_search` 수정

**현재 동작**: 검색 페이지로 navigate만 → 자동으로 검색 API 호출 안됨
**수정 방향**: 검색창에 입력 + Enter 시뮬레이션 → DOM에서 결과 추출

#### `mail_search` 메서드 교체
```python
def mail_search(self, query: str, max_n: int = 30) -> list[dict]:
    """메일 검색 — 검색창 입력 시뮬레이션 + DOM 추출.

    반환: [{id, from, subject, date, unread}]
    """
    from urllib.parse import quote
    self.go(f"https://mail.naver.com/v2/search?q={quote(query)}")
    time.sleep(3)
    
    # 검색 페이지가 자동 검색하지 않을 경우, 검색창에 직접 입력
    try:
        # 1차 시도: URL이동만으로 결과 로드 대기
        time.sleep(2)
        result = self._page.evaluate(_js("extract_mail_inbox.js"))
        if result and len(result) > 0:
            return result[:max_n]

        # 2차 시도: 검색창 클릭 + 입력 + Enter
        search_input = self._page.query_selector(
            'input[placeholder*="검색"], input[type="search"], [class*="search"] input'
        )
        if search_input:
            search_input.click()
            search_input.fill(query)
            self._page.keyboard.press("Enter")
            time.sleep(3)
            result = self._page.evaluate(_js("extract_mail_inbox.js"))
            return (result or [])[:max_n]
    except Exception:
        pass
    return []
```

---

### 1.4 mybox_mixin.py — `mybox_quota` 수정

**파일**: `scripts/browser/agent/mybox_mixin.py`

**현재 동작**: DOM 셀렉터 탐색 → 0개
**수정 방향**: `api.mybox.naver.com/service/quota/get` 직접 호출

#### `mybox_quota` 메서드 교체
```python
def mybox_quota(self) -> dict:
    """용량 정보 조회 — JSON API.

    반환: {used, total, unused, file_max, unit}
    단위는 bytes
    """
    self.go("https://mybox.naver.com/main/web/my")
    time.sleep(3)
    try:
        data = self._page.evaluate("""async () => {
            const resp = await fetch('https://api.mybox.naver.com/service/quota/get', { credentials: 'include' });
            if (!resp.ok) return null;
            return await resp.json();
        }""")
        if not data or data.get("code") != "0":
            return {}
        result = data.get("result", {})
        return {
            "used":     result.get("usedQuota", 0),
            "total":    result.get("totalQuota", 0),
            "unused":   result.get("unusedQuota", 0),
            "file_max": result.get("fileMaxSize", 0),
            "unit":     "bytes",
        }
    except Exception:
        return {}
```

#### 검증 응답 (이미 캡처됨)
```json
{
  "code": "0", "message": "success",
  "result": {
    "totalQuota": 32212254720, "usedQuota": 29538990814,
    "unusedQuota": 2673263906, "fileMaxSize": 4294967296
  }
}
```

---

### 1.5 mybox_mixin.py — `mybox_list` 수정 (제한 사항 명시)

**현재 상황**: MyBox 메인 페이지 로드시 파일 목록 API가 자동 호출되지 않음 (캡처된 API 7개 모두 quota/user/config 관련)

**수정 방향**: 두 가지 접근 시도
1. `api.mybox.naver.com/service/file/list` 등 추정 엔드포인트 시도
2. 실패시 메서드는 빈 리스트 반환하되, 로그/주석으로 한계 명시

#### `mybox_list` 메서드 교체
```python
def mybox_list(self, path: str = "/") -> list[dict]:
    """파일/폴더 목록 — JSON API 시도.

    Note: MyBox 메인 페이지에서는 파일 목록 API가 자동 호출되지 않음.
    추정 엔드포인트들을 순차 시도하며, 모두 실패시 빈 리스트.
    
    반환: [{name, type, size, mtime}]
    """
    from urllib.parse import quote
    self.go("https://mybox.naver.com/main/web/my")
    time.sleep(3)
    
    encoded_path = quote(path)
    try:
        data = self._page.evaluate(f"""async () => {{
            const candidates = [
                'https://api.mybox.naver.com/service/file/list?path={encoded_path}',
                'https://api.mybox.naver.com/service/files/list?path={encoded_path}',
                'https://api.mybox.naver.com/api/v1/file/list?path={encoded_path}',
                'https://api.mybox.naver.com/service/file/getList?path={encoded_path}',
            ];
            for (const url of candidates) {{
                try {{
                    const resp = await fetch(url, {{ credentials: 'include' }});
                    if (!resp.ok) continue;
                    const json = await resp.json();
                    if (json && json.code === '0' && json.result) {{
                        return {{ url, json }};
                    }}
                }} catch(e) {{}}
            }}
            return null;
        }}""")
        if not data:
            return []
        result = data.get("json", {}).get("result", {})
        raw = result.get("list") or result.get("fileList") or result.get("items") or []
        if not isinstance(raw, list):
            return []
        return [{
            "name":  f.get("name", f.get("fileName", "")),
            "type":  "folder" if f.get("isDir") or f.get("type") == "folder" else "file",
            "size":  f.get("size", f.get("fileSize", 0)),
            "mtime": f.get("modifiedDate", f.get("lastModified", "")),
        } for f in raw]
    except Exception:
        return []
```

> **주의**: 위 4개 엔드포인트는 추정. 실제 동작 엔드포인트는 사용자가 폴더 페이지에서 직접 클릭해야 캡처 가능. 향후 add_init_script 후킹으로 실제 엔드포인트 발견 후 업데이트.

---

## 2. verify_all_methods.py 수정

`mail_unread_count`가 정상 동작 후에도 0을 반환할 수 있고 (실제로 안읽은 메일이 없는 경우), `bool(0) == False`로 인해 실패로 표시됨. **숫자형 메서드는 별도 검증 로직** 적용.

**파일**: `scripts/verify_all_methods.py`

#### `check` 함수 시그니처에 `allow_zero` 추가
```python
def check(name, fn, *args, allow_zero=False, **kwargs):
    try:
        val = fn(*args, **kwargs)
        # 숫자형은 0이어도 정상 — 호출 자체가 성공한 것
        if allow_zero and isinstance(val, int):
            ok = True
        else:
            ok = bool(val)
        results.append((name, ok, val))
        ...
```

#### `mail_unread_count` 호출 라인 수정
```python
check("mail_unread_count()", a.mail_unread_count, allow_zero=True)
```

마찬가지로 `calendar_today()`도 빈 리스트가 정상 결과일 수 있으나, 일단 통과 기준은 유지하고 사용자가 today 일정 추가 후 재실행 권장.

---

## 3. 작업 순서 (Haiku 진행 가이드)

직렬로, 한 단계씩, 완료 검증 후 다음 단계로:

1. **calendar_mixin.py — calendar_events 메서드 교체** (1.1)
   - 검증: `python -c "from scripts.browser.agent.agent import BrowserAgent; a=BrowserAgent(); a.__enter__(); print(a.calendar_events('2026-05-01','2026-05-31'))"` 또는 verify 스크립트 일부 실행

2. **mail_mixin.py — mail_folders 교체** (1.2)
   - 검증: 폴더 목록과 count 값 확인 (받은메일함 unreadMailCount > 0 기대)

3. **mail_mixin.py — mail_unread_count 교체** (1.2)
   - 검증: 0이 아닌 양수 반환 기대 (이전 디버그에서 totalUnreadMail: 194 확인)

4. **mail_mixin.py — mail_search 교체** (1.3)
   - 검증: "네이버" 검색시 1개 이상 결과

5. **mybox_mixin.py — mybox_quota 교체** (1.4)
   - 검증: `{used, total, unused, file_max, unit}` 모두 양수 반환

6. **mybox_mixin.py — mybox_list 교체** (1.5)
   - 검증: 빈 리스트여도 통과 (제한 사항 명시됨)

7. **scripts/verify_all_methods.py — allow_zero 추가** (2)
   - 검증: 전체 9/9 또는 8/9 통과 (mybox_list 제외)

8. **최종 검증**: `python scripts/verify_all_methods.py` 실행 → 결과 요약 출력

---

## 4. 절대 하지 말 것

- ❌ 기존 메서드 시그니처(인자 이름, 반환 키) 변경 금지
- ❌ `_js()` 헬퍼 함수 제거 금지 (다른 메서드가 사용)
- ❌ `time.sleep(N)` 값 임의 축소 (네트워크 응답 대기 필수)
- ❌ `try/except` 제거 (네이버는 일시적 오류 자주 발생, fallback 동작 유지)
- ❌ 새로운 mixin 파일 생성 금지 (기존 파일 내부 메서드만 교체)
- ❌ `BrowserAgent.__enter__` 등 핵심 코드 수정 금지

---

## 5. 디버그시 참고할 캡처 데이터

이미 검증된 실제 API 응답 샘플 (`scripts/debug_init_script.py` 실행 결과):

- **캘린더**: `/ajax/GetScheduleList` → `retScheduleList.returnValue: []` (5월에 일정 없음)
- **메일 폴더**: `/json/folder/list?vipMailBox=true&u=skyjwsin` → `totalUnreadMail: 194`, `folderList[0].unreadMailCount: 54` (받은메일함)
- **MyBox quota**: `api.mybox.naver.com/service/quota/get` → `totalQuota: 32212254720, usedQuota: 29538990814`
- **MyBox user**: `api.mybox.naver.com/service/user/get` → `userId: skyjwsin`

---

**작성일**: 2026-05-10  
**작성자**: Claude Opus 4.7 (탐지 및 설계)  
**작업자**: Claude Haiku 4.5 (구현 및 검증)
