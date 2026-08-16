"""Google 비밀번호 관리자 전체 수집.

흐름:
  1. passwords.google.com 목록 → /password/ 링크 전체 수집
  2. 첫 항목 이동 → Windows Hello 팝업 → 사용자가 Chrome 창에서 인증 (1회)
  3. 이후 항목은 세션 유지로 자동 처리
  4. 아이디: 버튼 aria-label 파싱
  5. 비밀번호: "표시 또는 숨기기" 버튼 클릭 → input[type=text] 읽기

결과: data/google_password_sites.json
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_FILE = ROOT / "data" / "google_password_sites.json"

PASSKEY_PATTERNS = ["challenge/pk", "signin/challenge", "v3/signin"]
COPY_USER_RE = re.compile(r"클립보드에 사용자 이름\s+(.+?)\s+복사")
REVEAL_LABEL_TPL = "사용자 이름이 {user}인 계정의 비밀번호 표시 또는 숨기기"


def _is_challenge(url: str) -> bool:
    return any(p in url for p in PASSKEY_PATTERNS)


def _wait_passkey(pg, timeout_s: int = 120, label: str = "") -> bool:
    """패스키 인증 완료 대기 — passwords.google.com 으로 복귀하면 True."""
    deadline = time.time() + timeout_s
    first = True
    while time.time() < deadline:
        url = pg.url
        if "passwords.google.com/password/" in url:
            return True
        if first and _is_challenge(url):
            print(f"\n  ★ Chrome 창에서 Windows Hello / 패스키 인증하세요 (최대 {timeout_s}초 대기)...", flush=True)
            first = False
        time.sleep(1)
    return False


def _parse_users(pg) -> list[str]:
    """버튼 aria-label 에서 아이디 목록 추출."""
    try:
        labels = pg.evaluate(
            "() => Array.from(document.querySelectorAll('button[aria-label]')).map(b => b.getAttribute('aria-label'))"
        )
        return [COPY_USER_RE.search(lb).group(1) for lb in labels if lb and COPY_USER_RE.search(lb)]
    except Exception:
        return []


def _reveal_password(pg, username: str) -> str:
    """눈 버튼 클릭 후 비밀번호 text input 에서 값 읽기."""
    label = REVEAL_LABEL_TPL.format(user=username)
    try:
        pg.locator(f"button[aria-label='{label}']").first.click(timeout=3000)
        time.sleep(1.2)
        vals = pg.evaluate(
            "() => Array.from(document.querySelectorAll('input[type=text]')).map(i=>i.value).filter(v=>v)"
        )
        return vals[0] if vals else ""
    except Exception:
        return ""


def _parse_site(pg) -> str:
    """body text 첫 도메인/앱명."""
    try:
        lines = [ln.strip() for ln in pg.inner_text("body").split("\n") if ln.strip()]
        for line in lines:
            if re.match(r"^[\w\-\.]+\.(co\.kr|com|kr|net|org|io|go\.kr|or\.kr|me)$", line):
                return line
        # 앱 이름 fallback (도메인 패턴 없는 경우)
        skip = {"계정", "도움말", "비밀번호 관리자", "비밀번호 진단", "search", "Safer with Google"}
        for line in lines[2:]:
            if line not in skip and len(line) > 2:
                return line
    except Exception:
        pass
    return ""


def collect() -> list[dict]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://localhost:9222")
        ctx = b.contexts[0]
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 목록 전체 스크롤
        print("▶ 목록 로드 중...")
        pg.goto("https://passwords.google.com", timeout=20000, wait_until="domcontentloaded")
        time.sleep(3)
        prev = 0
        for _ in range(60):
            pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.6)
            h = pg.evaluate("document.body.scrollHeight")
            if h == prev:
                break
            prev = h

        links = pg.evaluate(
            "() => [...new Set(Array.from(document.querySelectorAll('a[href]'))"
            ".map(a=>a.href).filter(h=>h.includes('/password/')))]"
        )
        print(f"▶ {len(links)}개 항목 발견\n")

        results: list[dict] = []
        auth_done = False

        for i, link in enumerate(links, 1):
            print(f"[{i:3d}/{len(links)}] ", end="", flush=True)
            try:
                pg.goto(link, timeout=20000)
                time.sleep(0.5)

                if _is_challenge(pg.url):
                    if not auth_done:
                        ok = _wait_passkey(pg, timeout_s=120)
                        if not ok:
                            print("✗ 인증 타임아웃 — 스킵")
                            results.append({"site": link, "username": "", "password": "인증타임아웃"})
                            continue
                        auth_done = True
                        time.sleep(1)
                    else:
                        # 재인증 요구 시 짧게 대기
                        ok = _wait_passkey(pg, timeout_s=20)
                        if not ok:
                            results.append({"site": link, "username": "", "password": "재인증실패"})
                            continue

                site = _parse_site(pg)
                usernames = _parse_users(pg)

                if not usernames:
                    print(f"site={site:30s} 아이디 없음")
                    results.append({"site": site, "username": "", "password": ""})
                    continue

                for username in usernames:
                    pw = _reveal_password(pg, username)
                    pw_display = "✓ 수집" if pw and "●" not in pw else "✗ 표시실패"
                    print(f"site={site:30s} user={username:25s} pw={pw_display}")
                    results.append({"site": site, "username": username, "password": pw or "●●●● (표시실패)"})

            except Exception as e:
                print(f"오류: {str(e)[:60]}")
                results.append({"site": link, "username": "", "password": "오류"})

        b.close()
        return results


def main():
    print("=" * 60)
    print("Google 비밀번호 관리자 전체 수집")
    print("첫 항목에서 Chrome 창 Windows Hello 인증 필요 (1회)")
    print("=" * 60 + "\n")

    records = collect()

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps({"total": len(records), "records": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ok = sum(1 for r in records if r.get("password") and "●" not in r["password"] and "오류" not in r["password"])
    print(f"\n완료: {len(records)}개 계정 / 비밀번호 수집 {ok}개")
    print(f"저장: {OUT_FILE}")


if __name__ == "__main__":
    main()
