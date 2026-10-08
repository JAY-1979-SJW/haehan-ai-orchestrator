"""Hiworks CLI router."""

from __future__ import annotations

import contextlib
import json

from scripts.hiworks import gates
from scripts.hiworks.actions import APPROVAL_CONFIRM_TEXT as SUBMIT_CONFIRM_TEXT
from scripts.hiworks.actions import (
    apply_prepare_values,
    build_action_catalog,
    build_prepare_plan,
    build_submit_execution_plan,
    execute_approved_button,
    load_action_catalog,
    load_values,
    print_action_catalog_summary,
    print_prepare_plan_summary,
    save_action_catalog,
    save_prepare_plan,
    save_submit_record,
)
from scripts.hiworks.explorer import (
    extract_dashboard_apps,
    extract_visible_mail_actions,
    open_hiworks,
    print_apps,
    save_apps,
)
from scripts.hiworks.mail import open_compose
from scripts.hiworks.mail_batch import (
    APPROVAL_CONFIRM_TEXT,
    execute_send_batch,
    print_send_plan,
    print_send_result,
)
from scripts.hiworks.run_log import work_run
from scripts.hiworks.schemas import DATA_DIR, HIWORKS_DASHBOARD_URL, HIWORKS_MAIL_URL, workflow_for_alias
from scripts.hiworks.service_explorer import print_service_summary, save_service_report, scan_service, selected_targets
from scripts.hiworks.utils import HELP_TEXT, option_value
from scripts.hiworks.workflows import (
    build_and_save_send_plan,
    load_sales_queue,
    prepare_sales_mail,
    record_prepare_success,
)


def _command_table() -> dict:
    """task 별칭 -> (sub, args) 를 받는 실행 함수 표. 호출 시점에 _cmd_* 를 조회한다."""
    table: dict = {}
    for names, fn in (
        (("dashboard", "home"), lambda sub, args: _cmd_dashboard()),
        (("mail",), lambda sub, args: _cmd_mail(sub)),
        (("compose",), lambda sub, args: _cmd_compose()),
        (("prepare-sales-mail",), lambda sub, args: _cmd_prepare_sales_mail(sub)),
        (("send-batch",), lambda sub, args: _cmd_send_batch(sub, args)),
        (("apps", "scan"), lambda sub, args: _cmd_apps()),
        (("service", "services", "explore-services"), lambda sub, args: _cmd_service_scan(sub, args)),
        (("actions", "action-catalog"), lambda sub, args: _cmd_action_catalog(sub, args)),
        (("prepare-section", "section-prepare"), lambda sub, args: _cmd_prepare_section(sub, args)),
        (("submit-section", "section-submit"), lambda sub, args: _cmd_submit_section(sub, args)),
        (("queue", "sales-queue"), lambda sub, args: _cmd_queue(sub)),
    ):
        for name in names:
            table[name] = fn
    return table


def run_hiworks(task: str | None, sub: str | None, args: list[str]) -> None:
    handler = _command_table().get(task or "dashboard")
    if handler is None:
        _print_help()
        return
    handler(sub, args)


def _cmd_dashboard() -> None:
    gates.check_read()
    workflow = workflow_for_alias("dashboard") or {"key": "dashboard", "risk": "read"}
    with work_run(workflow, []):
        page = open_hiworks(HIWORKS_DASHBOARD_URL)
        print("=" * 60)
        print("Hiworks dashboard")
        print("=" * 60)
        print(f"url: {page.url}")
        # 디버그 출력용 page.title() 조회 실패는 해당 줄 출력만 생략, 기능 영향 없음
        with contextlib.suppress(Exception):
            print(f"title: {page.title()}")
        print_apps(extract_dashboard_apps(page)[:30])


def _cmd_apps() -> None:
    gates.check_read()
    workflow = workflow_for_alias("apps") or {"key": "apps", "risk": "read"}
    with work_run(workflow, []):
        page = open_hiworks(HIWORKS_DASHBOARD_URL)
        apps = extract_dashboard_apps(page)
        path = save_apps(apps, page.url)
        print_apps(apps)
        print(f"saved: {path}")


