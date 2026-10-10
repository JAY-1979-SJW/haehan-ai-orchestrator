"""EUM 서비스 라우터 — eum.cw.or.kr 자동화 진입점.

모든 브라우저 접근 명령은 _get_page()를 통해 세션을 얻으며,
로그인 여부를 자동 확인 후 필요 시 즉시 재로그인한다.
별도의 'eum login' 명령 없이도 항상 로그인 상태가 보장된다.
"""

from __future__ import annotations

from scripts.common.gate import check as gate_check
from scripts.common.logger import get_logger

__status__ = {
    "tasks": {
        "extract (WEBMAN390M00)": "done",
        "dashboard": "done",
        "promo-mail preview": "done",
        "promo-mail send": "done",
        "new-sites (WEBMAN380M00)": "done",
        "task-run (전체 파이프라인)": "done",
        # 신규 추가 (2026-05-12)
        "login (자동 로그인)": "done",
        "monitor (통신단절/미사용 감지)": "done",
        "history (WEBMAN400M00 이력)": "done",
        "demolition (WEBMAN382M00 철거)": "done",
        "explore (전체 사이트 탐색)": "done",
        # 신규 추가 (2026-05-12 권한 기능)
        "registration (WEBMAN381M00 신규등록)": "done",
        "deregistration (WEBMAN382M00 말소)": "done",
    },
    "note": "22대 단말기 전체 추출 완료(2026-05-11). 신규등록/말소 자동화 추가(2026-05-12)",
}

_log = get_logger(__name__)

EUM_URL = "https://eum.cw.or.kr/web/man/WEBMAN390M00"


def _get_page():
    """브라우저 페이지를 얻고 EUM 로그인을 보장한다.

    세션이 없거나 만료됐으면 자동으로 재로그인.
    모든 브라우저 접근 명령에서 get_page() 대신 이 함수를 사용한다.
    """
    from scripts.eum.auth import ensure_logged_in
    from scripts.browser.cdp.connection import get_page

    page = get_page()
    ensure_logged_in(page)
    return page


def _command_table() -> dict:
    """task 별칭 -> (sub, args) 를 받는 실행 함수 표. 호출 시점에 _cmd_* 를 조회한다."""
    table: dict = {}
    for names, fn in (
        (("extract",), lambda sub, args: _cmd_extract(sub, args)),
        (("mail", "promo-mail", "sales-mail"), lambda sub, args: _cmd_mail(sub, args)),
        (("new-sites",), lambda sub, args: _cmd_new_sites()),
        (("install-targets", "verify-install-targets"), lambda sub, args: _cmd_install_targets(sub, args)),
        # 신규 추가 (2026-05-12)
        (("login",), lambda sub, args: _cmd_login()),
        (("monitor",), lambda sub, args: _cmd_monitor()),
        (("history",), lambda sub, args: _cmd_history(sub, args)),
        (("demolition",), lambda sub, args: _cmd_demolition(sub, args)),
        (("labor-test",), lambda sub, args: _cmd_labor_test()),
        (("test-workers",), lambda sub, args: _cmd_test_workers()),
        (("site-devices",), lambda sub, args: _cmd_site_devices()),
        (("explore",), lambda sub, args: _cmd_explore()),
        (("explore-accessible", "access-map"), lambda sub, args: _cmd_explore_accessible(sub, args)),
        (("capabilities",), lambda sub, args: _cmd_capabilities()),
        (("build-capabilities", "catalog"), lambda sub, args: _cmd_build_capabilities()),
        (("page-info", "info"), lambda sub, args: _cmd_page_info(sub, args)),
        (("open-menu", "page"), lambda sub, args: _cmd_open_menu(sub, args)),
        (("work-index", "workspace", "map"), lambda sub, args: _cmd_work_index()),
        (("work",), lambda sub, args: _cmd_work(sub, args)),
        (("registration",), lambda sub, args: _cmd_registration(sub, args)),
        (("deregistration",), lambda sub, args: _cmd_deregistration(sub, args)),
    ):
        for name in names:
            table[name] = fn
    return table


def run_eum(task: str | None, sub: str | None, args: list[str]) -> None:
    """EUM 서비스 라우팅.

    task: extract | dashboard | mail | new-sites | task-run
    sub:  하위 옵션 (extract: full/quick, mail: preview/send)
    """
    handler = _command_table().get(task or "help")
    if handler is None:
        _print_help()
        return
    handler(sub, args)


