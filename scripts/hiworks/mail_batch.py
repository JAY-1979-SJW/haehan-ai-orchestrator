"""Hiworks one-recipient-at-a-time sales mail batch planning and execution."""

from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.common.publish_guard import guarded

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DEFAULT_QUEUE = DATA_DIR / "eum_sales_mail_queue_latest.jsonl"


@dataclass(frozen=True)
class BatchItem:
    index: int
    to: str
    subject: str
    delay_seconds: int
    status: str
    metadata: dict[str, Any]


def load_pending_queue(path: str | Path = DEFAULT_QUEUE, limit: int = 10) -> list[dict[str, Any]]:
    queue_path = Path(path)
    if not queue_path.exists():
        raise FileNotFoundError(f"queue not found: {queue_path}")
    rows: list[dict[str, Any]] = []
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("status", "pending") == "pending":
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def build_send_plan(
    *,
    queue_path: str | Path = DEFAULT_QUEUE,
    limit: int = 5,
    delay_min: int = 15,
    delay_max: int = 45,
    seed: int | None = 20260513,
) -> dict[str, Any]:
    """Build a safe one-recipient-per-message send plan."""
    if delay_min < 1:
        raise ValueError("delay_min must be >= 1")
    if delay_max < delay_min:
        raise ValueError("delay_max must be >= delay_min")
    rng = random.Random(seed)
    rows = load_pending_queue(queue_path, limit=limit)
    items = [
        BatchItem(
            index=idx,
            to=row["to"],
            subject=row["subject"],
            delay_seconds=rng.randint(delay_min, delay_max),
            status="planned",
            metadata=row.get("metadata") or {},
        )
        for idx, row in enumerate(rows, start=1)
    ]
    return {
        "timestamp": datetime.now().isoformat(),
        "mode": "dry_run_plan",
        "provider": "hiworks",
        "send_unit": "one_recipient_per_message",
        "queue_path": str(queue_path),
        "limit": limit,
        "delay_min": delay_min,
        "delay_max": delay_max,
        "selected": len(items),
        "items": [asdict(item) for item in items],
        "send_status": "not_sent",
    }


def save_send_plan(plan: dict[str, Any], output_dir: str | Path = DATA_DIR) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"hiworks_sales_mail_send_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = out_dir / "hiworks_sales_mail_send_plan_latest.json"
    latest.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


APPROVAL_CONFIRM_TEXT = "HIWORKS_APPROVED_SEND_BATCH"
LATEST_SEND_RESULT_PATH = DATA_DIR / "hiworks_sales_mail_send_result_latest.json"
SEND_RESULT_DIR = DATA_DIR / "hiworks_send_results"


@guarded("hiworks_mail_batch", ok_fn=lambda r: r["failed"] == 0)
def execute_send_batch(plan: dict[str, Any], *, page, approval: str | None = None) -> dict[str, Any]:
    """승인된 배치 발송 플랜을 실행한다. 1통씩 compose→fill→send→delay 순으로 진행.

    approval 이 APPROVAL_CONFIRM_TEXT 가 아니면 한 통도 보내지 않고 GateBlocked 를 낸다(직접 import 호출도 동일).
    수신거부 목록에 있는 수신자는 보내지 않고 skipped 로 기록한다. 발송 건수는 제한하지 않는다.
    """
    from scripts.common.gate import GateBlocked, require_side_effect
    from scripts.hiworks.mail import fill_compose, send_mail

    # 항목이 0건이어도 승인 문구가 틀리면 같은 방식으로 차단한다.
    require_side_effect("mail_send", approval=approval, expected=APPROVAL_CONFIRM_TEXT)

    items = plan.get("items") or []
    results: list[dict[str, Any]] = []
    sent = 0
    failed = 0
    skipped = 0

    for item in items:
        item_result: dict[str, Any] = {
            "index": item["index"],
            "to": item["to"],
            "subject": item["subject"],
            "delay_seconds": item["delay_seconds"],
            "sent": False,
            "error": None,
            "timestamp": datetime.now().isoformat(),
        }
        try:
            require_side_effect(
                "mail_send", approval=approval, expected=APPROVAL_CONFIRM_TEXT, recipient=item["to"], subject=item["subject"]
            )
            fill_compose(page, to=item["to"], subject=item["subject"], body=item.get("body", ""))
            send_result = send_mail(page)
            item_result["sent"] = send_result.get("success", False)
            item_result["detail"] = send_result.get("detail")
            if item_result["sent"]:
                sent += 1
            else:
                failed += 1
                item_result["error"] = send_result.get("error_msg") or "send_failed"
        except GateBlocked as exc:
            skipped += 1
            item_result["skipped_reason"] = exc.result.reason
            results.append(item_result)
            continue  # 보내지 않은 항목은 딜레이도 하지 않는다
        except Exception as exc:  # noqa: BLE001 - 하이웍스 메일 일괄발송 결과 집계 루프 - 개별 발송 실패는 failed 카운트와 error 필드에 기록
            failed += 1
            item_result["error"] = str(exc)

        results.append(item_result)

        # 마지막 항목이 아닐 때만 딜레이
        if item["index"] < len(items):
            time.sleep(item["delay_seconds"])

    result = {
        "timestamp": datetime.now().isoformat(),
        "mode": "executed",
        "provider": "hiworks",
        "selected": len(items),
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "items": results,
        "send_status": "done",
    }
    _save_send_result(result)
    return result


def _save_send_result(result: dict[str, Any]) -> Path:
    SEND_RESULT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SEND_RESULT_DIR / f"hiworks_send_result_{stamp}.json"
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    path.write_text(payload, encoding="utf-8")
    LATEST_SEND_RESULT_PATH.write_text(payload, encoding="utf-8")
    return path


def print_send_plan(plan: dict[str, Any], path: Path | None = None) -> None:
    print("=" * 60)
    print("Hiworks sales-mail send plan")
    print("=" * 60)
    print(f"mode: {plan.get('mode')}")
    print(f"send unit: {plan.get('send_unit')}")
    print(f"selected: {plan.get('selected')}")
    print(f"delay: {plan.get('delay_min')}~{plan.get('delay_max')} sec")
    print(f"send status: {plan.get('send_status')}")
    for item in plan.get("items", []):
        print(f"- #{item['index']} {item['to']} delay={item['delay_seconds']}s | {item['subject']}")
    if path:
        print(f"saved: {path}")


def print_send_result(result: dict[str, Any]) -> None:
    print("=" * 60)
    print("Hiworks sales-mail send result")
    print("=" * 60)
    print(f"mode: {result.get('mode')}")
    print(f"selected: {result.get('selected')}  sent: {result.get('sent')}  failed: {result.get('failed')}")
    for item in result.get("items", []):
        status = "✓" if item.get("sent") else "✗"
        err = f" [{item['error']}]" if item.get("error") else ""
        print(f"  {status} #{item['index']} {item['to']}{err}")