def _cmd_mail(sub: str | None) -> None:
    if (sub or "open") == "send":
        gates.check_send()
        raise SystemExit("Hiworks send is approval-gated and not implemented for bulk send yet.")

    gates.check_read()
    workflow = workflow_for_alias("mail") or {"key": "mail", "risk": "read"}
    with work_run(workflow, []):
        page = open_hiworks(HIWORKS_MAIL_URL)
        print("=" * 60)
        print("Hiworks mail")
        print("=" * 60)
        print(f"url: {page.url}")
        # 디버그 출력용 page.title() 조회 실패는 해당 줄 출력만 생략, 기능 영향 없음
        with contextlib.suppress(Exception):
            print(f"title: {page.title()}")
        for item in extract_visible_mail_actions(page)[:40]:
            print(f"- {item['text']} {item.get('href') or ''}")


def _cmd_compose() -> None:
    gates.check_read()
    workflow = workflow_for_alias("compose") or {"key": "compose", "risk": "read"}
    with work_run(workflow, []):
        page = open_hiworks(HIWORKS_MAIL_URL)
        result = open_compose(page)
        path = DATA_DIR / "hiworks_compose_page_latest.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = result["summary"]
        print("=" * 60)
        print("Hiworks compose page")
        print("=" * 60)
        print(f"url: {summary.get('url')}")
        print(f"clicked: {result.get('clicked')}")
        print(f"inputs: {len(summary.get('inputs', []))}")
        print(f"buttons: {len(summary.get('buttons', []))}")
        print(f"saved: {path}")


def _cmd_prepare_sales_mail(sub: str | None) -> None:
    gates.check_prepare()
    index = int(sub) if sub and str(sub).isdigit() else 1
    workflow = workflow_for_alias("prepare-sales-mail") or {"key": "prepare_sales_mail", "risk": "prepare"}
    with work_run(workflow, [str(index)]):
        rows = load_sales_queue(limit=index)
        page = open_hiworks(HIWORKS_MAIL_URL)
        result, path = prepare_sales_mail(page, index=index)
        record_prepare_success(index, rows[index - 1])
        print("=" * 60)
        print("Hiworks sales mail prepared")
        print("=" * 60)
        print(f"queue index: {index}")
        print(f"to: {result['to']}")
        print(f"subject: {result['subject']}")
        print("sent: False")
        print(f"saved: {path}")


def _cmd_queue(sub: str | None) -> None:
    gates.check_read()
    limit = int(sub) if sub and str(sub).isdigit() else 10
    rows = load_sales_queue(limit=limit)
    print("=" * 60)
    print("Hiworks sales-mail queue preview")
    print("=" * 60)
    print(f"preview: {len(rows)}")
    for idx, row in enumerate(rows, start=1):
        meta = row.get("metadata") or {}
        print(f"{idx:>2}. {row.get('to')} | {row.get('subject')}")
        print(f"    {meta.get('project_name', '')}")


def _cmd_service_scan(sub: str | None, args: list[str]) -> None:
    gates.check_read()
    name = sub or "all"
    limit = 120
    for arg in args:
        if str(arg).startswith("--limit="):
            limit = int(str(arg).split("=", 1)[1])
    workflow = workflow_for_alias("service") or {"key": "service_scan", "risk": "read"}
    with work_run(workflow, [name, f"--limit={limit}"]):
        results = [scan_service(key, target, limit=limit) for key, target in selected_targets(name).items()]
        path = save_service_report(results)
        print_service_summary(results, path)


def _cmd_action_catalog(sub: str | None, args: list[str]) -> None:
    gates.check_read()
    name = sub or "all"
    workflow = workflow_for_alias("actions") or {"key": "action_catalog", "risk": "read"}
    with work_run(workflow, [name]):
        catalog = build_action_catalog()
        if name and name != "all":
            catalog["services"] = [service for service in catalog["services"] if service.get("key") == name]
            if not catalog["services"]:
                raise KeyError(f"unknown Hiworks service in action catalog: {name}")
        path = save_action_catalog(catalog)
        print_action_catalog_summary(catalog, path)


def _cmd_prepare_section(sub: str | None, args: list[str]) -> None:
    gates.check_prepare()
    name = sub or "all"
    values_path = option_value(args, "--values=")
    dry_run = "--dry-run" in args or not values_path
    values = load_values(values_path) if values_path else {}
    workflow = workflow_for_alias("prepare-section") or {"key": "prepare_section", "risk": "prepare"}
    with work_run(workflow, [name, *(args or [])]):
        catalog = build_action_catalog()
        plan = build_prepare_plan(catalog, service_name=name, values=values)
        path = save_prepare_plan(plan)
        print_prepare_plan_summary(plan, path)
        if not dry_run:
            if name == "all":
                raise SystemExit("Live prepare with values requires one Hiworks service name, not all.")
            target = selected_targets(name)[name]
            page = open_hiworks(target["url"])
            page.wait_for_timeout(1200)
            result = apply_prepare_values(page, values)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print("submit_executed: False")


