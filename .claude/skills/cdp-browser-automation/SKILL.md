---
name: cdp-browser-automation
description: 이 프로젝트에서 브라우저 자동화가 필요할 때(사이트 접속, IP 등록, 로그인 세션 조작, 폼 입력 등) 사용하는 상시 CDP 실행 방식. "CDP 연결해", "브라우저로 접속해", "사이트에서 ~해줘" 같은 요청에 claude-in-chrome 확장 대신 이 방식을 우선 사용한다.
---

# CDP 브라우저 자동화 (상시 방식)

이 프로젝트는 `claude-in-chrome` MCP 확장이 아니라 **`scripts/browser/cdp/cdp_force_start.py` + `scripts/browser/cdp/cdp_helper.py`** 조합으로
Chrome을 CDP(포트 9222)로 직접 띄우고 조작한다. 확장 연결이 안 될 때 헤매지 말고 바로 이 경로를 쓴다.

## 1. CDP 확인/시작

```bash
python scripts/browser/cdp/cdp_force_start.py status   # 이미 떠 있는지 확인
python scripts/browser/cdp/cdp_force_start.py start [URL]   # 안 떠 있으면 시작 (선택적으로 시작 URL 지정)
python scripts/browser/cdp/cdp_force_start.py stop     # 종료 (요청 없이 임의로 하지 않음)
```

- 프로필: `HAEHAN_CDP_PROFILE` 환경변수(없으면 `data/cdp_profile/ai_chrome`) — 로그인 세션이 여기 유지된다.
- **로그인 세션 보존 원칙**: 쿠키 삭제, 로그아웃 URL 접속 금지 (CLAUDE.md `로그인 세션 보존` 참조).
- `status`가 "✓ 응답 중"이면 이미 실행 중이므로 재시작하지 않는다.

## 2. Python으로 조작

```python
import sys
sys.path.insert(0, r"C:\work\01. haehan-ai-orchestrator")
from scripts.browser.cdp.cdp_helper import CDP

cdp = CDP(port=9222)
cdp.navigate("https://example.com")
cdp.shot("label")              # data/browser_screenshot.png 로 저장 → Read 도구로 확인
result = cdp.js("document.title")   # 페이지 내 JS 실행
cdp.dom_enable()
node_ids = cdp.query_node_ids("input[type=file]")
cdp.close()
```

- 스크린샷은 `cdp.shot()` 저장 후 Read 도구로 열어 화면을 직접 눈으로 확인하고 다음 액션 결정.
- 클릭/타이핑은 `cdp.send("Input.dispatchMouseEvent", ...)` / `"Input.dispatchKeyEvent"` 등 CDP 프로토콜 직접 호출.
- 반복 패턴(로그인 감지, 폼 입력 등)은 `scripts/auth/login_sites.py`, `scripts/naver/mail/read/cdp.py` 등 기존 구현 먼저 확인 후 재사용.
- **`CDP(port=9222)`는 항상 Chrome의 `/json` 목록에서 첫 번째 "page" 탭에 붙는다** — 여러
  탭이 열려있는 세션(이 프로젝트는 거의 항상 그렇다)에서 "이미 열려있는 특정 탭"을 골라
  잡을 수 없다. 그래서 이 헬퍼는 **연결 직후 바로 `cdp.navigate(url)`로 원하는 URL로
  덮어써서 쓰는 단일 흐름 자동화용**이다. 이미 열려있는 특정 탭(예: OAuth 진행 중인 탭)을
  이어서 조작해야 한다면 이 헬퍼로는 안 되고 Playwright `connect_over_cdp` +
  `ctx.pages`로 URL 매칭해서 찾아야 한다(이때는 위 4번 규칙을 따른다).
- **`cdp.navigate()` 직후 `cdp.js()`로 상태를 바로 읽으면 빈 값이 나올 수 있다**
  (2026-08-21 실측: `navigate(wait=2)` 직후 `document.title`이 빈 문자열, 2초 더 기다린 뒤
  재조회하니 정상). 내비게이션 직후 값이 비어 있으면 성급하게 실패로 판단하지 말고
  1~2초 더 기다렸다가 다시 확인한다.

## 3. 언제 이 방식을 쓰는가

- 사용자가 "CDP 연결해", "브라우저로 접속", "사이트에서 IP 등록해줘" 등 브라우저 작업을 요청하면 **기본값**으로 이 방식을 쓴다.
- `mcp__claude-in-chrome__*` 도구는 확장 설치·로그인이 필요하고 이 환경에 연결되어 있지 않다 — 먼저 시도해서 시간 낭비하지 않는다.
- 새 사이트 자동화 전에는 CLAUDE.md의 `capability_check.py` 의무를 먼저 따른다 (기존 구현/벤더 API 우선, CDP는 없을 때만).

