"""Google 계정 해한AI 권한 삭제 후 YouTube OAuth 재인가.

비가역 작업(Google 권한 철회)이므로 기본은 dry-run 이다.
실제 실행은 ``python scripts/archive/one_off/temp_oauth_revoke.py --execute`` 로만 한다.
필수 환경변수(YOUTUBE_CLIENT_SECRETS_FILE, YOUTUBE_OAUTH_TOKEN_FILE)는
철회 전에 검증하며 하나라도 없으면 아무 것도 하지 않고 오류 종료한다.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

REQUIRED_ENV = ("YOUTUBE_CLIENT_SECRETS_FILE", "YOUTUBE_OAUTH_TOKEN_FILE")


def _load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv()


def _make_agent() -> Any:
    from scripts.browser.agent.agent import BrowserAgent

    agent = BrowserAgent()
    agent.connect()
    return agent


def _revoke_permissions(page: Any) -> None:
    # 해한AI 권한 삭제 페이지
    page.goto("https://myaccount.google.com/connections/overview/AcbYNTdqkQbDmr4kr37bklGx6gPcjC")
    time.sleep(3)

    # "모두 삭제" 버튼 — JS로 찾기
    js_click = """() => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
      let node;
      while ((node = walker.nextNode())) {
        if (node.tagName === 'BUTTON' || node.role === 'button') {
          const t = (node.innerText || node.textContent || '').trim();
          if (t.includes('모두 삭제') || t.includes('Remove all')) {
            node.click();
            return 'clicked: ' + t;
          }
        }
      }
      // aria-label 검색
      const btns = document.querySelectorAll('[aria-label]');
      for (const b of btns) {
        const lbl = b.getAttribute('aria-label');
        if (lbl && (lbl.includes('삭제') || lbl.includes('Remove'))) {
          b.click();
          return 'aria clicked: ' + lbl;
        }
      }
      return 'not found';
    }"""

    result = page.evaluate(js_click)
    print("삭제 버튼:", result)
    time.sleep(2)

    # 확인 다이얼로그
    for _ in range(5):
        dialogs = page.locator("[role=dialog]").all()
        if dialogs:
            print("다이얼로그 발견")
            confirm = page.locator("[role=dialog] button").all()
            for cb in confirm:
                t = (cb.inner_text() or "").strip()
                print("  dialog 버튼:", t)
                if "확인" in t or "삭제" in t or "OK" in t or "Remove" in t:
                    cb.click()
                    print("  → 클릭")
                    break
            break
        time.sleep(1)

    time.sleep(2)
    print("삭제 후 URL:", page.url[:80])


def _reauthorize(page: Any, secrets_file: Path, token_file: Path) -> None:  # noqa: C901, PLR0912, PLR0915 - 1회성 스크립트: 기존 모듈 최상위 절차를 동작 변경 없이 함수로 옮긴 것
    from google_auth_oauthlib.flow import Flow

    SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/userinfo.email",
        "openid",
    ]
    REDIRECT = "https://haehan-ai.kr/orchestrator/api/v1/oauth/youtube/callback"
    flow = Flow.from_client_secrets_file(str(secrets_file), scopes=SCOPES, redirect_uri=REDIRECT)
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")

    captured: list[Any] = []

    def on_request(req):
        if "oauth/youtube/callback" in req.url and "code=" in req.url:
            captured.append(req.url)

    page.on("request", on_request)
    page.goto(auth_url)

    for step in range(25):
        time.sleep(2)
        if captured:
            break
        url = page.url
        url_params = parse_qs(urlparse(url).query)
        if "code" in url_params:
            captured.append(url)
            break

        accounts = page.locator("[data-email]").all()
        if accounts:
            accounts[0].click()
            print(f"[{step}] 계정 클릭")
            continue

        if "consentsummary" in url:
            print(f"[{step}] consentsummary 화면")
            page.screenshot(path="data/consent_screen.png", full_page=True)
            cbs = page.locator("input[type=checkbox]").all()
            print(f"  체크박스 {len(cbs)}개")
            for cb in cbs:
                try:
                    checked = cb.is_checked()
                    print(f"  체크박스 checked={checked}")
                    if not checked:
                        cb.click()
                        time.sleep(0.5)
                        print(f"  → 체크 완료, 이제={cb.is_checked()}")
                except Exception as e:  # noqa: BLE001 - 1회성 수동 유지보수 스크립트(YouTube OAuth 재인가) — except는 동의화면 체크박스 상태확인·계속 버튼 클릭 UI 상호작용 실패만 흡수(print 또는 pass 후 계속), 권한삭제·토큰교환 등 실제 보안 동작은 except 밖에서 수행되며 except가 그 판정을 바꾸지 않음
                    print(f"  체크 오류: {e}")
            time.sleep(1)
            for btn in page.locator("button").all():
                try:
                    t = btn.inner_text().strip()
                    if "계속" in t:
                        btn.click()
                        print("  → 계속 클릭")
                        break
                except Exception:  # noqa: BLE001 - 1회성 수동 유지보수 스크립트(YouTube OAuth 재인가) — except는 동의화면 체크박스 상태확인·계속 버튼 클릭 UI 상호작용 실패만 흡수(print 또는 pass 후 계속), 권한삭제·토큰교환 등 실제 보안 동작은 except 밖에서 수행되며 except가 그 판정을 바꾸지 않음
                    pass
            continue

        btns = page.locator('button:has-text("계속")').all()
        if btns:
            btns[-1].click()
            print(f"[{step}] 계속: {url[:50]}")

    print("최종 URL:", page.url[:120])

    if captured:
        cb_url = captured[0]
        print("콜백:", cb_url[:100])
        flow.fetch_token(authorization_response=cb_url)
        creds = flow.credentials

        import requests as req_mod

        r = req_mod.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": creds.token}, timeout=10)
        info = r.json()
        print("실제 스코프:", info.get("scope", ""))

        token_data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": info.get("scope", "").split(),
        }
        token_file.write_text(json.dumps(token_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("✅ 토큰 저장:", token_file)

        from googleapiclient.discovery import build

        youtube = build("youtube", "v3", credentials=creds)
        resp = youtube.channels().list(part="snippet,statistics", mine=True).execute()
        ch = resp["items"][0]
        print(f"✅ 채널: {ch['snippet']['title']}")
        print(f"✅ 동영상: {ch['statistics'].get('videoCount', 0)}개")
    else:
        print("❌ 콜백 미캡처, 최종 URL:", page.url[:100])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true", help="실제로 권한 철회·토큰 재발급 실행(기본은 dry-run)")
    args = ap.parse_args(argv)

    _load_env()
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]

    if not args.execute:
        print("[dry-run] --execute 가 없어 아무 것도 실행하지 않습니다.")
        print(
            "[dry-run] 실행 시 순서: 환경변수 검증 -> 브라우저 연결 -> Google 계정 연결 권한 '모두 삭제' -> YouTube OAuth 재인가 -> 토큰 파일 저장"
        )
        missing_set = set(missing)
        for k in REQUIRED_ENV:
            print(f"[dry-run] 환경변수 {k}: {'설정됨' if k not in missing_set else '미설정'}")
        return 0

    if missing:
        print(f"오류: 필수 환경변수 미설정({', '.join(missing)}) - 권한 철회 전에 중단합니다.", file=sys.stderr)
        return 2
    secrets_file = Path(os.environ[REQUIRED_ENV[0]])
    token_file = Path(os.environ[REQUIRED_ENV[1]])
    if not secrets_file.is_file():
        print("오류: YOUTUBE_CLIENT_SECRETS_FILE 경로에 파일이 없습니다 - 권한 철회 전에 중단합니다.", file=sys.stderr)
        return 2

    sys.path.insert(0, ".")
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

    agent = _make_agent()
    page = agent.page
    _revoke_permissions(page)
    _reauthorize(page, secrets_file, token_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
