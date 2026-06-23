"""Google 계정 해한AI 권한 삭제 후 YouTube OAuth 재인가."""

import json
import os
import sys
import time

sys.path.insert(0, ".")
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow

from ai_orchestrator.local_agent.browser.agent import BrowserAgent

load_dotenv()

agent = BrowserAgent()
agent.connect()
page = agent._page

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

# OAuth 재인가 시작
secrets_file = Path(os.getenv("YOUTUBE_CLIENT_SECRETS_FILE"))
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

captured = []


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
            except Exception as e:
                print(f"  체크 오류: {e}")
        time.sleep(1)
        for btn in page.locator("button").all():
            try:
                t = btn.inner_text().strip()
                if "계속" in t:
                    btn.click()
                    print("  → 계속 클릭")
                    break
            except Exception:
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

    r = req_mod.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": creds.token})
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
    token_file = Path(os.getenv("YOUTUBE_OAUTH_TOKEN_FILE"))
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
