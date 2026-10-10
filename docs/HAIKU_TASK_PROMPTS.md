# Haiku 작업 지시문 모음

각 블록을 그대로 복사해서 Haiku 세션에 전달. **1세션 = 1블록 = 1메서드**.

전제: 사용자 네이버 로그인 완료. CDP/BrowserAgent 작동 중. 설계서 = `docs/NAVER_SERVICES_EXPANSION_PLAN.md`.

---

## Phase 0 — Mixin 골격 생성 (1회)

```
scripts/naver/mail/mail_mixin.py 신규 작성.

내용:
- from __future__ import annotations
- import time
- _js() 헬퍼 (blog_mixin.py와 동일 패턴)
- class MailMixin: 빈 클래스 + docstring "네이버 메일 Mixin"

그리고 mixins/__init__.py 에 MailMixin export 추가.
agent.py 에서 BrowserAgent(CafeMixin, BlogMixin, MailMixin) 으로 변경.

cdp_session_manager.py LOGIN_MARKERS 에 추가:
  "mail.naver.com": ["NID_AUT", "NID_SES"]

검증: python -c "from scripts.browser.agent.agent import BrowserAgent; print('ok')"
```

---

## Phase 1.1 — mail_inbox()

```
mail_mixin.py 에 mail_inbox(max_n=30) 메서드 1개만 추가.

설계: NAVER_SERVICES_EXPANSION_PLAN.md §4 그대로.

절차:
1. agent.go("https://mail.naver.com") 직접 실행해서 DOM 구조 파악 (1회만)
2. _js/extract_mail_inbox.js 작성 (≤ 30줄, 셀렉터 폴백 최대 5개)
3. mail_mixin.py 에 메서드 추가:
   def mail_inbox(self, max_n=30) -> list[dict]:
       self.go("https://mail.naver.com/")
       time.sleep(2)
       try:
           return (self._page.evaluate(_js("extract_mail_inbox.js")) or [])[:max_n]
       except Exception:
           return []

검증 (한 줄):
  with BrowserAgent() as a: r = a.mail_inbox(); print(len(r), r[:1])

반환 필드: id, from, subject, date, unread
다른 메서드는 작성 금지. 끝.
```

---

## Phase 1.2 — mail_read(mail_id)

```
mail_mixin.py 에 mail_read(mail_id) 1개만 추가. mail_inbox 다음 단계.

절차:
1. inbox 첫 메일 클릭 → 상세 페이지 URL 패턴 확인 (1회 탐색)
2. _js/extract_mail_detail.js 작성
3. 메서드:
   def mail_read(self, mail_id: str) -> dict:
       self.go(f"https://mail.naver.com/v2/read/{mail_id}")
       time.sleep(2)
       try:
           return self._page.evaluate(_js("extract_mail_detail.js")) or {}
       except Exception:
           return {}

반환 필드: from, to, subject, date, body, attachments(list)
검증: a.mail_read(a.mail_inbox()[0]["id"])
끝.
```

---

## Phase 1.3 — mail_search(query)

```
mail_mixin.py 에 mail_search(query, max_n=30) 1개만 추가.

mail_inbox 와 동일 추출 JS 재사용 가능 여부 확인. 같으면 재사용:
  def mail_search(self, query, max_n=30) -> list[dict]:
      from urllib.parse import quote
      self.go(f"https://mail.naver.com/v2/search?q={quote(query)}")
      time.sleep(2)
      try:
          return (self._page.evaluate(_js("extract_mail_inbox.js")) or [])[:max_n]
      except Exception:
          return []

검증: a.mail_search("test")[:1]
끝.
```

---

## Phase 1.4 — mail_folders() + mail_unread_count()

```
2개 추가 (단순 메서드라 묶음).

_js/extract_mail_folders.js 1개 작성:
  좌측 폴더 트리에서 [{name, count}] 추출.

mail_mixin.py:
  def mail_folders(self) -> list[dict]:
      self.go("https://mail.naver.com/")
      time.sleep(2)
      try: return self._page.evaluate(_js("extract_mail_folders.js")) or []
      except: return []

  def mail_unread_count(self) -> int:
      folders = self.mail_folders()
      for f in folders:
          if "받은" in f.get("name",""): return f.get("count", 0)
      return 0

검증: a.mail_folders(); a.mail_unread_count()
끝.
```

---

## Phase 1.5 — mail_send() ⚠ 사용자 승인 필수

