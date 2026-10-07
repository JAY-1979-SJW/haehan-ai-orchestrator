# 네이버 서비스 확장 설계서 (Haiku 작업 기준)

## 0. 목표
로그인 1회로 네이버 메일/캘린더/MyBox 등을 BrowserAgent에 추가. 카페/블로그와 동일 패턴 재사용.

---

## 1. 토큰 절감 원칙 (Haiku 작업 시 필수)

| 원칙 | 적용 방법 |
|---|---|
| **1 작업 = 1 메서드** | Haiku 한 세션 = Mixin 1개 메서드 1개 (JS 추출 + Python 래퍼) |
| **JS는 _js/로 분리** | Python 문자열 인라인 금지. `_js("extract_xxx.js")` 호출만 |
| **표준 시그니처 강제** | `service_action(target, **kwargs) → dict/list[dict]` |
| **읽기 전용 우선** | `list/read/search` 먼저 → `write/edit/delete` 마지막 |
| **검증은 한 줄** | 매 메서드 끝 `print(len(result), result[:1])` 만 |
| **재시도/예외 최소화** | `try/except: pass` 폴백 1단계만, 중첩 금지 |
| **DOM 셀렉터 ≤ 5개** | 한 메서드에서 시도하는 셀렉터 최대 5개 |

---

## 2. 표준 패턴 (모든 서비스 동일)

### 2.1 파일 구조
```
scripts/browser/agent/
├─ mixins/
│  ├─ blog_mixin.py     [완성]
│  ├─ cafe_mixin.py     [완성]
│  ├─ mail_mixin.py     [신규]
│  ├─ calendar_mixin.py [신규]
│  └─ mybox_mixin.py    [신규]
└─ _js/
   ├─ extract_mail_inbox.js
   ├─ extract_mail_detail.js
   ├─ extract_calendar_events.js
   └─ extract_mybox_files.js
```

### 2.2 BrowserAgent 등록 (1회만)
```python
# agent.py
from .mixins import CafeMixin, BlogMixin, MailMixin, CalendarMixin, MyBoxMixin
class BrowserAgent(CafeMixin, BlogMixin, MailMixin, CalendarMixin, MyBoxMixin):
    ...
```

### 2.3 Mixin 메서드 템플릿
```python
class MailMixin:
    def mail_inbox(self, max_n: int = 30) -> list[dict]:
        """받은 편지함."""
        self.go("https://mail.naver.com/")
        time.sleep(2)
        try:
            result = self._page.evaluate(_js("extract_mail_inbox.js"))
            return result[:max_n]
        except Exception:
            return []
```

### 2.4 LOGIN_MARKERS 추가 (cdp_session_manager.py)
```python
LOGIN_MARKERS = {
    ...,
    "mail.naver.com": ["NID_AUT", "NID_SES"],   # naver.com 쿠키 공유
    "calendar.naver.com": ["NID_AUT", "NID_SES"],
    "mybox.naver.com": ["NID_AUT", "NID_SES"],
}
```

---

## 3. 서비스 우선순위 (Phase별)

### Phase 1 — 메일 (최우선)
| 메서드 | URL/엔드포인트 | 반환 |
|---|---|---|
| `mail_inbox(max_n)` | `mail.naver.com/v2/folders/0/all` | `list[{id, from, subject, date, unread}]` |
| `mail_read(mail_id)` | `mail.naver.com/v2/read/<id>` | `dict{from, to, subject, body, attachments}` |
| `mail_search(query)` | `mail.naver.com/v2/search?q=` | `list[mail summary]` |
| `mail_send(to, subject, body)` | `mail.naver.com/v2/write` | `dict{ok, error}` ⚠ 사용자 승인 필수 |
| `mail_folders()` | DOM 좌측 트리 | `list[{name, count}]` |
| `mail_unread_count()` | 헤더 카운터 | `int` |

### Phase 2 — 캘린더
| 메서드 | 반환 |
|---|---|
| `calendar_events(start, end)` | `list[{id, title, start, end, location}]` |
| `calendar_today()` | `list[event]` |
| `calendar_create(title, start, end)` | `dict{ok}` ⚠ 승인 필수 |

### Phase 3 — MyBox (클라우드)
| 메서드 | 반환 |
|---|---|
| `mybox_list(path)` | `list[{name, type, size, mtime}]` |
| `mybox_quota()` | `dict{used, total}` |
| `mybox_download(path, save_to)` | `dict{ok, path}` |
| `mybox_upload(local_path, dest)` | `dict{ok}` ⚠ 승인 필수 |

