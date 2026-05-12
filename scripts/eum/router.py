"""EUM 서비스 라우터 — eum.cw.or.kr 자동화 진입점.

모든 브라우저 접근 명령은 _get_page()를 통해 세션을 얻으며,
로그인 여부를 자동 확인 후 필요 시 즉시 재로그인한다.
별도의 'eum login' 명령 없이도 항상 로그인 상태가 보장된다.
"""
from __future__ import annotations

from scripts.gate import check as gate_check
from scripts.logger import get_logger

__status__ = {
    "tasks": {
        "extract (WEBMAN390M00)": "done",
        "dashboard":              "done",
        "promo-mail preview":     "done",
        "promo-mail send":        "done",
        "new-sites (WEBMAN380M00)": "done",
        "task-run (전체 파이프라인)": "done",
        # 신규 추가 (2026-05-12)
        "login (자동 로그인)":         "done",
        "monitor (통신단절/미사용 감지)": "done",
        "history (WEBMAN400M00 이력)": "done",
        "demolition (WEBMAN382M00 철거)": "done",
        "explore (전체 사이트 탐색)":   "done",
    },
    "note": "22대 단말기 전체 추출 검증 완료(2026-05-11). 신규 모듈(auth/monitor/history/demolition/site_explorer) 추가(2026-05-12)",
}

_log = get_logger(__name__)

EUM_URL = "https://eum.cw.or.kr/web/man/WEBMAN390M00"


def _get_page():
    """브라우저 페이지를 얻고 EUM 로그인을 보장한다.

    세션이 없거나 만료됐으면 자동으로 재로그인.
    모든 브라우저 접근 명령에서 get_page() 대신 이 함수를 사용한다.
    """
    from scripts.web_connector import get_page
    from scripts.eum.auth import ensure_logged_in
    page = get_page()
    ensure_logged_in(page)
    return page


def run_eum(task: str | None, sub: str | None, args: list[str]) -> None:
    """EUM 서비스 라우팅.

    task: extract | dashboard | mail | new-sites | task-run
    sub:  하위 옵션 (extract: full/quick, mail: preview/send)
    """
    match task or "help":
        case "extract":
            _cmd_extract(sub, args)
        case "dashboard":
            _cmd_dashboard()
        case "mail" | "promo-mail":
            _cmd_mail(sub, args)
        case "new-sites":
            _cmd_new_sites()
        case "task-run":
            _cmd_task_run()
        # 신규 추가 (2026-05-12)
        case "login":
            _cmd_login()
        case "monitor":
            _cmd_monitor()
        case "history":
            _cmd_history(sub, args)
        case "demolition":
            _cmd_demolition(sub, args)
        case "explore":
            _cmd_explore()
        case _:
            _print_help()


# ── 명령 구현 ─────────────────────────────────────────────────────────

def _cmd_extract(sub: str | None, args: list[str]) -> None:
    """단말기설치현황 전체 추출 (WEBMAN390M00)."""
    gate_check("eum_extract_all_devices")
    page = _get_page()  # 자동 로그인 보장
    print("=" * 60)
    print("EUM 단말기설치현황 추출")
    print("=" * 60)
    from scripts.eum_extract_all_devices import main
    main()


def _cmd_dashboard() -> None:
    """추출 데이터 기반 업무 대시보드 생성 (브라우저 불필요)."""
    gate_check("eum_extract_all_devices")
    print("=" * 60)
    print("EUM 업무 대시보드")
    print("=" * 60)
    from scripts.eum_business_dashboard import main
    main()


def _cmd_mail(sub: str | None, args: list[str]) -> None:
    """홍보 메일 초안 생성 또는 발송."""
    mode = sub or "preview"
    if mode == "send":
        gate_check("naver_mail_send", force=False, context="EUM 홍보메일 발송")
    else:
        gate_check("eum_extract_all_devices")
    print("=" * 60)
    print(f"EUM 홍보메일 {'발송' if mode == 'send' else '초안 생성'}")
    print("=" * 60)
    from scripts.eum_prioritize_and_mail import main
    main()


