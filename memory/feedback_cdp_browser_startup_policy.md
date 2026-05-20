---
name: feedback_cdp_browser_startup_policy
description: CDP 브라우저는 앱 요청 시점에만 기동. PC 부팅 자동 시작 금지. input() 터미널 대기 금지.
metadata:
  type: feedback
---

CDP 브라우저(Chrome)는 앱 또는 기능이 브라우저를 필요로 하는 시점에만 기동한다.

**Why:** PC 부팅 시 자동 시작은 사용자가 원하지 않아도 항상 Chrome이 켜져 있는 상태가 됨. 상용 제품에서 허용 불가.

**How to apply:**
- `chrome_cdp_daemon.py install` / 시작 프로그램 등록 금지
- 작업 스케줄러(HaehanCdpChrome) 자동 시작 등록 금지
- `_ensure_cdp_daemon()` 패턴 사용 — 앱이 브라우저 필요 시 자동 기동, 불필요 시 미실행
- 로그인 대기는 `monitor_for_login()` 사용 — `input()` / `sys.stdin.isatty()` 패턴 금지
- 비터미널 환경(앱, GUI, API)에서도 동일하게 동작해야 함

[[feedback_no_prefill_command]]
