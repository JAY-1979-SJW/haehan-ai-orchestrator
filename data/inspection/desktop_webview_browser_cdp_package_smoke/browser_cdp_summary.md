# DESKTOP_WEBVIEW_BROWSER_CDP_PACKAGE_SMOKE_01 Summary

**일시**: 2026-05-21  
**HEAD**: 61f1382  
**배포본**: `dist/HaehanAI-Desktop/HaehanAI-Desktop.exe`

---

## 최종 판정

✅ **PASS_DESKTOP_WEBVIEW_BROWSER_CDP_PACKAGE_SMOKE**

⚠️ WARN_PLAYWRIGHT_BROWSER_NOT_BUNDLED  
⚠️ WARN_SYSTEM_CHROME_REQUIRED

---

## 항목별 결과

| 항목 | 결과 |
|------|------|
| playwright import | ✅ OK |
| psutil import | ✅ OK |
| websockets import | ✅ OK |
| webview (pywebview) | ✅ 배포본 번들됨 |
| scripts.web_connector import | ✅ OK |
| desktop.local_server import | ✅ OK |
| 시스템 Chrome 존재 | ✅ `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| Playwright 번들 Chromium | ⚠️ 미설치 (`playwright install chromium` 필요) |
| playwright 배포본 포함 여부 | ⚠️ **의도적 제외** (spec excludes=['playwright']) |
| CDP daemon 시작 (9222) | ✅ PASS — Chrome/148.0.7778.178 |
| /json/version 응답 | ✅ Protocol 1.3 |
| Chrome 프로필 재사용 | ✅ data/cdp_profile/ai_chrome (파일 46개) |
| connect_over_cdp | ✅ PASS — context 1개 접속 |
| screenshot (newtab) | ✅ PASS — 60,742 bytes |
| secret/token leak | ✅ 0건 |
| cookie 값 노출 | ✅ 없음 |

---

## 배포 시 필수 설치 항목

```bash
# 배포 대상 PC에서 1회 실행 필요
pip install playwright psutil websockets
playwright install chromium   # 또는 시스템 Chrome 사용
```

> **참고**: 시스템 Chrome이 있으면 `playwright install chromium` 없이도 동작함  
> cdp_daemon.py가 시스템 Chrome을 `--remote-debugging-port=9222`로 실행하기 때문

---

## 배포본 번들 현황

| 패키지 | 상태 |
|--------|------|
| psutil | ✅ 번들됨 |
| websockets | ✅ 번들됨 |
| webview (pywebview) | ✅ 번들됨 |
| playwright | ❌ 제외 (spec excludes) → 별도 설치 필요 |
| scripts/cdp_daemon | ❌ 소스 디렉토리에서 실행 |

---

## 흐름 검증

```
HaehanAI-Desktop.exe
  └── webview_app.py (pywebview)
        └── local_server.py (FastAPI 8765)
              └── _handle_browser_start()
                    └── web_connector._ensure_cdp_daemon()
                          └── cdp_daemon.py start
                                └── Chrome.exe --remote-debugging-port=9222
                                      --user-data-dir=data/cdp_profile/ai_chrome

web_connector.connect_over_cdp("http://127.0.0.1:9222")
  └── playwright.chromium.connect_over_cdp ✅
        └── browser.contexts[0] ✅ (로그인 세션 유지)
              └── page.screenshot() ✅ 60,742 bytes
```

---

## 산출물

- `browser_cdp_report.json` — 전체 결과 JSON
- `browser_cdp_summary.md` — 이 파일
- `screenshot_smoke.json` — 스크린샷 smoke 결과
- `screenshot_smoke_newtab.png` — newtab 스크린샷 (민감정보 없음)