# ── 명령 구현 ─────────────────────────────────────────────────────────


def _cmd_extract(sub: str | None, args: list[str]) -> None:
    """단말기설치현황 전체 추출 (WEBMAN390M00)."""
    gate_check("eum_extract_all_devices")
    _get_page()  # 자동 로그인 보장
    print("=" * 60)
    print("EUM 단말기설치현황 추출")
    print("=" * 60)
    from scripts.eum.extract_all_devices import main

    main()


def _cmd_mail(sub: str | None, args: list[str]) -> None:
    """홍보 메일 초안 생성 또는 발송."""
    mode = "preview"
    option_args = list(args)
    if sub:
        if str(sub).isdigit() or str(sub).upper() in {"A", "B", "C"}:
            option_args.insert(0, sub)
        else:
            mode = sub
    if mode == "send":
        gate_check("naver_mail_send", force=False, context="EUM 홍보메일 발송")
    else:
        gate_check("eum_extract_all_devices")
    print("=" * 60)
    print(f"EUM 홍보메일 {'발송' if mode == 'send' else '초안 생성'}")
    print("=" * 60)
    if mode == "send":
        raise SystemExit(
            "EUM sales-mail send is not wired here yet. Prepare a queue first, then use the approved company-mail sender."
        )
    from scripts.eum.sales_mail import main

    limit = 30
    min_grade = "A"
    for arg in option_args:
        if str(arg).isdigit():
            limit = int(arg)
        elif str(arg).upper() in {"A", "B", "C"}:
            min_grade = str(arg).upper()
    main(limit=limit, min_grade=min_grade)


def _cmd_new_sites() -> None:
    """신규 현장 전수 수집 (WEBMAN370M00 설치대상) → 영업메일 소스 저장."""
    gate_check("eum_extract_all_devices")
    print("=" * 60)
    print("EUM 신규 현장 전수 수집")
    print("=" * 60)
    from scripts.eum.install_targets import collect_all_install_targets
    from scripts.eum.sales_mail import DEFAULT_SOURCE, load_new_site_projects
    from scripts.site_engine.site_access import open_site

    page = open_site("eum")
    result = collect_all_install_targets(page)  # 표시개수 100 + 전 페이지 순회
    print(f"수집 신규현장: {result.get('total', 0)}개 ({result.get('pages_visited', 0)}페이지)")
    rows = load_new_site_projects(DEFAULT_SOURCE)
    with_email = sum(1 for row in rows if row.get("이메일"))
    print(f"저장: {result.get('saved_path', DEFAULT_SOURCE)}")
    print(f"이메일 확보: {with_email}/{len(rows)}")
    print("next: python scripts/entry/cdp_cli.py eum sales-mail")


def _cmd_install_targets(sub: str | None, args: list[str]) -> None:
    """Verify WEBMAN370M00 install targets from screen and optional Excel download."""
    gate_check("eum_extract_all_devices")
    from scripts.eum.install_targets import (
        download_install_targets_excel,
        print_excel_download_summary,
        print_summary,
        verify_install_targets,
    )
    from scripts.site_engine.site_access import open_site

    page = open_site("eum")
    if sub in {"download-excel", "excel"} or "download-excel" in args or "excel" in args:
        password = None
        for arg in args:
            if str(arg).startswith("--password="):
                password = str(arg).split("=", 1)[1]
        result = download_install_targets_excel(page, password=password)
        print_excel_download_summary(result)
        return

    no_download = sub == "no-download" or "--no-download" in args
    result = verify_install_targets(page, download=not no_download)
    print_summary(result)


def _cmd_login() -> None:
    """EUM 로그인 상태 확인 (상시 자동 처리되므로 수동 호출 불필요)."""
    gate_check("eum_extract_all_devices")
    print("=" * 60)
    print("EUM 로그인 상태 확인")
    print("=" * 60)
    _get_page()  # ensure_logged_in 내부에서 결과 출력
    from scripts.browser.cdp.connection import get_page

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


