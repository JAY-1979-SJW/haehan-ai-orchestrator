# 네이버 API 수정 설계서 V2 — Haiku 작업용

> **작성 배경**: V1 설계서 적용 후 5/9 통과. 미해결 4건에 대해 `scripts/explore_unresolved.py` + `explore_unresolved_v2.py`로 실제 API 호출 패턴 캡처 완료. 추정이 아닌 **실측 데이터** 기반 V2.

> **현재 상태**: 5/9 통과 (mail_inbox, mail_read, mail_folders, mail_unread_count, mybox_quota)
> **목표**: 9/9 통과

---

## 0. 핵심 원칙 (변경 없음)

```python
# ❌ 금지
self._page.request.get(url)

# ✅ 사용
self._page.evaluate("""async () => {
    const resp = await fetch(URL, { credentials: 'include' });
    return await resp.json();
}""")

# ✅ 또는 add_init_script로 XHR 후킹 후 캡처
```

---

## 1. 미해결 4건 수정 작업

### 🔧 1.1 calendar_events — 응답 구조 오해 수정

**파일**: `scripts/browser/agent/calendar_mixin.py`

**문제**: 현재 코드는 `data.retScheduleList.returnValue`를 **list로 가정**하고 사용 → 실제로는 **object**

**실측 응답 구조** (`scripts/explore_unresolved.py` 캡처):
```json
{
  "result": "success",
  "retScheduleList": {
    "result": "success",
    "returnValue": {
      "scheduleList": [],          ← 일정 배열은 여기!
      "anniversaryList": []
    }
  }
}
```

**추가 발견**:
- API는 **POST** 메서드 (현재 코드는 GET fetch). 하지만 XHR 후킹으로 받으면 무관.
- `?ts={timestamp}`만 있어도 동작 (startDt/endDt는 SPA 내부에서 세팅된 month 범위 사용)

#### `calendar_events` 메서드 교체 (전체 교체)
```python
def calendar_events(self, start: str, end: str) -> list[dict]:
    """일정 목록 조회 — XHR 후킹 방식. 응답 구조 v2 반영.

    Args:
        start: "YYYY-MM-DD"
        end: "YYYY-MM-DD"
    반환: [{id, title, start, end, location}]
    """
    HOOK = """
    window.__calendarRaw = null;
    const origXhrOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(m, u, ...r) {
        this._hookUrl = u;
        return origXhrOpen.apply(this, [m, u, ...r]);
    };
    const origXhrSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(...a) {
        this.addEventListener('load', function() {
            if (this._hookUrl && this._hookUrl.includes('GetScheduleList')) {
                try {
                    window.__calendarRaw = JSON.parse(this.responseText);
                } catch(e) {}
            }
        });
        return origXhrSend.apply(this, a);
    };
    """
    if not hasattr(self._page, '_calendar_hook_added'):
        self._page.add_init_script(HOOK)
        self._page._calendar_hook_added = True

    self.go("https://calendar.naver.com/")
    time.sleep(4)

    raw = self._page.evaluate("() => window.__calendarRaw")
    if not raw:
        return []

    # 응답 구조: retScheduleList.returnValue.scheduleList (배열)
    return_value = (raw.get("retScheduleList") or {}).get("returnValue") or {}
    if not isinstance(return_value, dict):
        return []
    schedule_list = return_value.get("scheduleList") or []
    if not isinstance(schedule_list, list):
        return []

    s_filter = start.replace("-", "")
    e_filter = end.replace("-", "")
    result = []
    for ev in schedule_list:
        ev_start = str(ev.get("startDt", ""))
        ev_end   = str(ev.get("endDt", ""))
        # 날짜 범위 필터 (빈 문자열은 제외)
        if ev_start and (ev_start <= e_filter and ev_end >= s_filter):
            result.append({
                "id":       str(ev.get("scheduleId", ev.get("id", ""))),
                "title":    ev.get("subject", ev.get("title", "")),
                "start":    ev_start,
                "end":      ev_end,
                "location": ev.get("location", ""),
            })
    return result
```

> **주의**: `calendar_today()`는 `calendar_events()`를 호출하므로 자동으로 같이 해결됨. 수정 불필요.

---

### 🔧 1.2 mail_search — search_input 셀렉터 + 직접 API 호출

**파일**: `scripts/naver/mail/mail_mixin.py`

**핵심 발견** (`explore_unresolved_v2.py` 캡처):

1. **검색 input 정확한 셀렉터**: `input.search_input` (placeholder="메일 검색")
2. **검색 결과 API**: `POST /json/search/?page=1&from=&folderSN=-1&to=&body={query}&bodyCond=0&exceptTrash=true`
3. **응답 구조**:
   ```json
   {
     "lastPage": 1, "totalCount": 13, "listCount": 13,
     "body": "네이버", "Result": "OK",
     "mailData": [{
       "mailSN": 112236, "folderSN": 0,
       "from": {"name": "네이버", "email": "..."},
       "subject": "...", "receivedTime": 1778375275, ...
     }]
   }
   ```

