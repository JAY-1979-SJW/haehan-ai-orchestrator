"""셀렉터 헬스체크 CLI — 코드에 박힌 셀렉터가 실제 사이트에서 유효한지 실측.

사용:
    python tools/selector_health/selector_health_check.py naver_blog
    python tools/selector_health/selector_health_check.py --all
    python tools/selector_health/selector_health_check.py --list

종료 코드:
    0 = 문제 없음
    1 = 드리프트 감지(MISSING/HIDDEN/ERROR 존재)
    2 = 실행 오류(CDP 미연결 등)

읽기 전용이다. 페이지를 열고 셀렉터 존재만 확인하며 저장/발행은 하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# haehan-root-bootstrap: 정본 paths 를 import 하기 전이라 루트를 직접 찾는다 — 폴더가 옮겨져도 깨지지 않게 pyproject.toml 이 있는 상위 폴더를 찾는다
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))

from tools.selector_health import format_report, load_specs, run_site_checks  # noqa: E402
from tools.selector_health.core import ERROR, HIDDEN, MISSING  # noqa: E402

REPORT_DIR = ROOT / "data" / "selector_health"


def _print_site_list(specs):
    print("등록된 사이트:")
    for k, s in specs.items():
        print(f"  {k:<16} {s.title}  (셀렉터 {len(s.checks)}건)")


def _select_targets(ap, args, specs):
    if args.all:
        targets = list(specs.values())
    elif args.site:
        if args.site not in specs:
            print(f"알 수 없는 사이트: {args.site}")
            print(f"사용 가능: {', '.join(specs)}")
            return (2), None
        targets = [specs[args.site]]
    else:
        ap.print_help()
        return (2), None
    return None, targets


def _print_problems(problems):
    if problems:
        print("\n  ⚠ 조치 필요:")
        for r in problems:
            kind = {MISSING: "DOM 에 없음", HIDDEN: "숨김 상태", ERROR: "검사 오류"}.get(r.status, r.status)
            print(f"    - {r.name}: {kind}")


def _save_json_report(args, all_results):
    if args.json:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = REPORT_DIR / f"selector_health_{stamp}.json"
        out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON 리포트: {out}")


def main() -> int:
    ap = argparse.ArgumentParser(description="셀렉터 헬스체크")
    ap.add_argument("site", nargs="?", help="사이트 키 (예: naver_blog)")
    ap.add_argument("--all", action="store_true", help="등록된 전 사이트 검사")
    ap.add_argument("--list", action="store_true", help="등록된 사이트 목록")
    ap.add_argument("--json", action="store_true", help="JSON 리포트도 저장")
    args = ap.parse_args()

    specs = load_specs()

    if args.list:
        _print_site_list(specs)
        return 0

    _early, targets = _select_targets(ap, args, specs)
    if _early is not None:
        return _early

    try:
        from scripts.browser.cdp.connection import get_page, run_on_browser_thread
    except Exception as e:  # noqa: BLE001 - web_connector 로드 실패/브라우저 스레드 실행 실패시 오류 메시지 출력 후 return 2로 명시적 실패 종료 — 성공 위장 없음
        print(f"web_connector 로드 실패: {e}")
        return 2

    all_results = {}
    problem_total = 0

    for spec in targets:
        print(f"\n{'=' * 70}")

        def _run(sp=spec):
            page = get_page()
            return run_site_checks(page, sp, log=print)

        try:
            results = run_on_browser_thread(_run, timeout=180)
        except Exception as e:  # noqa: BLE001 - web_connector 로드 실패/브라우저 스레드 실행 실패시 오류 메시지 출력 후 return 2로 명시적 실패 종료 — 성공 위장 없음
            print(f"[{spec.key}] 검사 실패: {type(e).__name__}: {str(e)[:120]}")
            print("  CDP 브라우저가 떠 있는지 확인: python scripts/browser/cdp/cdp_force_start.py status")
            return 2

        print(format_report(spec, results))
        problems = [r for r in results if r.is_problem]
        problem_total += len(problems)
        all_results[spec.key] = [
            {
                "name": r.name,
                "selector": r.selector,
                "status": r.status,
                "count": r.count,
                "visible": r.visible_count,
                "detail": r.detail,
                "note": r.note,
            }
            for r in results
        ]

        _print_problems(problems)

    _save_json_report(args, all_results)

    print(f"\n{'=' * 70}")
    if problem_total:
        print(f"드리프트 {problem_total}건 감지 — 위 셀렉터를 수정해야 합니다.")
        return 1
    print("모든 셀렉터 정상.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
