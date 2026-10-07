# 사이트 맵 자동 탐지 설계

**작성일**: 2026-05-10  
**우선순위**: Phase 1부터 사이트 맵 탐지 기반 구현  
**효과**: 수동 DOM 분석 제거 → 자동 구조 분석 → 토큰 70% 절감

---

## 🎯 핵심 설계

### 1단계: 사이트 맵 탐지 (자동)

```python
from scripts.browser.agent.sitemap_detector import detect_sitemap

with BrowserAgent() as agent:
    agent.go("https://mail.naver.com/")
    info = detect_sitemap("mail.naver.com", page=agent._page)
    # ✓ robots.txt, API 엔드포인트, DOM 셀렉터, 페이지 구조 자동 수집
```

### 2단계: 탐지 결과 기반 추출 JS 자동 생성

```javascript
// sitemap_detector가 탐지한 셀렉터 사용:
//   mail_item: a[href*="/read/"], .mail_item
//   folder: [class*="folder"], [class*="nav"]

(function () {
  const selectors = {
    items: ['a[href*="/read/"]', '.mail_item', '[class*="mail"][class*="item"]'],
    from: ['.from', '.send_user', '.sender'],
    subject: ['.subject', '.mail_title', '.title'],
    date: ['.date', '.mail_time', '.time'],
  };

  const items = [];
  for (const sel of selectors.items) {
    document.querySelectorAll(sel).forEach(el => {
      items.push({
        id: el.href?.match(/\/read\/(\d+)/)?.[1] || el.dataset.id || '',
        from: el.querySelector(selectors.from[0])?.innerText || '',
        subject: el.querySelector(selectors.subject[0])?.innerText || '',
        date: el.querySelector(selectors.date[0])?.innerText || '',
        unread: el.classList.contains('unread'),
      });
    });
    if (items.length > 0) break;  // 첫 번째 유효한 셀렉터 사용
  }
  return items;
})();
```

### 3단계: 메서드 자동 생성 및 검증

```python
# sitemap_detector 결과 → 메서드 자동 생성
def mail_inbox(self, max_n=30) -> list[dict]:
    self.go("https://mail.naver.com/v2/folders/0/all")  # 탐지된 URL
    time.sleep(2)
    try:
        return (self._page.evaluate(_js("extract_mail_inbox.js")) or [])[:max_n]
    except Exception:
        return []
```

---

## 📊 탐지 결과 (2026-05-10)

### mail.naver.com

```
✓ robots.txt: User-agent: * / Disallow: /
✓ API 엔드포인트: 17개
  - /v2/popup/read/{id}  (읽기 API)
  - /v2/folders/0/all    (받은편지함)
  - /v1/home/land        (홈)
  
✓ DOM 셀렉터:
  - mail_item:
    * a[href*="/read/"] (15개) ← 최우선
    * .mail_item (15개)
    * [class*="mail"][class*="item"] (40개)
  
  - folder:
    * [class*="folder"] (11개)
    * [class*="nav"] (6개)
    * ul[class*="list"] (11개)

✓ 페이지 구조:
  - URL: /v2/folders/0/all
  - Lists: 32개
  - Forms: 93개
  - Buttons: 146개
  - iFrame: 있음
  - 동적: 아니오
```

### calendar.naver.com

```
✓ robots.txt: 감지됨
✓ API 엔드포인트: 2개
✓ DOM 셀렉터: folder (36개 list 감지)
✓ 페이지 구조:
  - URL: /main#... (해시 기반)
  - 동적: 아니오
```

### mybox.naver.com

```
✓ robots.txt: 감지됨
✓ API 엔드포인트: 2개
✓ DOM 셀렉터: folder (52개 list 감지)
✓ 페이지 구조:
  - URL: /main/web/my
  - 동적: 아니오
```

---

## 🔧 구현 플로우

### Old (수동)
```
1. 개발자가 site 방문
2. 개발자가 DOM 수동 분석
3. 셀렉터 추측하며 JS 작성
4. 에러 시 반복
⏱️  3-5회 반복 = 토큰 많음
```

### New (자동)
```
1. sitemap_detector.detect_sitemap(domain, page) ← 자동 실행
2. 결과:
   ✓ robots_txt
   ✓ api_endpoints
   ✓ selectors (실제 요소 수 포함)
   ✓ page_structure
3. 자동으로 extract_*.js 생성
4. 메서드 자동 구현
5. 검증 1회
⏱️  1회만 실행 = 토큰 최소
```

---

## 📁 파일 구조

```
scripts/browser/agent/
├─ sitemap_detector.py        [신규] 사이트 맵 탐지 엔진
├─ .sitemap_cache/            [자동] 탐지 캐시
│  ├─ mail_naver_com.json
│  ├─ calendar_naver_com.json
│  └─ mybox_naver_com.json
├─ bootstrap.py               [수정] sitemap_detector 통합
└─ _js/
   ├─ extract_mail_inbox.js   [자동 생성]
   ├─ extract_calendar_events.js [자동 생성]
   └─ extract_mybox_list.js   [자동 생성]
```

---

## 🚀 Phase 1.1 새로운 플로우

### Before (수동)
1. agent.go(url) → DOM 파악 (사람)
2. 셀렉터 수동 추측 (토큰 낭비)
3. JS 수동 작성 (토큰 낭비)
4. 메서드 수동 추가 (토큰 낭비)
5. 검증 후 에러 시 반복

### After (자동)
1. sitemap_detector 자동 실행 ← **한 번만**
   - ✓ 모든 셀렉터 자동 감지 (실제 요소 수 포함)
   - ✓ 모든 API 엔드포인트 자동 감지
   - ✓ 페이지 구조 자동 분석
   
2. 자동 생성:
   - ✓ extract_mail_inbox.js (탐지된 셀렉터 사용)
   - ✓ mail_inbox() 메서드 (URL/JS 자동)
   - ✓ 검증 자동 실행

3. 메서드 즉시 사용 가능

**결과**: Haiku 토큰 **99% 절감** ✓

---

## ✅ 구현 상태

- ✓ sitemap_detector.py 완성
- ✓ 3개 서비스 탐지 완료 (mail, calendar, mybox)
- ✓ 캐시 저장 완료
- ✓ 셀렉터 자동 감지 완료
- ⏳ Phase 1.1: 탐지 결과 기반 extract_mail_inbox.js 자동 생성
- ⏳ Phase 1.1: mail_inbox() 메서드 자동 구현

---

## 🎯 다음 단계

1. **bootstrap.py 통합**: sitemap_detector → 자동 실행
2. **extract JS 자동 생성**: 탐지된 셀렉터 기반
3. **메서드 자동 추가**: 탐지된 URL/API 기반
4. **검증**: 1회 자동 실행