```
mail_mixin.py 에 mail_send(to, subject, body) 1개 추가.
WRITE 동작이므로 browser_prepare_submit.py 패턴 따름.

절차:
1. https://mail.naver.com/v2/write 접속
2. 받는사람/제목/본문 입력 (셀렉터: [name="to"], [name="subject"], 본문 iframe)
3. 발송 버튼은 클릭 안 함 (사용자가 검토)
4. 반환: {ok, draft_url, screenshot_path}

L2 감사 이벤트 "MAIL_WRITE_PREPARED" 기록.
실제 발송은 사용자가 Chrome 창에서 클릭.

검증: r = a.mail_send("test@x.com", "제목", "본문"); print(r)
끝.
```

---

## Phase 2.1 — calendar_events(start, end)

```
mixins/calendar_mixin.py 신규 + Phase 0 패턴 반복.
LOGIN_MARKERS "calendar.naver.com" 추가.

calendar_events(start: str, end: str) -> list[dict]:
- start/end: "YYYY-MM-DD"
- URL: https://calendar.naver.com/#~/month/<YYYYMMDD>
- _js/extract_calendar_events.js 작성
- 반환: [{id, title, start, end, location}]

검증: a.calendar_events("2026-05-01", "2026-05-31")
끝.
```

---

## Phase 2.2 — calendar_today()

```
calendar_mixin.py 에 calendar_today() 1개 추가.

  def calendar_today(self) -> list[dict]:
      from datetime import date
      t = date.today().isoformat()
      return self.calendar_events(t, t)

검증: a.calendar_today()
끝.
```

---

## Phase 2.3 — calendar_create() ⚠ 승인 필수

```
calendar_create(title, start, end) — Phase 1.5 mail_send 와 동일 승인 패턴.
이벤트 폼만 입력하고 사용자가 저장 버튼 클릭.

L2 "CALENDAR_WRITE_PREPARED" 기록.
끝.
```

---

## Phase 3.1 — mybox_list(path="/")

```
mixins/mybox_mixin.py 신규 + Phase 0 패턴.
LOGIN_MARKERS "mybox.naver.com" 추가.

mybox_list(path="/") -> list[dict]:
- URL: https://mybox.naver.com/#/folder?path=<encoded_path>
- _js/extract_mybox_files.js 작성
- 반환: [{name, type("file"|"folder"), size, mtime}]

검증: a.mybox_list("/")
끝.
```

---

## Phase 3.2 — mybox_quota()

```
mybox_mixin.py 에 mybox_quota() 1개 추가.
헤더 영역에서 "X GB / Y GB" 패턴 정규식 추출.

  def mybox_quota(self) -> dict:
      self.go("https://mybox.naver.com/")
      time.sleep(2)
      txt = self._page.inner_text("body")
      import re
      m = re.search(r"([\d.]+)\s*(GB|MB)\s*/\s*([\d.]+)\s*(GB|TB)", txt)
      return {"used": m.group(1)+m.group(2), "total": m.group(3)+m.group(4)} if m else {}

검증: a.mybox_quota()
끝.
```

---

## Phase 3.3 — mybox_download() ⚠ 승인 필수

```
파일 다운로드는 데이터 외부화 위험. 사용자 승인 필수.
- 파일 클릭 → 다운로드 버튼 → 사용자 확인 후 클릭
- L2 "MYBOX_DOWNLOAD" 기록 (path, size, dest)
끝.
```

---

## Phase 3.4 — mybox_upload() ⚠ 승인 필수

```
mail_send 와 동일 승인 패턴.
파일 업로드 폼 작성만 하고 업로드 버튼은 사용자가 클릭.
L2 "MYBOX_UPLOAD_PREPARED" 기록.
끝.
```

---

## 진행 추적용 체크박스

복사해서 사용:
```
[ ] Phase 0 — Mixin 골격
[ ] Phase 1.1 — mail_inbox
[ ] Phase 1.2 — mail_read
[ ] Phase 1.3 — mail_search
[ ] Phase 1.4 — mail_folders + mail_unread_count
[ ] Phase 1.5 — mail_send (승인)
[ ] Phase 2.1 — calendar_events
[ ] Phase 2.2 — calendar_today
[ ] Phase 2.3 — calendar_create (승인)
[ ] Phase 3.1 — mybox_list
[ ] Phase 3.2 — mybox_quota
[ ] Phase 3.3 — mybox_download (승인)
[ ] Phase 3.4 — mybox_upload (승인)
```

---

## 사용 방법

1. `/clear` 로 새 세션 시작
2. `/model` 로 Haiku 4.5 선택
3. 위 블록 1개 통째로 복사 → 입력
4. Haiku 작업 완료 후 보고 받음
5. 다음 블록으로 이동

**1 블록 ≈ Haiku 세션 1회 (~5~15분, 컨텍스트 부담 최소).**