def _cmd_submit_section(sub: str | None, args: list[str]) -> None:
    service = sub or ""
    control_id = args[0] if args else ""
    if not service or not control_id:
        raise SystemExit(
            "usage: python scripts/entry/cdp_cli.py hiworks submit-section <service> <control_id> "
            "[--approved --confirm=<승인 문구(직접 입력)>] [--dry-run] [--approved-by=name]"
        )
    approved = "--approved" in args
    dry_run = "--dry-run" in args
    confirm = option_value(args, "--confirm=") or ""
    approved_by = option_value(args, "--approved-by=") or "operator"
    if approved and confirm != SUBMIT_CONFIRM_TEXT:
        raise SystemExit("approved submit requires --confirm=<사용자가 직접 입력한 승인 문구>")

    gates.require_send(
        approval=confirm if approved else None,
        expected=SUBMIT_CONFIRM_TEXT,
        service=service,
        control_id=control_id,
        dry_run=dry_run,
        approved_by=approved_by,
    )
    workflow = workflow_for_alias("submit-section") or {"key": "submit_section", "risk": "send"}
    with work_run(workflow, [service, control_id, *(args or [])]):
        catalog = load_action_catalog()
        plan = build_submit_execution_plan(
            catalog,
            service_name=service,
            control_id=control_id,
            approved_by=approved_by,
            dry_run=dry_run,
        )
        target = selected_targets(service)[service]
        page = open_hiworks(target["url"])
        page.wait_for_timeout(1200)
        record = execute_approved_button(page, plan, approved=approved, dry_run=dry_run)
        path = save_submit_record(record)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        print(f"saved: {path}")


def _cmd_send_batch(sub: str | None, args: list[str]) -> None:
    dry_run = "--dry-run" in args or sub in (None, "dry-run")
    approved = "--approved" in args
    confirm = option_value(args, "--confirm=") or ""
    option_args = [a for a in ([sub] if sub else []) + list(args) if a and a not in ("--dry-run", "--approved")]
    limit = 5
    delay_min = 15
    delay_max = 45
    for arg in option_args:
        text = str(arg)
        if text.isdigit():
            limit = int(text)
        elif text.startswith("--delay-min="):
            delay_min = int(text.split("=", 1)[1])
        elif text.startswith("--delay-max="):
            delay_max = int(text.split("=", 1)[1])

    if approved and not dry_run:
        if confirm != APPROVAL_CONFIRM_TEXT:
            raise SystemExit("approved send requires --confirm=<사용자가 직접 입력한 승인 문구>")
        gates.require_send(approval=confirm, expected=APPROVAL_CONFIRM_TEXT, dry_run=False, batch_limit=limit)
        workflow = workflow_for_alias("send-batch") or {"key": "send_batch_execute", "risk": "send"}
        with work_run(workflow, [str(limit), f"--delay-min={delay_min}", f"--delay-max={delay_max}", "--approved"]):
            from scripts.hiworks.explorer import open_hiworks
            from scripts.hiworks.schemas import HIWORKS_MAIL_URL

            plan, _ = build_and_save_send_plan(limit=limit, delay_min=delay_min, delay_max=delay_max)
            page = open_hiworks(HIWORKS_MAIL_URL)
            result = execute_send_batch(plan, page=page, approval=confirm)
            print_send_result(result)
        return

    if not dry_run:
        raise SystemExit(
            "Actual Hiworks batch send requires --approved --confirm=<사용자가 직접 입력한 승인 문구>\n"
            "Run with --dry-run first to preview the plan."
        )

    gates.check_read()
    workflow = workflow_for_alias("send-batch") or {"key": "send_batch_plan", "risk": "prepare"}
    with work_run(workflow, [str(limit), f"--delay-min={delay_min}", f"--delay-max={delay_max}"]):
        plan, path = build_and_save_send_plan(limit=limit, delay_min=delay_min, delay_max=delay_max)
        print_send_plan(plan, path)


def _print_help() -> None:
    print(HELP_TEXT)
