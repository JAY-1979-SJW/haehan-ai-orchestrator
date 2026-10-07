"""cdp_tab_manager.py — CDP 자동화 브라우저(9222) 탭 정리.

CDP HTTP 엔드포인트만 사용(경량, playwright attach 불필요 → 빌드 중에도 안전·빠름).

안전 정책:
  - 기본 dry-run (닫을 목록만 표시, 실제 미실행)
  - 로그인/인증/세션 탭 보호(PROTECT 패턴) — 절대 닫지 않음
  - about:blank·새 탭·중복 URL 만 정리 대상

사용:
    python scripts/browser/cdp/cdp_tab_manager.py list
    python scripts/browser/cdp/cdp_tab_manager.py clean            # dry-run (기본)
    python scripts/browser/cdp/cdp_tab_manager.py clean --confirm  # 실제 닫기

L4 Browser Engine 계층. 업무 로직 없음.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

CDP = "http://127.0.0.1:9222"

# 절대 닫지 않는 보호 패턴 (로그인·인증·세션 도메인)
PROTECT = [
    "nid.naver",
    "oauth",
    "captcha",
    "login",
    "accounts.google",
    "naver.com",
    "smartstore",
    "gabia",
    "kakao",
    "data.go.kr",
    "hiworks",
    "google.com",
    "mail",
]

# 정리 대상(빈 탭) 패턴
_BLANK = ("about:blank", "", "chrome://newtab", "chrome://new-tab-page")


def _get(path: str):
    with urllib.request.urlopen(f"{CDP}{path}", timeout=10) as r:
        return json.loads(r.read().decode())


def _close(tid: str) -> str:
    """탭 닫기 — PUT 우선, 실패 시 GET 폴백."""
    for method in ("PUT", "GET"):
        try:
            req = urllib.request.Request(f"{CDP}/json/close/{tid}", method=method)
            with urllib.request.urlopen(req, timeout=10) as r:
                return f"{method}:{r.read().decode()[:20]}"
        except Exception as e:  # noqa: BLE001 - CDP 탭 관리 CLI -- 탭 닫기 시도 각 방식 실패는 마지막 에러만 기록 후 다음 방식 시도, 탭 목록 조회 실패는 종료코드 1로 안내(출력용 CLI 도구)
            last = f"{method} 실패:{e}"
    return last


def list_pages() -> list[dict]:
    return [t for t in _get("/json/list") if t.get("type") == "page"]


def is_protected(url: str) -> bool:
    u = (url or "").lower()
    return any(p in u for p in PROTECT)


def plan_clean(
    pages: list[dict], all_unprotected: bool = False
) -> tuple[list[tuple[dict, str]], list[tuple[dict, str]]]:
    """닫을 후보와 유지 목록 결정.

    기본: 빈 탭 + 중복 URL(보호 탭이라도 사본은 1개만 유지).
    all_unprotected=True: 비보호 단독 탭도 정리(보호 탭은 항상 유지).
    """
    close: list[tuple[dict, str]] = []
    keep: list[tuple[dict, str]] = []
    seen: set[str] = set()
    for p in pages:
        url = p.get("url", "")
        low = url.lower()
        # 1) 빈 탭
        if low in _BLANK or low.startswith("chrome://newtab") or low.startswith("chrome://new-tab"):
            close.append((p, "빈 탭"))
            continue
        # 2) 중복 URL — 보호 여부 무관, 첫 개만 유지
        if url in seen:
            close.append((p, "중복"))
            continue
        seen.add(url)
        # 3) 보호 탭은 항상 유지
        if is_protected(url):
            keep.append((p, "보호(세션/인증)"))
            continue
        # 4) 비보호 단독 탭 — aggressive 모드에서만 정리
        if all_unprotected:
            close.append((p, "비보호"))
        else:
            keep.append((p, "유지"))
    return close, keep


def _cmd_list(pages: list) -> int:
    """list 서브커맨드: 열린 탭 출력."""
    print(f"열린 탭 {len(pages)}개:")
    for p in pages:
        mark = "🔒" if is_protected(p.get("url", "")) else "  "
        print(f"  {mark} {(p.get('title', '') or '(무제)')[:38]:38} | {p.get('url', '')[:72]}")
    return 0


def _cmd_clean(pages: list, args: argparse.Namespace) -> int:
    """clean 서브커맨드: 정리 계획 출력 후 --confirm 이면 실제 닫기."""
    close, keep = plan_clean(pages, all_unprotected=args.all_unprotected)
    print(f"=== 정리 계획 (닫기 {len(close)} / 유지 {len(keep)}) ===")
    for p, why in close:
        print(f"  [닫기·{why}] {p.get('url', '')[:72]}")
    if not close:
        print("  정리할 빈 탭/중복 없음")
    for p, why in keep:
        if why.startswith("보호"):
            print(f"  [보호] {(p.get('title', '') or '')[:30]} | {p.get('url', '')[:50]}")
    if not args.confirm:
        print("\n(dry-run) 실제로 닫으려면 --confirm 추가")
        return 0
    closed = 0
    for p, _why in close:
        res = _close(p["id"])
        print(f"  닫음: {p.get('url', '')[:50]} → {res}")
        closed += 1
    print(f"완료: {closed}개 닫음")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="CDP 탭 정리")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list")
    c = sub.add_parser("clean")
    c.add_argument("--confirm", action="store_true", help="실제 닫기 (없으면 dry-run)")
    c.add_argument("--all-unprotected", action="store_true", help="비보호 단독 탭도 정리")
    args = ap.parse_args()

    try:
        pages = list_pages()
    except Exception as e:  # noqa: BLE001 - CDP 탭 관리 CLI -- 탭 닫기 시도 각 방식 실패는 마지막 에러만 기록 후 다음 방식 시도, 탭 목록 조회 실패는 종료코드 1로 안내(출력용 CLI 도구)
        print(f"[cdp] 9222 연결 실패: {e}")
        return 1

    if args.cmd in (None, "list"):
        return _cmd_list(pages)

    if args.cmd == "clean":
        return _cmd_clean(pages, args)

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
