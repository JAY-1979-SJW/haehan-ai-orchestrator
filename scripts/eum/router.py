"""EUM 서비스 라우터 — eum.cw.or.kr 자동화 진입점."""
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
    print("=" * 60)
    print("EUM 단말기설치현황 추출")
    print("=" * 60)
    from scripts.eum_extract_all_devices import main
    main()


def _cmd_dashboard() -> None:
    """추출 데이터 기반 업무 대시보드 생성."""
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
        gate_check("naver_mail_send", force=False,
                   context="EUM 홍보메일 발송")
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
    print("=" * 60)
    print("EUM 신규 현장 발굴")
    print("=" * 60)
    from scripts.eum_extract_new_sites import main
    main()


def _cmd_task_run() -> None:
    """EUM 전체 파이프라인 자동 실행."""
    gate_check("eum_extract_all_devices")
    print("=" * 60)
    print("EUM 전체 작업 자동 실행")
    print("=" * 60)
    from scripts.eum_task_runner import main
    main()


def _cmd_login() -> None:
    """EUM 자동 로그인."""
    gate_check("eum_extract_all_devices")
    print("=" * 60)
    print("EUM 자동 로그인")
    print("=" * 60)
    from scripts.eum.auth import main
    main()


def _cmd_monitor() -> None:
    """단말기 운용 모니터링 (통신단절/미사용/준공 임박)."""
    gate_check("eum_extract_all_devices")
    print("=" * 60)
    print("EUM 단말기 운용 모니터링")
    print("=" * 60)
    from scripts.eum.monitor import main
    main()


def _cmd_history(sub: str | None, args: list[str]) -> None:
    """단말기 이력 조회 (WEBMAN400M00)."""
    gate_check("eum_extract_all_devices")
    print("=" * 60)
    print("EUM 단말기 이력 조회")
    print("=" * 60)
    # sub를 device_id로 사용 가능 (예: eum history 12345)
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
    print("=" * 60)
    print("EUM 단말기 철거 관리")
    print("=" * 60)
    from scripts.eum.demolition import main
    main(apply=apply_mode, device_id=device_id)


def _cmd_explore() -> None:
    """전체 사이트 탐색 (메뉴/WEBMAN 구조 추출)."""
    gate_check("eum_extract_all_devices")
    print("=" * 60)
    print("EUM 전체 사이트 탐색")
    print("=" * 60)
    from scripts.eum.site_explorer import main
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