### Phase 4 — 보조 (선택)
- 톡톡, 폼, 쇼핑, 페이, 지도, 뉴스 — 필요 시 동일 패턴

---

## 4. 메일 상세 설계 (Haiku 1세션 분량)

### 4.1 작업 순서 (Haiku가 따라 할 1회 절차)
1. **사이트 탐색** — `agent.go("https://mail.naver.com")` → DOM 구조 파악
2. **JS 1개 작성** — `_js/extract_mail_inbox.js` 생성
3. **Python 래퍼** — `mail_mixin.py` 메서드 1개 추가
4. **검증** — `posts = agent.mail_inbox(); print(len(posts), posts[:1])`

### 4.2 JS 추출 (extract_mail_inbox.js 패턴)
```javascript
(function () {
  const mails = [];
  document.querySelectorAll('li[data-mailsn], tr.mail_list').forEach(el => {
    mails.push({
      id: el.dataset.mailsn || el.id || '',
      from: (el.querySelector('.from, .send_user') || {}).innerText || '',
      subject: (el.querySelector('.subject, .mail_title') || {}).innerText || '',
      date: (el.querySelector('.date, .mail_time') || {}).innerText || '',
      unread: el.classList.contains('unread'),
    });
  });
  return mails;
})();
```

### 4.3 셀렉터 폴백 (최대 5개)
```
li[data-mailsn]  → 신형 UI
tr.mail_list     → 구형 UI
.mailListItem    → 모바일 UI
[role="listitem"][data-id]  → ARIA 폴백
a[href*="/read/"]  → 최후 수단
```

### 4.4 모바일 폴백 패턴 (블로그처럼)
PC 추출 0건이면 `m.mail.naver.com`으로 재시도. 동일 JS 적용.

---

## 5. 권한/보안 정책

| 동작 | 권한 |
|---|---|
| 읽기 (inbox/read/search/list) | `AUTO_ALLOWED` |
| 검색/조회 | `AUTO_ALLOWED` |
| 쓰기 (send/create/upload/delete) | `USER_DELEGATED_PERMISSION_REQUIRED` |
| 발송/공개 | `WRITE_INTENT` 감사 이벤트 자동 기록 (L2) |

읽기 메서드는 즉시 실행. 쓰기 메서드는 `browser_prepare_submit.py` 경유.

---

## 6. Haiku 1세션 작업 단위 (예시)

**입력 (사용자 → Haiku):**
> "메일 받은편지함 메서드 추가해"

**Haiku 절차:**
1. `agent.go("https://mail.naver.com")` → 1회 탐색
2. DOM 출력 보고 → 셀렉터 후보 3~5개 식별
3. `_js/extract_mail_inbox.js` 작성 (≤ 30줄)
4. `mail_mixin.py`에 `mail_inbox()` 추가 (≤ 15줄)
5. `agent.mail_inbox()` 검증 → 건수 보고
6. 끝 (다음 메서드는 다음 세션)

**금지:**
- 한 세션에서 여러 메서드 동시 작성
- JS를 Python 문자열에 인라인
- 5개 초과 셀렉터 폴백
- `try/except` 3중 이상 중첩

---

## 7. 검증 체크리스트 (메서드 추가 시)

```
[ ] _js/ 파일 분리됨 (인라인 JS 없음)
[ ] try/except 1단계만
[ ] 반환 타입 표준 (list[dict] / dict)
[ ] DOM 셀렉터 5개 이하
[ ] LOGIN_MARKERS 등록됨 (새 도메인이면)
[ ] BrowserAgent 클래스에 Mixin 등록됨
[ ] 검증 print 1줄
```

---

## 8. 진행 상태 추적

| Phase | Mixin | 메서드 수 | 상태 |
|---|---|---|---|
| Cafe | cafe_mixin.py | 다수 | ✓ 완성 |
| Blog | blog_mixin.py | 39 | ✓ 완성 |
| Mail | mail_mixin.py | 0/6 | ☐ 시작 |
| Calendar | calendar_mixin.py | 0/3 | ☐ |
| MyBox | mybox_mixin.py | 0/4 | ☐ |

---

## 9. 다음 단계
사용자 지시 시 Haiku에 다음 형식으로 전달:
> "메일 mixin Phase 1 시작 — `mail_inbox()` 1개만 작성. 본 설계서 §4.2 패턴 따름."