**해결 전략**: 직접 API 호출 (XHR 후킹) — page.evaluate fetch는 빈 응답 가능성 → XHR 후킹 일관성 유지

#### `mail_search` 메서드 교체 (전체 교체)
```python
def mail_search(self, query: str, max_n: int = 30) -> list[dict]:
    """메일 검색 — search_input 입력 + Enter → XHR 후킹 캡처.

    반환: [{id, from, subject, date, unread}]
    """
    HOOK = """
    window.__mailSearchResult = null;
    const origXhrOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(m, u, ...r) {
        this._hookUrl = u;
        return origXhrOpen.apply(this, [m, u, ...r]);
    };
    const origXhrSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(...a) {
        this.addEventListener('load', function() {
            if (this._hookUrl && this._hookUrl.includes('/json/search/')) {
                try {
                    window.__mailSearchResult = JSON.parse(this.responseText);
                } catch(e) {}
            }
        });
        return origXhrSend.apply(this, a);
    };
    """
    if not hasattr(self._page, '_mail_search_hook_added'):
        self._page.add_init_script(HOOK)
        self._page._mail_search_hook_added = True

    # 메일 페이지 진입
    self.go("https://mail.naver.com/v2/folders/0/all")
    time.sleep(3)

    # 검색창 활성화 - 우선 search_area 클릭 (혹은 input 직접 시도)
    try:
        sa = self._page.query_selector('div.gnb_search_area, [class*="search_area"]')
        if sa and sa.is_visible():
            sa.click()
            time.sleep(1)
    except Exception:
        pass

    # 검색 input 찾아서 입력 + Enter
    try:
        search_input = self._page.query_selector('input.search_input')
        if not search_input or not search_input.is_visible():
            # 폴백: placeholder 매칭
            search_input = self._page.query_selector('input[placeholder*="메일 검색"]')
        if search_input and search_input.is_visible():
            search_input.click()
            search_input.fill(query)
            self._page.keyboard.press("Enter")
            time.sleep(4)
    except Exception:
        return []

    # XHR 후킹된 검색 결과 추출
    raw = self._page.evaluate("() => window.__mailSearchResult")
    if not raw:
        return []
    mail_data = raw.get("mailData") or []
    if not isinstance(mail_data, list):
        return []

    result = []
    for m in mail_data[:max_n]:
        from_info = m.get("from") or {}
        result.append({
            "id":      str(m.get("mailSN", "")),
            "from":    from_info.get("name") or from_info.get("email") or "",
            "subject": m.get("subject", ""),
            "date":    m.get("receivedTime", ""),
            "unread":  not bool(m.get("isRead", False)) if "isRead" in m else False,
        })
    return result
```

---

### 🔧 1.3 mybox_list — 2단계 API 호출 (file/get → file/list)

**파일**: `scripts/browser/agent/mybox_mixin.py`

**핵심 발견** (`explore_unresolved_v2.py` 캡처):

1. **루트 폴더 API**: `GET https://api.mybox.naver.com/service/file/get?resourceKey=root`
   - 응답: `{"code":"0", "result":{"resourceKey":"c2t5andzaW58...", "totalFolderCount":49, "totalFileCount":9936}}`
2. **파일 리스트 API**: `GET https://api.mybox.naver.com/service/file/list?resourceKey={resourceKey}`
   - 응답: `{"code":"0", "result":{"resourceKey":"...", "totalCount":134, "list":[{resourceNo, ...}]}}`

**해결 전략**: 페이지 진입 → file/get?resourceKey=root → resourceKey 획득 → file/list?resourceKey={key}

> **주의**: `path` 파라미터는 무시되거나, `resourceKey="root"` 단축 키워드를 사용해야 함. 임의 path 매핑은 별도 API 필요 (현재 미발견).

#### `mybox_list` 메서드 교체 (전체 교체)
```python
def mybox_list(self, path: str = "/") -> list[dict]:
    """파일/폴더 목록 — file/get + file/list 2단계 호출.

    Note: 현재 path는 "/" (root)만 지원. 하위 폴더 진입은 추후 확장.
    반환: [{name, type, size, mtime, resource_key}]
    """
    self.go("https://mybox.naver.com/main/web/my")
    time.sleep(3)

    try:
        data = self._page.evaluate("""async () => {
            // 1단계: root 정보 조회
            const r1 = await fetch('https://api.mybox.naver.com/service/file/get?resourceKey=root', { credentials: 'include' });
            if (!r1.ok) return { error: 'get failed', status: r1.status };
            const j1 = await r1.json();
            const rk = j1?.result?.resourceKey;
            if (!rk) return { error: 'no resourceKey', json: j1 };

            // 2단계: 파일 리스트 조회
            const r2 = await fetch('https://api.mybox.naver.com/service/file/list?resourceKey=' + encodeURIComponent(rk), { credentials: 'include' });
            if (!r2.ok) return { error: 'list failed', status: r2.status };
            return await r2.json();
        }""")
        if not data or data.get("code") != "0":
            return []
        result = data.get("result", {})
        raw = result.get("list", [])
        if not isinstance(raw, list):
            return []
        return [{
            "name":         f.get("resourcePath", "").lstrip("/").split("/")[-1] or f.get("name", ""),
            "type":         f.get("resourceType", "file"),
            "size":         f.get("resourceSize", 0),
            "mtime":        f.get("updateDate", 0),
            "resource_key": f.get("resourceKey", ""),
        } for f in raw]
    except Exception:
        return []
```

