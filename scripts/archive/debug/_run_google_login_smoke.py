"""Live Google login smoke — production domain only.
No secret/token/cookie value output. Observe-only for Google auth screen.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright

APP_URL = "https://attendance.haehan-ai.kr"
EXPECTED_REDIRECT_URI = f"{APP_URL}/api/auth/callback/google"

result: dict = {
    "login_page_reached": False,
    "google_button_found": False,
    "google_button_clicked": False,
    "accounts_google_reached": False,
    "redirect_uri_correct": False,
    "redirect_uri_observed": "",
    "consent_or_account_screen": False,
    "callback_reached": False,
    "complete_reached": False,
    "login_success": False,
    "final_url": "",
    "session_cookie_present": False,
    "error_message": "",
    "raw_secret_printed": False,
}


def cookie_present(ctx, names: list) -> bool:
    try:
        cookies = ctx.cookies()
        return any(c["name"] in names for c in cookies)
    except Exception:
        return False


try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()

        # 1. Login page
        try:
            page.goto(f"{APP_URL}/login", wait_until="networkidle", timeout=20000)
        except Exception:
            page.goto(f"{APP_URL}/login", wait_until="domcontentloaded", timeout=20000)
        page.bring_to_front()
        time.sleep(3)  # React hydration wait
        result["login_page_reached"] = "/login" in page.url or page.url.rstrip("/") == APP_URL

        # 2. Find Google button
        google_btn = None
        for selector in [
            "[data-testid='google-login-btn']",
            "button:has-text('Google')",
            "button:has-text('구글')",
            "[class*='google']",
        ]:
            try:
                el = page.locator(selector)
                if el.count() > 0:
                    google_btn = el.first
                    break
            except Exception:
                pass

        result["google_button_found"] = google_btn is not None

        # 3. Capture redirect_uri from network before clicking
        _observed = [""]

        def on_request(req):
            if "accounts.google.com" in req.url and "redirect_uri" in req.url:
                import urllib.parse as up
                try:
                    qs = up.parse_qs(up.urlparse(req.url).query)
                    uri = qs.get("redirect_uri", [""])[0]
                    if uri:
                        _observed[0] = uri
                except Exception:
                    pass

        page.on("request", on_request)

        # 4. Click Google button
        if google_btn:
            try:
                google_btn.scroll_into_view_if_needed()
                time.sleep(0.5)
                with page.expect_navigation(wait_until="commit", timeout=15000):
                    google_btn.click(timeout=5000)
                result["google_button_clicked"] = True
            except Exception:
                # Navigation may have already completed
                try:
                    google_btn.click(timeout=3000)
                    result["google_button_clicked"] = True
                except Exception as e2:
                    result["error_message"] = f"btn_click_error: {str(e2)[:100]}"

        if not result["google_button_clicked"]:
            # CSRF fallback
            try:
                csrf_token = page.evaluate("""async () => {
                    const r = await fetch('/api/auth/csrf');
                    const d = await r.json();
                    return d.csrfToken || '';
                }""")
                if csrf_token:
                    import json as _json
                    page.evaluate(f"""() => {{
                        const f = document.createElement('form');
                        f.method = 'POST';
                        f.action = '/api/auth/signin/google';
                        const a = document.createElement('input');
                        a.name = 'csrfToken';
                        a.value = {_json.dumps(csrf_token)};
                        f.appendChild(a);
                        const b = document.createElement('input');
                        b.name = 'callbackUrl';
                        b.value = '/';
                        f.appendChild(b);
                        document.body.appendChild(f);
                        f.submit();
                    }}""")
                    result["google_button_clicked"] = True
            except Exception as e:
                result["error_message"] += f" csrf_fallback: {str(e)[:100]}"

        # 5. Wait for accounts.google.com or callback
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            url = page.url
            if "accounts.google.com" in url:
                result["accounts_google_reached"] = True
                break
            if "callback/google" in url:
                result["callback_reached"] = True
                break
            if "error" in url.lower() and "google" not in url:
                result["error_message"] = f"error_url: {url[:150]}"
                break
            time.sleep(0.5)

        # 6. Record redirect_uri
        observed_redirect_uri = _observed[0]
        result["redirect_uri_observed"] = observed_redirect_uri
        result["redirect_uri_correct"] = (
            observed_redirect_uri == EXPECTED_REDIRECT_URI
            or EXPECTED_REDIRECT_URI in page.url
        )

        # 7. Observe Google auth screen (no password entry)
        if result["accounts_google_reached"]:
            time.sleep(2)
            try:
                page_text = page.inner_text("body")[:3000]
            except Exception:
                page_text = ""

            has_account_chooser = any(t in page_text for t in [
                "계정 선택", "Choose an account", "계속", "Continue",
                "로그인", "Sign in", "@gmail.com", "@",
            ])
            result["consent_or_account_screen"] = has_account_chooser

            # Wait up to 60s for user to complete Google auth manually
            deadline2 = time.monotonic() + 60
            while time.monotonic() < deadline2:
                url = page.url
                if "callback/google" in url:
                    result["callback_reached"] = True
                if "auth/complete" in url:
                    result["complete_reached"] = True
                    break
                if url.startswith(APP_URL) and "/login" not in url and "error" not in url.lower() and "accounts.google" not in url:
                    break
                if "error" in url.lower() and "google" not in url:
                    result["error_message"] = f"error_url: {url[:150]}"
                    break
                time.sleep(1)

        # If already skipped to callback directly (existing session)
        elif result["callback_reached"] or (
            page.url.startswith(APP_URL) and "/login" not in page.url
        ):
            deadline3 = time.monotonic() + 15
            while time.monotonic() < deadline3:
                url = page.url
                if "auth/complete" in url:
                    result["complete_reached"] = True
                    break
                if url.startswith(APP_URL) and "/login" not in url and "error" not in url.lower():
                    break
                time.sleep(0.5)

        result["final_url"] = page.url

        # 8. Session cookie check (presence only, no values)
        session_cookie_names = [
            "next-auth.session-token",
            "__Secure-next-auth.session-token",
            "authjs.session-token",
            "__Secure-authjs.session-token",
        ]
        result["session_cookie_present"] = cookie_present(ctx, session_cookie_names)

        # 9. Determine success
        final = result["final_url"]
        result["login_success"] = (
            result["session_cookie_present"]
            or (
                final.startswith(APP_URL)
                and "/login" not in final
                and "error" not in final.lower()
                and result["callback_reached"]
            )
        )

        time.sleep(1)
        browser.close()

except Exception as e:
    result["error_message"] = f"playwright_error: {str(e)[:300]}"

print(json.dumps(result, ensure_ascii=False, indent=2))