## 4. Playwright(`connect_over_cdp`)를 쓸 때 반드시 지킬 것 (2026-08-21, 반복 오류 원인 확정)

인스타/네이버클립/유튜브 3채널 발행 작업에서 같은 실수를 여러 번 반복했다. 원인은
`scripts/browser/cdp/cdp_helper.py`(raw CDP) 대신 **Playwright `connect_over_cdp`를 매 스크립트 실행마다 새로
붙이고 `ctx.new_page()`로 새 탭을 판 것**이었다. 반드시 아래 규칙을 지킨다.

- **탭 하나를 여러 Bash 호출에 걸쳐 재사용하지 마라.** `ctx.new_page()`로 만든 탭은 그 파이썬
  프로세스가 끝나면(스크립트 종료) 사라지는 것처럼 보인다(실제로는 CDP 세션 종료로 정리됨).
  "탭A에서 로그인/OAuth 진행 중 → 다음 Bash 호출에서 이어서" 같은 흐름은 **절대 안 된다.**
  한 번에 끝나는 흐름(navigate → click → 다음 click → screenshot)은 **하나의 스크립트 안에서
  전부 처리**한다. 여러 단계가 필요하면 매번 `ctx.pages`로 기존 탭을 다시 찾아 재사용하되,
  중간에 사용자 입력을 기다려야 하는 단계(OAuth 동의, 캡차 등)에서는 **그 탭을 만든 스크립트를
  끝내지 말고 그 탭에서 계속 폴링**하거나, 최소한 탭을 `close()` 하지 않는다.
- **`page.close()`를 습관적으로 넣지 마라.** 특히 OAuth/로그인처럼 사용자 입력을 기다려야 하는
  페이지는 스크린샷 찍고 바로 `close()`하면 그 흐름 자체가 끊긴다. 완전히 끝난 게 확실한
  탭만 정리한다.
- **`page.screenshot()`이 "waiting for fonts to load"로 자주 멈춘다** (특히 YouTube, Instagram
  같은 무거운 SPA). 상태 확인은 스크린샷 대신 `page.inner_text('body')` 또는
  `page.evaluate(...)`로 먼저 시도하고, 꼭 스크린샷이 필요하면 timeout을 넉넉히 잡거나
  실패를 각오하고 재시도한다.
- **커스텀 웹컴포넌트(shadow DOM) 입력창은 Playwright `locator('input').fill()`로 못 잡을 때가
  많다** (예: YouTube 채널 생성 모달의 이름/핸들 입력창). 좌표 클릭도 신뢰도가 낮다.
  이런 경우 억지로 자동화 시도를 반복하지 말고, **딱 그 입력 단계만 사용자에게 직접
  입력해달라고 요청**하고 나머지(발행, 파일 업로드 등)는 계속 자동으로 진행한다.
- **OAuth 콜백 URL이 403을 반환해도 당황하지 마라.** `code=` 쿼리 파라미터가 URL에 이미
  있으면 그걸로 충분하다 — `page.url`에서 직접 추출해 `exchange_code()`에 넘기면 된다.
  redirect_uri는 반드시 client_secret.json에 **등록된 것과 정확히 일치**해야 하며
  (`.env`의 `YOUTUBE_OAUTH_REDIRECT_URI` 로드 안 하면 기본값이 localhost로 빠져 mismatch
  에러가 남 — `load_dotenv()` 필수), 로컬 리다이렉트가 등록 안 돼 있으면 프로덕션 콜백
  URL을 그대로 써야 한다.
- **네이버 클립 업로드**: 새 영상을 올릴 때마다 `/web/upload` → `/web/draft/{id}`로 URL이
  바뀌는데, **카테고리(1차/2차) 드롭다운은 이전 드래프트에서 선택했던 값이 유지되지 않는다.**
  "리빙, 홈 > 인테리어, DIY" 같은 칩이 화면에 남아 있어도 실제 폼 상태는 비어 있을 수
  있으니, `등록` 클릭 후 "카테고리를 선택해주세요" 토스트가 뜨면 카테고리를 다시 선택하고
  재시도한다.
- **모바일 뷰포트 에뮬레이션으로 우회되지 않는 제한도 있다.** 인스타그램 프로필 "웹사이트"
  필드는 데스크톱 웹은 물론 `Emulation.setDeviceMetricsOverride`로 모바일 UA/뷰포트를
  흉내내도 여전히 "모바일 앱에서만 가능"으로 막힌다 — 서버 사이드 게이트라 뷰포트 트릭이
  안 통한다. 이런 경우 재시도하지 말고 사용자에게 앱에서 직접 하도록 안내한다.
