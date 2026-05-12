"""스마트스토어 서비스 라우터."""
from __future__ import annotations

from scripts.gate import check as gate_check
from scripts.logger import get_logger

__status__ = {
    "tasks": {
        "product list":    "partial",
        "product register":"todo",
        "order new":       "partial",
        "inventory":       "partial",
        "seo":             "todo",
        "ai review-reply": "todo",
        "competitor":      "todo",
        "csv import":      "todo",
        "analytics":       "partial",
    },
    "note": "라우터/클래스 구조 완성. 각 기능은 naver/automation/ 하위 모듈 검증 필요",
}

_log = get_logger(__name__)


def run_smartstore(task: str | None, sub: str | None, args: list[str]) -> None:
    """스마트스토어 서비스 라우팅.

    task: product | order | inventory | seo | ai | competitor | csv | analytics
    sub:  하위 명령 (list / register / update / delete 등)
    """
    match task or "help":
        case "product":
            _cmd_product(sub, args)
        case "order":
            _cmd_order(sub, args)
        case "inventory":
            _cmd_inventory(sub, args)
        case "seo":
            _cmd_seo(sub, args)
        case "ai":
            _cmd_ai(sub, args)
        case "competitor":
            _cmd_competitor(sub, args)
        case "csv":
            _cmd_csv(sub, args)
        case "analytics":
            _cmd_analytics(sub, args)
        case "session-check":
            _cmd_session_check()
        case _:
            _print_help()


# ── 명령 구현 ─────────────────────────────────────────────────────────

def _cmd_product(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    action = sub or "list"
    print(f"[스마트스토어] 상품 {action}")
    from scripts.smartstore import SmartStore
    from scripts.web_connector import get_page
    ss = SmartStore(get_page())
    if action == "list":
        result = ss.products.list()
        _print_result(result)
    elif action == "register":
        gate_check("eum_register")  # 상품등록 = approve 수준
        print("  상품 등록 기능은 별도 데이터 파일 필요. scripts/sample_product_data.json 참고")
    else:
        print(f"  알 수 없는 하위 명령: {action}")


def _cmd_order(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    action = sub or "new"
    print(f"[스마트스토어] 주문 {action}")
    from scripts.smartstore import SmartStore
    from scripts.web_connector import get_page
    ss = SmartStore(get_page())
    result = ss.orders.fetch_new()
    _print_result(result)


def _cmd_inventory(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    print("[스마트스토어] 재고 확인")
    from scripts.smartstore import SmartStore
    from scripts.web_connector import get_page
    ss = SmartStore(get_page())
    result = ss.inventory.check_low_stock()
    _print_result(result)


def _cmd_seo(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    print("[스마트스토어] SEO 최적화")
    from scripts.smartstore import SmartStore
    from scripts.web_connector import get_page
    ss = SmartStore(get_page())
    result = ss.seo.optimize({})
    _print_result(result)


def _cmd_ai(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    print("[스마트스토어] AI 리뷰 응답")
    from scripts.smartstore import SmartStore
    from scripts.web_connector import get_page
    ss = SmartStore(get_page())
    review = " ".join(args) if args else ""
    result = ss.ai.reply_review(review) if review else {"error": "리뷰 텍스트 필요"}
    _print_result(result)


def _cmd_competitor(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    keyword = " ".join(args) or sub or ""
    print(f"[스마트스토어] 경쟁사 분석: {keyword or '(키워드 미지정)'}")
    from scripts.smartstore import SmartStore
    from scripts.web_connector import get_page
    ss = SmartStore(get_page())
    result = ss.competitor.track(keyword)
    _print_result(result)


def _cmd_csv(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    file_path = args[0] if args else sub or ""
    if not file_path:
        print("  사용법: smartstore csv <파일경로>")
        return
    print(f"[스마트스토어] CSV 가져오기: {file_path}")
    from scripts.smartstore import SmartStore
    from scripts.web_connector import get_page
    ss = SmartStore(get_page())
    result = ss.csv.import_csv(file_path)
    _print_result(result)


def _cmd_analytics(sub: str | None, args: list[str]) -> None:
    gate_check("goto")
    print("[스마트스토어] 오늘 통계 수집")
    from scripts.smartstore import SmartStore
    from scripts.web_connector import get_page
    ss = SmartStore(get_page())
    result = ss.analytics.collect_today()
    _print_result(result)


def _cmd_session_check() -> None:
    from scripts.site_base import check_session
    print("=" * 60)
    print("스마트스토어 세션 확인")
    print("=" * 60)
    result = check_session("naver")
    if result["error"]:
        print(f"⚠  연결 실패: {result['error']}")
    elif result["logged_in"]:
        print("✓ 네이버 로그인 정상 (스마트스토어 접근 가능)")
    else:
        print("✗ 네이버 로그인 필요")
    print("=" * 60)


def _print_help() -> None:
    print("""스마트스토어 사용법:
  python scripts/cdp_client.py smartstore product list       상품 목록
  python scripts/cdp_client.py smartstore order new         신규 주문
  python scripts/cdp_client.py smartstore inventory         재고 확인
  python scripts/cdp_client.py smartstore seo               SEO 최적화
  python scripts/cdp_client.py smartstore ai <리뷰텍스트>    AI 리뷰 응답
  python scripts/cdp_client.py smartstore competitor <키워드> 경쟁사 분석
  python scripts/cdp_client.py smartstore csv <파일>         CSV 가져오기
  python scripts/cdp_client.py smartstore analytics         오늘 통계""")


def _print_result(result) -> None:
    import json
    if isinstance(result, dict):
        print(json.dumps(result, ensure_ascii=False, indent=2)[:500])
    else:
        print(result)
