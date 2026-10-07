"""Hiworks business workflows and safe mail preparation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.hiworks.mail import fill_compose
from scripts.hiworks.schemas import DATA_DIR, SALES_QUEUE


def load_sales_queue(path: str | Path = SALES_QUEUE, limit: int = 10) -> list[dict[str, Any]]:
    queue_path = Path(path)
    if not queue_path.exists():
        raise FileNotFoundError(f"queue not found: {queue_path}")
    rows = []
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
        if len(rows) >= limit:
            break
    return rows


def prepare_sales_mail(page, *, index: int = 1, queue_path: str | Path = SALES_QUEUE) -> tuple[dict[str, Any], Path]:
    rows = load_sales_queue(queue_path, limit=index)
    if len(rows) < index:
        raise IndexError(f"queue item not found: {index}")
    item = rows[index - 1]
    result = fill_compose(
        page,
        to=item["to"],
        subject=item["subject"],
        body=item["body"],
    )
    path = DATA_DIR / "hiworks_prepare_sales_mail_latest.json"
    path.write_text(
        json.dumps({**result, "metadata": item.get("metadata")}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result, path


def record_prepare_success(index: int, item: dict[str, Any]) -> None:
    try:
        from scripts.browser.cdp import cdp_db

        cdp_db.init_db()
        cdp_db.mark_mail_queue_prepared(provider="hiworks", recipient=item["to"], subject=item["subject"])
        cdp_db.log_automation_run(
            "hiworks",
            "prepare_sales_mail",
            command=f"python scripts/entry/cdp_cli.py hiworks prepare-sales-mail {index}",
            status="success",
            risk_level="notify",
            input_ref=str(SALES_QUEUE),
            detail=f"recipient={item['to']}",
        )
    except Exception:  # noqa: BLE001 - 메일 준비/발송계획 성공 이후의 감사로그(cdp_db) 기록 실패를 무시 — 이미 완료된 업무 자체에는 영향 없는 best-effort 로깅
        pass


def build_and_save_send_plan(
    *, limit: int = 5, delay_min: int = 15, delay_max: int = 45
) -> tuple[dict[str, Any], Path]:
    from scripts.hiworks.mail_batch import build_send_plan, save_send_plan

    plan = build_send_plan(limit=limit, delay_min=delay_min, delay_max=delay_max)
    path = save_send_plan(plan)
    try:
        from scripts.browser.cdp import cdp_db

        cdp_db.init_db()
        cdp_db.log_automation_run(
            "hiworks",
            "sales_mail_send_batch_plan",
            command=f"python scripts/entry/cdp_cli.py hiworks send-batch {limit} --dry-run",
            status="success",
            risk_level="notify",
            input_ref=str(SALES_QUEUE),
            output_ref=str(path),
            detail=f"selected={plan.get('selected')} delay={delay_min}-{delay_max}",
        )
    except Exception:  # noqa: BLE001 - 메일 준비/발송계획 성공 이후의 감사로그(cdp_db) 기록 실패를 무시 — 이미 완료된 업무 자체에는 영향 없는 best-effort 로깅
        pass
    return plan, path