def _cmd_labor_test() -> None:
    """근로내역테스트 조회 (WEBMAN460M00)."""
    page = _get_page()
    print("=" * 60)
    print("EUM 근로내역테스트 조회")
    print("=" * 60)
    from scripts.eum.labor_test import fetch_labor_test, save_labor_test
    from scripts.eum.menu_actions import fetch_save_print

    fetch_save_print(page, fetch_labor_test, save_labor_test, "근로내역테스트")


def _cmd_test_workers() -> None:
    """테스트근로자등록 조회 (WEBMAN470M00)."""
    page = _get_page()
    print("=" * 60)
    print("EUM 테스트근로자등록 조회")
    print("=" * 60)
    from scripts.eum.test_workers import fetch_test_workers, save_test_workers

    records = fetch_test_workers(page)
    path = save_test_workers(records)
    print(f"테스트근로자등록: {len(records)}건 조회 → {path}")


def _cmd_site_devices() -> None:
    """현장별단말기목록 조회 (WEBMAN380M00, 필드명 미매핑 원본 보존)."""
    page = _get_page()
    print("=" * 60)
    print("EUM 현장별단말기목록 조회")
    print("=" * 60)
    from scripts.eum.menu_actions import fetch_save_print
    from scripts.eum.site_devices import fetch_site_devices, save_site_devices

    fetch_save_print(page, fetch_site_devices, save_site_devices, "현장별단말기목록")


def _cmd_history(sub: str | None, args: list[str]) -> None:
    """단말기 이력 조회 (WEBMAN400M00)."""
    gate_check("eum_extract_all_devices")
    _get_page()  # 자동 로그인 보장
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


def _cmd_explore_accessible(sub: str | None = None, args: list[str] | None = None) -> None:
    """Explore pages available in the current account menu."""
    gate_check("eum_extract_all_devices")
    from scripts.eum.access_explorer import explore_accessible_pages, print_summary, save_accessible_pages
    from scripts.site_engine.site_access import open_site

    page = open_site("eum")
    max_pages = int(sub) if sub and str(sub).isdigit() else None
    path = save_accessible_pages({"status": "starting", "pages": []})
    result = explore_accessible_pages(page, max_pages=max_pages, partial_path=path)
    path = save_accessible_pages(result, path)
    print_summary(result, path)


def _cmd_work_index() -> None:
    """Build a read-only EUM business/work index from the live UI."""
    gate_check("eum_extract_all_devices")
    from scripts.eum.workspace import build_work_index, print_summary, save_work_index
    from scripts.site_engine.site_access import open_site

    page = open_site("eum")
    index = build_work_index(page)
    path = save_work_index(index)
    print_summary(index, path)


def _cmd_capabilities() -> None:
    """Print current-account EUM workflow availability."""
    gate_check("eum_extract_all_devices")
    from scripts.eum.workspace import build_work_index
    from scripts.site_engine.site_access import open_site

    page = open_site("eum")
    index = build_work_index(page)
    print("=" * 60)
    print("EUM capabilities")
    print("=" * 60)
    print("Available WEBMAN codes:", ", ".join(index.get("available_webman_codes", [])))
    for workflow in index.get("known_workflows", []):
        status = "available" if workflow.get("available", True) else "not-available"
        print(f"  - {workflow['key']:<24} {status:<13} {workflow.get('command')}")


def _cmd_build_capabilities() -> None:
    """Build a capability catalog from the last accessible-page exploration."""
    gate_check("eum_extract_all_devices")
    from scripts.eum.capabilities import build_capabilities, print_summary, save_capabilities

    result = build_capabilities()
    path = save_capabilities(result)
    print_summary(result, path)


def _cmd_page_info(sub: str | None, args: list[str]) -> None:
    """Print compact capability details for one menu page."""
    query = " ".join([part for part in [sub, *(args or [])] if part]).strip()
    if not query:
        print("usage: python scripts/entry/cdp_cli.py eum page-info <menu-name-or-WEBMAN-code>")
        return
    from scripts.eum.capabilities import find_capability, print_page_info

    ok = print_page_info(find_capability(query), query)
    if not ok:
        raise SystemExit(1)