> **참고**: 응답의 각 항목은 `resourceNo`, `resourceKey`, `resourcePath`, `resourceType`, `resourceSize`, `createDate`, `updateDate`, `fileType` 등을 포함. 향후 파일명/확장자 분리 등 추가 필드 가능.

---

## 2. 작업 순서 (Haiku 진행 가이드)

직렬, 한 단계씩, 각 단계 완료 후 검증:

### Step 1: calendar_events 교체
- 파일: `calendar_mixin.py`
- 작업: `calendar_events` 메서드 전체 교체 (1.1)
- 검증 포인트: `retScheduleList.returnValue.scheduleList` 경로 정확

### Step 2: mail_search 교체
- 파일: `mail_mixin.py`
- 작업: `mail_search` 메서드 전체 교체 (1.2)
- 셀렉터: `input.search_input` (확인됨)

### Step 3: mybox_list 교체
- 파일: `mybox_mixin.py`
- 작업: `mybox_list` 메서드 전체 교체 (1.3)
- API: file/get → file/list 2단계

### Step 4: 최종 검증
```bash
python scripts/verify_all_methods.py
```
- 목표: **9/9 통과** (또는 8/9, 단 mybox_list가 totalCount > 0으로 반환되면 통과)
- `calendar_today()`는 5월 10일 오늘 일정이 없으면 빈 리스트 정상 (실패 표시되어도 무방)

---

## 3. 절대 금지 사항 (V1 설계서와 동일)

- ❌ 기존 메서드 시그니처 변경 금지
- ❌ `_js()` 헬퍼 제거 금지
- ❌ 새 mixin 파일 생성 금지
- ❌ `BrowserAgent.__enter__` 등 핵심 코드 수정 금지
- ❌ V1에서 작동 중인 메서드 재수정 금지 (mail_folders, mail_unread_count, mybox_quota는 그대로 유지)

---

## 4. 검증된 실측 데이터 (참조용)

### 4.1 캘린더 응답 전체
```json
{
  "result": "success",
  "retTaskList": {"result":"success","returnValue":[]},
  "retTimezoneInfo": {...},
  "retScheduleList": {
    "result": "success",
    "returnValue": {
      "scheduleList": [],     ← 실제 데이터
      "anniversaryList": []
    }
  }
}
```

### 4.2 mail_search 응답
```json
{
  "lastPage": 1, "totalCount": 13, "listCount": 13,
  "body": "네이버", "Result": "OK",
  "mailData": [
    {
      "mailSN": 112236, "folderSN": 0,
      "from": {"name": "네이버", "email": "account_noreply@navercorp.com"},
      "subject": "알림 없이 로그인하는 기기로 등록 되었습니다.",
      "receivedTime": 1778375275,
      "status": 2129920
    }
  ]
}
```

### 4.3 mybox file/get 응답
```json
{
  "code": "0", "message": "success",
  "result": {
    "resourceKey": "c2t5andzaW58MTEwNTQ2NjMyfER8MA",
    "resourcePath": "/", "resourceNo": 110546632,
    "resourceType": "folder", "totalFolderCount": 49, "totalFileCount": 9936
  }
}
```

### 4.4 mybox file/list 응답
```json
{
  "code": "0", "message": "success",
  "result": {
    "resourceKey": "c2t5andzaW58MTEwNTQ2NjMyfER8MA",
    "totalCount": 134,
    "list": [
      {"resourceNo": 110546634, "resourceKey": "...", "resourcePath": "/...", "resourceType": "folder|file", ...}
    ]
  }
}
```

---

## 5. 탐지 결과 파일 (참조)

- V1 탐지: `data/reports/local_agent/explore_unresolved_20260510_115759.json`
- V2 탐지: `data/reports/local_agent/explore_unresolved_v2_20260510_120339.json`
- V1 스크립트: `scripts/explore_unresolved.py`
- V2 스크립트: `scripts/explore_unresolved_v2.py`

---

**작성일**: 2026-05-10
**작성자**: Claude Opus 4.7 (탐지 + 설계)
**작업자**: Claude Haiku 4.5 (구현 + 검증)
**전제**: V1 설계서로 5/9 통과 상태에서 시작. V2 적용 후 9/9 또는 8/9 (calendar_today는 일정 유무 따라 가변) 목표.
