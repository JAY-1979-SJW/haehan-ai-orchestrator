# 브라우저 자동화 도구 목록

**마지막 업데이트**: 2026-05-11

## 📋 목차
1. [브라우저 기본 도구](#브라우저-기본-도구)
2. [로그인 관련 도구](#로그인-관련-도구)
3. [페이지 탐색 도구](#페이지-탐색-도구)
4. [팝업 처리 도구](#팝업-처리-도구)
5. [데이터 관리 도구](#데이터-관리-도구)
6. [사용 가이드](#사용-가이드)

---

## 🌐 브라우저 기본 도구

### 1. CDP 데몬 (`scripts/browser/cdp/cdp_daemon.py`)
**용도**: Chrome 브라우저 항상 실행 + 자동 재시작

```bash
# 데몬 시작
python scripts/browser/cdp/cdp_daemon.py start

# 상태 확인
python scripts/browser/cdp/cdp_daemon.py status

# 로그 확인
python scripts/browser/cdp/cdp_daemon.py logs

# 정지
python scripts/browser/cdp/cdp_daemon.py stop
```

**특징**:
- ✓ 포트 9222에서 CDP 수신
- ✓ 프로세스 자동 재시작
- ✓ 상태 파일 저장 (data/cdp_daemon_state.json)

---

### 2. CDP 클라이언트 (`scripts/cdp_client.py`)
**용도**: 데몬 크롬에 명령 전달

```bash
# 페이지 이동
python scripts/entry/cdp_cli.py goto <URL>

# 로그인 대기
python scripts/entry/cdp_cli.py wait-login <사이트> [타임아웃초]

# 클릭
python scripts/entry/cdp_cli.py click-button <버튼텍스트>

# 입력
python scripts/entry/cdp_cli.py type-into <셀렉터> <텍스트>

# 저장
python scripts/entry/cdp_cli.py save-session <사이트>

# 자동 로그인
python scripts/entry/cdp_cli.py auto-login <사이트> [URL]

# 탭 상태 확인
python scripts/entry/cdp_cli.py check-login

# 팝업 감지
python scripts/entry/cdp_cli.py detect-popup

# 팝업 닫기
python scripts/entry/cdp_cli.py close-popup

# 페이지 탐색
python scripts/entry/cdp_cli.py explore page|tabs [셀렉터]
```

---

## 🔐 로그인 관련 도구

### 3. 로그인 감지 (`scripts/auth/login_detector.py`)
**용도**: 페이지에서 로그인 자동 감지 + 세션 저장

```python
from scripts.auth.login_detector import monitor_for_login, detect_login_on_current_tab
from scripts.web_connector import get_page

page = get_page()

# 페이지 로드 후 자동 감지
result = monitor_for_login(page, check_interval=1, timeout_s=300)
# {detected, site, url, elapsed_s}

# 현재 로그인 상태 확인
is_logged_in, site = detect_login_on_current_tab(page)
```

**지원 사이트**:
- 🔷 Naver (naver.com)
- 🔵 Google (google.com)
- 💛 Kakao (kakao.com)
- ⚙️ EUM (eum.cw.or.kr)

**특징**:
- ✓ MutationObserver 실시간 감지
- ✓ 1초 간격 체크
- ✓ 자동 세션 저장
- ✓ 감지 시간 2-3초 이내

---

### 4. 현재 탭 로그인 상태 확인 (`scripts/auth/check_login_status.py`)
**용도**: 모든 열려있는 탭의 로그인 상태 스캔

```bash
python scripts/entry/cdp_cli.py check-login
```

**출력**: 표 형식으로 모든 탭의 URL, 사이트, 로그인 여부 표시

---

### 5. 로그인 세션 관리 (`scripts/auth/login_session.py`)
**용도**: 쿠키 기반 로그인 상태 판별 + 확인

```python
from scripts.auth.login_session import is_logged_in, ensure_login
from scripts.web_connector import get_page

page = get_page()

# 로그인 상태 확인
if is_logged_in(page, "naver"):
    print("네이버 로그인됨")

# 로그인 대기 (미로그인 시)
ensure_login(page, "naver")  # 최대 5분 대기
```

---

## 🗺️ 페이지 탐색 도구

### 6. 페이지 스냅샷 (`scripts/explorer/page_snapshot.py`)
**용도**: 페이지 구조 추출 (links, inputs, buttons, forms, headings)

```bash
python scripts/entry/cdp_cli.py explore page [save_dir]
```

**저장 위치**: `data/sitemap/{url_slug}.json`

**포함 정보**:
- 링크 목록 (text, href, target)
- 입력 필드 (tag, type, name, id, placeholder, required)
- 버튼 목록 (text, aria-label, class)
- 양식 (id, action, method)
- 제목 (h1/h2/h3)

---

### 7. 탭 탐색 (`scripts/explorer/tab_explorer.py`)
**용도**: 탭 인터페이스 순회 + 각 패널 내용 추출

```bash
python scripts/entry/cdp_cli.py explore tabs [tab_selector] [panel_selector]
```

**기본 셀렉터**:
- tab_selector: `button.tab_link`
- panel_selector: `.form_cont.tab_cont.on, [role='tabpanel'][aria-hidden='false']`

**저장 위치**: `data/sitemap/{url_slug}_login_tabs.json`

**특징**:
- ✓ 모든 탭 클릭
- ✓ 각 탭의 활성 패널 추출
- ✓ 자동으로 첫 탭으로 복귀
- ✓ 페이지 상태 보존

---

## 🚫 팝업 처리 도구

### 8. 팝업 감지 (`scripts/browser/popup/popup_detector.py`)
**용도**: 모달/다이얼로그/알림 팝업 자동 감지 및 처리

```bash
# 팝업 감지
python scripts/entry/cdp_cli.py detect-popup

# 팝업 닫기
python scripts/entry/cdp_cli.py close-popup
```

```python
from scripts.browser.popup.popup_detector import detect_popup, close_all_popups, handle_page_popups
from scripts.web_connector import get_page

page = get_page()

# 팝업 감지
result = detect_popup(page)
# {detected, popup_count, types, elements}

# 모든 팝업 닫기
result = close_all_popups(page, max_attempts=5)

# 페이지 로드 후 자동 처리
result = handle_page_popups(page)
```

**지원 팝업 유형**:
- 모달 다이얼로그 (div.modal, [role="dialog"])
- 알림 배너
- 광고 팝업
- 기본 alert/confirm

**닫기 우선순위**:
1. 닫기 버튼 (.close, .btn-close)
2. 확인 버튼 (contains "확인" or "OK")
3. ESC 키

---

### 9. 팝업 감시 (`scripts/browser/popup/popup_watcher.py`)
**용도**: MutationObserver로 특정 팝업 감시 + 자동 처리

```bash
# 감시 설치
python scripts/entry/cdp_cli.py popup-install

# 이벤트 폴링
python scripts/entry/cdp_cli.py popup-poll

# 자동 처리
python scripts/entry/cdp_cli.py popup-auto
```

```python
from scripts.browser.popup.popup_watcher import install_watcher, poll_events, auto_handle

# 감시기 설치 (모든 프레임)
result = install_watcher(page)

# 감지된 이벤트 폴링
events = poll_events(page)

# 자동 처리
result = auto_handle(page)
# {handled, skipped, unknown}
```

**감지 대상** (POPUP_MARKERS):
- "작성 중인 글"
- "이어서 작성"
- "임시저장"

---

## 💾 데이터 관리 도구

### 10. 감시 데이터베이스 (`scripts/browser/cdp/cdp_db.py`)
**용도**: 로그인 세션, 메일 발송, 작업 로그 저장 + 조회

```bash
# 세션 목록
python scripts/browser/cdp/cdp_db.py sessions

# 작업 로그
python scripts/browser/cdp/cdp_db.py logs [site] [limit]

# 메일 발송 이력
python scripts/browser/cdp/cdp_db.py mails [site] [limit]

# 요청 이력
python scripts/browser/cdp/cdp_db.py requests [site|summary] [limit]
```

**데이터베이스**: `data/cdp.db`

**테이블**:
- `sessions` - 로그인 세션 (site_name, logged_in, last_login)
- `task_logs` - 작업 이력 (site, task, status, duration, error)
- `mail_sends` - 메일 발송 (recipient, subject, status, error)
- `site_requests` - 사용자 요청

---

## 📝 로깅 도구

### 11. 로거 (`scripts/common/logger.py`)
**용도**: 모든 활동을 파일 + 콘솔에 기록

**로그 파일**: `data/logs/app.log` (96KB, RotatingFileHandler)

**모듈별 로그 마커**:
- `[login-detector]` - 로그인 감지
- `[popup-detector]` - 팝업 처리
- `[explorer]` - 페이지 탐색
- `[popup_watcher]` - 팝업 감시
- `[check-login]` - 탭 상태 확인

```bash
# 실시간 로그 보기
tail -f data/logs/app.log

# 특정 모듈 로그만
tail -f data/logs/app.log | grep "\[login-detector\]"
```

---

## 📚 사용 가이드

### 전형적인 작업 흐름

#### 1️⃣ 사이트 로그인 + 세션 저장

```bash
# 방법 1: 자동 로그인 감지
python scripts/entry/cdp_cli.py auto-login eum.cw.or.kr https://eum.cw.or.kr/main

# 방법 2: 수동 + 자동 저장
python scripts/entry/cdp_cli.py goto https://eum.cw.or.kr/main
# → 브라우저에서 로그인
python scripts/entry/cdp_cli.py save-session eum.cw.or.kr
```

#### 2️⃣ 현재 상태 확인

```bash
# 모든 탭의 로그인 상태
python scripts/entry/cdp_cli.py check-login

# 특정 팝업 감지
python scripts/entry/cdp_cli.py detect-popup

# DB에서 세션 조회
python scripts/browser/cdp/cdp_db.py sessions
```

#### 3️⃣ 페이지 탐색 및 구조 분석

```bash
# 단일 페이지 스냅샷
python scripts/entry/cdp_cli.py explore page

# 탭 인터페이스 탐색
python scripts/entry/cdp_cli.py explore tabs

# JSON 결과 확인
ls -lh data/sitemap/
cat data/sitemap/eum.cw.or.kr*.json | jq '.'
```

#### 4️⃣ 메일 작성 + 발송

```bash
# 메일 작성
python scripts/entry/cdp_cli.py naver mail compose skyjwshin@kakao.com "제목" "본문"

# 메일 발송 (별도 승인)
python scripts/entry/cdp_cli.py naver mail send

# 발송 이력 확인
python scripts/browser/cdp/cdp_db.py mails
```

---

## 🔧 도구 개선 계획

### 현재 상태
- ✅ 브라우저 기본 자동화
- ✅ 로그인 자동 감지
- ✅ 팝업 자동 처리
- ✅ 페이지 구조 탐색
- ✅ 세션 관리 + 데이터 저장

### 필요한 개선사항
- [ ] 동적 페이지 로드 감시 (JavaScript 렌더링 완료 대기)
- [ ] AJAX/XHR 요청 감시
- [ ] 폼 자동 채우기 (지능형)
- [ ] 테이블 데이터 자동 추출
- [ ] 페이지 메뉴 자동 매핑
- [ ] 에러 자동 복구
- [ ] 성능 프로파일링 도구

---

## 🚀 상시 사용 명령어

```bash
# 빠른 참고용
alias cdp-status='python scripts/browser/cdp/cdp_daemon.py status'
alias cdp-logs='tail -f data/logs/app.log'
alias cdp-check='python scripts/entry/cdp_cli.py check-login'
alias cdp-db='python scripts/browser/cdp/cdp_db.py'

# 예제
cdp-status
cdp-logs
cdp-check
cdp-db sessions
```

---

**마지막 업데이트**: 2026-05-11 17:10  
**개발 커밋**: fb4710a (팝업 자동 감지 및 처리 기능)