def _cmd_open_menu(sub: str | None, args: list[str]) -> None:
    """Open a current-account menu page by name, menu id, or WEBMAN code."""
    gate_check("eum_extract_all_devices")
    query = " ".join([part for part in [sub, *(args or [])] if part]).strip()
    if not query:
        print("usage: python scripts/entry/cdp_cli.py eum open-menu <menu-name-or-WEBMAN-code>")
        return

    from scripts.eum.menu_actions import open_menu_page, print_menu_result, save_menu_result
    from scripts.site_engine.site_access import open_site

    page = open_site("eum")
    result = open_menu_page(page, query)
    path = save_menu_result(result)
    print_menu_result(result, path)
    if not result.get("ok"):
        raise SystemExit(1)


def _handle_non_auto_workflow(workflow: dict, pass_args: list[str], *, prepare: bool, submit: bool) -> None:
    """읽기 전용 자동 실행 대상이 아닌 workflow 처리 — 준비/실행 플래그가 없으면 안내만 출력."""
    if prepare:
        _prepare_approval_workflow(workflow, pass_args)
    elif submit:
        _execute_approval_workflow(workflow, pass_args)
    else:
        print("approval/action workflow: command was not executed automatically.")
        print("Use --dry-run to create a plan, --prepare to fill the form without submit, or --submit to execute.")


def _run_auto_workflow(key: str, pass_args: list[str]) -> None:
    """읽기 전용 workflow key 에 맞는 자동 실행기를 호출."""
    if key == "device_inventory":
        _cmd_extract(None, [])
    elif key == "new_sites":
        _cmd_new_sites()
    elif key == "sales_mail":
        _cmd_mail(None, pass_args)
    elif key == "device_history":
        device_id = pass_args[0] if pass_args else None
        _cmd_history(device_id, [])
    elif key == "demolition_lookup":
        _cmd_demolition(None, [])
    elif key == "monitor":
        _cmd_monitor()
    elif key == "labor_test":
        _cmd_labor_test()
    elif key == "test_workers":
        _cmd_test_workers()
    elif key == "site_devices":
        _cmd_site_devices()
    else:
        print("No auto executor is registered for this workflow.")


def _cmd_work(sub: str | None, args: list[str]) -> None:
    """Resolve an EUM work alias and execute safe read-only workflows."""
    from scripts.eum.run_log import work_run
    from scripts.eum.workspace import print_workflow_help, workflow_for_alias

    alias = sub or (args[0] if args else "")
    if not alias:
        print("usage: python scripts/entry/cdp_cli.py eum work <alias-or-WEBMAN-code>")
        print_workflow_help("__missing__")
        return

    workflow = workflow_for_alias(alias)
    if not workflow:
        print_workflow_help(alias)
        raise SystemExit(1)

    dry_run = "--dry-run" in args
    prepare = "--prepare" in args
    submit = "--submit" in args
    pass_args = [arg for arg in args if arg not in ("--dry-run", "--prepare", "--submit")]
    print_workflow_help(alias)

    if dry_run:
        if workflow.get("risk") != "read":
            from scripts.eum.work_plan import build_action_plan, print_action_plan, save_action_plan

            plan = build_action_plan(workflow, pass_args)
            path = save_action_plan(plan)
            print_action_plan(plan, path)
        return

    if workflow.get("risk") != "read" or not workflow.get("auto_execute"):
        _handle_non_auto_workflow(workflow, pass_args, prepare=prepare, submit=submit)
        return

    key = workflow["key"]
    print("=" * 60)
    print(f"EUM work execute: {key}")
    print("=" * 60)

    with work_run(workflow, pass_args):
        _run_auto_workflow(key, pass_args)


def _execute_approval_workflow(workflow: dict, args: list[str]) -> None:
    """Validate an approval workflow, then execute only through its gate."""
    from scripts.eum.run_log import work_run
    from scripts.eum.work_plan import build_action_plan, print_action_plan, save_action_plan
    from scripts.common.gate import force_approved

    plan = build_action_plan(workflow, args)
    path = save_action_plan(plan)
    print_action_plan(plan, path)
    if not plan.get("valid"):
        raise SystemExit(2)

    key = workflow["key"]
    print("=" * 60)
    print(f"EUM approval execute: {key}")
    print("=" * 60)

    with work_run(workflow, args), force_approved():
        if key == "device_registration":
            result = _cmd_registration(args[0], args[1:], submit=True)
        elif key == "device_deregistration":
            result = _cmd_deregistration(args[0], args[1:], submit=True)
        else:
            raise SystemExit(f"No approval executor is registered for {key}.")
        if isinstance(result, dict) and not result.get("success"):
            raise RuntimeError(result.get("error") or "approval submit failed")


