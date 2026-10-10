"""Google 비밀번호 관리자 사이트/아이디 목록화 (비밀번호 값은 수집·저장하지 않음).

보안 금지선(secret/password 값 저장 금지)에 따라 비밀번호 필드는 읽지도 저장하지도 않는다.
- 기본은 dry-run(계획만 출력, 브라우저 접속 안 함). 실제 수집은 --execute 필요.
- 전용 새 탭만 열고 닫는다(사용자 기존 탭은 건드리지 않음).
- 사용자명이 이메일이면 기본 마스킹(앞 2자+***@도메인). --no-mask-email 로 해제.

결과: data/google_password_sites.json (site, username 만)
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_FILE = ROOT / "data" / "google_password_sites.json"

PASSKEY_PATTERNS = ["challenge/pk", "signin/challenge", "v3/signin"]
COPY_USER_RE = re.compile(r"클립보드에 사용자 이름\s+(.+?)\s+복사")
CDP_PORT = 9222
ALLOWED_KEYS = ("site", "username")


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
    except Exception:  # noqa: BLE001 - Google 비밀번호 관리자 전체 수집 CLI - 사용자가 직접 실행, Windows Hello/패스키로 본인 인증 필요. except는 개별 항목 파싱/조회 실패만 감싸 빈 문자열로 폴백, 결과를 JSON 파일로 저장하는 건 도구의 의도된 동작(비밀번호 값 자체를 노출시키는 게 아니라 그대로 반환)
        return []


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
    except Exception:  # noqa: BLE001 - Google 비밀번호 관리자 전체 수집 CLI - 사용자가 직접 실행, Windows Hello/패스키로 본인 인증 필요. except는 개별 항목 파싱/조회 실패만 감싸 빈 문자열로 폴백, 결과를 JSON 파일로 저장하는 건 도구의 의도된 동작(비밀번호 값 자체를 노출시키는 게 아니라 그대로 반환)
        pass
    return ""


def _scroll_password_list(pg):
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


def mask_username(name: str) -> str:
    """이메일이면 앞 2자+***@도메인 으로 마스킹, 아니면 그대로."""
    if "@" not in name:
        return name
    local, _, domain = name.partition("@")
    return f"{local[:2]}***@{domain}"


def sanitize_records(records: list[dict]) -> tuple[list[dict], int]:
    """허용 키(site, username) 외 모든 키(password 등) 제거. (정제 목록, 제거된 키 개수) 반환."""
    clean: list[dict] = []
    removed = 0
    for r in records:
        clean.append({k: r.get(k, "") for k in ALLOWED_KEYS})
        removed += sum(1 for k in r if k not in ALLOWED_KEYS)
    return clean, removed


def collect_from_page(pg, mask_email: bool = True) -> list[dict]:
    """전달받은 페이지(전용 탭)로 목록 수집. 비밀번호는 읽지 않는다."""
    _scroll_password_list(pg)
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
                ok = _wait_passkey(pg, timeout_s=20 if auth_done else 120)
                if not ok:
                    print("✗ 인증 실패/타임아웃 — 스킵")
                    results.append({"site": link, "username": ""})
                    continue
                auth_done = True
                time.sleep(1)
            site = _parse_site(pg)
            usernames = _parse_users(pg)
            if not usernames:
                print(f"site={site:30s} 아이디 없음")
                results.append({"site": site, "username": ""})
                continue
            for username in usernames:
                shown = mask_username(username) if mask_email else username
                print(f"site={site:30s} user={shown}")
                results.append({"site": site, "username": shown})
        except Exception as e:  # noqa: BLE001 - 항목별 조회 실패만 기록하고 계속 진행
            print(f"오류: {str(e)[:60]}")
            results.append({"site": link, "username": ""})
    return results


def collect(mask_email: bool = True) -> list[dict]:
    """9222 Chrome 에 접속해 전용 새 탭으로 수집 후 그 탭만 닫는다."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        ctx = b.contexts[0]
        pg = ctx.new_page()
        try:
            return collect_from_page(pg, mask_email=mask_email)
        finally:
            try:
                pg.close()  # 전용 탭만 닫음
            except Exception:  # noqa: BLE001 - 이미 닫힌 탭
                pass


def write_output(records: list[dict], out_file: Path | None = None) -> int:
    """방어적 검사 후 저장. 허용 키 외 값이 있으면 제거하고 경고. 제거 건수 반환."""
    out_file = out_file or OUT_FILE
    clean, removed = sanitize_records(records)
    if removed:
        print(f"경고: 허용되지 않는 필드 {removed}개 제거 후 저장 (비밀번호성 값은 저장하지 않음)")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps({"total": len(clean), "records": clean}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return removed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Google 비밀번호 관리자 사이트/아이디 목록화 (비밀번호 미수집)")
    ap.add_argument("--execute", action="store_true", help="실제 수집 실행(기본은 dry-run)")
    ap.add_argument("--no-mask-email", action="store_true", help="이메일 사용자명 마스킹 해제")
    args = ap.parse_args(argv)
    mask = not args.no_mask_email

    if not args.execute:
        print("[dry-run] 브라우저에 접속하지 않습니다.")
        print(f"  계획: localhost:{CDP_PORT} Chrome 에 전용 새 탭을 열어 passwords.google.com 의 site/username 만 목록화")
        print(f"  출력: {OUT_FILE} (password 키 없음, 이메일 마스킹={'on' if mask else 'off'})")
        print("  실제 실행: --execute")
        return 0

    print(f"※ 9222 포트({CDP_PORT})의 사용자 Chrome 에 접속합니다. 전용 새 탭만 사용합니다.")
    print("첫 항목에서 Windows Hello 인증이 필요할 수 있습니다.\n")
    records = collect(mask_email=mask)
    write_output(records)
    print(f"\n완료: {len(records)}개 항목 (비밀번호 미수집)")
    print(f"저장: {OUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