def _cmd_new_sites() -> None:
    """신규 현장 발굴 (WEBMAN380M00)."""
    gate_check("eum_extract_all_devices")
    _get_page()  # 자동 로그인 보장
    print("=" * 60)
    print("EUM 신규 현장 발굴")
    print("=" * 60)
    from scripts.eum_extract_new_sites import main
    main()


def _cmd_task_run() -> None:
    """EUM 전체 파이프라인 자동 실행."""
    gate_check("eum_extract_all_devices")
    _get_page()  # 자동 로그인 보장
    print("=" * 60)
    print("EUM 전체 작업 자동 실행")
    print("=" * 60)
    from scripts.eum_task_runner import main
    main()


def _cmd_login() -> None:
    """EUM 로그인 상태 확인 (상시 자동 처리되므로 수동 호출 불필요)."""
    gate_check("eum_extract_all_devices")
    print("=" * 60)
    print("EUM 로그인 상태 확인")
    print("=" * 60)
    _get_page()  # ensure_logged_in 내부에서 결과 출력
    from scripts.web_connector import get_page
    print(f"  현재 URL: {get_page().url}")
    print("=" * 60)


def _cmd_monitor() -> None:
    """단말기 운용 모니터링 (통신단절/미사용/준공 임박, 브라우저 불필요)."""
    gate_check("eum_extract_all_devices")
    print("=" * 60)
    print("EUM 단말기 운용 모니터링")
    print("=" * 60)
    from scripts.eum.monitor import main
    main()


def _cmd_history(sub: str | None, args: list[str]) -> None:
    """단말기 이력 조회 (WEBMAN400M00)."""
    gate_check("eum_extract_all_devices")
    page = _get_page()  # 자동 로그인 보장
    print("=" * 60)
    print("EUM 단말기 이력 조회")
    print("=" * 60)
    device_id = sub or (args[0] if args else None)
    from scripts.eum.history import main
    main(device_id=device_id)


def _cmd_demolition(sub: str | None, args: list[str]) -> None:
    """철거 현황 조회 및 신청 (WEBMAN382M00)."""
    apply_mode = sub == "apply" or (args and args[0] == "apply")
    device_id = args[0] if apply_mode and args else None
    if apply_mode:
        gate_check("eum_remove", force=False)
    else:
        gate_check("eum_extract_all_devices")
    _get_page()  # 자동 로그인 보장
    print("=" * 60)
    print("EUM 단말기 철거 관리")
    print("=" * 60)
    from scripts.eum.demolition import main
    main(apply=apply_mode, device_id=device_id)


def _cmd_explore() -> None:
    """전체 사이트 세밀 탐색 (WEBMAN 23개 + 메뉴 전체)."""
    gate_check("eum_extract_all_devices")
    _get_page()  # 자동 로그인 보장
    print("=" * 60)
    print("EUM 전체 사이트 세밀 탐색")
    print("=" * 60)
    from scripts.eum.full_explorer import main
    main()


def _print_help() -> None:
    print("""EUM 사용법:
  python scripts/cdp_client.py eum extract      단말기 전체 추출
  python scripts/cdp_client.py eum dashboard    업무 대시보드
  python scripts/cdp_client.py eum mail         홍보메일 초안
  python scripts/cdp_client.py eum mail send    홍보메일 발송 (승인 필요)
  python scripts/cdp_client.py eum new-sites    신규 현장 발굴
  python scripts/cdp_client.py eum task-run     전체 파이프라인 실행
  python scripts/cdp_client.py eum login        자동 로그인
  python scripts/cdp_client.py eum monitor      운용 모니터링 (통신단절/미사용/준공임박)
  python scripts/cdp_client.py eum history      단말기 이력 조회 (WEBMAN400M00)
  python scripts/cdp_client.py eum history 123  특정 단말기 이력
  python scripts/cdp_client.py eum demolition   철거 현황 조회 (WEBMAN382M00)
  python scripts/cdp_client.py eum explore      전체 사이트 탐색""")