def _prepare_approval_workflow(workflow: dict, args: list[str]) -> None:
    """Validate and prepare an approval workflow without final submit."""
    from scripts.eum.run_log import work_run
    from scripts.eum.work_plan import build_action_plan, print_action_plan, save_action_plan

    plan = build_action_plan(workflow, args, mode="prepare")
    path = save_action_plan(plan)
    print_action_plan(plan, path)
    if not plan.get("valid"):
        raise SystemExit(2)

    key = workflow["key"]
    print("=" * 60)
    print(f"EUM approval prepare: {key}")
    print("=" * 60)

    with work_run(workflow, args):
        if key == "device_registration":
            result = _cmd_registration(args[0], args[1:], submit=False)
        elif key == "device_deregistration":
            result = _cmd_deregistration(args[0], args[1:], submit=False)
        else:
            raise SystemExit(f"No approval preparer is registered for {key}.")
        if isinstance(result, dict) and not result.get("success"):
            raise RuntimeError(result.get("error") or "approval prepare failed")


def _cmd_registration(sub: str | None, args: list[str], *, submit: bool = False) -> dict | None:
    """단말기 신규 등록 (WEBMAN381M00)."""
    if submit:
        gate_check("eum_register_device", force=False)
    else:
        gate_check("eum_extract_all_devices")
    _get_page()  # 자동 로그인 보장
    print("=" * 60)
    print("EUM 단말기 신규 등록")
    print("=" * 60)
    from scripts.eum.registration import register_device

    if sub:
        # 예: python scripts/entry/cdp_cli.py eum registration 2024-001 DEV-001 장소
        project_code = sub
        device_id = args[0] if args else "TEST-001"
        location = args[1] if len(args) > 1 else "서울시"

        result = register_device(project_code, project_code, device_id, location, submit=submit)
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result
    else:
        print("  사용법: eum registration <공사코드> <단말기번호> [설치장소]")
        return None


def _cmd_deregistration(sub: str | None, args: list[str], *, submit: bool = False) -> dict | None:
    """단말기 철거(말소) (WEBMAN382M00)."""
    if submit:
        gate_check("eum_deregister_device", force=False)
    else:
        gate_check("eum_extract_all_devices")
    _get_page()  # 자동 로그인 보장
    print("=" * 60)
    print("EUM 단말기 철거")
    print("=" * 60)
    from scripts.eum.deregistration import deregister_device

    if sub:
        device_id = sub
        date_str = args[0] if args else None

        result = deregister_device(device_id, date_str, submit=submit)
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result
    else:
        print("  사용법: eum deregistration <단말기번호> [철거예정일]")
        return None


def _print_help() -> None:
    print("""EUM 사용법:
  [조회/분석]
  python scripts/entry/cdp_cli.py eum extract      단말기 전체 추출
  python scripts/entry/cdp_cli.py eum dashboard    업무 대시보드
  python scripts/entry/cdp_cli.py eum monitor      운용 모니터링 (통신단절/미사용/준공임박)
  python scripts/entry/cdp_cli.py eum history      단말기 이력 조회 (WEBMAN400M00)
  python scripts/entry/cdp_cli.py eum explore      전체 사이트 탐색

  [홍보/메일]
  python scripts/entry/cdp_cli.py eum new-sites    신규 현장 발굴
  python scripts/entry/cdp_cli.py eum mail         홍보메일 초안
  python scripts/entry/cdp_cli.py eum mail send    홍보메일 발송 (승인 필요)

  [단말기 관리] ✨ 신규 기능
  python scripts/entry/cdp_cli.py eum registration <공사코드> <단말기ID> [장소]  신규 등록 (WEBMAN381M00)
  python scripts/entry/cdp_cli.py eum deregistration <단말기ID> [철거일]  철거 신청 (WEBMAN382M00)

  [시스템]
  python scripts/entry/cdp_cli.py eum task-run     전체 파이프라인 실행
  python scripts/entry/cdp_cli.py eum login        자동 로그인""")
